"""The requested story trial must not consume the player's sparse normal gear."""
import asyncio
import pytest

from tests.unit.test_economy import env
from tests.unit.test_battle import packet, request
from x2server.player.battle import BattleService
from x2server.messages.battle import BATTLE_SCHEMAS, FIGHT_DATA, FIGHT_HERO, HERO_SKILL, PROFILE_HERO, CHECKOUT


@pytest.mark.parametrize('wire_id', [1003, 1303])
def test_chapter7_trial_is_independent_of_account_and_replays_without_extra_cost(env, wire_id):
    store, economy, context = env
    player = store.get(1)
    normal = {**player['snapshot'], 'heroes': [{'id': 1003, 'level': 1, 'star': 1, 'state': 2,
        'skills': [{'id': 10033, 'level': 1}], 'equips': []}]}
    store.save_snapshot(1, normal, player['revision'])
    battle = BattleService(store, economy)
    values = request()
    values.update(missionId=2110607, chapter=2010700, sceneId=2210607,
                  heros=[PROFILE_HERO.encode({'heroId': wire_id, 'leader': 1})])
    entry = asyncio.run(battle.enter(context, packet(values, 711)))
    assert entry.values['result'] == 10
    hero = FIGHT_HERO.decode(FIGHT_DATA.decode(entry.values['data'])['fightHeros'][0])
    assert (hero['id'], hero['level'], hero['star']) == (1303, 50, 15)
    assert len(hero['heroEquip']) == 6
    assert {HERO_SKILL.decode(r)['id']: HERO_SKILL.decode(r)['level']
            for r in hero['heroSkill']}[10033] == 5
    after = store.get(1)['snapshot']
    assert after['heroes'] == normal['heroes']
    assert after['mobility']['power'] == normal['mobility']['power'] - 6
    replay = asyncio.run(battle.enter(context, packet(values, 711)))
    schema = BATTLE_SCHEMAS['L2C_FightData']
    assert schema.encode(replay.values) == schema.encode(entry.values)
    assert store.get(1)['snapshot'] == after
    done = packet({'checkout': CHECKOUT.encode({'chapterId': 2010700, 'sectionId': 2110607,
                  'success': True, 'fightTime': 100})}, 712, 'C2L_CheckoutMainMissionSign')
    assert asyncio.run(battle.checkout(context, done)).values['result'] == 10
    assert store.get(1)['snapshot']['heroes'] == normal['heroes']
    assert store.get(1)['snapshot']['main_section'] == 2110607


@pytest.mark.parametrize('section,team', [(2110607, [1004]), (2110607, [1003, 1004]),
                                         (2110608, [1003]), (2110605, [1003])])
def test_story_trial_exception_keeps_normal_parties_and_other_sections(env, section, team):
    store, economy, context = env
    player = store.get(1)
    heroes = [{'id': hid, 'state': 2, 'level': 2, 'star': 1} for hid in (1003, 1004)]
    store.save_snapshot(1, {**player['snapshot'], 'heroes': heroes}, player['revision'])
    battle = BattleService(store, economy)
    row = battle.catalog.sections[section]
    values = request()
    values.update(missionId=section, chapter=row['ChapterID'], sceneId=row['Maps'][0],
                  heros=[PROFILE_HERO.encode({'heroId': hid, 'leader': int(i == 0)})
                         for i, hid in enumerate(team)])
    entry = asyncio.run(battle.enter(context, packet(values)))
    assert entry.values['result'] == 10
    decoded = [FIGHT_HERO.decode(raw) for raw in FIGHT_DATA.decode(entry.values['data'])['fightHeros']]
    assert [(h['id'], h['level'], h['star']) for h in decoded] == [(hid, 2, 1) for hid in team]
    assert store.get(1)['snapshot']['heroes'] == heroes
