"""Audit existing budget behavior; these tests do not declare an official quota."""
import asyncio
import pytest
from tests.unit.test_battle import packet, request
from x2server.messages.battle import BATTLE_SCHEMAS, DROP_DATA, FIGHT_DATA
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState
from x2server.player.battle import BattleService
from x2server.player.economy import EconomyService
from x2server.player.store import PlayerStore


@pytest.mark.parametrize('section,difficulty,budget', [(2133109, 9, 6000), (2133110, 10, 13200)])
def test_hui_and_blood_moon_entry_and_refresh_budget_agree(tmp_path, section, difficulty, budget):
    store = PlayerStore(tmp_path / 'beastlord.db')
    p = store.login('audit', 1, 0)
    store.save_snapshot(1, dict(p['snapshot'], level=60, mobility={'power': 150},
        heroes=[{'id': 1003, 'state': 2, 'level': 1, 'star': 1}]), p['revision'])
    ctx = DispatchContext('audit', 'local', SessionState('audit', 'session', player_id=1))
    economy = EconomyService(store)
    battle = BattleService(store, economy)
    row = battle.catalog.sections[section]
    assert row['DifficultyLevel'] == difficulty
    with store.db:
        for prerequisite in (row.get('OpenParam'), section - 1):
            if prerequisite:
                store.db.execute('INSERT OR IGNORE INTO economy_clears VALUES (?,?,?)', (1, prerequisite, 'audit-prerequisite'))
    values = request()
    values.update(missionId=section, chapter=row['ChapterID'], sceneId=row['Maps'][0])
    response = asyncio.run(battle.enter(ctx, packet(values)))
    assert response.values['result'] == 10
    entry_budget = DROP_DATA.decode(FIGHT_DATA.decode(response.values['data'])['dropData'])['dropValues']
    refreshed = asyncio.run(battle.drop_data(ctx, packet({'missionId': section,
        'chapterId': row['ChapterID']}, request_id=2, name='C2L_FightDropData')))
    assert refreshed.values['result'] == 10
    refresh_budget = DROP_DATA.decode(refreshed.values['data'])['dropValues']
    expected = [5000] * 27 + [3000, 3000]
    expected[5] = budget
    assert entry_budget == refresh_budget == expected
    assert entry_budget[5] == budget  # Beastlord value cap, not item count.
    assert store.db.execute('SELECT policy_version FROM battle_drop_budget_versions WHERE uuid=?',
                            (response.values['uuid'],)).fetchone()[0] == battle.drop_budget.version
    # Mid-run policy change cannot enlarge, shrink or refill its existing cap.
    battle.drop_budget.beastlord_budgets[section] = 99999
    again = asyncio.run(battle.drop_data(ctx, packet({'missionId': section,
        'chapterId': row['ChapterID']}, request_id=3, name='C2L_FightDropData')))
    assert DROP_DATA.decode(again.values['data'])['dropValues'] == expected
    store.close()

    # A service/database restart still uses the run's original serialized cap.
    restored_store = PlayerStore(tmp_path / 'beastlord.db')
    restored = BattleService(restored_store, EconomyService(restored_store))
    restored.drop_budget.beastlord_budgets[section] = 1
    after_restart = asyncio.run(restored.drop_data(ctx, packet({'missionId': section,
        'chapterId': row['ChapterID']}, request_id=4, name='C2L_FightDropData')))
    assert DROP_DATA.decode(after_restart.values['data'])['dropValues'] == expected
    # Runs entered before this policy have no version row and still retain their
    # old wire budget. Refresh must not upgrade such a run after deployment.
    legacy = dict(response.values)
    legacy_data = FIGHT_DATA.decode(legacy['data'])
    legacy_data['dropData'] = DROP_DATA.encode({'missionId': section, 'dropValues': [5000] * 27})
    legacy['data'] = FIGHT_DATA.encode(legacy_data)
    with restored_store.db:
        restored_store.db.execute('UPDATE battle_entries SET response=? WHERE uuid=?',
            (BATTLE_SCHEMAS['L2C_FightData'].encode(legacy), response.values['uuid']))
        restored_store.db.execute('DELETE FROM battle_drop_budget_versions WHERE uuid=?',
            (response.values['uuid'],))
    old_run = asyncio.run(restored.drop_data(ctx, packet({'missionId': section,
        'chapterId': row['ChapterID']}, request_id=5, name='C2L_FightDropData')))
    assert DROP_DATA.decode(old_run.values['data'])['dropValues'] == [5000] * 27
    restored_store.close()
