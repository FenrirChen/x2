"""Completed one-time activity stages must still satisfy clear-class tasks.

Sakura G33's hidden side stories (2161011-2161016) have no AgainSwitch, so a
clear that was recorded while the task event was broken leaves the stage
unreachable and tasks 5000277-5000282 stuck at zero. repair_tasks has to replay
the durable clear ledger instead of waiting for another checkout.
"""
import pytest

from tests.unit.test_economy import env
from x2server.messages.economy import TASK
from x2server.player.activity import ActivityService
from x2server.player.activity_rotation import ActivityRotation


@pytest.fixture
def activity(env):
    store, economy, _ctx = env
    now = [ActivityRotation.ANCHOR]
    economy.clock = lambda: now[0]
    return store, economy, ActivityService(economy), now


def test_repair_credits_clear_class_hidden_tasks_from_clear_ledger(activity):
    _, economy, service, now = activity
    now[0] = service.rotation.bounds(1)[0]
    period = service.period(1)
    task = service.tasks[5000277]
    condition = service.conditions[task['TaskConditionID']]
    assert condition['CompleteType']['value'] == 3
    assert condition['CompleteValue1'] == [2161011]
    with economy.transaction():
        service.rotation.put(1, period, 'clear', 2161011, 1)
        service.rotation.once(1, period, 'task-repair-v1')
    state = next(r for r in map(TASK.decode, service.task_values(1, 9)['taskList'])
                 if r['taskId'] == 5000277)
    assert state['taskProgress'] == 1 and state['taskStatus'] == 3
    assert service.claim_task(1, 5000277, 9, 72035)['code'] == 10


def test_clear_repair_preserves_claim_and_does_not_leak_into_next_period(activity):
    _, economy, service, now=activity
    now[0]=service.rotation.bounds(1)[0]
    period=service.period(1)
    with economy.transaction():
        service.rotation.put(1,period,'clear',2161011,1)
        service.rotation.put(1,period,'tasks',5000277,{'progress':1,'claimed':True})
        # A previous deployment already ran the older repair.
        service.rotation.once(1,period,'task-repair-v1')
    service.repair_tasks(1,period)
    assert service.rotation.get(1,period,'tasks',5000277)['claimed']
    assert service.claim_task(1,5000277,9,72035)['code']==13
    now[0]=service.rotation.bounds(8)[0]
    next_period=service.period(1)
    service.repair_tasks(1,next_period)
    assert service.rotation.get(1,next_period,'tasks',5000277,{}).get('progress',0)==0


def test_clear_counts_do_not_prove_additional_conditions(activity,monkeypatch):
    _,economy,service,now=activity
    now[0]=service.rotation.bounds(1)[0]
    period=service.period(1)
    cid=service.tasks[5000277]['TaskConditionID']
    monkeypatch.setitem(service.conditions,cid,dict(service.conditions[cid],CompleteValue2=[2]))
    with economy.transaction():
        service.rotation.put(1,period,'clear',2161011,1)
    service.repair_tasks(1,period)
    assert service.rotation.get(1,period,'tasks',5000277,{}).get('progress',0)==0
