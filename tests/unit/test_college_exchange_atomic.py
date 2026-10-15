import asyncio
import pytest
from tests.unit.test_college_upgrade import game
from tests.unit.test_battle import packet


def request(game,rid=91):
    return asyncio.run(game[3].dispatch(game[4],packet({'power':3},rid,'C2L_ExchangePower')))


def seed(game):
    state=game[2].load(1)
    state.update(extra_power=5000,star_energy=100)
    game[2].save(1,state)


def test_exchange_replay_and_authoritative_sync(game):
    seed(game)
    before=game[0].get(1)['snapshot'].get('mobility',{}).get('power',0)
    result=request(game)
    assert result.values=={'code':10,'power':3,'extraPower':2000}
    assert game[0].get(1)['snapshot'].get('mobility',{}).get('power',0)==before+3
    assert request(game).values==result.values
    assert game[0].get(1)['snapshot'].get('mobility',{}).get('power',0)==before+3
    assert game[2].load(1)['star_energy']==100
    assert [m.message_name for m in result.pushes]==['PlayerDataProto','L2C_QueryGrowthBase']


def test_snapshot_failure_rolls_back_tower_and_receipt(game,monkeypatch):
    seed(game)
    before=game[2].load(1)
    def fail(*args):
        raise RuntimeError('disk failure')
    monkeypatch.setattr(game[3].economy,'save_snapshot',fail)
    with pytest.raises(RuntimeError):
        request(game)
    assert game[2].load(1)==before
    assert not game[0].db.execute("SELECT 1 FROM college_upgrade_receipts WHERE receipt_key LIKE '%ExchangePower'").fetchone()

