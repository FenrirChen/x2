import asyncio
import pytest
from tests.unit.test_college_upgrade import game
from tests.unit.test_battle import packet


def request(game,rid=91):
    return asyncio.run(game[3].dispatch(game[4],packet({'power':3},rid,'C2L_ExchangePower')))


def seed(game):
    snap=game[0].get(1)['snapshot']
    snap['mobility']={'power':100,'recover_anchor':game[1].now()}
    game[3].economy.save_snapshot(1,snap)
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



def test_zero_energy_full_tower_withdrawal_and_replay(game):
    seed(game)
    state=game[2].load(1)
    state.update(extra_power=150000,star_energy=0)
    game[2].save(1,state)
    before=game[0].get(1)['snapshot']['mobility']['power']
    pkt=packet({'power':150},92,'C2L_ExchangePower')
    reply=asyncio.run(game[3].dispatch(game[4],pkt))
    assert reply.values=={'code':10,'power':150,'extraPower':0}
    assert game[2].load(1)['star_energy']==0
    assert game[0].get(1)['snapshot']['mobility']['power']==before+150
    assert asyncio.run(game[3].dispatch(game[4],pkt)).values==reply.values
    assert game[0].get(1)['snapshot']['mobility']['power']==before+150


def test_receive_ceiling_keeps_tower_and_allows_exact_boundary(game):
    seed(game)
    cap=game[3].economy.items[1237900]['ItemValue']
    snap=game[0].get(1)['snapshot']
    snap['mobility']['power']=cap-2
    game[3].economy.save_snapshot(1,snap)
    before=game[2].load(1)
    assert request(game,93).values['code']==13
    after=game[2].load(1)
    assert (after['extra_power'],after['star_energy'])==(before['extra_power'],before['star_energy'])
    assert game[0].get(1)['snapshot']['mobility']['power']==cap-2
    reply=asyncio.run(game[3].dispatch(game[4],packet({'power':2},94,'C2L_ExchangePower')))
    assert reply.values['code']==10
    assert game[2].load(1)['extra_power']==3000
    assert game[2].load(1)['star_energy']==100
    assert game[0].get(1)['snapshot']['mobility']['power']==cap


@pytest.mark.parametrize('amount',[0,-1,6])
def test_invalid_or_insufficient_tower_cannot_grant(game,amount):
    seed(game)
    before=game[2].load(1)
    balance=game[0].get(1)['snapshot']['mobility']['power']
    reply=asyncio.run(game[3].dispatch(game[4],packet({'power':amount},95,'C2L_ExchangePower')))
    assert reply.values['code']==(22 if amount==6 else 13)
    after=game[2].load(1)
    assert (after['extra_power'],after['star_energy'])==(before['extra_power'],before['star_energy'])
    assert game[0].get(1)['snapshot']['mobility']['power']==balance
