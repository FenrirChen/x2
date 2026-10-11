import pytest

from tests.unit.test_economy import env
from x2server.messages.equipment import HERO_EQUIP
from x2server.messages.economy import REWARD


@pytest.mark.parametrize('level,star', [(10, 4), (15, 4), (25, 5), (30, 5), (40, 6), (45, 6)])
def test_course_quality_instances_push_and_no_duplicate(env, level, star):
    store, economy, _ = env
    service = economy.extra_activity
    response = service.recive_star_privilege(1, [level])
    assert response.values['code'] == 10
    equip = HERO_EQUIP.decode(REWARD.decode(response.values['rewardData'])['rewardEquip'][0])
    assert equip['star'] == star
    push = next(p for p in response.pushes if p.message_name == 'L2C_EquipUpdate')
    assert HERO_EQUIP.decode(push.values['equip'][0]) == equip
    row = store.db.execute('SELECT id,star FROM equipment_instances WHERE player_id=1').fetchone()
    assert tuple(row) == (equip['id'], star)
    assert service.recive_star_privilege(1, [level]).values['code'] == 13
    assert store.db.execute('SELECT count(*) FROM equipment_instances WHERE player_id=1').fetchone()[0] == 1
    # Simulate the old course grant without changing its provenance/identity.
    with store.db:
        store.db.execute('UPDATE equipment_instances SET star=1,locked=1 WHERE id=?', (equip['id'],))
    assert service.repair_course_equipment(1) == [equip['id']]
    repaired = store.db.execute('SELECT id,star,locked FROM equipment_instances WHERE id=?', (equip['id'],)).fetchone()
    assert tuple(repaired) == (equip['id'], star, 1)
    assert service.repair_course_equipment(1) == []


def test_simple_activity_native_enum_preserves_existing_claims(env):
    store, economy, _ = env
    service = economy.extra_activity
    unlocked = service.simple_activity_opt(1, {'opt': 1, 'param': 0})
    assert unlocked.values['code'] == 10
    assert unlocked.values['unlockInfo'] == [0]
    main = service.simple_activity_opt(1, {'opt': 2, 'param': 0})
    assert main.values['code'] == 10
    assert main.values['mainRewards'] == [0]
    assert main.values['extraRewards'] == [-1]
    assert store.db.execute('SELECT track FROM simple_activity_claims WHERE player_id=1').fetchone()[0] == 1
    assert service.simple_activity_opt(1, {'opt': 2, 'param': 0}).values['code'] == 13
    extra = service.simple_activity_opt(1, {'opt': 3, 'param': 0})
    assert extra.values['code'] == 10
    assert extra.values['extraRewards'] == [0]
