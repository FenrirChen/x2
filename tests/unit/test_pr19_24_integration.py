import asyncio
from datetime import datetime

import pytest

from tests.unit.test_economy import env
from tests.unit.test_battle import packet, request
from tests.unit.test_college_upgrade import game
from tests.unit.test_college_alchemy import send
from tests.unit.test_college_jobs import funded
from x2server.messages.battle import FIGHT_DATA, FIGHT_HERO, HERO_ATTR, PROFILE_HERO
from x2server.messages.core import HERO_GOD_EQUIP, INT_PAIR
from x2server.messages.economy import TASK
from x2server.player.battle import BattleService
from x2server.player.battle_bonuses import GOD_EQUIP_ATTR, JEWEL_ATTR, LONG_PAIR
from x2server.player.divination import DivinationService
from x2server.player.server_clock import BEIJING


def test_activity_landing_preserves_real_rookie_start_for_expiry_and_reconnect(env):
    from x2server.messages.core import BASE_INFO
    from x2server.player.login import LoginService
    store, economy, context = env
    player = store.get(1)
    original = player.copy()
    created = player['created_at']
    # GameActivity[999999] keeps the seven-day sign-in page for 14 days.
    # After that, the native client chooses the star-house landing tab.
    for now in (created + 86400, created + 15 * 86400):
        push = LoginService.snapshot_push(player, store, now)
        base = BASE_INFO.decode(push.values['BaseInfo'])
        assert base['SignInStartTime'] == created
    assert store.get(1) == original


@pytest.mark.parametrize('wire_id', [1303, 1003])
def test_behemoth_trial_has_canonical_skills_and_gems_without_account_changes(env, wire_id):
    store, economy, context = env
    before = store.get(1)['snapshot']
    battle = BattleService(store, economy)
    section = battle.catalog.sections[2110707]
    values = request()
    values.update(missionId=2110707, chapter=section['ChapterID'], sceneId=section['Maps'][0],
                  heros=[PROFILE_HERO.encode({'heroId': wire_id, 'leader': 1})])
    response = asyncio.run(battle.enter(context, packet(values)))
    assert response.values['result'] == 10
    hero = FIGHT_HERO.decode(FIGHT_DATA.decode(response.values['data'])['fightHeros'][0])
    assert (hero['id'], hero['level'], hero['star']) == (1303, 50, 15)
    assert HERO_ATTR.decode(hero['heroAttrCount']) == {'atk': 826, 'def': 711, 'hp': 6450, 'sp': 3000}
    artifact = HERO_GOD_EQUIP.decode(hero['heroGodEquip'])
    assert (artifact['star'], artifact['level']) == (4, 15)
    assert [INT_PAIR.decode(v) for v in artifact['jewel']] == [{'Key': 0, 'Value': 1251056}]
    attrs = GOD_EQUIP_ATTR.decode(artifact['godEquipAttr'])
    jewel = JEWEL_ATTR.decode(attrs['jewelAttr'][0])
    assert LONG_PAIR.decode(jewel['effect1']) == {'Key': 102, 'Value': 352}
    assert jewel['effect2'] == [241251, 241303, 241306]
    from x2server.messages.battle import HERO_SKILL
    assert [HERO_SKILL.decode(v) for v in hero['heroSkill']] == [
        {'id': i, 'level': 5} for i in [10030, 10031, 10032, 10033, 10035]]
    assert len(hero['heroEquip']) == 6
    assert store.get(1)['snapshot']['heroes'] == before['heroes']


@pytest.mark.parametrize('wire_id', [1307, 1007])
def test_chapter_seven_thetis_trial_uses_full_official_loadout(env, wire_id):
    store, economy, context = env
    before = store.get(1)['snapshot']
    battle = BattleService(store, economy)
    section = battle.catalog.sections[2110606]
    assert section['ChapterID'] == 2010700
    values = request()
    values.update(missionId=2110606, chapter=section['ChapterID'], sceneId=section['Maps'][0],
                  heros=[PROFILE_HERO.encode({'heroId': wire_id, 'leader': 1})])
    response = asyncio.run(battle.enter(context, packet(values)))
    assert response.values['result'] == 10
    hero = FIGHT_HERO.decode(FIGHT_DATA.decode(response.values['data'])['fightHeros'][0])
    assert (hero['id'], hero['level'], hero['star']) == (1307, 50, 15)
    assert hero['battleSkinId'] == 0  # 1220701 would force normal ActionFileID 1007.
    assert HERO_ATTR.decode(hero['heroAttrCount']) == {'atk': 14803, 'def': 611, 'hp': 6480, 'sp': 3000}
    from x2server.messages.battle import HERO_ATTR_ADD
    raw_attributes = {a['attrId']: a['attrValue'] for a in map(HERO_ATTR_ADD.decode, hero['attrAdd'])}
    assert raw_attributes[162] == 1090  # Trial PlayerAttrib[1307], not normal [1007].
    artifact = HERO_GOD_EQUIP.decode(hero['heroGodEquip'])
    assert (artifact['id'], artifact['star'], artifact['level']) == (1507, 4, 15)
    assert not artifact.get('jewel')  # The canonical Thetis trial has no WeaponGems.
    from x2server.messages.battle import HERO_SKILL
    assert [HERO_SKILL.decode(v) for v in hero['heroSkill']] == [
        {'id': skill, 'level': 5} for skill in [10070, 10071, 13072, 10073, 10075]]
    assert len(hero['heroEquip']) == 6
    assert store.get(1)['snapshot']['heroes'] == before['heroes']
    from x2server.player.progression import hero_attributes
    assert hero_attributes({'id': 1007, 'level': 50, 'star': 15})['atk'] == 892


@pytest.mark.parametrize('wire_id', [1303, 1003])
def test_behemoth_trial_preserves_original_action_skin_and_loadout(env, wire_id):
    store, economy, context = env
    before = store.get(1)['snapshot']['heroes']
    battle = BattleService(store, economy)
    section = battle.catalog.sections[2110707]
    values = request()
    values.update(missionId=2110707, chapter=section['ChapterID'], sceneId=section['Maps'][0],
                  heros=[PROFILE_HERO.encode({'heroId': wire_id, 'leader': 1})])
    response = asyncio.run(battle.enter(context, packet(values)))
    assert response.values['result'] == 10
    hero = FIGHT_HERO.decode(FIGHT_DATA.decode(response.values['data'])['fightHeros'][0])
    assert (hero['id'], hero['level'], hero['star'], hero['battleSkinId']) == (1303, 50, 15, 1220301)
    assert HERO_ATTR.decode(hero['heroAttrCount']) == {'atk': 826, 'def': 711, 'hp': 6450, 'sp': 3000}
    artifact = HERO_GOD_EQUIP.decode(hero['heroGodEquip'])
    assert (artifact['id'], artifact['star'], artifact['level']) == (1503, 4, 15)
    from x2server.messages.core import INT_PAIR
    assert [INT_PAIR.decode(raw) for raw in artifact['jewel']] == [{'Key': 0, 'Value': 1251056}]
    from x2server.messages.battle import HERO_SKILL
    skills = [HERO_SKILL.decode(raw)['id'] for raw in hero['heroSkill']]
    assert 10033 in skills and 10057 not in skills
    assert len(hero['heroEquip']) == 6
    assert store.get(1)['snapshot']['heroes'] == before


def test_element_compose_transport_replay_limit_and_session_scope(env):
    store, economy, context = env
    with store.db:
        store.db.execute("INSERT INTO economy_runs (uuid,player_id,session_id,section_id,settled) VALUES ('compose',1,'session',2035101,0)")
    service = economy.element_compose
    compose = packet({'elementID': 420501, 'count': 1}, 10, 'C2L_ElementCompose')
    first = asyncio.run(service.compose(context, compose))
    assert first.values['code'] == 10
    assert asyncio.run(service.compose(context, compose)).values == first.values
    assert store.db.execute('SELECT count FROM battle_element_compose').fetchone()[0] == 1
    assert asyncio.run(service.compose(context, packet({'elementID': 420501, 'count': 2}, 11,
                                                      'C2L_ElementCompose'))).values['code'] == 13
    context.session.session_id = 'another-session'
    assert asyncio.run(service.compose(context, packet({'elementID': 420501, 'count': 1}, 12,
                                                      'C2L_ElementCompose'))).values['code'] == 13
    assert service.profile_fields(1, 'compose')['elementExp'] == 30


def test_divination_next_year_same_calendar_day_really_delivers(env):
    store, economy, context = env
    old = int(datetime(2025, 10, 11, tzinfo=BEIJING).timestamp())
    now = int(datetime(2026, 10, 11, tzinfo=BEIJING).timestamp())
    economy.clock = lambda: now
    service = DivinationService(store, economy)
    with store.db:
        store.db.execute('INSERT INTO player_divination VALUES (1,1011,?,?)', (1 << 10, old))
        store.db.execute("INSERT INTO economy_grants VALUES (1,'divination:1011','{}',?)", (old,))
    assert asyncio.run(service.query(context, packet({}, name='C2L_QueryDivination'))).values['checkIn'] == 0
    result = asyncio.run(service.claim(context, packet({}, name='C2L_Divination')))
    assert result.values['code'] == 10
    assert store.db.execute("SELECT 1 FROM economy_grants WHERE source='divination:2026:1011'").fetchone()
    assert asyncio.run(service.claim(context, packet({}, name='C2L_Divination'))).values['code'] == 101


def test_college_explore_counts_success_once(game):
    hero = funded(game)
    store, clock, _, service, _ = game
    assert send(game, 'StartExplore', seq=401, exploreId=0, ruinId=34001, heroIds=[hero]).values['code'] == 10
    clock.value += 10800
    assert send(game, 'FinishExplore', seq=402, exploreId=0).values['code'] == 10
    assert send(game, 'FinishExplore', seq=402, exploreId=0).values['code'] == 10
    progress = {TASK.decode(raw)['taskId']: TASK.decode(raw)['taskProgress']
                for raw in service.jobs.economy.task_values(1, 2)['taskList']}
    assert progress[630107] == 1


def test_recurring_customer_trades_count_separately_but_retry_does_not(game):
    store, _, _, service, _ = game
    customer = service._customer_for(1, 1)
    item, count = customer['itemId'][0], customer['itemNum'][0]
    with store.db:
        store.db.execute('INSERT INTO inventory VALUES (?,?,?)', (1, item, count * 2))
    for sequence in [501, 502]:
        result = send(game, 'AlchemyFinish', seq=sequence, type=1, posIndex=1)
        assert result.values['code'] == 10
        assert send(game, 'AlchemyFinish', seq=sequence, type=1, posIndex=1).values == result.values
    progress = {TASK.decode(raw)['taskId']: TASK.decode(raw)['taskProgress']
                for raw in service.alchemy.economy.task_values(1, 2)['taskList']}
    assert progress[630113] == progress[630114] == 2


def test_first_recharge_rewards_are_once_and_persist_across_restart(env):
    store, economy, _ = env
    assert economy.query_first_recharge(1).values['state'] == 1
    result = economy.receive_first_recharge(1)
    assert result.values['code'] == 10
    assert economy.query_first_recharge(1).values['state'] == 2
    inventory = list(store.db.execute('SELECT * FROM inventory ORDER BY item_id'))
    snapshot = store.get(1)['snapshot']
    from x2server.player.economy import EconomyService
    restored = EconomyService(store)
    assert restored.receive_first_recharge(1).values['code'] == 13
    assert list(store.db.execute('SELECT * FROM inventory ORDER BY item_id')) == inventory
    assert store.get(1)['snapshot'] == snapshot
