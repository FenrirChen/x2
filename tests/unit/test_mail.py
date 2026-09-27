import asyncio
from pathlib import Path

from tests.unit.test_battle import packet
from tests.unit.test_economy import env
from x2server.messages.economy import REWARD, REWARD_ITEM
from x2server.messages.mail import MAIL_ATTACHMENT, MAIL_INFO
from x2server.player.mail import MailService
from x2server.player.store import PlayerStore
from x2server.player.economy import EconomyService
from x2server.protocol.codec import ProtocolCodec
from x2server.protocol.headers import ResponseHeader


def call(service, context, name, values=None):
    return asyncio.run(service.handle(context, packet(values or {}, name="C2L_" + name)))


def test_mail_delivery_read_claim_replay_and_delete(env):
    store, economy, context = env
    service = MailService(store, economy, clock=lambda: 1700000000)
    mail_id = service.send(1, "测试", "附件", {1237915: 5})
    listing = call(service, context, "MailData", {"pageIndex": 1, "pageSize": 20}).values
    assert listing["code"] == 10 and listing["total"] == 1
    shown = MAIL_INFO.decode(listing["mails"][0])
    assert shown["id"] == mail_id and shown["state"] == 0
    assert MAIL_ATTACHMENT.decode(shown["attachments"][0]) == {"itemID": 1237915, "itemNum": 5}
    wire = ProtocolCodec().encode("L2C_MailData", listing, ResponseHeader(request_id=5))
    assert ProtocolCodec().decode(wire, ResponseHeader).values["total"] == 1
    assert call(service, context, "DelMail", {"mailid": mail_id}).values["code"] == 13
    assert call(service, context, "ReadMail", {"mailid": mail_id}).values["code"] == 10
    claimed = call(service, context, "ReceiveAttachment", {"mailid": mail_id})
    assert claimed.values["code"] == 10
    rewards = [REWARD_ITEM.decode(x) for x in REWARD.decode(claimed.values["rewardData"])["rewardItem"]]
    assert rewards[0]["itemId"] == 1237915 and rewards[0]["itemNum"] == 5
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237915").fetchone()[0] == 5
    assert MAIL_INFO.decode(service.list_values(1)["mails"][0])["state"] == 3
    reopened = PlayerStore(Path(store.db.execute("PRAGMA database_list").fetchone()[2]))
    try:
        assert MAIL_INFO.decode(MailService(reopened, EconomyService(reopened)).list_values(1)["mails"][0])["state"] == 3
    finally:
        reopened.close()
    assert call(service, context, "ReceiveAttachment", {"mailid": mail_id}).values["code"] == 13
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237915").fetchone()[0] == 5
    assert call(service, context, "DelMail", {"mailid": mail_id}).values["code"] == 10
    assert service.list_values(1)["total"] == 0


def test_mail_bulk_ignores_client_reward_and_rejects_foreign_ids(env):
    store, economy, context = env
    service = MailService(store, economy)
    one = service.send(1, "一", "内容", {1237915: 2})
    two = service.send(1, "二", "内容", {1237915: 3})
    forged = economy.reward_bytes({1237915: 999})
    result = call(service, context, "ReceiveAllAttachment", {"mailids": [one, two], "rewardData": forged})
    assert result.values["code"] == 10
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237915").fetchone()[0] == 5
    assert call(service, context, "ReceiveAllAttachment", {"mailids": [one, two]}).values["code"] == 13
    third = service.send(1, "三", "内容", {1237915: 1})
    assert call(service, context, "ReceiveAllAttachment", {"mailids": [third, 999999]}).values["code"] == 13
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237915").fetchone()[0] == 5
    assert call(service, context, "ReceiveAllAttachment", {"mailids": [one, third]}).values["code"] == 10
    assert store.db.execute("SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237915").fetchone()[0] == 6


def test_empty_mail_and_attachment_validation(env):
    store, economy, context = env
    service = MailService(store, economy)
    assert call(service, context, "MailData", {"pageIndex": 0, "pageSize": 20}).values == {
        "code": 10, "total": 0, "mails": []}
    try:
        service.send(1, "bad", "body", {99999999: 1})
    except ValueError:
        pass
    else:
        assert False
    assert service.list_values(1)["total"] == 0


def test_delete_all_preserves_unclaimed_attachments(env):
    store, economy, context = env
    service = MailService(store, economy)
    keep = service.send(1, "待领取", "附件", {1237915: 2})
    delete = service.send(1, "已领取", "附件", {1237915: 1})
    assert call(service, context, "ReceiveAttachment", {"mailid": delete}).values["code"] == 10
    assert call(service, context, "DelAllMail").values["code"] == 10
    assert [MAIL_INFO.decode(x)["id"] for x in service.list_values(1)["mails"]] == [keep]


def test_new_mail_is_pushed_to_online_player(env):
    store, economy, _ = env
    service = MailService(store, economy)

    class LiveServer:
        def __init__(self):
            self.received = asyncio.Event()
            self.message = None

        async def push_to_player(self, player_id, message):
            assert player_id == 1
            self.message = message
            self.received.set()
            return 1

    async def verify():
        server = LiveServer()
        task = asyncio.create_task(service.watch(server, interval=0.01))
        await asyncio.sleep(0)
        service.send(1, "新邮件", "在线推送", {1237915: 1})
        try:
            await asyncio.wait_for(server.received.wait(), timeout=1)
            assert server.message.message_name == "L2C_MailData"
            assert server.message.values["total"] == 1
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    asyncio.run(verify())
