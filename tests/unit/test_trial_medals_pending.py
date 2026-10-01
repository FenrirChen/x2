import asyncio
import json
from tests.unit.test_economy import env
from tests.unit.test_battle import packet, request
from x2server.player.battle import BattleService
from x2server.player.economy import EconomyService
from x2server.player.medals import MedalService
from x2server.player.pending_delivery import recover
from x2server.player.trial_units import trial_hero, equipment, catalog
from x2server.player.login import LoginService
from x2server.messages.core import INT_PAIR
from x2server.messages.medals import MEDAL_SYSTEM, MEDAL_PACK, MEDAL_SHOW
from x2server.messages.battle import FIGHT_DATA, FIGHT_HERO, HERO_ATTR


def test_trial_loadout_all_client_rows_and_no_account_mutation(env):
    store, economy, ctx = env
    for row in catalog()['units']:
        hero = trial_hero(row['TrialHeroID'], row['TrialHeroID'])
        assert hero['battle_base_id'] == row['UnitID']
        assert hero['level'] == row['HeroLevel'] and hero['star'] == row['HeroStars']
        equips, effects = equipment(hero)
        assert len(equips) == min(len(row.get('EquipGroupID', [])), len(row.get('EquipAttrID', [])))
        if len(equips) >= 2:
            assert effects
    battle = BattleService(store, economy)
    before = store.get(1)['snapshot']['heroes']
    # Prerequisite clear is a fixture, never the active database.
    static = battle.catalog.sections[2110208]
    values = request()
    values.update(missionId=2110208, chapter=static['ChapterID'], sceneId=static['Maps'][0],
                     heros=[__import__('x2server.messages.battle', fromlist=['PROFILE_HERO']).PROFILE_HERO.encode({'heroId': 1219, 'leader': 1})])
    answer = asyncio.run(battle.enter(ctx, packet(values)))
    assert answer.values['result'] == 10
    hero = FIGHT_HERO.decode(FIGHT_DATA.decode(answer.values['data'])['fightHeros'][0])
    assert (hero['id'], hero['level'], hero['star']) == (1219, 20, 10)
    assert HERO_ATTR.decode(hero['heroAttrCount'])['atk'] > 100
    assert hero['heroGodEquip'] and len(hero['heroEquip']) == 6 and hero['heroSkill']
    assert hero['battleSkinId'] == 1221901
    assert store.get(1)['snapshot']['heroes'] == before


def test_medal_achievement_claim_wear_and_unwear_persist(env):
    store, economy, ctx = env
    achv = economy.achievements
    target = 661180
    achv.states(1)
    with store.db:
        store.db.execute('UPDATE achievements SET progress=? WHERE player_id=1 AND achv_id=?',
                         (achv.rows[target]['targets'][0], target))
    result = asyncio.run(achv.handle(ctx, packet({'achvId': target}, name='C2L_AchvReward')))
    assert result.values['code'] == 10
    medal = 1260010
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?', (medal,)).fetchone()[0] == 1
    service = MedalService(economy)
    def wear(values, rid):
        return asyncio.run(service.handle(ctx, packet({'pos': [INT_PAIR.encode(v) for v in values]},
                    name='C2L_MedalOpt', request_id=rid)))
    assert wear([{'Key': 0, 'Value': medal}], 2).values['code'] == 10
    assert wear([{'Key': 1, 'Value': 1260009}], 3).values['code'] == 13
    assert wear([{'Key': 3, 'Value': medal}], 4).values['code'] == 13
    assert wear([{'Key': 1, 'Value': medal}], 5).values['code'] == 13
    system = MEDAL_SYSTEM.decode(LoginService.snapshot_push(store.get(1), store).values['MedalSystem'])
    assert INT_PAIR.decode(MEDAL_PACK.decode(system['MedalPack'])['Medal'][0])['Key'] == medal
    assert INT_PAIR.decode(MEDAL_SHOW.decode(system['MedalShow'])['Position'][0])['Value'] == medal
    assert wear([{'Key': 0, 'Value': 0}], 6).values['code'] == 10
    assert store.get(1)['snapshot']['medal_positions']['0'] == 0
    assert asyncio.run(achv.handle(ctx, packet({'achvId': target}, name='C2L_AchvReward'))).values == result.values
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=?', (medal,)).fetchone()[0] == 1


def test_deferred_story_rewards_delivered_once_without_replaying_clear(env):
    store, economy, _ = env
    with store.db:
        store.db.execute("INSERT INTO economy_runs (uuid,player_id,session_id,section_id,settled) VALUES ('old',1,'fixture',2110801,1)")
        store.db.execute("INSERT INTO economy_grants VALUES (1,'battle:old','{}',1)")
        for item in (1237914, 1240002):
            store.db.execute("INSERT INTO pending_rewards VALUES (1,'battle:old',?,1,'unrecovered item instance or currency destination')", (item,))
    recover(economy, 1)
    recover(economy, 1)
    EconomyService(store)  # restart migration is also idempotent
    assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=1 AND item_id=1237914').fetchone()[0] == 1
    assert store.db.execute('SELECT COUNT(*) FROM equipment_instances WHERE player_id=1 AND type_id=1240002').fetchone()[0] == 1
    assert store.db.execute('SELECT COUNT(*) FROM pending_reward_deliveries').fetchone()[0] == 2
    assert not store.db.execute('SELECT 1 FROM economy_clears').fetchone()
