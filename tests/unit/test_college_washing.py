import asyncio
import json
import pytest

from tests.unit.test_college_upgrade import game, quantity
from tests.unit.test_battle import packet
from x2server.messages.core import CORE_SCHEMAS
from x2server.messages.equipment import EQUIP_PARAM, HERO_EQUIP
from x2server.player.equipment import EquipmentService
from x2server.player.college import CollegeService
from x2server.player.task_calendar import task_period


def setup(game, star=6):
    store, clock, repo, service, ctx = game
    state = repo.load(1)
    repo.catalog.state_row(state, 708)['buildingStar'] = 5
    repo.save(1, state)
    p = store.get(1)
    store.save_snapshot(1, dict(p['snapshot'], gold=10000000, crystal=10000, equip_exp=10000000), p['revision'])
    param = service.washing.factory.roll_param(1240001, star)
    # Exercise the add/delete range deterministically.
    tiers = service.washing.factory.data['minor_count_tiers'][str(star)]
    for slot in range(tiers['base'] + 2, 7):
        for k in ('at', 'av', 'lock'):
            param[f'{k}{slot}'] = 0
    with store.db:
        store.db.execute('INSERT INTO equipment_instances (player_id,type_id,star,level,exp,param,marker) VALUES (?,?,?,?,?,?,?)',
                         (1, 1240001, star, 0, 0, json.dumps(param), 'washing-test'))
        eid = store.db.execute('SELECT last_insert_rowid()').fetchone()[0]
        for item in (1237804, 1237805, 1237806, 1237807, 1237808, 1237920):
            store.db.execute('INSERT OR REPLACE INTO inventory VALUES (?,?,?)', (1, item, 1000))
    return eid


def send(game, eid, op=None, seq=1, **fields):
    flow = 'WashingRoomRandomAttri' if op is None else 'WashingRoomOpt'
    fields.update(equipID=eid)
    if op is not None:
        fields['opt'] = op
    response = asyncio.run(game[3].dispatch(game[4], packet(fields, seq, 'C2L_' + flow)))
    for message in (*response.before_response, response, *response.pushes):
        CORE_SCHEMAS[message.message_name].encode(message.values)
    return response


def saved(game, eid):
    row = game[0].db.execute('SELECT level,exp,param FROM equipment_instances WHERE id=?', (eid,)).fetchone()
    return row[0], row[1], json.loads(row[2])


def test_preview_accept_replay_reconnect_and_no_inventory_mutation_until_accept(game):
    eid = setup(game)
    store, clock, repo, service, ctx = game
    original = saved(game, eid)
    result = send(game, eid)
    assert result.values['code'] == 10
    assert saved(game, eid) == original
    assert store.get(1)['snapshot']['gold'] == 9940000
    assert quantity(store, 1237920) == 998 and quantity(store, 1237808) == 999
    assert result.values['washingCountDay'] == 1
    assert send(game, eid).values == result.values
    assert store.get(1)['snapshot']['gold'] == 9940000
    restored = CollegeService(repo, economy=service.washing.economy)
    ctx.session.session_id = 'reconnected'
    next_game = (*game[:3], restored, ctx)
    assert send(next_game, eid, seq=2).values == result.values
    assert store.get(1)['snapshot']['gold'] == 9940000
    candidate = EQUIP_PARAM.decode(result.values['equipParam'])
    accepted = send(next_game, eid, 5, seq=3)
    assert accepted.values['code'] == 10
    assert saved(game, eid)[2] == candidate
    assert repo.load(1)['washing_count_day'] == 1
    assert send(next_game, eid, 5, seq=3).values == accepted.values
    assert send(next_game, eid, 5, seq=4).values['code'] == 13
    assert store.get(1)['snapshot']['gold'] == 9940000


def test_add_delete_lock_and_locked_values_survive_numeric_preview(game):
    eid = setup(game)
    initial = saved(game, eid)[2]
    added = send(game, eid, 1)
    assert added.values['code'] == 10
    current = saved(game, eid)[2]
    assert sum(bool(current[f'at{s}']) for s in range(2,7)) == 5
    assert len({current[f'at{s}'] for s in range(2,7)}) == 5
    assert send(game, eid, 1, seq=2).values['code'] == 13
    current['lock3'] = 1
    assert send(game, eid, 3, seq=3, equipParam=EQUIP_PARAM.encode(current)).values['code'] == 10
    protected = (current['at3'], current['av3'])
    preview = send(game, eid, seq=4)
    assert preview.values['code'] == 10
    assert EQUIP_PARAM.decode(preview.values['equipParam'])['av3'] == protected[1]
    gold = game[0].get(1)['snapshot']['gold']
    assert gold == 10000000 - 60000 - 60000 - 120000
    deleted = send(game, eid, 2, seq=5)
    assert deleted.values['code'] == 10
    changed = saved(game, eid)[2]
    assert protected in [(changed[f'at{s}'],changed[f'av{s}']) for s in range(2,7) if changed[f'lock{s}']]
    assert sum(bool(changed[f'at{s}']) for s in range(2,7)) == 4
    assert send(game, eid, 2, seq=6).values['code'] == 13
    assert send(game, eid, 5, seq=7).values['code'] == 13


def test_daily_gold_to_crystal_discount_and_midnight_reset(game):
    eid = setup(game)
    store, clock, repo, service, ctx = game
    state = repo.load(1)
    repo.catalog.state_row(state, 708)['buildingLevel'] = 2
    repo.settle(state)
    state['washing_count_day'] = 7
    repo.save(1, state)
    assert send(game, eid).values['code'] == 10
    assert store.get(1)['snapshot']['gold'] == 10000000 - 58800
    assert send(game, eid, seq=2).values['code'] == 10
    assert store.get(1)['snapshot']['crystal'] == 10000 - 59
    assert repo.load(1)['washing_count_day'] == 9
    clock.value = task_period(1, clock.value)[1]
    assert repo.growth_base(1)['washingCountDay'] == 0
    assert send(game, eid, seq=3).values['code'] == 10
    assert store.get(1)['snapshot']['gold'] == 10000000 - 2*58800


def test_monthcard_uses_ten_gold_operations(game):
    eid = setup(game)
    store, clock, repo, service, _ = game
    with store.db:
        store.db.execute('CREATE TABLE IF NOT EXISTS gift_package_claims (player_id INTEGER, package_id INTEGER, period TEXT, claimed_at INTEGER)')
        store.db.execute('INSERT INTO gift_package_claims VALUES (1,2700001,?,?)', ('once',clock.value))
    state = repo.load(1)
    repo.settle(state)
    state['washing_count_day'] = 9
    repo.save(1, state)
    assert send(game, eid).values['code'] == 10
    assert store.get(1)['snapshot']['gold'] == 9940000
    assert send(game, eid, seq=2).values['code'] == 10
    assert store.get(1)['snapshot']['crystal'] == 9940


def test_reset_restores_initial_values_and_refunds_only_invested_soul(game):
    eid = setup(game)
    store, clock, repo, service, ctx = game
    base = saved(game, eid)[2]
    for seq in range(1,4):
        response = asyncio.run(service.washing.equipment.strengthen(ctx, packet({'equipID':eid},seq,'C2L_EquipStrengthen')))
        assert response.values['code'] == 10
    invested = service.washing.equipment.exp_costs[3]
    expected = invested['cumulative_exp'] * (1000-invested['loss_exp']) // 1000
    exp_before = store.get(1)['snapshot']['equip_exp']
    result = send(game, eid, 4, seq=10)
    assert result.values['code'] == 10
    assert saved(game, eid) == (0,0,base)
    assert store.get(1)['snapshot']['equip_exp'] == exp_before + expected
    assert send(game, eid, 4, seq=10).values == result.values
    assert store.get(1)['snapshot']['equip_exp'] == exp_before + expected
    assert send(game, eid, 4, seq=11).values['code'] == 13
    assert not store.db.execute('SELECT 1 FROM equipment_enhancements WHERE equip_id=?',(eid,)).fetchone()
    assert expected <= invested['cumulative_exp']


def test_stale_preview_cannot_overwrite_strengthened_gear(game):
    eid = setup(game)
    assert send(game, eid).values['code'] == 10
    assert asyncio.run(game[3].washing.equipment.strengthen(game[4],packet({'equipID':eid},2,'C2L_EquipStrengthen'))).values['code'] == 10
    before = saved(game,eid)
    assert send(game,eid,5,seq=3).values['code'] == 13
    assert saved(game,eid) == before


@pytest.mark.parametrize('star',range(1,7))
def test_star_minor_minimum_is_enforced(game,star):
    eid = setup(game,star)
    assert send(game,eid,2).values['code'] == 13


def test_forgery_foreign_gear_and_insufficient_materials_roll_back_everything(game):
    eid = setup(game)
    store, clock, repo, service, ctx = game
    before = saved(game,eid)
    fake = dict(before[2],av1=999999,lock1=1)
    assert send(game,eid,3,equipParam=EQUIP_PARAM.encode(fake)).values['code'] == 13
    assert send(game,eid+1,1,seq=2).values['code'] == 13
    with store.db:
        store.db.execute('UPDATE inventory SET quantity=0 WHERE item_id=1237804')
    assert send(game,eid,1,seq=3).values['code'] == 22
    assert saved(game,eid) == before
    assert store.get(1)['snapshot']['gold'] == 10000000
    assert repo.load(1)['washing_count_day'] == 0
    assert not store.db.execute('SELECT 1 FROM college_washing_receipts').fetchone()


def test_native_gates_and_exact_material_quantity(game):
    eid = setup(game)
    state = game[2].load(1)
    game[2].catalog.state_row(state,708)['buildingStar'] = 1
    game[2].save(1,state)
    assert send(game,eid,seq=1).values['code'] == 57
    with game[0].db:
        for item in (1237804,1237805):
            game[0].db.execute('UPDATE inventory SET quantity=1 WHERE item_id=?',(item,))
    assert send(game,eid,1,seq=2).values['code'] == 10
    assert quantity(game[0],1237804) == quantity(game[0],1237805) == 0


def test_wire_failure_rolls_back_cost_preview_and_count(game,monkeypatch):
    eid = setup(game)
    def fail(*args):
        raise ValueError('wire failure')
    monkeypatch.setattr(game[3].washing.equipment,'values',fail)
    assert send(game,eid).values['code'] == 13
    assert game[0].get(1)['snapshot']['gold'] == 10000000
    assert game[2].load(1)['washing_count_day'] == 0
    assert not game[0].db.execute('SELECT 1 FROM college_washing_pending').fetchone()


def test_worn_equipment_reads_saved_wash_and_reclaim_cleans_pending(game):
    from x2server.player.battle_equipment import battle_equipment
    eid = setup(game)
    assert send(game,eid,1).values['code'] == 10
    snapshot = game[0].get(1)
    hero = {'id':1003,'state':2,'level':1,'star':1,'equips':[{'position':0,'equip_id':eid}]}
    game[0].save_snapshot(1,dict(snapshot['snapshot'],heroes=[hero]),snapshot['revision'])
    raw = battle_equipment(game[0],1,hero)[0][0]
    assert EQUIP_PARAM.decode(HERO_EQUIP.decode(raw)['param']) == saved(game,eid)[2]
    assert send(game,eid,seq=2).values['code'] == 10
    snapshot = game[0].get(1)
    game[0].save_snapshot(1,dict(snapshot['snapshot'],heroes=[dict(hero,equips=[])]),snapshot['revision'])
    result = asyncio.run(game[3].washing.equipment.reclaim(game[4],packet({'equipID':[eid]},3,'C2L_EquipReclaim')))
    assert result.values['code'] == 10
    assert not game[0].db.execute('SELECT 1 FROM college_washing_pending').fetchone()
    assert not game[0].db.execute('SELECT 1 FROM college_washing_receipts').fetchone()


def test_pending_preview_and_receipts_survive_cross_account_import(tmp_path):
    from tests.unit.test_save_manager import make_env, build_full_schema
    from x2server.player.college import CollegeStateRepository
    from x2server.player.economy import EconomyService
    from x2server.network.dispatcher import DispatchContext
    from x2server.network.session import SessionState
    from tests.unit.test_college_upgrade import Clock
    store,accounts,manager = make_env(tmp_path)
    try:
        build_full_schema(store)
        accounts.create('alpha-wash','password-alpha',100)
        accounts.create('beta-wash','password-beta',101)
        clock = Clock()
        repo = CollegeStateRepository(store,clock)
        economy = EconomyService(store,clock.now)
        service = CollegeService(repo,economy=economy)
        ctx = DispatchContext('wash','local',SessionState('wash','old-session',player_id=1))
        game = (store,clock,repo,service,ctx)
        eid = setup(game)
        result = send(game,eid)
        assert result.values['code'] == 10
        archive = manager.export_save(1)
        manager.import_save(2,archive)
        target = store.db.execute('SELECT equip_id FROM college_washing_pending WHERE player_id=2').fetchone()[0]
        assert target != eid
        assert store.db.execute('SELECT equip_id FROM college_washing_receipts WHERE player_id=2').fetchone()[0] == target
        ctx.session.player_id = 2
        ctx.session.session_id = 'new-account-session'
        gold = store.get(2)['snapshot']['gold']
        resumed = send(game,target,seq=2)
        assert resumed.values['equipParam'] == result.values['equipParam']
        assert store.get(2)['snapshot']['gold'] == gold
        assert send(game,target,5,seq=3).values['code'] == 10
        assert store.db.execute('SELECT param FROM equipment_instances WHERE player_id=2 AND id=?',(target,)).fetchone()[0] == json.dumps(EQUIP_PARAM.decode(result.values['equipParam']),sort_keys=True)
    finally:
        manager.close()
        store.close()


def test_legacy_levelled_equipment_without_growth_ledger_keeps_growth_on_preview(game):
    eid = setup(game)
    param = saved(game,eid)[2]
    ladder = game[3].washing.factory._attr_ladder(6,'0',param['at1'])[0]
    param['av1'] = max(ladder)+1234
    with game[0].db:
        game[0].db.execute('UPDATE equipment_instances SET level=15,param=? WHERE id=?',(json.dumps(param),eid))
    result = send(game,eid)
    assert result.values['code'] == 10
    assert EQUIP_PARAM.decode(result.values['equipParam'])['av1'] in [value+1234 for value in ladder]
    assert saved(game,eid)[2] == param


def test_delete_insufficient_materials_restores_slot_and_enhancement_ledger(game,monkeypatch):
    eid = setup(game)
    assert send(game,eid,1).values['code'] == 10
    with game[0].db:
        game[0].db.execute('INSERT INTO equipment_enhancements VALUES (1,?,3,2,9)',(eid,))
        game[0].db.execute('UPDATE inventory SET quantity=0 WHERE item_id=1237920')
    monkeypatch.setattr(game[3].washing.factory.rng,'choice',lambda choices:choices[0])
    before = saved(game,eid)
    assert send(game,eid,2,seq=2).values['code'] == 22
    assert saved(game,eid) == before
    assert game[0].db.execute('SELECT attribute_slot,bonus FROM equipment_enhancements WHERE equip_id=?',(eid,)).fetchone()[:] == (2,9)
    assert game[2].load(1)['washing_count_day'] == 1


def test_multiple_locked_affixes_and_atomic_lock_swap_are_refused(game):
    eid = setup(game)
    param = saved(game,eid)[2]
    param.update(lock2=1,lock3=1)
    assert send(game,eid,3,equipParam=EQUIP_PARAM.encode(param)).values['code'] == 13
    param['lock3'] = 0
    assert send(game,eid,3,seq=2,equipParam=EQUIP_PARAM.encode(param)).values['code'] == 10
    param.update(lock2=0,lock3=1)
    assert send(game,eid,3,seq=3,equipParam=EQUIP_PARAM.encode(param)).values['code'] == 13
