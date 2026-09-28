"""Terminal requests render eligible content and persist player interactions."""

import asyncio

from tests.unit.test_battle import packet
from tests.unit.test_economy import env
from x2server.messages.terminal import BLOG_BOX, BLOG_GROUP, CHAT_GROUP, LETTER_BOX, LETTER_GROUP, PAIR
from x2server.player.terminal import TerminalService


def ask(service, context, name, values):
    return asyncio.run(service.handle(context, packet(values, name="C2L_" + name)))


def test_communication_and_moments_persist_per_account(env):
    store, economy, context = env
    service = TerminalService(store, economy, clock=lambda: 1700000000)
    assert ask(service, context, "QueryPrivateLetter", {"type": 0}).values["letterBoxs"] == []
    assert ask(service, context, "QueryNpcBlog", {}).values["blogBox"] == []
    player = store.get(1)
    player["snapshot"]["heroes"][0]["favor"] = {"level": 4, "exp": 0}
    store.save_snapshot(1, player["snapshot"], player["revision"])

    letters = ask(service, context, "QueryPrivateLetter", {"type": 0}).values
    box = LETTER_BOX.decode(letters["letterBoxs"][0])
    assert box["heroID"] == 1003
    assert LETTER_GROUP.decode(box["groups"][0])["letterData"]
    blogs = ask(service, context, "QueryNpcBlog", {}).values
    blog_box = BLOG_BOX.decode(blogs["blogBox"][0])
    blog_ids = {BLOG_GROUP.decode(group)["groupID"] for group in blog_box["blogGroup"]}
    assert 550056 in blog_ids

    assert ask(service, context, "ReplyLetter", {"heroID": 1003, "groupID": 200303,
        "letterID": 20030301, "replyID": 200303011}).values["code"] == 10
    assert ask(service, context, "ReplyLetter", {"heroID": 1003, "groupID": 200303,
        "letterID": 20030301, "replyID": 999}).values["code"] == 13
    assert ask(service, context, "LikeNpcBlog", {"heroID": 1003, "groupID": 550056}).values["code"] == 10
    assert ask(service, context, "ReplyNpcBlog", {"heroID": 1003, "groupID": 550056,
        "chatGroupID": 0, "replyID": service.blogs[550056]["ReplyContent"][0]}).values["code"] == 10
    assert ask(service, context, "AddBlackNpc", {"heroID": 1003}).values["code"] == 10

    restarted = TerminalService(store, economy, clock=lambda: 1700000001)
    letters = ask(restarted, context, "QueryPrivateLetter", {"type": 0}).values
    assert len(LETTER_GROUP.decode(LETTER_BOX.decode(letters["letterBoxs"][0])["groups"][0])["letterData"]) == 2
    assert letters["blcakHeros"]
    blogs = ask(restarted, context, "QueryNpcBlog", {}).values
    group = next(BLOG_GROUP.decode(raw) for raw in BLOG_BOX.decode(blogs["blogBox"][0])["blogGroup"]
                 if BLOG_GROUP.decode(raw)["groupID"] == 550056)
    assert group["likeTime"] == 1700000000 and group["chatGroup"]
    chat = CHAT_GROUP.decode(group["chatGroup"][0])
    assert PAIR.decode(chat["chat"][0]) == {"Key": service.blogs[550056]["ReplyContent"][0],
                                             "Value": 1700000000}


def test_communication_auto_lines_and_existing_progress(env):
    store, economy, context = env
    player = store.get(1)
    hero = player["snapshot"]["heroes"][0]
    hero["id"] = 1028
    hero["favor"] = {"level": 4, "exp": 0}
    # Progress written by the earlier server stopped at a line without choices.
    player["snapshot"]["terminal"] = {"blocked": {}, "blogs": {}, "letters": {
        "202802": {"chain": [20280201, 20280202, 20280212, 20280213],
                   "replies": {"20280201": 202802011, "20280202": 202802022,
                               "20280212": 202802121}, "start": 1700000000}}}
    store.save_snapshot(1, player["snapshot"], player["revision"])
    service = TerminalService(store, economy, clock=lambda: 1700000001)
    answer = ask(service, context, "ReplyLetter", {"heroID": 1028, "groupID": 202802,
        "letterID": 20280214, "replyID": 202802141})
    assert answer.values["code"] == 10
    chain = store.get(1)["snapshot"]["terminal"]["letters"]["202802"]["chain"]
    assert chain[4:7] == [20280214, 20280215, 20280216]
    assert chain[-1] == 20280218
