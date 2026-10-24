"""Verify a release APK against its baseline and explicit patch manifest."""
import argparse,hashlib,json,struct,zipfile
from pathlib import Path


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(4<<20),b''):h.update(b)
    return h.hexdigest()


def validate(baseline,apk,manifest,report):
    expected=json.loads(Path(manifest).read_text());expected['lib/arm64-v8a/libil2cpp.so']=str(Path(manifest).parent/'libil2cpp.so')
    with zipfile.ZipFile(baseline) as old,zipfile.ZipFile(apk) as new:
        prior={i.filename:i for i in old.infolist() if not i.filename.startswith('META-INF/')}
        current={i.filename:i for i in new.infolist() if not i.filename.startswith('META-INF/')}
        assert prior.keys()==current.keys(),'unexpected entry addition/removal'
        changed=[n for n in prior if (prior[n].CRC,prior[n].file_size)!=(current[n].CRC,current[n].file_size)]
        assert set(changed)<=set(expected),set(changed)-set(expected)
        for name,path in expected.items():assert hashlib.sha256(new.read(name)).hexdigest()==sha(path),name
        assert new.read('classes5.dex')==old.read('classes5.dex')
        assert new.read('lib/arm64-v8a/libunity.so')==old.read('lib/arm64-v8a/libunity.so')
        config='assets/42c44a368fc3544296d1e717a485b306.ab'
        assert new.read(config)==old.read(config),'server URL/config changed'
        bridge=new.read('lib/arm64-v8a/libx2save.so')
        assert b'x2_open_save_manager' in bridge and b'x2_play_login_title_voice' in bridge
        with Path(apk).open('rb') as f:
            for i in new.infolist():
                if i.compress_type!=0:continue
                f.seek(i.header_offset);hdr=f.read(30);nl,el=struct.unpack_from('<HH',hdr,26)
                assert (i.header_offset+30+nl+el)%4==0,'stored entry not aligned: '+i.filename
        assert new.testzip() is None,'ZIP CRC failure'
    size=Path(apk).stat().st_size;assert size<2**31-1,'signed APK exceeds Unity compatibility limit'
    result=dict(apk=str(apk),bytes=size,sha256=sha(apk),changed_entries=changed,config_preserved=True,
        save_manager_and_allocator_preserved=True,full_zip_crc='passed',stored_entry_alignment=4)
    Path(report).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(result,ensure_ascii=True))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('baseline');p.add_argument('apk');p.add_argument('manifest');p.add_argument('report');a=p.parse_args();validate(a.baseline,a.apk,a.manifest,a.report)
