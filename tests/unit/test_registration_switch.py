import json
from urllib.parse import urlencode

import pytest

from tests.integration.test_local_registration import AccountFlow
from tools.registration import configure


def test_live_switch_blocks_creation_but_not_login_and_is_not_in_save(tmp_path):
    flow = AccountFlow(tmp_path)
    try:
        assert flow.register('existing', 'pw')['success']
        assert configure(flow.store.path, 'close') is False
        assert not flow.register('blocked', 'pw')['success']
        assert flow.accounts.get_by_name('blocked') is None
        assert flow.store.db.execute('SELECT count(*) FROM players').fetchone()[0] == 1
        flow.game_session('existing', 'pw')
        from x2server.player.accounts import AccountStore
        reopened = AccountStore(flow.store)
        assert reopened.create('still-blocked', 'pw', 1) == 'closed'
        reopened.close()
        from x2server.player.save_manager import SaveManager
        from tests.unit.test_save_manager import build_full_schema
        build_full_schema(flow.store)
        manager = SaveManager(flow.store)
        try:
            saved = manager.export_save(1)
            assert 'server_settings' not in manager.parse_save(saved).rows
            manager.import_save(1, saved)
            assert configure(flow.store.path, 'status') is False
        finally:
            manager.close()
        assert configure(flow.store.path, 'open') is True
        assert flow.register('new', 'pw')['success']
    finally:
        flow.accounts.close()
        flow.store.close()


def test_switch_refuses_missing_database(tmp_path):
    path = tmp_path / 'missing.db'
    with pytest.raises(FileNotFoundError):
        configure(path, 'close')
    assert not path.exists()
