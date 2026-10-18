import asyncio
import json
from pathlib import Path
from tests.unit.test_economy import env
from tests.unit.test_battle import packet, request
from x2server.messages.battle import DROP_DATA, FIGHT_DATA, BATTLE_SCHEMAS
from x2server.player.battle import BattleService
from x2server.player.drop_budget import CRYSTAL_GROUP, CRYSTAL_GROUP_BUDGET


def test_official_element_crystals_have_a_reachable_value_budget(env):
    _, economy, _ = env
    evidence = json.loads((Path(__file__).resolve().parents[2] /
                          'analysis/equipment/element_crystal_group_20261018.json').read_text(encoding='utf8'))
    crystals = evidence['items']
    assert len(crystals) == 4  # water/fire/earth/wind element crystals.
    assert {row['ItemID'] for row in crystals} == {1103006, 1103007, 1103008, 1103009}
    assert {row['ItemValue'] for row in crystals} == {12}
    # Group 28 is the highest AddADCGroup in the whole official Item table.
    assert {row['AddADCGroup'] for row in crystals} == {CRYSTAL_GROUP}
    # A battle-only material: E_Maze (never settled into the account bag).
    assert {row['ItemUseScence']['value'] for row in crystals} == {0}
    # The official sections routing group 28 are exactly the eight element ones.
    sections = evidence['sections']
    assert len(sections) == 8
    assert {row['Type'] for row in sections} == {7}
    assert all(CRYSTAL_GROUP in row['DroopLimit2'] for row in sections)
    values = BattleService(env[0], economy).drop_budget.budget_for(2110291)
    # JudgeDropItem rejects the whole group when Count <= AddADCGroup.
    assert len(values) > max(row['AddADCGroup'] for row in crystals)
    assert values[CRYSTAL_GROUP] == CRYSTAL_GROUP_BUDGET
    assert sum(row['ItemValue'] for row in crystals) <= values[CRYSTAL_GROUP]
    # The compact settlement catalog already lists them (AddADCGroup omitted);
    # E_Maze items never reach outsideItems, so no new grant logic is needed.
    assert all(row['ItemID'] in economy.items for row in crystals)


def test_legacy_28_group_run_is_accepted_without_budget_topup(env):
    store, economy, ctx = env
    battle = BattleService(store, economy)
    entered = asyncio.run(battle.enter(ctx, packet(request())))
    data = FIGHT_DATA.decode(entered.values['data'])
    drop = DROP_DATA.decode(data['dropData'])
    drop['dropValues'] = [100 + i for i in range(28)]  # PR12 generation: no group 28.
    data['dropData'] = DROP_DATA.encode(drop)
    with store.db:
        store.db.execute('UPDATE battle_entries SET response=? WHERE uuid=?',
                         (BATTLE_SCHEMAS['L2C_FightData'].encode(
                             {**entered.values, 'data': FIGHT_DATA.encode(data)}), entered.values['uuid']))
    for _ in range(2):
        answer = asyncio.run(battle.drop_data(ctx, packet(
            {'missionId': 2110801, 'chapterId': 2010100}, name='C2L_FightDropData')))
        assert answer.values['result'] == 10
        assert DROP_DATA.decode(answer.values['data'])['dropValues'] == drop['dropValues']
