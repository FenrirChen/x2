"""Activity route ownership and unsolicited push contracts.

An encodable protobuf is not necessarily safe for the receiving module. Keep
ownership explicit here, including unsupported routes, so new routes/pushes
cannot silently inherit a different activity's semantics.
"""
from x2server.messages.activity import ACTIVITY_SCHEMAS
from x2server.messages.lobby import LOBBY_SCHEMAS
from .economy import UnresolvedEconomy
from .activity import enum

GLOBAL_ROUTES = {'QueryActivity', 'EntryidStatus'}
SHARED_ROUTES = {'SceneGlobalParam', 'ActivityPassRecord', 'ExtraDropData',
                 'AccountBuffData', 'AccountBuffAutoStop', 'ActivityReissueState'}
UNSUPPORTED_ROUTES = {'ActivityBuilding', 'ActivityBuildingUpgrade',
                      'ActivityTowerLevelUp', 'ActivityReissue'}
REQUIRED_KINDS = {
    'QueryActivityTower': {50}, 'ActivityTowerPassive': {50},
    'QueryShuangHanActivity': {13}, 'PlayShuangHanPV': {13},
    'ActivityPreNotic': {1, 15, 24}, 'ActivityPreNoticInfo': {1, 15, 24},
    'ActivityShop': {3, 14, 43},
    'QueryActivityMissionRecord': {2}, 'ActivityMissionRecordSave': {2, 29},
    'ActivityDialogReciveInfo': {1, 27}, 'ActivityDialogue': {1},
}
ID_KINDS = {
    'ActivityMissionData': {2, 25, 28, 29, 50}, 'ActivityMissionSelBranch': {2, 25},
    'ActivityRewardPoolInfo': {26}, 'ActivityRewardPoolDraw': {26},
    'QueryFoodMissionReward': {29}, 'ReceiveFoodMissionReward': {29},
    **{op: {30} for op in ('LanternShowQueryData', 'LanternShowQuestion',
                          'LanternShowAnswerQuestion', 'LanternShowRecBox')},
    'LanternShowPaper': {31},
}
CAFE_ROUTES = {'CafeStoreInfo', 'CafeStoreUnLock', 'CafeStorePositionSet',
               'CafeStoreCooking', 'CafeStoreLevelUp', 'CafeStoreReceiveRevenue',
               'CafeStoreUpdate'}
REQUIRED_KINDS.update({op: {27} for op in CAFE_ROUTES})
ALL_ROUTES = GLOBAL_ROUTES | SHARED_ROUTES | UNSUPPORTED_ROUTES | REQUIRED_KINDS.keys() | ID_KINDS.keys()


def check_request(runtime, player, op, request):
    if op not in ALL_ROUTES or op in UNSUPPORTED_ROUTES:
        raise UnresolvedEconomy('activity operation has no implemented contract')
    if op in GLOBAL_ROUTES or (op == 'SceneGlobalParam' and runtime.e.season.active(player)):
        return
    period = runtime.a.period(player)
    kinds = {enum(row['ActivityType']) for row in period.theme['activities']}
    required = REQUIRED_KINDS.get(op)
    if required and not kinds & required:
        raise UnresolvedEconomy('activity operation belongs to another theme')
    if op == 'QueryActivityMissionRecord' and period.theme['group'] != 99:
        raise UnresolvedEconomy('YueXi mission records belong to group 99')
    if op in ID_KINDS:
        row = runtime.r.activity(request.get('activityId', 0), period)
        if row is None or enum(row['ActivityType']) not in ID_KINDS[op]:
            raise UnresolvedEconomy('activity ID does not own this operation')


def check_progress(runtime, period, message):
    name, values = message.message_name, message.values
    if name in {'L2C_SceneGlobalParam', 'L2C_ActivityPassRecord'}:
        pass
    elif name == 'L2C_QueryActivityMissionRecord':
        if period.theme['group'] != 99:
            raise UnresolvedEconomy('YueXi progress cannot be dispatched to another theme')
    elif name == 'L2C_QueryShuangHanActivity':
        if runtime.r.of_type(13, period) is None:
            raise UnresolvedEconomy('winter progress cannot be dispatched to another theme')
    elif name == 'L2C_ActivityMissionData':
        row = runtime.r.activity(values.get('activityId', 0), period)
        if row is None or enum(row['ActivityType']) not in ID_KINDS['ActivityMissionData']:
            raise UnresolvedEconomy('mission progress has no current activity owner')
    else:
        raise UnresolvedEconomy('unsolicited activity progress has no declared contract')
    schema = ACTIVITY_SCHEMAS.get(name) or LOBBY_SCHEMAS[name]
    schema.encode(values)
