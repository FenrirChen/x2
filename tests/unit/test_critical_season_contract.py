"""Native 150% base plus isolated season attribute/passive carriers."""
import asyncio
from collections import Counter

import pytest
from tests.unit.test_origin_season import env
from tests.unit.test_season_protocol_tasks import ctx
from tests.unit.test_season_talent_reallocation import allocate, call
from tests.unit.test_battle import packet, request
from x2server.messages.battle import FIGHT_DATA, FIGHT_HERO, HERO_ATTR_ADD, PROFILE_HERO
from x2server.messages.season import SEASON_SCHEMAS
from x2server.player.battle import BattleService
from x2server.player.college_power import rules
from x2server.player.season import SeasonService
from x2server.player.season_schedule import ANCHOR, DURATION


def entry(battle, values, rid):
    result = asyncio.run(battle.enter(ctx(), packet(values, rid)))
    assert result.values['result'] == 10
    data = FIGHT_DATA.decode(result.values['data'])
    assert data.get('CRIDmg', 0) == 0  # additional global bonus, NOT base crit
    heroes = [FIGHT_HERO.decode(x) for x in data['fightHeros']]
    attrs = {h['id']: {v['attrId']: v['attrValue'] for v in map(HERO_ATTR_ADD.decode, h['attrAdd'])}
             for h in heroes}
    return heroes, attrs


def test_native_critical_base_is_150_percent_and_talent_adds_percentage_points():
    attributes, prototypes, params = rules()
    assert int(params['CRI_Dmg']) == 1500
    from x2server.player.progression import battle_hero_base
    assert battle_hero_base()['1003']['CriticalDamage'] == 0  # native fallback to CRI_Dmg
    assert attributes[113]['ValueMax'] == 8000
    from x2server.player.season import catalog
    row = next(t for t in catalog()['battlepasstalent'] if t['TalentID'] == 6006007)
    assert row['AttribId'] == [113] and row['LevelValue'] == 100
    # Native units: 1000 == 100%, so one point adds 10 percentage points.
    assert (int(params['CRI_Dmg']) + row['LevelValue']) / 1000 == 1.6


@pytest.mark.parametrize('season_battle', [False, True])
def test_all_fifteen_talents_allocate_reload_reset_and_reallocate_in_battle(env, season_battle):
    store, economy, season = env
    player = store.get(1)
    store.save_snapshot(1, dict(player['snapshot'], heroes=[
        {'id':1003,'state':2,'level':1,'star':1},
        {'id':1004,'state':2,'level':1,'star':1}]), player['revision'])
    with economy.transaction():
        economy._grant(1, 'crit-season-points', {1291002:30, 1202901:10})
    values = request()
    values['heros'] = [PROFILE_HERO.encode({'heroId':i,'leader':int(i==1003)}) for i in (1003,1004)]
    if season_battle:
        config = min(season.configs.values(), key=lambda r:r['Level'])
        sid = config['SectionGroup'][0]
        section = season.sections[sid]
        values.update(missionId=sid, chapter=section['ChapterID'], sceneId=section['Maps'][0])
    battle = BattleService(store, economy)
    _, baseline = entry(battle, values, 1000)
    assert len(season.talents) == 15
    changes = [(tid,2) for tid in sorted(season.talents)]
    response = allocate(season, changes, 1001)
    assert response.values['code'] == 10
    update = next(m for m in response.before_response if m.message_name == 'L2C_BattlePassTalentInfo')
    assert all(v['level'] == 2 for v in map(SEASON_SCHEMAS['TalentInfo'].decode,update.values['info']))
    assert season.state(1)['points'] == 0
    # Reconstruct from persisted state rather than relying on the old service cache.
    restored = SeasonService(economy, enabled=True, instance=season.base_instance)
    economy.season = restored
    expected = Counter()
    for row in restored.talents.values():
        for attr in row['AttribId']:
            if attr:
                expected[attr] += row['LevelValue'] * 2
    heroes, grown = entry(battle, values, 1002)
    for h in heroes:
        hid = h['id']
        expected_attrs = dict(baseline[hid])
        for attr, amount in expected.items():
            expected_attrs[attr] = expected_attrs.get(attr,0) + amount
        assert grown[hid] == expected_attrs
        assert grown[hid][113] - baseline[hid].get(113,0) == 200
        wire = {v['id']:v for v in map(SEASON_SCHEMAS['TalentAttr'].decode,h['talentAttr'])}
        assert set(wire) == set(restored.talents)
        for tid,row in restored.talents.items():
            assert wire[tid]['level'] == 2
            assert wire[tid]['upValue'] == row['LevelValue'] * 2
            assert wire[tid]['attrId'] == row['AttribId']
            assert wire[tid].get('passiveId',0) == row.get('PassiveID',0)
    for rid,tid in enumerate(sorted(restored.talents),1100):
        assert call(restored,'BattlePassTalentReset',{'id':tid},rid).values['code'] == 10
    _, reset = entry(battle, values, 1200)
    assert reset == baseline
    assert restored.state(1)['points'] == 30
    assert allocate(restored,[(tid,1) for tid in sorted(restored.talents)],1201).values['code'] == 10
    _, reapplied = entry(battle, values, 1202)
    for hid in reapplied:
        assert reapplied[hid][113] - baseline[hid].get(113,0) == 100
    # Ending the occurrence removes temporary attributes and passive carriers.
    economy.clock = lambda: ANCHOR + DURATION
    assert restored.attributes(1) == {} and restored.battle_talents(1) == []
