import pytest
from tests.unit.test_economy import env
from tests.unit.test_activity_runtime import runtime
from tests.activity_calendar_helpers import activity_start
from x2server.player.economy import UnresolvedEconomy
from x2server.player.save_manager import GLOBAL_TABLES


def prepare(runtime):
    store,e,ctx,rt,now=runtime
    now[0]=activity_start(6)+12*3600
    for sid in range(2160111,2160115):
        rt.r.put(1,rt.r.at(),'clear',sid,1)
    store.db.commit()
    return store,e,rt,now


def test_master_success_once_failed_retry_and_daily_rollover(runtime):
    store,e,rt,now=prepare(runtime)
    sid=2160115; period=rt.r.at()
    assert rt.a.admission(1,sid)==period
    assert not store.db.in_transaction  # Admission must remain read-only.
    for uuid in ('failed','first','parallel'):
        with e.transaction(): rt.r.bind_run(1,sid,uuid)
    with e.transaction():rt.a.complete(1,'failed',sid,False)
    assert rt.a.admission(1,sid)==period
    with e.transaction():rt.a.complete(1,'first',sid,True)
    assert rt.a.daily_uses(1,period,sid)==1
    with pytest.raises(UnresolvedEconomy,match='daily challenge'):
        rt.a.admission(1,sid)
    before=list(store.db.execute('SELECT * FROM server_activity_limits'))
    with pytest.raises(UnresolvedEconomy,match='daily challenge'):
        with e.transaction():rt.a.complete(1,'parallel',sid,True)
    assert list(store.db.execute('SELECT * FROM server_activity_limits'))==before
    assert rt.r.get(1,period,'clear',sid)==1
    # Another repeatable tier remains open; the restriction is per section.
    assert rt.a.admission(1,2160114)==period
    now[0]+=86400
    assert rt.a.admission(1,sid)==period
    assert rt.a.daily_uses(1,period,sid)==0
    assert 'server_activity_limits' in GLOBAL_TABLES


@pytest.mark.parametrize('success',[False,True])
def test_old_successful_settlements_are_counted_on_upgrade(runtime, success):
    from x2server.player.battle import BattleService
    from x2server.messages.battle import CHECKOUT
    store,e,rt,now=prepare(runtime)
    BattleService(store,e)
    sid=2160115;period=rt.r.at()
    with e.transaction():
        rt.r.bind_run(1,sid,'old')
        store.db.execute("UPDATE activity_runs SET settled=1 WHERE uuid='old'")
        store.db.execute('INSERT INTO battle_checkout_wire VALUES (?,?,?)',('old',CHECKOUT.encode({'success':success}),'[]'))
        store.db.execute('INSERT INTO reward_settlement_audit VALUES (?,?,?,?,?,?)',
                         ('old',1,sid,'{}','[]',now[0]))
    assert rt.a.daily_uses(1,period,sid)==int(success)
    if success:
        with pytest.raises(UnresolvedEconomy):rt.a.admission(1,sid)
    else:
        assert rt.a.admission(1,sid)==period


def test_master_replay_does_not_spend_twice(runtime):
    store,e,rt,now=prepare(runtime)
    sid=2160115
    with e.transaction():rt.r.bind_run(1,sid,'once')
    with e.transaction():rt.a.complete(1,'once',sid,True)
    with pytest.raises(UnresolvedEconomy):
        with e.transaction():rt.a.complete(1,'once',sid,True)
    assert rt.a.daily_uses(1,rt.r.at(),sid)==1


def test_master_battle_entry_settlement_and_transport_replay(runtime):
    import asyncio
    from x2server.player.battle import BattleService
    from x2server.messages.battle import CHECKOUT, PROFILE_HERO
    from tests.unit.test_battle import packet
    store,e,rt,now=prepare(runtime)
    ctx=runtime[2];e.activity=rt.a
    battle=BattleService(store,e)
    player=store.get(1)
    store.save_snapshot(1,{**player['snapshot'],'mobility':{'power':100000}},player['revision'])
    row=battle.catalog.sections[2160115]
    entry={'missionId':2160115,'chapter':row['ChapterID'],'sceneId':row['Maps'][0],
           'heros':[PROFILE_HERO.encode({'heroId':1003,'leader':1})]}
    assert asyncio.run(battle.enter(ctx,packet(entry,900))).values['result']==10
    request=packet({'checkout':CHECKOUT.encode({'chapterId':row['ChapterID'],
        'sectionId':2160115,'success':True,'fightTime':200})},901,name='C2L_CheckoutMainMissionSign')
    reply=asyncio.run(battle.checkout(ctx,request))
    assert reply.values['result']==10
    assert asyncio.run(battle.checkout(ctx,request)).values==reply.values
    assert rt.a.daily_uses(1,rt.r.at(),2160115)==1
    assert asyncio.run(battle.enter(ctx,packet(entry,902))).values['result']==13
    now[0]+=86400
    assert asyncio.run(battle.enter(ctx,packet(entry,903))).values['result']==10
