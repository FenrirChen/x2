"""Terminal requests render eligible content and persist player interactions."""

import asyncio

from tests.unit.test_battle import packet
from tests.unit.test_economy import env
from x2server.messages.terminal import BLOG_BOX, BLOG_GROUP, CHAT_GROUP, LETTER_BOX, LETTER_GROUP, LETTER_DATA, PAIR
from x2server.player.terminal import TerminalService


def ask(service, context, name, values):
    return asyncio.run(service.handle(context, packet(values, name="C2L_" + name)))


def test_communication_and_moments_persist_per_account(env):
    store, economy, context = env
    service = TerminalService(store, economy, clock=lambda: 1700000000)
    initial = ask(service, context, "QueryPrivateLetter", {"type": 0}).values['letterBoxs']
    assert LETTER_DATA.decode(LETTER_GROUP.decode(LETTER_BOX.decode(initial[0])['groups'][0])['letterData'][0])['letterID'] == 20031801
    initial_blog = BLOG_BOX.decode(ask(service, context, "QueryNpcBlog", {}).values['blogBox'][0])
    assert all(service.blogs[BLOG_GROUP.decode(raw)['groupID']]['TriggerType']['enum'] == 'E_SpecialDay'
               for raw in initial_blog['blogGroup'])
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


def test_all_official_communication_choices_cross_zero_sentinel_lines(env):
    store, economy, context = env
    service = TerminalService(store, economy)
    checked = 0
    # Exercise every choice edge through the same continuation routine used
    # in queries/replies, including all Inanna groups (hero 1019).
    for row in service.letters.values():
        for index, option in enumerate(row.get('ReplyContent', [])):
            if not option:
                continue
            progress = {'chain': [row['PrivateMailID']], 'replies': {str(row['PrivateMailID']): option}}
            service._extend_auto_chain(progress)
            targets = row.get('NextPrivateMailID', [])
            if index < len(targets) and targets[index] in service.letters:
                assert len(progress['chain']) >= 2
                assert progress['chain'][1] == targets[index]
            last = service.letters[progress['chain'][-1]]
            if not any(last.get('ReplyContent', [])):
                assert not any(i in service.letters and service.letters[i]['GroupID'] == last['GroupID']
                    for i in last.get('NextPrivateMailID', []))
            assert len(progress['chain']) == len(set(progress['chain']))
            checked += 1
    assert checked > 2000


def test_inanna_all_branches_reply_and_relogin(env):
    store, economy, context = env
    player = store.get(1)
    player['snapshot']['heroes'] = [{'id': 1019, 'state': 2, 'favor': {'level': 99}, 'level': 1, 'star': 1}]
    store.save_snapshot(1, player['snapshot'], player['revision'])
    with store.db:
        store.db.execute('INSERT INTO economy_clears VALUES (?,?,?)', (1, 2110509, 'inanna-story'))
    service = TerminalService(store, economy)
    checked = 0
    for row in service.letters.values():
        if row.get('HeroID') != 1019 or not any(row.get('ReplyContent', [])):
            continue
        root = next(r for r in service.roots if r['GroupID'] == row['GroupID'])
        if not service._available(root, {'favor': {'level': 99}}, 1, player['snapshot']):
            continue
        for reply in row['ReplyContent']:
            if not reply:
                continue
            player = store.get(1)
            progress = {'chain': [row['PrivateMailID']], 'replies': {}, 'start': 1700000000}
            player['snapshot']['terminal'] = {'letters': {str(row['GroupID']): progress}, 'blogs': {}, 'blocked': {}}
            store.save_snapshot(1, player['snapshot'], player['revision'])
            values = {'heroID': 1019, 'groupID': row['GroupID'], 'letterID': row['PrivateMailID'], 'replyID': reply}
            answer = ask(service, context, 'ReplyLetter', values)
            assert answer.values['code'] == 10
            assert ask(service, context, 'ReplyLetter', values).values['code'] == 10
            refreshed = ask(TerminalService(store, economy), context, 'QueryPrivateLetter', {'type': 0})
            box = LETTER_BOX.decode(refreshed.values['letterBoxs'][0])
            assert any(LETTER_DATA.decode(raw).get('replyID') == reply
                       for group in box['groups'] for raw in LETTER_GROUP.decode(group)['letterData'])
            checked += 1
    assert checked > 36


def test_sparse_hero_row_and_reply_cannot_switch_completed_branch(env):
    store, economy, context = env
    player = store.get(1)
    player['snapshot']['heroes'][0]['favor'] = {'level': 99}
    player['snapshot']['terminal'] = {'letters': {'200307': {
        'chain': [20030705], 'replies': {}, 'start': 1700000000}}, 'blogs': {}, 'blocked': {}}
    store.save_snapshot(1, player['snapshot'], player['revision'])
    service = TerminalService(store, economy)
    assert ask(service, context, 'ReplyLetter', {'heroID': 1003, 'groupID': 200307,
        'letterID': 20030705, 'replyID': 200307031}).values['code'] == 10
    assert ask(service, context, 'ReplyLetter', {'heroID': 1003, 'groupID': 200303,
        'letterID': 20030301, 'replyID': 200303011}).values['code'] == 10
    first = {'heroID': 1003, 'groupID': 200303, 'letterID': 20030302, 'replyID': 200303021}
    assert ask(service, context, 'ReplyLetter', first).values['code'] == 10
    before = store.get(1)['snapshot']['terminal']
    assert ask(service, context, 'ReplyLetter', dict(first, replyID=200303022)).values['code'] == 13
    assert store.get(1)['snapshot']['terminal'] == before


def test_story_choice_effect_and_calendar_triggers_preserve_requirements(env):
    store, economy, _ = env
    service = TerminalService(store, economy, clock=lambda: 1700000000)
    hero = {'favor': {'level': 99}}
    story = next(r for r in service.roots if r['PrivateMailID'] == 20190301)
    assert not service._available(story, hero, 1, {})
    with store.db:
        store.db.execute('INSERT INTO economy_clears VALUES (?,?,?)', (1, 2110509, 'inanna-story'))
    assert service._available(story, hero, 1, {})
    assert not service._available(story, hero, 2, {})
    effect = next(r for r in service.roots if r.get('TriggerType', {}).get('enum') == 'E_OptionEffect')
    assert not service._available(effect, hero, 1, {})
    source = next(r for r in service.letters.values() if effect['TypeNumber'] in r.get('OptionEffectID', []))
    index = source['OptionEffectID'].index(effect['TypeNumber'])
    snapshot = {'terminal': {'letters': {'effect': {'replies': {
        str(source['PrivateMailID']): source['ReplyContent'][index]}}}}}
    assert service._available(effect, hero, 1, snapshot)
    calendar = {'TriggerType': {'enum': 'E_SpecialDay'}, 'TypeNumber': 20220520}
    assert service._available(calendar, hero)
    assert not service._available(dict(calendar, TypeNumber=20991231), hero)
