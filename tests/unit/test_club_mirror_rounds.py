"""镜域额外层 (2170037~2170052) 按 4 周目轮换, 必须和客户端算法对齐。

反汇编依据 (见 docs/knowledge/club_mirror_rewards_20261015.md):
* ClubModule_Get5AMWeekIndex (0x01585A34) = floor((ServerTime - 18000) / 604800) + 1
  -> 每周四 13:00 (北京) 换周目。
* ClubModule_GetClubActivityCurExtraLayerStart (0x01564C98) = 36 + 4 * (weekIndex % 4)
  -> 额外层首层依次是 37 / 41 / 45 / 49。
* ClubModule_GetClubActivityLayer (0x015615D8) 只有 clubLayer_ 前缀连续时才会把 cur
  往前推; 常驻 1~36 有缺口时 cur 停在缺口上, 额外层宝箱永远不亮。
"""
import pytest

from tests.unit.test_social import social, create, act
from tests.unit.test_economy import env, rewards
from x2server.player.social import (MIRROR_BASE_LAYERS, MIRROR_ROUND_LAYERS,
                                    mirror_block_start, mirror_week_index, roster)
from x2server.player.economy import UnresolvedEconomy


def setup(s, ctx, members=0):
    create(s, ctx)
    with s.economy.transaction():
        state = s.state(1)
        state['club']['members'] = {str(r['id']): 0 for r in roster()[:members]}
        s.save(1, state)


def base_rows(s):
    return s.mirror_health[:MIRROR_BASE_LAYERS]


def block_rows(s, start=None):
    start = start or mirror_block_start(s.clock())
    return s.mirror_health[start-1:start-1+MIRROR_ROUND_LAYERS]


def section_of(layer):
    return 2170000 + layer


def update(s, **fields):
    with s.economy.transaction():
        state = s.state(1)
        state['mirror'].update(**fields)
        s.save(1, state)


def test_week_boundary_is_thursday_13_beijing_and_blocks_cycle():
    for k in range(400, 408):
        tick = 18000 + k * 604800  # 北京周四 13:00 的切换点
        assert mirror_week_index(tick) == k + 1
        assert mirror_week_index(tick - 1) == k
        assert mirror_block_start(tick) == 37 + 4 * ((k + 1) % 4)
        assert mirror_block_start(tick - 1) == 37 + 4 * (k % 4)
        assert mirror_block_start(tick + 604799) == mirror_block_start(tick)
    assert {mirror_block_start(18000 + k * 604800) for k in range(4)} == {37, 41, 45, 49}


def test_current_layer_walks_base_before_the_rotating_block(social):
    s, ctx, _ = social
    setup(s, ctx)
    start = mirror_block_start(s.clock())
    base = base_rows(s)
    update(s, clears=[r['bossId'] for r in base[:-1]])
    # 常驻 1~36 有缺口时, 客户端 cur 停在缺口上, 额外层还不能进。
    with pytest.raises(UnresolvedEconomy, match='current layer'):
        s.admission(1, section_of(start))
    update(s, clears=[r['bossId'] for r in base])
    s.admission(1, section_of(start))
    with pytest.raises(UnresolvedEconomy, match='current layer'):
        s.admission(1, section_of(start + 1))
    other = start + 4 if start + MIRROR_ROUND_LAYERS <= 52 else start - 4
    with pytest.raises(UnresolvedEconomy, match='rotation'):
        s.admission(1, section_of(other))
    update(s, clears=[r['bossId'] for r in base] + [block_rows(s, start)[0]['bossId']])
    s.admission(1, section_of(start + 1))


def test_round_rotation_forgets_extra_progress_but_keeps_base(social):
    s, ctx, stamp = social
    setup(s, ctx)
    start = mirror_block_start(stamp[0])
    base, block = base_rows(s), block_rows(s, start)
    base_clears = [r['bossId'] for r in base]
    base_claims = [r['section'] for r in base]
    week = mirror_week_index(stamp[0])
    update(s, clears=base_clears + [r['bossId'] for r in block],
           claimed=base_claims + [r['section'] for r in block],
           damage={str(r['bossId']): r['maxHP'] for r in block},
           sections=base_claims + [r['section'] for r in block], round=week)
    state = s.state(1)
    assert state['mirror']['round'] == week
    assert state['mirror']['clears'] == base_clears + [r['bossId'] for r in block]
    assert act(s, ctx, 'ClubActiMainData', {}, 40).values['receivedLayer'] == base_claims + [
        r['section'] for r in block]
    meta = {p['Name']: p['Value']['VInt64'] for p in s.http('/ClubService.GetClub', {}, 1)['Club']['Meta']}
    assert meta[f'clubLayer_{start}'] == 1
    # 4 周一轮正好回到同一组; 进度存的是周目号, 所以照样会重置。
    stamp[0] += MIRROR_ROUND_LAYERS * 604800
    assert mirror_block_start(stamp[0]) == start
    assert mirror_week_index(stamp[0]) != week
    state = s.state(1)
    assert state['mirror']['round'] == mirror_week_index(stamp[0])
    assert state['mirror']['clears'] == base_clears
    assert state['mirror']['claimed'] == base_claims
    assert state['mirror']['damage'] == {}
    assert state['mirror']['sections'] == base_claims
    assert act(s, ctx, 'ClubActiMainData', {}, 41).values['receivedLayer'] == base_claims
    meta = {p['Name']: p['Value']['VInt64'] for p in s.http('/ClubService.GetClub', {}, 1)['Club']['Meta']}
    extra = [int(name.split('_')[1]) for name in meta
             if name.startswith(('clubLayer_', 'clubDamage_'))]
    assert extra and all(i <= MIRROR_BASE_LAYERS or start <= i < start + MIRROR_ROUND_LAYERS
                         for i in extra)
    assert f'clubLayer_{start}' not in meta


def test_extra_chest_is_claimable_once_per_round_and_again_next_cycle(social):
    s, ctx, stamp = social
    setup(s, ctx)
    start = mirror_block_start(stamp[0])
    section, row = section_of(start), s.mirror_sections[section_of(start)]
    update(s, clears=[r['bossId'] for r in base_rows(s)])
    with s.economy.transaction():
        s.bind_run(1, section, 'cycle-1')
        s.completed(1, section, True, run='cycle-1')
    reply = act(s, ctx, 'ClubReceiveReward', {'opt': 2, 'param': section}, 30)
    assert reply.values['code'] == 10
    assert rewards(reply.values['rewardData']) == s.economy.gifts([row['winReward']])
    assert act(s, ctx, 'ClubReceiveReward', {'opt': 2, 'param': section}, 31).values['code'] == 13
    stamp[0] += MIRROR_ROUND_LAYERS * 604800
    assert mirror_block_start(stamp[0]) == start
    assert s.state(1)['mirror']['clears'] == [r['bossId'] for r in base_rows(s)]
    assert act(s, ctx, 'ClubReceiveReward', {'opt': 2, 'param': section}, 32).values['code'] == 13
    with s.economy.transaction():
        s.bind_run(1, section, 'cycle-2')
        s.completed(1, section, True, run='cycle-2')
    reply = act(s, ctx, 'ClubReceiveReward', {'opt': 2, 'param': section}, 33)
    assert reply.values['code'] == 10
    assert rewards(reply.values['rewardData']) == s.economy.gifts([row['winReward']])


def test_npc_assist_chain_stops_at_the_block_edge(social):
    s, ctx, _ = social
    setup(s, ctx, members=10)
    start = mirror_block_start(s.clock())
    base, block = base_rows(s), block_rows(s, start)
    update(s, clears=[r['bossId'] for r in base])
    for i in range(MIRROR_ROUND_LAYERS):
        s.mirror_health[start-1+i] = dict(block[i], maxHP=10)
    with s.economy.transaction():
        s.bind_run(1, section_of(start), 'chain')
        result = s.completed(1, section_of(start), True, 1000, 'chain')
    assert [t['boss'] for t in result['turns']][:5] == [r['bossId'] for r in block]
    assert s.state(1)['mirror']['clears'] == [r['bossId'] for r in base] + [
        r['bossId'] for r in block]
    assert s.mirror_current(s.state(1)) is None
    if start + MIRROR_ROUND_LAYERS <= 52:
        assert s.mirror_health[start + MIRROR_ROUND_LAYERS - 1]['bossId'] not in s.state(1)['mirror']['clears']


def test_legacy_save_without_round_keeps_base_and_only_the_current_block(social):
    s, ctx, _ = social
    setup(s, ctx)
    start = mirror_block_start(s.clock())
    base, block = base_rows(s), block_rows(s, start)
    block_bosses = [r['bossId'] for r in block]
    stale_boss = next(b for b in range(2070037, 2070053) if b not in block_bosses)
    with s.economy.transaction():
        state = s.state(1)
        state['mirror'].pop('round', None)
        state['mirror']['clears'] = [2070001] + block_bosses + [stale_boss]
        state['mirror']['claimed'] = [2170001] + [r['section'] for r in block]
        s.save(1, state)
    state = s.state(1)
    assert state['mirror']['round'] == mirror_week_index(s.clock())
    assert state['mirror']['clears'] == [2070001] + block_bosses
    # Keep claims with retained current-block clears; migration must not re-award.
    assert state['mirror']['claimed'] == [2170001] + [r['section'] for r in block]


def test_run_bound_before_rotation_is_refused_without_spending(social):
    s, ctx, stamp = social
    setup(s, ctx)
    start = mirror_block_start(stamp[0])
    update(s, clears=[r['bossId'] for r in base_rows(s)])
    with s.economy.transaction():
        s.bind_run(1, section_of(start), 'late')
    stamp[0] += 7 * 86400
    assert mirror_block_start(stamp[0]) != start
    with pytest.raises(UnresolvedEconomy, match='rotation'):
        with s.economy.transaction():
            s.completed(1, section_of(start), True, run='late')
    state = s.state(1)
    assert state['mirror']['runs']['late']['done'] is False
    assert block_rows(s, start)[0]['bossId'] not in state['mirror']['clears']


def test_legacy_current_round_claim_is_not_granted_twice(social):
    s, ctx, _ = social
    setup(s, ctx)
    start = mirror_block_start(s.clock())
    section = section_of(start)
    update(s, clears=[r['bossId'] for r in base_rows(s)])
    with s.economy.transaction():
        s.bind_run(1, section, 'legacy-claimed')
        s.completed(1, section, True, run='legacy-claimed')
    assert act(s,ctx,'ClubReceiveReward',{'opt':2,'param':section},801).values['code']==10
    with s.economy.transaction():
        state=s.state(1)
        state['mirror'].pop('round')
        s.save(1,state)
    serial=s.state(1)['serial']
    assert section in s.mirror_claimed_sections(s.state(1))
    assert act(s,ctx,'ClubReceiveReward',{'opt':2,'param':section},802).values['code']==13
    assert s.state(1)['serial']==serial


def test_pending_run_cannot_settle_after_four_weeks_returns_to_same_group(social):
    s, ctx, stamp = social
    setup(s,ctx)
    section=section_of(mirror_block_start(s.clock()))
    update(s,clears=[r['bossId'] for r in base_rows(s)])
    with s.economy.transaction():
        s.bind_run(1,section,'four-weeks-late')
    stamp[0]+=4*604800
    before=s.state(1)
    with pytest.raises(UnresolvedEconomy,match='rotation'):
        with s.economy.transaction():
            s.completed(1,section,True,run='four-weeks-late')
    assert s.state(1)==before


@pytest.mark.parametrize('age_weeks,has_evidence,allowed',[(0,True,True),(4,True,False),(0,False,False)])
def test_legacy_pending_extra_run_requires_entry_time_evidence(social,age_weeks,has_evidence,allowed):
    from x2server.player.battle import BattleService
    s,ctx,stamp=social
    setup(s,ctx)
    section=section_of(mirror_block_start(s.clock()))
    update(s,clears=[r['bossId'] for r in base_rows(s)])
    BattleService(s.store,s.economy)
    with s.economy.transaction():
        s.bind_run(1,section,'old-pending')
        state=s.state(1);state['mirror']['runs']['old-pending'].pop('round');s.save(1,state)
        if has_evidence:
            s.store.db.execute('INSERT INTO battle_entries(player_id,request_key,uuid,created_at,response) VALUES (1,?,?,?,?)',
                ('old-pending','old-pending',stamp[0]-age_weeks*604800,b'legacy'))
    before=s.state(1)
    if allowed:
        with s.economy.transaction():
            assert s.completed(1,section,True,run='old-pending')['done']
    else:
        with pytest.raises(UnresolvedEconomy,match='rotation'):
            with s.economy.transaction():s.completed(1,section,True,run='old-pending')
        assert s.state(1)==before


def test_layer_24_npc_chest_charges_one_correct_key(social):
    s,ctx,_=social
    setup(s,ctx)
    update(s,clears=[r['bossId'] for r in base_rows(s)[:24]])
    from tests.unit.test_social import fund
    fund(s,1283204,1)
    result=act(s,ctx,'ClubReceiveReward',{'opt':2,'param':2170024},901)
    assert result.values['code']==10
    assert rewards(result.values['rewardData'])==s.economy.gifts([778124])
    assert s.quantity(1,1283204)==0
    assert act(s,ctx,'ClubReceiveReward',{'opt':2,'param':2170024},902).values['code']==13


def test_actual_entry_checkout_claim_replay_and_next_four_week_cycle(social):
    import asyncio
    from tests.unit.test_battle import packet,request
    from x2server.player.battle import BattleService
    from x2server.messages.battle import CHECKOUT
    s,ctx,stamp=social
    setup(s,ctx)
    update(s,clears=[r['bossId'] for r in base_rows(s)])
    battle=BattleService(s.store,s.economy)
    first_section=section_of(mirror_block_start(s.clock()))
    for cycle in range(2):
        section=section_of(mirror_block_start(s.clock()))
        assert section==first_section
        config=battle.catalog.sections[section]
        values=request();values.update(missionId=section,chapter=config['ChapterID'],sceneId=config['Maps'][0])
        begin=asyncio.run(battle.enter(ctx,packet(values,1500+cycle)))
        assert begin.values['result']==10
        bound=s.state(1)['mirror']['runs'][begin.values['uuid']]
        assert bound['round']==mirror_week_index(s.clock())
        done=packet({'checkout':CHECKOUT.encode({'chapterId':config['ChapterID'],
            'sectionId':section,'success':True,'fightTime':60})},1600+cycle,'C2L_CheckoutMainMissionSign')
        result=asyncio.run(battle.checkout(ctx,done))
        assert result.values['result']==10
        before=s.state(1)
        assert asyncio.run(battle.checkout(ctx,done)).values==result.values
        assert s.state(1)==before
        reward=act(s,ctx,'ClubReceiveReward',{'opt':2,'param':section},1700+cycle*2)
        assert reward.values['code']==10
        assert act(s,ctx,'ClubReceiveReward',{'opt':2,'param':section},1701+cycle*2).values['code']==13
        stamp[0]+=4*604800
