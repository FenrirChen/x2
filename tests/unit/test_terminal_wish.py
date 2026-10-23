import asyncio
import json
import pytest

from tests.unit.test_college_upgrade import game
from tests.unit.test_battle import packet, request
from x2server.messages.core import CORE_SCHEMAS
from x2server.messages.economy import TASK, FINISH_REQUEST, FINISH_RESULT
from x2server.messages.battle import PROFILE_HERO, CHECKOUT
from x2server.player.battle import BattleService
from x2server.player.college import CollegeService
from x2server.player.favor import FavorService
from x2server.player.task_calendar import task_period


@pytest.fixture
def wishes(game):
    store,clock,repo,college,ctx = game
    e = college.washing.economy
    p = store.get(1)
    heroes = [{'id':hid,'level':1,'star':1,'state':2,'exp':0} for hid in (1003,1004,1010)]
    store.save_snapshot(1,dict(p['snapshot'],heroes=heroes,main_chapter=2010800,main_section=2110707,crystal=1000,mobility={'power':500}),p['revision'])
    with store.db:
        store.db.execute('INSERT INTO inventory VALUES (1,1204002,99)')
        e.mark_section_cleared(1,2110308,'wish-fixture',0)
    return (*game,e,e.terminal_wish)


def wire(response):
    for message in (*response.before_response,response,*response.pushes):
        CORE_SCHEMAS[message.message_name].encode(message.values)
    return response


def query(wishes,seq=1,analyse=True):
    return wire(asyncio.run(wishes[5].handle(wishes[4],packet({'type':6,'extraType':int(analyse),'chapterId':0},seq,'C2L_GameTask'))))


def accept(wishes,ids,seq=2,kind=6):
    return wire(asyncio.run(wishes[6].accept(wishes[4],packet({'type':kind,'taskIds':ids},seq,'C2L_AcceptFavorTask'))))


EIGHT_TASKS = (635030, 635031, 635033, 635042, 635105, 635044, 635048, 635100)


def choose(wishes,monkeypatch,ids=EIGHT_TASKS):
    def sample(pool,count):
        assert count == 8 and set(ids) <= set(pool)
        return list(ids)
    monkeypatch.setattr(wishes[6].rng,'sample',sample)
    result = query(wishes)
    assert result.values['code'] == 10
    assert [r['taskId'] for r in map(TASK.decode,result.values['taskList'])] == list(ids)
    assert accept(wishes,ids[:3]).values['code'] == 10
    return list(ids)


def claim(wishes,tid,seq=3,async_mode=False):
    fields = {'taskId':tid,'type':6} if async_mode else {'data':[FINISH_REQUEST.encode({'taskId':tid,'type':6})]}
    name = 'C2L_FinishGameTaskAsync' if async_mode else 'C2L_FinishGameTask'
    response = wire(asyncio.run(wishes[5].handle(wishes[4],packet(fields,seq,name))))
    raw = response.values['data'] if async_mode else response.values['data'][0]
    return FINISH_RESULT.decode(raw),response


def test_analysis_eight_candidates_stable_relogin_and_acceptance_limit(wishes):
    before = query(wishes,analyse=False)
    assert before.values['taskList'] == []
    result = query(wishes,seq=2)
    ids = [r['taskId'] for r in map(TASK.decode,result.values['taskList'])]
    assert len(ids) == len(set(ids)) == 8
    assert all(wishes[6].tasks[tid]['HeroID'] in (1003,1004,1010) for tid in ids)
    assert query(wishes,seq=3).values == result.values
    assert query(wishes,seq=4,analyse=False).values == result.values
    # 选择页仍只接 3 条: 少于/多于/重复/整批 8 条都不收
    assert accept(wishes,[ids[0]],seq=5).values['code'] == 13
    assert accept(wishes,ids[:4],seq=6).values['code'] == 13
    assert accept(wishes,[ids[0],ids[0],ids[1]],seq=7).values['code'] == 13
    assert accept(wishes,[ids[0]]*3,seq=8).values['code'] == 13
    assert accept(wishes,ids,seq=9).values['code'] == 13
    assert accept(wishes,ids[:3],seq=10,kind=5).values['code'] == 13
    assert accept(wishes,ids[:3],seq=11).values['code'] == 10
    assert accept(wishes,ids[:3],seq=11).values['code'] == 10
    assert accept(wishes,ids[3:6],seq=12).values['code'] == 13
    assert wishes[6].load(1)['accepted'] == 3
    assert {r['taskStatus'] for r in map(TASK.decode,query(wishes,seq=13).values['taskList'])} == {2}
    from x2server.player.terminal_wish import TerminalWishService
    restored = TerminalWishService(wishes[5])
    assert restored.load(1) == wishes[6].load(1)


def test_equal_weight_pool_is_sampled_once_and_preaccept_events_do_not_count(wishes,monkeypatch):
    wishes[5].record_event(1,'old-gift',68,1003,3,1204002)
    choose(wishes,monkeypatch)
    assert all(r['progress']==0 for r in wishes[6].load(1)['tasks'].values())
    wishes[5].record_event(1,'old-gift',68,1003,3,1204002)
    assert wishes[6].load(1)['tasks']['635033']['progress'] == 0


def test_real_gift_progress_exact_reward_favor_and_no_duplicate_claim(wishes,monkeypatch):
    choose(wishes,monkeypatch)
    favor = FavorService(wishes[0],wishes[5],clock=wishes[1].now)
    gift = packet({'opt':2,'optionId':1204002,'heroId':1003,'num':3},3,'C2L_AddFavor')
    assert wire(asyncio.run(favor.handle(wishes[4],gift))).values['code'] == 10
    assert wishes[6].load(1)['tasks']['635033']['progress'] == 3
    hero = next(h for h in wishes[0].get(1)['snapshot']['heroes'] if h['id']==1003)
    old_favor = hero['favor']['exp']
    old_exp = wishes[0].get(1)['snapshot'].get('exp',0)
    result,response = claim(wishes,635033,4)
    assert result['code'] == 10
    assert wishes[0].get(1)['snapshot']['exp'] == old_exp + 110
    assert next(h for h in wishes[0].get(1)['snapshot']['heroes'] if h['id']==1003)['favor']['exp'] == old_favor + 50
    assert 'L2C_FavorChangeInfo' in [r.message_name for r in response.pushes]
    after = wishes[0].get(1)['snapshot']
    assert claim(wishes,635033,5,True)[0] == result
    assert wishes[0].get(1)['snapshot'] == after
    assert wishes[6].load(1)['tasks']['635033']['claimed']
    assert claim(wishes,635031,6)[0]['code'] == 13


def test_battle_uses_bound_team_success_only_and_repeated_reports_do_not_count(wishes,monkeypatch):
    choose(wishes,monkeypatch)
    battle = BattleService(wishes[0],wishes[5])
    section = 2130501
    row = battle.catalog.sections[section]
    values = request()
    values.update(missionId=section,chapter=row['ChapterID'],sceneId=row['Maps'][0],
                  heros=[PROFILE_HERO.encode({'heroId':1003,'leader':1})])
    entry = wire(asyncio.run(battle.enter(wishes[4],packet(values,3))))
    assert entry.values['result'] == 10
    assert wishes[6].load(1)['tasks']['635030']['progress'] == 0
    done = packet({'checkout':CHECKOUT.encode({'chapterId':row['ChapterID'],'sectionId':section,'success':True,'fightTime':100})},4,'C2L_CheckoutMainMissionSign')
    assert wire(asyncio.run(battle.checkout(wishes[4],done))).values['result'] == 10
    assert wishes[6].load(1)['tasks']['635030']['progress'] == 1
    assert asyncio.run(battle.checkout(wishes[4],done)).values['result'] == 10
    assert wishes[6].load(1)['tasks']['635030']['progress'] == 1


def test_real_training_completion_counts_without_cancellation_or_retry_duplicates(wishes,monkeypatch):
    choose(wishes,monkeypatch)
    state = wishes[2].load(1)
    state['star_energy'] = 300
    wishes[2].save(1,state)
    result = wire(asyncio.run(wishes[3].dispatch(wishes[4],packet({'trainId':0,'heroId':1003},3,'C2L_StartTrain'))))
    assert result.values['code'] == 10
    assert wishes[6].load(1)['tasks']['635031']['progress'] == 0
    wishes[1].value += result.values['trainTime']
    result = wire(asyncio.run(wishes[3].dispatch(wishes[4],packet({'trainId':0},4,'C2L_FinishTrain'))))
    assert result.values['code'] == 10
    assert wishes[6].load(1)['tasks']['635031']['progress'] == 1
    assert asyncio.run(wishes[3].dispatch(wishes[4],packet({'trainId':0},4,'C2L_FinishTrain'))).values['code'] == 10
    assert wishes[6].load(1)['tasks']['635031']['progress'] == 1


def test_event_matching_covers_all_official_kinds_and_hero_item_ruin_difficulty(wishes,monkeypatch):
    ids = choose(wishes,monkeypatch,(635042,635105,635033,635030,635031,635044,635048,635100))
    for kind,hero,value2 in [(67,1003,34001),(67,1004,999),(25,1010,1),(68,1003,1204003)]:
        wishes[5].record_event(1,f'wrong:{kind}:{hero}:{value2}',kind,hero,3,value2)
    assert all(r['progress']==0 for r in wishes[6].load(1)['tasks'].values())
    wishes[5].record_event(1,'explore:job',67,1004,1,34001)
    wishes[5].record_event(1,'challenge:run',25,1010,1,2)
    wishes[5].record_event(1,'gift:new',68,1003,3,1204002)
    assert [wishes[6].load(1)['tasks'][str(tid)]['progress'] for tid in ids[:3]] == [1,1,3]


def test_midnight_clears_candidates_tasks_accept_count_and_old_packet_cannot_accept(wishes,monkeypatch):
    ids = choose(wishes,monkeypatch)
    wishes[1].value = task_period(1,wishes[1].value)[1]-1
    assert wishes[6].load(1)['accepted'] == 3
    wishes[1].value += 1
    assert query(wishes,seq=8,analyse=False).values['taskList'] == []
    assert wishes[6].load(1)['accepted'] == 0
    assert accept(wishes,ids,seq=2).values['code'] == 13
    assert query(wishes,seq=1).values['code'] == 173
    assert query(wishes,seq=9).values['code'] == 10
    assert accept(wishes,ids[:3],seq=10).values['code'] == 10


def test_insufficient_pool_and_locked_entry_return_native_denials(wishes,monkeypatch):
    monkeypatch.setattr(wishes[6],'eligible',lambda pid:[635030,635031])
    assert query(wishes).values['code'] == 173
    assert wishes[6].load(1)['candidates'] == []
    p = wishes[0].get(1)
    wishes[0].save_snapshot(1,dict(p['snapshot'],level=19),p['revision'])
    assert query(wishes,seq=2).values['code'] == 13


def test_claim_failure_rolls_back_items_favor_state_and_history(wishes,monkeypatch):
    choose(wishes,monkeypatch)
    wishes[5].record_event(1,'gift-event',68,1003,3,1204002)
    before = wishes[0].get(1)['snapshot']
    from x2server.messages.economy import FINISH_RESULT
    def fail(*args):
        raise ValueError('wire failure')
    monkeypatch.setattr(FINISH_RESULT,'encode',fail)
    assert wishes[6].claim(1,635033)['code'] == 13
    assert wishes[0].get(1)['snapshot'] == before
    assert not wishes[6].load(1)['tasks']['635033']['claimed']
    assert not wishes[0].db.execute("SELECT 1 FROM economy_grants WHERE source LIKE 'terminal-wish:%'").fetchone()


def test_real_exploration_claim_counts_the_actual_heroes_and_ruin(wishes,monkeypatch):
    choose(wishes,monkeypatch,(635042,635105,635033,635030,635031,635044,635048,635100))
    # Supply a team with sufficient real battle power for the first ruin.
    p = wishes[0].get(1)
    heroes = [dict(h,level=50,star=15) for h in p['snapshot']['heroes']]
    wishes[0].save_snapshot(1,dict(p['snapshot'],heroes=heroes),p['revision'])
    wishes[2].growth_base(1)
    wishes[2].unlock_ruins(1)
    state = wishes[2].load(1)
    state['star_energy'] = 300
    wishes[2].save(1,state)
    start = packet({'exploreId':0,'ruinId':34001,'heroIds':[1004,1003,1010]},3,'C2L_StartExplore')
    assert wire(asyncio.run(wishes[3].dispatch(wishes[4],start))).values['code'] == 10
    assert wishes[6].load(1)['tasks']['635042']['progress'] == 0
    wishes[1].value = wishes[2].load(1)['explore'][0]['exploreEndTime']
    finish = packet({'exploreId':0},4,'C2L_FinishExplore')
    assert wire(asyncio.run(wishes[3].dispatch(wishes[4],finish))).values['code'] == 10
    assert wishes[6].load(1)['tasks']['635042']['progress'] == 1
    assert asyncio.run(wishes[3].dispatch(wishes[4],finish)).values['code'] == 10
    assert wishes[6].load(1)['tasks']['635042']['progress'] == 1


def test_all_351_rows_have_supported_conditions_rewards_and_hero_data(wishes):
    w = wishes[6]
    assert len(w.tasks) == 351
    assert {c['CompleteType']['value'] for c in w.conditions.values()} == {11,25,67,68,69}
    for task in w.tasks.values():
        assert task['HeroID'] in w.favor.heroes
        assert task['FavorabilityGift'] > 0
        assert w.e.gifts([task['GiftGroup']])
        assert w.conditions[str(task['TaskCondition'])]['CompleteNum'] > 0


def test_migration_preserves_candidates_progress_claims_and_quota(wishes,monkeypatch,tmp_path):
    from tests.unit.test_save_manager import build_full_schema
    from x2server.player.save_manager import SaveManager
    choose(wishes,monkeypatch)
    wishes[5].record_event(1,'gift-complete',68,1003,3,1204002)
    assert claim(wishes,635033)[0]['code'] == 10
    before = wishes[6].load(1)
    wishes[0].login('new-owner',2,0)
    build_full_schema(wishes[0])
    manager = SaveManager(wishes[0],backup_root=tmp_path/'backups')
    try:
        archive = manager.export_save(1)
        manager.import_save(2,archive)
        assert wishes[6].load(2) == before
        wishes[4].session.player_id = 2
        wishes[4].session.session_id = 'after-import'
        target = wishes[0].get(2)['snapshot']
        assert claim(wishes,635033,7)[0]['code'] == 10
        assert wishes[0].get(2)['snapshot'] == target
        assert accept(wishes,list(map(int,before['tasks'])),seq=8).values['code'] == 13
    finally:
        manager.close()


def test_midnight_watcher_expiration_sends_empty_current_state_without_claiming(wishes,monkeypatch):
    choose(wishes,monkeypatch)
    before = wishes[0].get(1)['snapshot']
    wishes[1].value = task_period(1,wishes[1].value)[1]
    expired = wire(wishes[6].expire_day(1))
    assert expired.message_name == 'L2C_GameTask'
    assert expired.values['type'] == 6 and expired.values['taskList'] == []
    assert wishes[0].get(1)['snapshot'] == before
    assert wishes[6].load(1)['accepted'] == 0
    assert wishes[6].expire_day(1) is None
    assert not wishes[0].db.execute("SELECT 1 FROM economy_grants WHERE source LIKE 'terminal-wish:%'").fetchone()


def test_independent_native_accept_wire_tags(wishes,monkeypatch):
    from x2server.messages.terminal import TERMINAL_SCHEMAS
    # Native serializer 0x37d09a0 writes tag08 repeatedly; 0x37d0a2c
    # writes tag10 for type. This is independent of declaration-order guesses.
    raw = bytes.fromhex('0801080208031006')
    assert TERMINAL_SCHEMAS['C2L_AcceptFavorTask'].decode(raw) == {'taskIds':[1,2,3],'type':6}
    assert TERMINAL_SCHEMAS['L2C_AcceptFavorTask'].encode({'code':10}) == bytes.fromhex('080a')


def test_accept_write_failure_returns_denial_and_does_not_consume_quota(wishes,monkeypatch):
    ids = [r['taskId'] for r in map(TASK.decode,query(wishes).values['taskList'])]
    before = wishes[6].load(1)
    import sqlite3
    def failed_save(*args):
        raise sqlite3.OperationalError('disk write failure')
    monkeypatch.setattr(wishes[6],'save',failed_save)
    assert accept(wishes,ids[:3]).values['code'] == 13
    assert wishes[6].load(1) == before


def test_actual_dispatcher_routes_analysis_accept_and_claim_to_wish_service(wishes,monkeypatch):
    from x2server.network.dispatcher import Dispatcher, DispatchStatus
    from x2server.player.terminal import TerminalService
    # Same ordering as local_game_server: terminal conversations must not
    # intercept the newly registered heart-wish accept flow.
    router = Dispatcher({**wishes[5].handlers(), **TerminalService(wishes[0],wishes[5]).handlers()})
    result = asyncio.run(router.dispatch(wishes[4],packet({'type':6,'extraType':1},1,'C2L_GameTask')))
    assert result.status == DispatchStatus.HANDLED
    ids = [r['taskId'] for r in map(TASK.decode,result.response.values['taskList'])]
    result = asyncio.run(router.dispatch(wishes[4],packet({'type':6,'taskIds':ids[:3]},2,'C2L_AcceptFavorTask')))
    assert result.status == DispatchStatus.HANDLED
    assert wire(result.response).values['code'] == 10
