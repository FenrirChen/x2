import asyncio
import json
import pytest

from tests.unit.test_college_upgrade import game
from tests.unit.test_battle import packet, request
from x2server.messages.core import CORE_SCHEMAS
from x2server.messages.moon import MOON_IDS, MOON_SCHEMAS as S
from x2server.messages.economy import FINISH_REQUEST, FINISH_RESULT, REWARD, REWARD_ITEM
from x2server.messages.battle import OUTSIDE_ITEM, CHECKOUT, FIGHT_PROFILE
from x2server.player.battle import BattleService
from x2server.player.moon import PARAMETERS, catalog


@pytest.fixture
def moon(game):
    store, clock, _, college, ctx = game
    economy = college.washing.economy
    return store, clock, economy, economy.moon, ctx


def send(moon, name, seq=1, **values):
    response = asyncio.run(moon[3].handle(moon[4], packet(values, seq, 'C2L_' + name)))
    for message in (*response.before_response, response, *response.pushes):
        CORE_SCHEMAS[message.message_name].encode(message.values)
    return response


def put(moon, item, quantity):
    with moon[2].transaction():
        moon[0].db.execute('INSERT INTO inventory VALUES (1,?,?) ON CONFLICT(player_id,item_id) DO UPDATE SET quantity=excluded.quantity', (item, quantity))


def complete(moon, mid=5010001, seq=3):
    group = S['MoonMissionGroup'].encode({'missionGroupId': mid, 'moonChildrenMission': [
        S['ChildrenMission'].encode({'childrenMissionId': q, 'childrenMissionStatus': 4})
        for q in moon[3].missions[mid]['QuestID']]})
    return send(moon, 'MoonMissionGroupSync', seq, moonMissionGroup=[group])


def reward_items(raw):
    return {i['itemId']: i['itemNum'] for i in map(REWARD_ITEM.decode, REWARD.decode(raw).get('rewardItem', []))}


def test_original_catalog_and_all_protocol_ids(moon):
    assert len(catalog()['mooncamp']) == 4
    assert len(catalog()['moonnpc']) == 20
    assert len(catalog()['moonequip']) == 24
    assert len(catalog()['missiontable']) == 193
    assert PARAMETERS['MoonFlowerGetLimit'] == '6'
    assert PARAMETERS['MoonEquipExpGetLimit'] == '300'
    assert PARAMETERS['MoonFlowerGiveLimit'] == '9999'
    from x2server.protocol.registry import CORE_MESSAGE_REGISTRY
    for name, request_id, response_id in MOON_IDS:
        assert CORE_MESSAGE_REGISTRY.name_for(request_id) == 'C2L_' + name
        assert CORE_MESSAGE_REGISTRY.name_for(response_id) == 'L2C_' + name
        assert 'C2L_' + name in moon[3].handlers()


@pytest.mark.parametrize('name', ['MoonCampUnlock', 'MoonCampPrestige', 'MoonNPCFavorability', 'MoonEquip', 'MoonAcceptableRepeatTask'])
def test_every_entry_query_has_wire_response(moon, name):
    result = send(moon, name)
    assert result.values['code'] == 10
    if name == 'MoonCampUnlock':
        assert len(result.values['moonCampUnlock']) == 4
        assert result.before_response[0].message_name == 'L2C_GameTask'
        assert result.before_response[0].values['type'] == 16
    if name == 'MoonEquip':
        normal = list(map(S['MoonEquipBarInfo'].decode, result.values['moonEquipBarNormal']))
        assert [r['moonEquipId'] for r in normal] == [-1, -1, -1, -1]
        assert len(result.values['moonEquipBarSpecial']) == 1
    if name == 'MoonNPCFavorability':
        assert len(result.values['moonNPCFavorability']) == 20


def test_guide_completion_unlocks_camp_and_equipment_once(moon):
    assert complete(moon).values['code'] == 10
    assert moon[3].quantity(1, 1110001) == 1
    assert moon[3].camp_open(moon[3].load(1), 700001)
    assert complete(moon).values['code'] == 10  # transport replay
    assert complete(moon, seq=4).values['code'] == 10  # scene sync replay
    assert moon[3].quantity(1, 1110001) == 1
    data = S['MoonEquipData'].decode(send(moon, 'MoonEquip', 5).values['moonEquip'][0])
    assert data == {'moonEquipId': 111001, 'moonEquipLevel': 1}


def test_reject_forged_child_and_roll_back_entire_sync(moon):
    valid = S['MoonMissionGroup'].encode({'missionGroupId': 5010001, 'moonChildrenMission': [
        S['ChildrenMission'].encode({'childrenMissionId': 580900, 'childrenMissionStatus': 4})]})
    invalid = S['MoonMissionGroup'].encode({'missionGroupId': 5010002, 'moonChildrenMission': [
        S['ChildrenMission'].encode({'childrenMissionId': 580900, 'childrenMissionStatus': 4})]})
    assert send(moon, 'MoonMissionGroupSync', moonMissionGroup=[valid, invalid]).values['code'] == 13
    assert moon[3].load(1)['tasks']['5010001']['children']['580900'] == 2
    assert moon[3].quantity(1, 1110001) == 0


def test_flower_exact_inventory_per_flower_five_and_replay(moon):
    complete(moon)
    put(moon, 1120002, 4)
    result = send(moon, 'MoonFlowerGive', 10, moonNPCId=2250, moonFlowerNumber=4)
    assert result.values == {'code': 10, 'moonNPCId': 2250, 'favorability': 20, 'realNum': 4}
    assert moon[3].quantity(1, 1120002) == 0
    assert send(moon, 'MoonFlowerGive', 10, moonNPCId=2250, moonFlowerNumber=4).values == result.values
    assert send(moon, 'MoonFlowerGive', 11, moonNPCId=2250, moonFlowerNumber=1).values['code'] == 13
    assert send(moon, 'MoonFlowerGive', 12, moonNPCId=2350, moonFlowerNumber=1).values['code'] == 13
    assert send(moon, 'MoonNPCFavorabilityReward', 13, moonNPCId=2250, rewardIndex=0).values['code'] == 10
    assert send(moon, 'MoonNPCFavorabilityReward', 14, moonNPCId=2250, rewardIndex=0).values['code'] == 13


def test_equipment_official_upgrade_costs_and_slot_ownership(moon):
    complete(moon)
    put(moon, 1120001, 3600)
    for seq, (level, remain) in enumerate([(2, 3000), (3, 1800), (4, 0)], 20):
        result = send(moon, 'MoonEquipUpLevel', seq, moonEquipId=111001)
        assert result.values['code'] == 10
        assert S['MoonEquipData'].decode(result.values['moonEquip'])['moonEquipLevel'] == level
        assert moon[3].quantity(1, 1120001) == remain
        assert send(moon, 'MoonEquipUpLevel', seq, moonEquipId=111001).values == result.values
    assert send(moon, 'MoonEquipUpLevel', 25, moonEquipId=111001).values['code'] == 13
    assert send(moon, 'MoonEquipUpLevel', 26, moonEquipId=111002).values['code'] == 13
    assert send(moon, 'MoonEquipPutOnOrOff', 27, operate=1, moonEquipId=111001, slotIndex=0).values['code'] == 10
    assert send(moon, 'MoonEquipPutOnOrOff', 28, operate=2, moonEquipId=111001, slotIndex=0).values['moonEquipId'] == 0
    put(moon, 1110005, 1)
    assert send(moon, 'MoonEquipPutOnOrOff', 29, operate=1, moonEquipId=111005, slotIndex=1).values['code'] == 13
    put(moon, 1120007, 2)
    assert send(moon, 'MoonEquipPutOnOrOff', 30, operate=1, moonEquipId=111005, slotIndex=1).values['code'] == 10


def test_prestige_exact_threshold_claim_and_no_repeat_grant(moon):
    complete(moon)
    put(moon, 1120003, 599)
    assert send(moon, 'MoonCampPrestigeReward', 40, moonCampId=700001, rewardIndex=1).values['code'] == 13
    put(moon, 1120003, 600)
    result = send(moon, 'MoonCampPrestigeReward', 41, moonCampId=700001, rewardIndex=1)
    assert result.values['code'] == 10
    assert moon[3].quantity(1, 1120013) == 1
    assert moon[3].daily_limit(1, 'MoonFlowerGetLimit') == 7
    assert send(moon, 'MoonCampPrestigeReward', 41, moonCampId=700001, rewardIndex=1).values == result.values
    assert moon[3].quantity(1, 1120013) == 1
    assert send(moon, 'MoonCampPrestigeReward', 42, moonCampId=700001, rewardIndex=1).values['code'] == 13


def test_repeat_accept_sync_claim_and_day_rollover(moon):
    complete(moon)
    offers = send(moon, 'MoonAcceptableRepeatTask', 50).values
    assert len(offers['repeatTaskData']) == 3
    offered = S['TaskData'].decode(offers['repeatTaskData'][0])
    mid = offered['taskId']
    group = S['MoonMissionGroup'].encode({'missionGroupId': mid})
    assert send(moon, 'MoonMissionGroupAcceptedSync', 51, moonMissionGroup=group).values['code'] == 10
    assert complete(moon, mid, 52).values['code'] == 10
    claim = moon[3].claim_task(1, mid, 18)
    assert claim['code'] == 10 and reward_items(claim['rewardData'])
    assert REWARD.decode(claim['rewardData']).get('rewardEquip')
    assert moon[3].claim_task(1, mid, 18)['code'] == 13
    assert moon[3].load(1)['accepted'] == 1
    moon[1].value += 86400
    state = moon[3].load(1)
    assert state['accepted'] == 0
    assert str(mid) not in state['tasks']
    assert state['tasks']['5010001']['status'] == 4


def test_refresh_daily_limit_and_forged_mission(moon):
    complete(moon)
    for seq in range(60, 65):
        assert send(moon, 'MoonAcceptableRepeatTask', seq, opt=2).values['code'] == 10
    assert send(moon, 'MoonAcceptableRepeatTask', 65, opt=2).values['code'] == 13
    bad = S['MoonMissionGroup'].encode({'missionGroupId': 5022025})
    assert send(moon, 'MoonMissionGroupAcceptedSync', 67, moonMissionGroup=bad).values['code'] == 13


def test_moon_battle_entry_settlement_daily_caps_and_replay(moon):
    store, _, economy, service, ctx = moon
    player = store.get(1)
    store.save_snapshot(1, dict(player['snapshot'], mobility={'power': 100},
        heroes=[{'id': 1003, 'state': 2, 'level': 1, 'star': 1}]), player['revision'])
    battle = BattleService(store, economy)
    values = request()
    values.update(missionId=2111001, chapter=2011000, sceneId=2211001)
    enter = asyncio.run(battle.enter(ctx, packet(values, 80)))
    assert enter.values['result'] == 10
    assert store.get(1)['snapshot']['mobility']['power'] == 100
    data = {'chapterId': 2011000, 'sectionId': 2111001, 'success': True, 'fightTime': 60,
        'outsideItems': [OUTSIDE_ITEM.encode({'id': i, 'num': n}) for i, n in [(1120001, 500), (1120002, 20)]]}
    pkt = packet({'checkout': CHECKOUT.encode(data)}, 81, 'C2L_CheckoutMainMissionSign')
    result = asyncio.run(battle.checkout(ctx, pkt))
    assert result.values['result'] == 10
    assert service.quantity(1, 1120001) == 300
    assert service.quantity(1, 1120002) == 6
    assert asyncio.run(battle.checkout(ctx, pkt)).values == result.values
    assert service.quantity(1, 1120001) == 300


@pytest.mark.parametrize('kind', [16, 17, 18, 19])
def test_generic_task_query_is_delegated(moon, kind):
    response = asyncio.run(moon[2].handle(moon[4], packet({'type': kind}, 100, 'C2L_GameTask')))
    CORE_SCHEMAS[response.message_name].encode(response.values)
    assert response.values['code'] == 10 and response.values['type'] == kind


def test_state_survives_new_service_instance_and_is_account_owned(moon):
    complete(moon)
    from x2server.player.moon import MoonService
    restored = MoonService(moon[2])
    assert restored.load(1)['tasks']['5010001']['status'] == 4
    moon[0].login('other-moon-account', 2, 0)
    assert restored.load(2)['tasks']['5010001']['status'] == 2


def test_original_query_operation_does_not_spend_refresh(moon):
    complete(moon)
    first = send(moon, 'MoonAcceptableRepeatTask', 200, opt=1)
    again = send(moon, 'MoonAcceptableRepeatTask', 201, opt=1)
    assert first.values == again.values
    assert moon[3].load(1)['refreshed'] == 0
    send(moon, 'MoonAcceptableRepeatTask', 202, opt=2)
    assert moon[3].load(1)['refreshed'] == 1


def test_midnight_preserves_progress_equipment_and_resets_quota(moon):
    complete(moon)
    with moon[2].transaction():
        state = moon[3].load(1)
        state.update(flowers=6, chips=300, given=20, accepted=4, refreshed=5)
        moon[3].save(1, state)
    moon[1].value += 86400
    pushes = moon[3].expire_day(1)
    assert len(pushes) == 2
    assert moon[3].expire_day(1) == ()
    assert moon[3].load(1)['flowers'] == moon[3].load(1)['accepted'] == 0
    assert moon[3].quantity(1, 1110001) == 1
    assert moon[3].camp_open(moon[3].load(1), 700001)


def test_moon_equipment_team_caster_uses_original_skill_variant(moon):
    from x2server.messages.battle import FIGHT_GROUP_SKILL
    complete(moon)
    assert moon[3].battle_skill(1) == b''
    send(moon, 'MoonEquipPutOnOrOff', 210, operate=1, moonEquipId=111001, slotIndex=0)
    skill = FIGHT_GROUP_SKILL.decode(moon[3].battle_skill(1))
    assert skill['activeSkillId'] == 99141 and skill['activeSkillLevel'] == 1
    put(moon, 1120007, 1)
    put(moon, 1110005, 1)
    send(moon, 'MoonEquipPutOnOrOff', 211, operate=1, moonEquipId=111005, slotIndex=0)
    skill = FIGHT_GROUP_SKILL.decode(moon[3].battle_skill(1))
    assert skill['activeSkillId'] == 99142 and skill['unitId'] == 9914


def test_moon_state_in_save_export_and_import(moon, tmp_path):
    from x2server.player.save_manager import SaveManager
    complete(moon)
    manager = SaveManager(moon[0], backup_root=tmp_path / 'moon-backups')
    try:
        archive = manager.export_save(1)
        parsed = manager.parse_save(archive)
        assert any('moon' in str(row) for row in parsed.rows['activity_state'])
        with moon[2].transaction():
            moon[0].db.execute("DELETE FROM activity_state WHERE player_id=1 AND namespace='moon'")
        manager.import_save(1, archive)
        assert moon[3].load(1)['tasks']['5010001']['status'] == 4
        assert moon[3].quantity(1, 1110001) == 1
    finally:
        manager.close()


def test_every_mission_reward_can_be_delivered(moon):
    service = moon[3]
    with moon[2].transaction():
        state = service.load(1)
        for mid, row in service.missions.items():
            state['tasks'][str(mid)] = service.task(row, 3, difficulty=9)
            reward = service.finish(1, state, mid)
            assert REWARD.decode(reward) is not None
        service.save(1, state)


def test_repeat_reward_through_generic_claim_pushes_equipment(moon):
    complete(moon)
    offered = S['TaskData'].decode(send(moon, 'MoonAcceptableRepeatTask', 220, opt=1).values['repeatTaskData'][0])
    mid = offered['taskId']
    group = S['MoonMissionGroup'].encode({'missionGroupId': mid})
    send(moon, 'MoonMissionGroupAcceptedSync', 221, moonMissionGroup=group)
    complete(moon, mid, 222)
    result = asyncio.run(moon[2].handle(moon[4], packet({'data': [FINISH_REQUEST.encode({'taskId': mid, 'type': 18})]}, 223, 'C2L_FinishGameTask')))
    row = FINISH_RESULT.decode(result.values['data'][0])
    assert row['code'] == 10
    assert result.before_response[0].message_name == 'L2C_EquipUpdate'
    for message in (*result.before_response, result, *result.pushes):
        CORE_SCHEMAS[message.message_name].encode(message.values)


@pytest.mark.parametrize('mid', [5010001, 5010002, 5010003, 5010004, 5010005])
def test_story_children_resume_without_replaying_completed_dialogue(moon, mid):
    """Native children 2=active, 3=done; reconnect must preserve each step."""
    from x2server.player.moon import MoonService
    service = moon[3]
    seq = 1000
    children = service.missions[mid]['QuestID']
    for index, qid in enumerate(children):
        group = S['MoonMissionGroup'].encode({'missionGroupId': mid,
            'moonChildrenMission': [S['ChildrenMission'].encode({
                'childrenMissionId': qid, 'childrenMissionStatus': 3})]})
        assert send(moon, 'MoonMissionGroupSync', seq, moonMissionGroup=[group]).values['code'] == 10
        # A fresh session/service reads committed progress, not cached defaults.
        restored = MoonService(moon[2])
        task = restored.load(1)['tasks'][str(mid)]
        assert [task['children'][str(i)] for i in children] == [
            3 if n <= index else 2 for n, i in enumerate(children)]
        assert task['status'] == (4 if index == len(children)-1 else 2)
        seq += 1
    before = list(moon[0].db.execute('SELECT item_id,quantity FROM inventory WHERE player_id=1 ORDER BY item_id'))
    # A delayed new request after the completion receipt must be idempotent too.
    reply = send(moon, 'MoonMissionGroupAcceptedSync', seq,
                 moonMissionGroup=S['MoonMissionGroup'].encode({'missionGroupId': mid}))
    assert reply.values['code'] == 10
    saved = S['MoonMissionGroup'].decode(reply.values['moonMissionGroup'])
    assert all(S['ChildrenMission'].decode(raw)['childrenMissionStatus'] == 3
               for raw in saved['moonChildrenMission'])
    moon[1].value += 86400
    rows = service.task_values(1, 19)['taskList']
    wire = next(S['TaskData'].decode(raw) for raw in rows
                if S['TaskData'].decode(raw)['taskId'] == mid)
    assert wire['taskStatus'] == 4
    assert list(moon[0].db.execute('SELECT item_id,quantity FROM inventory WHERE player_id=1 ORDER BY item_id')) == before


def test_finished_commission_cannot_be_reaccepted_to_bypass_daily_limit(moon):
    complete(moon)
    offer = S['TaskData'].decode(send(moon, 'MoonAcceptableRepeatTask', 1100, opt=1).values['repeatTaskData'][0])
    mid = offer['taskId']
    group = S['MoonMissionGroup'].encode({'missionGroupId': mid})
    assert send(moon, 'MoonMissionGroupAcceptedSync', 1101, moonMissionGroup=group).values['code'] == 10
    assert complete(moon, mid, 1102).values['code'] == 10
    assert moon[3].claim_task(1, mid, 18)['code'] == 10
    assert send(moon, 'MoonMissionGroupAcceptedSync', 1103, moonMissionGroup=group).values['code'] == 13
    assert moon[3].load(1)['accepted'] == 1
