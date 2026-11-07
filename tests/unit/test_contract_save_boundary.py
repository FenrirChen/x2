import io
import json
import zipfile

import pytest

from tests.unit.test_save_manager import env
from x2server.player.save_manager import CONTRACT_ADDED_TABLES


def test_contract_tables_survive_cross_account_import(env):
    store, _, manager, source, destination = env
    with store.db:
        store.db.execute('DELETE FROM hero_contracts WHERE player_id=?', (source,))
        store.db.execute('DELETE FROM hero_date_options WHERE player_id=?', (source,))
        store.db.execute('INSERT INTO hero_contracts VALUES (?,1010,1800000000)', (source,))
        store.db.execute('INSERT INTO hero_date_options VALUES (?,1010,101001,1,1,1800000000)', (source,))
    archive = manager.export_save(source)
    manager.import_save(destination, archive)
    assert tuple(store.db.execute('SELECT hero_id,created_at FROM hero_contracts WHERE player_id=?',
                                  (destination,)).fetchone()) == (1010, 1800000000)
    assert tuple(store.db.execute('SELECT hero_id,date_id,option_id,value FROM hero_date_options WHERE player_id=?',
                                  (destination,)).fetchone()) == (1010, 101001, 1, 1)


def test_pre_contract_save_accepts_missing_pair_but_not_partial_tables(env):
    _, _, manager, source, _ = env
    with zipfile.ZipFile(io.BytesIO(manager.export_save(source))) as z:
        manifest = json.loads(z.read('manifest.json'))
        document = json.loads(z.read('save.json'))
        blobs = [z.read(name) for name in sorted(z.namelist()) if name.startswith('blobs/')]
    document['tables'].pop('hero_contracts')
    with pytest.raises(ValueError, match='表集不符'):
        manager.parse_save(manager._container_bytes(manifest, document, blobs))
    document['tables'].pop('hero_date_options')
    plan = manager.parse_save(manager._container_bytes(manifest, document, blobs))
    assert all(plan.rows[name] == [] for name in CONTRACT_ADDED_TABLES)
