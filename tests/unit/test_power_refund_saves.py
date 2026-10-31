from tests.unit.test_economy import env
from tests.unit.test_save_manager import build_full_schema
from x2server.player.save_manager import SaveManager
from x2server.player import power_refund


def test_refund_marker_survives_real_import_and_new_owner_is_ineligible(env,tmp_path):
    store,e,_=env
    build_full_schema(store)
    player=store.get(1)
    player['snapshot']['power_buy']={'day':1789920000,'count':10}
    e.save_snapshot(1,player['snapshot'])
    manager=SaveManager(store,backup_root=tmp_path/'backups')
    try:
        old_archive=manager.export_save(1)
        with store.db:
            assert power_refund.settle(store.db,1,player['snapshot'],1790000000)==390
        manager.import_save(1,old_archive)
        assert not store.db.execute('SELECT 1 FROM player_mail WHERE source_key=?',(power_refund.SOURCE%1,)).fetchone()
        with store.db:
            assert power_refund.settle(store.db,1,store.get(1)['snapshot'],1790000001)==0
        store.login('new-after-fix',2,1790000001)
        manager.import_save(2,old_archive)
        with store.db:
            assert power_refund.settle(store.db,2,store.get(2)['snapshot'],1790000001)==0
    finally:
        manager.close()
