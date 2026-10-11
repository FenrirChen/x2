import asyncio
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from tests.unit.test_battle import packet
from x2server.network.dispatcher import DispatchContext
from x2server.network.session import SessionState
from x2server.player.accounts import AccountStore
from x2server.player.economy import EconomyService
from x2server.player.mail import MailService
from x2server.player.store import PlayerStore
from x2server.player.system_mail import (ULTIMATE_CAUSALITY_CARD, deliver_ultimate_causality,
    deliver_revival_supply, BRILLIANCE, WISH_COIN)


@pytest.mark.parametrize('deliver,ensure,prefix,rewards', [
    (deliver_ultimate_causality, 'ensure_ultimate_causality_mail', 'ultimate_causality_', {ULTIMATE_CAUSALITY_CARD: 50}),
    (deliver_revival_supply, 'ensure_revival_supply_mail', 'revival_supply_',
     {ULTIMATE_CAUSALITY_CARD: 200, BRILLIANCE: 7200, WISH_COIN: 140}),
])
def test_old_offline_and_new_accounts_claim_use_delete_restart(tmp_path, deliver, ensure, prefix, rewards):
    path = tmp_path / 'causality.db'
    store = PlayerStore(path)
    store.login('legacy', 1, 100)
    accounts = AccountStore(store)
    assert deliver(store, 200) == (1, [])
    assert accounts.create('new', 'pw', 201) == 'created'
    new_id = accounts.get_by_name('new')['player_id']
    assert not getattr(accounts, ensure)(new_id, 202)
    assert deliver(store, 203) == (0, [])
    economy = EconomyService(store)
    mail = MailService(store, economy)
    for player_id in (1, new_id):
        player = store.get(player_id)
        store.save_snapshot(player_id, dict(player['snapshot'], level=60,
            mobility={'power': 150, 'recover_anchor': int(economy.clock())}), player['revision'])
        row = store.db.execute("SELECT * FROM player_mail WHERE player_id=? AND source_key LIKE ?", (player_id, prefix + '%')).fetchone()
        assert json.loads(row['attachments']) == {str(k): v for k, v in rewards.items()}
        crystal_before = store.get(player_id)['snapshot']['crystal']
        ctx = DispatchContext('test', 'local', SessionState('test', 'session', player_id=player_id))
        req = packet({'mailid': row['id']}, name='C2L_ReceiveAttachment')
        assert asyncio.run(mail.handle(ctx, req)).values['code'] == 10
        assert asyncio.run(mail.handle(ctx, req)).values['code'] == 13
        assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=? AND item_id=?', (player_id, ULTIMATE_CAUSALITY_CARD)).fetchone()[0] == rewards[ULTIMATE_CAUSALITY_CARD]
        assert store.get(player_id)['snapshot']['crystal'] == crystal_before + rewards.get(BRILLIANCE, 0)
        if WISH_COIN in rewards:
            assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=? AND item_id=?', (player_id, WISH_COIN)).fetchone()[0] == 140
        economy.refresh_stamina(player_id)
        power = store.get(player_id)['snapshot']['mobility']['power']
        use = packet({'opt': 0, 'id': ULTIMATE_CAUSALITY_CARD, 'count': 1}, request_id=2, name='C2L_ItemOpt')
        response = economy.use_causality_card(ctx, use, {'opt': 0, 'id': ULTIMATE_CAUSALITY_CARD, 'count': 1})
        assert response.values['code'] == 10
        assert store.get(player_id)['snapshot']['mobility']['power'] == power + 100
        assert economy.use_causality_card(ctx, use, {'opt': 0, 'id': ULTIMATE_CAUSALITY_CARD, 'count': 1}).values == response.values
        assert store.db.execute('SELECT quantity FROM inventory WHERE player_id=? AND item_id=?', (player_id, ULTIMATE_CAUSALITY_CARD)).fetchone()[0] == rewards[ULTIMATE_CAUSALITY_CARD] - 1
        with store.db:
            store.db.execute('UPDATE player_mail SET deleted=1 WHERE id=?', (row['id'],))
    assert deliver(store, 204) == (0, [])
    accounts.close()
    store.close()
    reopened = PlayerStore(path)
    assert deliver(reopened, 300) == (0, [])
    reopened.close()


@pytest.mark.parametrize('ensure,prefix', [
    ('ensure_ultimate_causality_mail', 'ultimate_causality_'),
    ('ensure_revival_supply_mail', 'revival_supply_'),
])
def test_causality_concurrent_lazy_backfill_and_registration_rollback(tmp_path, ensure, prefix):
    store = PlayerStore(tmp_path / 'causality.db')
    accounts = AccountStore(store)
    assert accounts.create('new', 'pw', 100) == 'created'
    player_id = accounts.get_by_name('new')['player_id']
    with accounts.db:
        accounts.db.execute("DELETE FROM player_mail WHERE source_key LIKE ?", (prefix + '%',))
        accounts.db.execute('DELETE FROM system_mail_issues WHERE kind=?',
                            ('ultimate_causality' if prefix == 'ultimate_causality_' else 'revival_supply',))
    other = AccountStore(store)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda a: getattr(a, ensure)(player_id, 200), (accounts, other)))
    assert sorted(results) == [False, True]
    with accounts.db:
        accounts.db.execute(f"""CREATE TRIGGER fail_causality BEFORE INSERT ON player_mail
            WHEN NEW.source_key LIKE '{prefix}%'
            BEGIN SELECT RAISE(ABORT, 'gift mail failed'); END""")
    with pytest.raises(sqlite3.IntegrityError):
        accounts.create('failed', 'pw', 300)
    assert accounts.get_by_name('failed') is None
    assert not store.db.execute("SELECT 1 FROM players WHERE account='failed'").fetchone()
    other.close()
    accounts.close()
    store.close()
