from tests.activity_calendar_helpers import activity_start, next_activity_cycle
"""Exercise message ownership independently of protobuf encodability."""
import asyncio
import pytest

from tests.unit.test_activity_runtime import runtime, env
from tests.unit.test_battle import packet
from x2server.messages.activity import ACTIVITY_SCHEMAS
from x2server.messages.lobby import LOBBY_SCHEMAS
from x2server.messages.battle import PROFILE_HERO, CHECKOUT
from x2server.network.dispatcher import OutboundMessage
from x2server.player.activity_protocol import ALL_ROUTES, ID_KINDS, check_request, check_progress
from x2server.player.activity_rotation import ActivityRotation
from x2server.player.battle import BattleService
from x2server.player.economy import UnresolvedEconomy


def test_every_registered_route_has_an_explicit_contract(runtime):
    rt = runtime[3]
    assert {name[4:] for name in rt.handlers()} == ALL_ROUTES


@pytest.mark.parametrize('theme', range(7))
def test_every_route_in_every_theme_returns_a_valid_owned_response(runtime, theme):
    _, _, ctx, rt, now = runtime
    now[0] = activity_start(theme) + 3600
    period = rt.r.at()
    family = 2 if period.theme['group'] == 7 else 1 if period.theme['group'] == 99 else 3
    for rid, op in enumerate(sorted(ALL_ROUTES), 40000):
        request = {}
        if op in {'ActivityPreNotic', 'ActivityPreNoticInfo', 'ActivityShop'}:
            request['activityType'] = family
        if op in ID_KINDS:
            owner = next((a for a in period.theme['activities']
                          if a['ActivityType']['value'] in ID_KINDS[op]), None)
            request['activityId'] = owner['ActivityID'] if owner else -1
        try:
            check_request(rt, 1, op, request)
            allowed = True
        except UnresolvedEconomy:
            allowed = False
        reply = asyncio.run(rt.handle(ctx, packet(request, rid, 'C2L_' + op)))
        assert reply.message_name == 'L2C_' + op
        schema = ACTIVITY_SCHEMAS.get(reply.message_name) or LOBBY_SCHEMAS[reply.message_name]
        schema.decode(schema.encode(reply.values))
        if not allowed and 'code' in reply.values:
            assert reply.values['code'] == 13, (theme, op)
            assert not reply.before_response and not reply.pushes
    for message in rt.progress_messages(1):
        check_progress(rt, period, message)


@pytest.mark.parametrize('op', sorted(ID_KINDS))
def test_foreign_activity_id_is_rejected_before_operation(runtime, op):
    _, _, ctx, rt, _ = runtime
    response = asyncio.run(rt.handle(ctx, packet({'activityId': -12345}, 41000, 'C2L_' + op)))
    assert response.values['code'] == 13
    assert not response.before_response and not response.pushes


def test_query_replay_rechecks_theme_and_reads_next_occurrence(runtime):
    _, _, ctx, rt, now = runtime
    query = packet({'activityId': 72046}, 42000, 'C2L_LanternShowQueryData')
    assert asyncio.run(rt.handle(ctx, query)).values['code'] == 10
    now[0] = rt.r.at().end
    assert asyncio.run(rt.handle(ctx, query)).values['code'] == 13
    now[0] += 6 * ActivityRotation.SECONDS
    assert rt.r.at().theme['group'] == 37
    # A query describes the current occurrence; old query receipts must not
    # block it when its owning theme comes back. Foreign themes still reject.
    assert asyncio.run(rt.handle(ctx, query)).values['code'] == 10
    fresh = packet({'activityId': 72046}, 42001, 'C2L_LanternShowQueryData')
    assert asyncio.run(rt.handle(ctx, fresh)).values['code'] == 10


def test_all_routes_reply_when_no_theme_is_open(runtime):
    _, _, ctx, rt, now = runtime
    now[0] = ActivityRotation.ANCHOR - 1
    for rid, op in enumerate(sorted(ALL_ROUTES), 42500):
        reply = asyncio.run(rt.handle(ctx, packet({}, rid, 'C2L_' + op)))
        assert reply.message_name == 'L2C_' + op
        schema = ACTIVITY_SCHEMAS.get(reply.message_name) or LOBBY_SCHEMAS[reply.message_name]
        schema.encode(reply.values)
        if op not in {'QueryActivity', 'EntryidStatus', 'ExtraDropData'}:
            assert reply.values['code'] == 13
        assert not reply.before_response and not reply.pushes


def test_wrong_push_receiver_and_wrong_activity_owner_are_rejected(runtime):
    rt = runtime[3]
    period = rt.r.at()
    for name, data in [('L2C_QueryActivityMissionRecord', rt.records(1, period)),
                       ('L2C_QueryShuangHanActivity', {'code': 10}),
                       ('L2C_ActivityMissionData', {'code': 10, 'activityId': 70010}),
                       ('L2C_CafeStoreCooking', {'code': 10})]:
        with pytest.raises(UnresolvedEconomy):
            check_progress(rt, period, OutboundMessage(name, data))


def battle_entry(runtime):
    store, e, ctx, rt, _ = runtime
    e.activity = rt.a
    battle = BattleService(store, e)
    sid = rt.r.at().theme['section_ids'][0]
    row = battle.catalog.sections[sid]
    entry = packet({'missionId': sid, 'chapter': row['ChapterID'], 'sceneId': row['Maps'][0],
                    'heros': [PROFILE_HERO.encode({'heroId': 1003, 'leader': 1})]})
    assert asyncio.run(battle.enter(ctx, entry)).values['result'] == 10
    checkout = packet({'checkout': CHECKOUT.encode({'sectionId': sid, 'chapterId': row['ChapterID'],
                       'success': True, 'fightTime': 200})}, 43000, 'C2L_CheckoutMainMissionSign')
    return battle, checkout, sid


def test_optional_progress_failure_cannot_abort_successful_checkout(runtime, monkeypatch, caplog):
    battle, request, sid = battle_entry(runtime)
    def broken_progress(player):
        raise IndexError('injected progress contract failure')
    monkeypatch.setattr(runtime[3], 'progress_messages', broken_progress)
    reply = asyncio.run(battle.checkout(runtime[2], request))
    assert reply.values['result'] == 10
    assert 'checkout progress unavailable' in caplog.text
    assert runtime[3].r.get(1, runtime[3].r.at(), 'clear', sid) == 1


def test_boundary_checkout_does_not_push_next_themes_progress(runtime):
    rt, now = runtime[3:]
    now[0] = ActivityRotation.FIRST_END - 10
    old_period = rt.r.at()
    battle, request, sid = battle_entry(runtime)
    now[0] += 20
    reply = asyncio.run(battle.checkout(runtime[2], request))
    assert reply.values['result'] == 10
    assert not any(message.message_name in ACTIVITY_SCHEMAS for message in reply.before_response)
    assert rt.r.get(1, old_period, 'clear', sid) == 1
