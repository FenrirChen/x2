from x2server.player.trial_units import trial_hero, equipment, chapter7_equipment
from x2server.player.battle_bonuses import artifact_attributes
from x2server.messages.equipment import HERO_EQUIP,EQUIP_PARAM


def test_only_story_behemoth_flat_attack_gear_is_changed():
    hero=trial_hero(1303,1303)
    original,suits=equipment(hero)
    bonus=artifact_attributes(hero)
    boosted=chapter7_equipment(2110607,hero,original,bonus)
    before=HERO_EQUIP.decode(original[0]); after=HERO_EQUIP.decode(boosted[0])
    old=EQUIP_PARAM.decode(before.pop('param')); new=EQUIP_PARAM.decode(after.pop('param'))
    assert before == after
    assert old['av1'] == 478
    assert new['av1'] == 15661
    assert (826 + 234 + new['av1'] +149) == 10*(826+234+old['av1']+149)
    old.pop('av1'); new.pop('av1')
    assert new == old
    assert boosted[1:] == original[1:]
    assert equipment(hero) == (original,suits)
    for section in (2110707,2161190,2110606):
        assert chapter7_equipment(section,hero,original,bonus) == original
    assert chapter7_equipment(2110607,dict(hero,trial_unit=1304),original,bonus) == original
