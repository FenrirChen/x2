import json
import pytest
from tests.integration.test_save_manager_http import service


@pytest.mark.parametrize('setting', [None, '0', 'false', 'invalid'])
@pytest.mark.parametrize('isolated', [False, True])
def test_closed_import_does_no_work(service,monkeypatch,setting,isolated):
    identity,accounts,manager,online,store=service
    from x2server.bootstrap.save_manager_api import SaveManagerAPI
    if setting is None:
        monkeypatch.delenv('X2_SAVE_IMPORT_ENABLED',raising=False)
    else:
        monkeypatch.setenv('X2_SAVE_IMPORT_ENABLED',setting)
    api=SaveManagerAPI(manager,accounts,lambda:set(),isolated_jobs=isolated)
    def fail(*a,**kw):
        raise AssertionError('disabled import performed work')
    monkeypatch.setattr(manager,'import_save',fail)
    monkeypatch.setattr(manager,'parse_save',fail)
    if api.runner:
        monkeypatch.setattr(api.runner,'run',fail)
    before=store.db.total_changes
    try:
        status,_,body=api.respond('POST','/save-manager/import',b'bad archive','')
        assert status==503 and json.loads(body)['error']=='save_import_disabled'
        assert store.db.total_changes==before
        assert not list(manager.backup_root.rglob('*.x2save'))
        assert api._jobs.acquire(blocking=False)
        api._jobs.release()
    finally:
        api.close()


def test_export_preserved_and_reenable_import(service,monkeypatch):
    identity,accounts,manager,online,store=service
    monkeypatch.delenv('X2_SAVE_IMPORT_ENABLED',raising=False)
    auth=identity.respond('POST','/save-manager/auth',b'account=alpha&password=pw-alpha')
    bearer='Bearer '+json.loads(auth.body)['token']
    export=identity.respond('POST','/save-manager/export',b'',authorization=bearer)
    assert export.status==200 and export.body.startswith(b'PK')
    result=identity.respond('POST','/save-manager/import',export.body,authorization=bearer)
    assert result.status==503
    assert identity.respond('POST','/save-manager/status',b'',authorization=bearer).status==200
    monkeypatch.setenv('X2_SAVE_IMPORT_ENABLED','1')
    result=identity.respond('POST','/save-manager/import',export.body,authorization=bearer)
    assert result.status==200
