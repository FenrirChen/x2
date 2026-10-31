"""购买因果 (134/137): 页面显示价与实扣同源, 旧阶梯多扣的部分只退一次。

证据链 (见 economy.POWER_BUY_PRICES 的注释): 页面显示价由客户端自己算
(PowerModule_GetPrice 0x015C478C 读 ServerData.PowerPrice / PowerTimesInterval,
出厂值 [60,60,60,60,60] / {1,2,4,6,10}); 服务端此前按 20 档阶梯 20/20/40/…/220/…/1000
实扣, 于是第 5 次起「写着 60 扣得更多」。这里锁住三件事:

1. 成交价 = 平价 60, 且 server_config 下发的两张表也是同一组数;
2. power_refund 回放 ``power-buy:<日>:<第几次>`` 得到的差额 = 旧阶梯 - 60×次数;
3. 返还邮件靠 player_mail 的 source_key 唯一索引只发一次 (重复登录/重连不再发)。
"""
import asyncio
import json

from tests.unit.test_battle import packet
from tests.unit.test_economy import env  # noqa: F401
from x2server.messages.core import STRING_PAIR
from x2server.player import power_refund
from x2server.player.economy import EconomyService
from x2server.player.login import LoginService
from x2server.player.task_calendar import task_period

# 固定时钟: fetch_mobility_power 用 task_period(1, now) 做日切 (北京 00:00), 固定它
# 才能连买多次并让「当日第几次」真的递增。
FIXED_NOW = 1_790_000_000
DAY_START, _ = task_period(1, FIXED_NOW)


def test_price_table_matches_client_defaults(env):
    store, economy, ctx = env
    assert EconomyService.POWER_BUY_PRICES == (60, 60, 60, 60, 60)
    assert EconomyService.POWER_BUY_INTERVALS == (1, 2, 4, 6, 10)
    response = asyncio.run(LoginService(None, store, economy).server_config(
        ctx, packet({}, name="C2L_ServerTableConfig")))
    pairs = {row["key"]: row["val"] for row in map(STRING_PAIR.decode, response.values["keyVal"])}
    assert pairs["PowerPrice"] == "60,60,60,60,60"
    assert pairs["PowerTimesInterval"] == "1,2,4,6,10"


def test_every_tier_charges_the_price_the_page_shows(env):
    store, economy, ctx = env
    economy.clock = lambda: FIXED_NOW
    snapshot = store.get(1)["snapshot"]
    snapshot["mobility"] = {"power": 0}
    snapshot["crystal"] = 60 * 12
    economy.save_snapshot(1, snapshot)
    for tier in range(12):
        before = store.get(1)["snapshot"]
        response = asyncio.run(economy.fetch_mobility_power(
            ctx, packet({"itemId": 0}, tier + 1, "C2L_FetchMobilityPower")))
        assert response.values["result"] == 10
        after = store.get(1)["snapshot"]
        # 旧阶梯在第 5 次就会扣 80, 第 10 次 220; 平价后每一档都必须是 60。
        assert before["crystal"] - after["crystal"] == 60, f"tier {tier} overcharged"
        assert after["power_buy"]["count"] == tier + 1
        assert after["mobility"]["power"] == (tier + 1) * EconomyService.POWER_BUY_AMOUNT
    assert store.get(1)["snapshot"]["crystal"] == 0


def test_old_ladder_difference_is_replayed_from_the_ledger(env):
    store, _, _ = env
    with store.db:
        store.db.execute("CREATE TABLE IF NOT EXISTS economy_events "
                         "(player_id INTEGER, event_key TEXT)")
        store.db.executemany("INSERT INTO economy_events VALUES (?,?)",
                             [(1, f"1:{DAY_START}:power-buy:{DAY_START}:{n}") for n in range(1, 11)])
    expected = sum(price - power_refund.FAIR_PRICE for price in power_refund.OLD_LADDER[:10])
    amount, days = power_refund.refund_amount(store.db, 1, {"power_buy": {"day": DAY_START, "count": 10}})
    assert (amount, days) == (expected, {DAY_START: 10}) == (390, {DAY_START: 10})


def test_refund_mail_is_minted_once_per_player(env):
    store, _, _ = env
    with store.db:
        store.db.execute("CREATE TABLE IF NOT EXISTS economy_events "
                         "(player_id INTEGER, event_key TEXT)")
        store.db.executemany("INSERT INTO economy_events VALUES (?,?)",
                             [(1, f"1:{DAY_START}:power-buy:{DAY_START}:{n}") for n in range(1, 16)])
    snapshot = {"crystal": 0, "power_buy": {"day": DAY_START, "count": 15}}
    paid = power_refund.settle(store.db, 1, snapshot, FIXED_NOW)
    assert paid == sum(price - 60 for price in power_refund.OLD_LADDER[:15]) == 1860
    rows = store.db.execute("SELECT title, attachments, source_key, state FROM player_mail "
                            "WHERE player_id=1").fetchall()
    assert len(rows) == 1
    assert rows[0]["title"] == power_refund.TITLE
    assert json.loads(rows[0]["attachments"]) == {"1237902": paid}
    assert rows[0]["source_key"] == power_refund.SOURCE % 1
    # 再登录(或重连)一次: 唯一索引挡住了第二封, 也不会有第二笔附件。
    assert power_refund.settle(store.db, 1, snapshot, FIXED_NOW + 60) == 0
    assert store.db.execute("SELECT count(*) FROM player_mail WHERE player_id=1").fetchone()[0] == 1


def test_being_undercharged_is_not_back_charged(env):
    """1~4 次时旧阶梯其实比显示价便宜, 净额为负 → 不发信, 也不倒扣。"""
    store, _, _ = env
    amount, days = power_refund.refund_amount(store.db, 1, {"power_buy": {"day": DAY_START, "count": 4}})
    assert (amount, days) == (-100, {DAY_START: 4})
    assert power_refund.settle(store.db, 1, {"power_buy": {"day": DAY_START, "count": 4}}, FIXED_NOW) == 0
    assert store.db.execute("SELECT count(*) FROM player_mail WHERE player_id=1").fetchone()[0] == 0


def test_login_helper_mints_then_stays_quiet(env):
    store, _, _ = env
    with store.db:
        store.db.execute("CREATE TABLE IF NOT EXISTS economy_events "
                         "(player_id INTEGER, event_key TEXT)")
        store.db.executemany("INSERT INTO economy_events VALUES (?,?)",
                             [(1, f"1:{DAY_START}:power-buy:{DAY_START}:{n}") for n in range(1, 9)])
    service = LoginService(None, store)
    player = store.get(1)
    player["snapshot"]["power_buy"] = {"day": DAY_START, "count": 8}
    assert service._power_refund_mail(player, FIXED_NOW) is True
    assert service._power_refund_mail(player, FIXED_NOW + 60) is False


def test_deleted_or_replaced_mail_does_not_reissue_refund(env):
    store,_,_=env
    snapshot={'power_buy':{'day':DAY_START,'count':10}}
    with store.db:
        assert power_refund.settle(store.db,1,snapshot,FIXED_NOW)==390
        store.db.execute('DELETE FROM player_mail WHERE player_id=1')
    with store.db:
        assert power_refund.settle(store.db,1,snapshot,FIXED_NOW+1)==0
    assert store.db.execute('SELECT count(*) FROM player_mail').fetchone()[0]==0


def test_new_account_cannot_import_old_counter_to_claim_compensation(env):
    store,_,_=env
    store.login('new-after-price-fix',2,FIXED_NOW)
    snapshot={'power_buy':{'day':DAY_START,'count':15}}
    with store.db:
        assert power_refund.settle(store.db,2,snapshot,FIXED_NOW)==0
    assert store.db.execute('SELECT count(*) FROM player_mail WHERE player_id=2').fetchone()[0]==0
    with store.db:power_refund.initialize(store.db)
    assert not power_refund.eligible(store.db,2)


def test_new_price_purchases_are_not_reconstructed_as_old_overcharges(env):
    store,e,ctx=env
    e.clock=lambda:FIXED_NOW
    snapshot=store.get(1)['snapshot'];snapshot.update(crystal=10000,mobility={'power':0})
    e.save_snapshot(1,snapshot)
    for rid in range(1,16):
        assert asyncio.run(e.fetch_mobility_power(ctx,packet({},rid,'C2L_FetchMobilityPower'))).values['result']==10
    after=store.get(1)['snapshot']
    assert after['power_buy']['price_version']==2
    assert power_refund.refund_amount(store.db,1,after)==(0,{})
    assert store.db.execute('SELECT count(*) FROM player_mail WHERE source_key LIKE "power_refund_%"').fetchone()[0]==0


def test_first_new_purchase_preserves_old_counter_before_replacing_version(env):
    store,e,ctx=env
    e.clock=lambda:FIXED_NOW
    snapshot=store.get(1)['snapshot']
    snapshot.update(crystal=10000,mobility={'power':0},power_buy={'day':DAY_START,'count':10})
    e.save_snapshot(1,snapshot)
    result=asyncio.run(e.fetch_mobility_power(ctx,packet({},400,'C2L_FetchMobilityPower')))
    assert result.values['result']==10
    assert store.get(1)['snapshot']['crystal']==9940
    mail=store.db.execute('SELECT attachments FROM player_mail WHERE source_key=?',(power_refund.SOURCE%1,)).fetchone()
    assert json.loads(mail[0])=={'1237902':390}


def test_refund_and_server_marker_roll_back_together(env):
    import pytest
    from x2server.player.transactions import transaction
    store,_,_=env
    snapshot={'power_buy':{'day':DAY_START,'count':10}}
    with pytest.raises(RuntimeError):
        with transaction(store.db):
            assert power_refund.settle(store.db,1,snapshot,FIXED_NOW)==390
            raise RuntimeError('injected failure')
    with store.db:assert power_refund.settle(store.db,1,snapshot,FIXED_NOW)==390


def test_large_ordinal_uses_constant_time_formula_and_rejects_unsafe_mail(env):
    import pytest
    from x2server.player.transactions import transaction
    store,_,_=env
    count=10**7
    assert power_refund.overcharge_for(count)==sum(p-60 for p in power_refund.OLD_LADDER)+(count-20)*940
    with pytest.raises(ValueError,match='integer limit'):
        with transaction(store.db):
            power_refund.settle(store.db,1,{'power_buy':{'day':DAY_START,'count':count}},FIXED_NOW)
    exists=store.db.execute("SELECT 1 FROM sqlite_master WHERE name='system_mail_issues'").fetchone()
    assert not exists or not store.db.execute('SELECT 1 FROM system_mail_issues WHERE player_id=1 AND kind=?',(power_refund.KIND,)).fetchone()
