import asyncio
from tests.unit.test_origin_season import env
from tests.unit.test_battle import packet, request
from x2server.player.battle import BattleService
from x2server.messages.battle import CHECKOUT
from x2server.messages.season import SEASON_SCHEMAS, encode


def test_all_origin_layers_unlock_past_ten_to_one_hundred(env):
    store, e, season = env
    from x2server.network.dispatcher import DispatchContext
    from x2server.network.session import SessionState
    ctx = DispatchContext('test','local',SessionState('test','season-hundred',player_id=1))
    with e.transaction():
        e._grant(1,'boundary-tickets',{1202901:110})
        snap = store.get(1)['snapshot']
        snap['mobility']['power'] = 9999
        e.save_snapshot(1,snap)
    battle = BattleService(store,e)
    configs = sorted(season.configs.values(),key=lambda r:r['Level'])
    assert [r['Level'] for r in configs] == list(range(1,101))
    for config in configs:
        level = config['Level']
        sid = config['SectionGroup'][0]
        section = season.sections[sid]
        values = request()
        values.update(missionId=sid,chapter=section['ChapterID'],sceneId=section['Maps'][0])
        if level == 1:
            later = configs[10]['SectionGroup'][0]
            from x2server.player.economy import UnresolvedEconomy
            import pytest
            with pytest.raises(UnresolvedEconomy):
                season.admission(1,later)
        entry = asyncio.run(battle.enter(ctx,packet(values,1000+level)))
        assert entry.values['result'] == 10,(level,entry.values)
        done = packet({'checkout':CHECKOUT.encode({'chapterId':section['ChapterID'],
            'sectionId':sid,'success':True,'fightTime':60})},2000+level,'C2L_CheckoutMainMissionSign')
        result = asyncio.run(battle.checkout(ctx,done))
        assert result.values['result'] == 10,(level,result.values)
        assert season.state(1)['max_layer'] == level
        update = next(m for m in result.before_response if m.message_name=='L2C_BattlePassMissionInfo')
        decoded = SEASON_SCHEMAS['L2C_BattlePassMissionInfo'].decode(encode('L2C_BattlePassMissionInfo',update.values))
        assert decoded['maxSeasonId'] == 2090000+min(level+1,100)
        assert decoded['maxPassId'] == config['ID']
        assert asyncio.run(battle.checkout(ctx,done)).values == result.values
        assert season.state(1)['stats']['passes'] == level
    assert season.mission_values(1)['maxSeasonId'] == 2090100
