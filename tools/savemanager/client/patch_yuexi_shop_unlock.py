"""Restore retained YueXi soul thresholds in an already restored ShopConfig.
Only four field-5 values change; existing narrow plaintext loader stays intact.
"""
import argparse
import hashlib
import json
import struct
import sys
import zipfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path[:0] = [str(ROOT), str(ROOT.parent), str(ROOT.parent / '.phase2_deps')]
import UnityPy
from phase3_protobuf import parse_table_array, parse_table_container, parse_message
from tools.analysis.patch_activity_scenes import ld, varint
from tools.savemanager.client.patch_treasure_activity import text_asset
from tools.savemanager.client.patch_yuexi_shop_config import BASE, RECOVERED, CAVE, HOOK
from tools.savemanager.client.patch_activity_ui import branch
THRESHOLDS = (0,1,2,4)


def patch(apk, output):
    output.mkdir(parents=True,exist_ok=True)
    entry='assets/bin/Data/'+BASE
    with zipfile.ZipFile(apk) as archive:
        env=UnityPy.load(archive.read(entry))
        obj,tree,plain=text_asset(env)
        native=archive.read('lib/arm64-v8a/libil2cpp.so')
        recovered=parse_table_container(text_asset(UnityPy.load(
            archive.read('assets/bin/Data/'+RECOVERED)))[2])
    keys,items,unknown,used=parse_table_array(plain[4:])
    assert struct.unpack_from('<I',plain)[0]==len(keys)==len(items)==29
    assert not unknown and used==len(plain)-4
    records=dict(zip(keys,items)); originals=dict(zip(recovered['keys'],recovered['items']))
    before=dict(records); audit=[]
    for index,key in enumerate(range(887,891)):
        fields,_=parse_message(records[key])
        old=[f.value for f in fields if f.field==5]
        assert old in ([6*(index+1)],[THRESHOLDS[index]])
        records[key]=b''.join(varint(5<<3)+varint(THRESHOLDS[index])
            if f.field==5 else records[key][f.start:f.end] for f in fields)
        # Byte-for-byte equality with retained official row is the authority.
        assert records[key]==originals[key], key
        audit.append({'shop_id':key,'old':old,'soul_threshold':THRESHOLDS[index]})
    patched=struct.pack('<I',len(keys))+b''.join(varint(1<<3)+varint(k) for k in keys)+b''.join(ld(2,records[k]) for k in keys)
    assert len(patched)==len(plain)
    assert patched[:16]==plain[:16]==native[CAVE+72:CAVE+88]
    assert struct.unpack_from('<I',native,HOOK)[0]==branch(HOOK,CAVE)
    assert all(records[k]==before[k] for k in keys if k not in range(887,891))
    old_objects={o.path_id:o.get_raw_data() for o in env.objects}
    tree['m_Script']=patched.decode('utf8','surrogateescape');obj.save_typetree(tree)
    data=env.file.save(); reread=UnityPy.load(data)
    assert text_asset(reread)[2]==patched
    assert all(o.get_raw_data()==old_objects[o.path_id] for o in reread.objects if o.path_id!=obj.path_id)
    target=output/BASE;target.write_bytes(data)
    (output/'libil2cpp.so').write_bytes(native)
    (output/'manifest.json').write_text(json.dumps({entry:str(target.resolve())},indent=2),encoding='utf8')
    report={'baseline':str(apk),'shops':audit,'unchanged_rows':25,'native_unchanged':True,
            'loader_prefix_unchanged':True,'asset_sha256':hashlib.sha256(data).hexdigest()}
    (output/'audit.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('apk',type=Path);p.add_argument('output',type=Path)
    a=p.parse_args();patch(a.apk,a.output)
