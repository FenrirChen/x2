"""Build the explicitly approved 2026-10-24 APK patches; preserve baseline patches."""
import argparse,copy,hashlib,json,struct,sys,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
sys.path[:0]=[str(ROOT),str(ROOT/'tools'),str(ROOT.parent/'.phase2_deps'),str(ROOT.parent/'.phase3_deps')]
import UnityPy
from capstone import Cs,CS_ARCH_ARM64,CS_MODE_ARM
from tools import patch_izanagi_skin as skin
from tools.savemanager.client import patch_title_voice as voice
from tools.savemanager.client.patch_activity_backgrounds import PAGES
from analysis.progression.probe import resources


def dump(sf):
    payload=sf.save()
    checked=next(iter(UnityPy.load(payload).files.values()))
    assert set(checked.objects)==set(sf.objects)
    return payload


def external(sf,path):
    for i,ext in enumerate(sf.externals,1):
        if ext.path==path:return i
    ext=copy.copy(sf.externals[0]);ext.path=path;ext.guid=bytes(16);ext.type=0;ext.temp_empty=''
    sf.externals.append(ext);return len(sf.externals)


def native_patch(data):
    original=data
    assert data[0x13bda24:0x13bda30]==bytes.fromhex('f44fbea9fd7b01a9fd430091'), 'MainAniEnter version mismatch'
    data,title_cave=voice.patch(data,0x13bda24,1,None,None,None)
    elf=voice.parse_elf(data);cave=voice.find_cave(elf,data,128,voice.RESERVED)
    hook=0x1e497d8;resume=hook+4
    assert struct.unpack_from('<I',data,hook)[0]==0x7102041f,'six-star comparator changed'
    # w26=0 only on the six-star pass; x19 is Item, ItemType(+0x24)=10 is E_Equip.
    words=[0x7100035f,0,0xB9402668,0x7100291f,0,0x7106041f,0,0x7102041f,0]
    # cmp w26,0; b.ne original; ldr w8,[x19,0x24]; cmp w8,10;
    # b.ne original; cmp w0,385; b resume; original: cmp w0,129; b resume.
    for i in (1,4):words[i]=0x54000001|((((cave+28)-(cave+i*4))//4)<<5)
    words[6]=voice.b(cave+24,resume);words[8]=voice.b(cave+32,resume)
    out=bytearray(data);out[cave:cave+36]=struct.pack('<9I',*words);struct.pack_into('<I',out,hook,voice.b(hook,cave))
    md=Cs(CS_ARCH_ARM64,CS_MODE_ARM);ins=list(md.disasm(bytes(out[cave:cave+36]),cave))
    assert ins[0].mnemonic=='cmp' and ins[0].op_str=='w26, #0'
    assert ins[2].op_str=='w8, [x19, #0x24]'
    assert ins[5].op_str=='w0, #0x181' and ins[7].op_str=='w0, #0x81'
    ranges=[(0x13bda24,0x13bda28),(title_cave,title_cave+voice.CAVE_SIZE),(hook,hook+4),(cave,cave+36)]
    assert all(any(a<=i<b for a,b in ranges) for i,(a,b) in enumerate(zip(original,out)) if a!=b)
    return bytes(out),dict(title_cave=title_cave,star_cave=cave,star_hook=hook,
        probability='min(3*p6,1); six-star E_Equip pass only; one original RNG call',
        disassembly=[f'{i.address:x}: {i.mnemonic} {i.op_str}' for i in ins])


def patch(apk,output):
    output.mkdir(parents=True,exist_ok=True)
    manifest={};audit={'source':str(apk),'backgrounds':[],'season':[]}
    def put(name,data):
        target=output/(name.rsplit('/',1)[-1]);target.write_bytes(data);manifest[name]=str(target.resolve())
    with zipfile.ZipFile(apk) as z:
        n,report=native_patch(z.read('lib/arm64-v8a/libil2cpp.so'));(output/'libil2cpp.so').write_bytes(n);audit['native']=report
        # Use the canonical runtime resource map, but read every asset from the
        # supplied release baseline so existing scene fixes survive.
        def load(h):return next(iter(UnityPy.load(z.read('assets/bin/Data/'+h)).files.values()))
        # Open all formerly weekday-restricted trials, preserving level gates.
        h=resources['table/dailydungeon']['source_hash']
        def daily(encrypted):
            t=skin.parse_table_container(encrypted);plain=t['plain'];prefix=skin.rsa_public_unpad(encrypted[:128]);_,keys,rows,spans,end=skin.split_array(plain);changed=[]
            for i,key in enumerate(keys):
                fields=skin.parse_message(rows[i])[0];days=[f.value for f in fields if f.field==8]
                typ=next((f.value for f in fields if f.field==2),0)
                if typ!=2 or not days or all(days):continue
                assert len(days)==7 and spans[i]>=len(prefix)
                # All seven flags already have a one-byte varint, retaining the
                # RSA prefix and row lengths; use the existing daily-open label.
                rows[i]=b''.join((skin.varint(8<<3)+b'\x01') if f.field==8 else
                    (skin.varint(6<<3)+skin.varint(20301003)) if f.field==6 else rows[i][f.start:f.end] for f in fields)
                changed.append(key)
            repaired=skin.build_array(plain,end,rows);out=skin.reencrypt(encrypted,repaired,prefix)
            check=skin.parse_table_container(out)
            for key,row in zip(check['keys'],check['items']):
                if key in changed:assert [f.value for f in skin.parse_message(row)[0] if f.field==8]==[1]*7
            return out,{'always_open':changed}
        data,report=skin.rebuild_table(apk,h,'DailyDungeon',daily);put('assets/bin/Data/'+h,data);audit['daily']=report
        # Fix only explicitly audited background nodes. The previous patch
        # handled both dimensions zero but missed a single zero dimension.
        idx=json.loads((ROOT/'tools/savemanager/client/activity_resource_index.json').read_text(encoding='utf8'))
        for art,pages in PAGES.items():
            if art=='ann1':continue # retired activity remains closed
            for page,pids in pages.items():
                h=idx['ui/'+page][0];sf=load(h);before={i:o.get_raw_data() for i,o in sf.objects.items()};changed=set()
                for pid in pids:
                    image=sf.objects[pid];raw=bytearray(image.get_raw_data());assert len(raw)==292
                    f,sp=struct.unpack_from('<iq',raw,196)
                    assert f>0 and sp>0,'baseline lost its existing background binding'
                    target=load(sf.externals[f-1].path).objects[sp].read()
                    width,height=target.m_Rect.width,target.m_Rect.height
                    go=struct.unpack_from('<q',raw,4)[0]
                    rect=next(o for o in sf.objects.values() if o.type.name=='RectTransform' and o.read_typetree()['m_GameObject']['m_PathID']==go)
                    t=rect.read_typetree();old=copy.deepcopy(t)
                    if t['m_AnchorMin']==t['m_AnchorMax']:
                        if t['m_SizeDelta']['x']<=0:t['m_SizeDelta']['x']=float(width)
                        if t['m_SizeDelta']['y']<=0:t['m_SizeDelta']['y']=float(height)
                    raw[60]=0 # background never consumes pointer input
                    if t!=old:rect.save_typetree(t);changed.add(rect.path_id)
                    if bytes(raw)!=image.get_raw_data():image.set_raw_data(bytes(raw));changed.add(pid)
                    audit['backgrounds'].append(dict(page=page,image=pid,sprite=target.m_Name,
                        dimensions_before=old['m_SizeDelta'],dimensions_after=t['m_SizeDelta'],binding_preserved=True))
                if changed:
                    for pid,raw in before.items():
                        if pid not in changed:assert sf.objects[pid].get_raw_data()==raw
                    put('assets/bin/Data/'+h,dump(sf))
        origin='0999fa1dc42cb4d46897892076b8ce2a'
        # Each hall entry is a separate prefab branch, some incorrectly styled
        # with later-season art. Keep its control identities/click handlers.
        h=resources['ui/mainpage']['source_hash'];sf=load(h);fid=external(sf,origin)
        for pid in (572,610,715,797):
            o=sf.objects[pid];raw=bytearray(o.get_raw_data());struct.pack_into('<iq',raw,196,fid,75);o.set_raw_data(bytes(raw))
        for pid in (569,584,612,623,721,856,857):
            o=sf.objects[pid];raw=bytearray(o.get_raw_data());raw[12]=0;o.set_raw_data(bytes(raw))
        put('assets/bin/Data/'+h,dump(sf));audit['season'].append({'hall_entries':[572,610,715,797],'sprite':'SaiJi_RuKou (origin)'})
        # Season main already references UI_BattlePass_Main's official origin
        # title. Replace the shared farm's later-season backdrop and add the
        # same official origin logo without changing controls/bindings.
        h=resources['ui/ui_battlepass_farm']['source_hash'];sf=load(h)
        raw=bytearray(sf.objects[422].get_raw_data());struct.pack_into('<iq',raw,196,external(sf,'00741e64da7f8a846aa1290f6ed6f0de'),2);sf.objects[422].set_raw_data(bytes(raw))
        raw=bytearray(sf.objects[431].get_raw_data());struct.pack_into('<iq',raw,196,external(sf,origin),67);sf.objects[431].set_raw_data(bytes(raw))
        # Clone a local Image/RectTransform/CanvasRenderer trio; no new script.
        image=sf.objects[422];oldgo=struct.unpack_from('<q',image.get_raw_data(),4)[0];go=sf.objects[oldgo]
        rect=next(o for o in sf.objects.values() if o.type.name=='RectTransform' and o.read_typetree()['m_GameObject']['m_PathID']==oldgo)
        renderer=next(o for o in sf.objects.values() if o.type.name=='CanvasRenderer' and o.read_typetree()['m_GameObject']['m_PathID']==oldgo)
        rootgo=sf.objects[resources['ui/ui_battlepass_farm']['path_id']]
        rootrect=next(o for o in sf.objects.values() if o.type.name=='RectTransform' and o.read_typetree()['m_GameObject']['m_PathID']==rootgo.path_id)
        base=max(sf.objects)+1;ids=[base+i for i in range(4)]
        for src,newid in zip((go,rect,renderer,image),ids):
            obj=copy.copy(src);obj.path_id=newid;obj.assets_file=sf;obj.set_raw_data(src.get_raw_data());sf.objects[newid]=obj
        gt=go.read_typetree();gt['m_Name']='OriginParadoxTitle';gt['m_IsActive']=True;gt['m_Component']=[{'component':{'m_FileID':0,'m_PathID':i}} for i in ids[1:]];sf.objects[ids[0]].save_typetree(gt)
        rt=rect.read_typetree();rt.update(m_GameObject={'m_FileID':0,'m_PathID':ids[0]},m_Father={'m_FileID':0,'m_PathID':rootrect.path_id},m_Children=[],m_AnchorMin={'x':0.,'y':1.},m_AnchorMax={'x':0.,'y':1.},m_SizeDelta={'x':280.,'y':76.},m_AnchoredPosition={'x':215.,'y':-55.},m_LocalScale={'x':1.,'y':1.,'z':1.});sf.objects[ids[1]].save_typetree(rt)
        ct=renderer.read_typetree();ct['m_GameObject']={'m_FileID':0,'m_PathID':ids[0]};sf.objects[ids[2]].save_typetree(ct)
        raw=bytearray(image.get_raw_data());struct.pack_into('<q',raw,4,ids[0]);struct.pack_into('<iq',raw,196,external(sf,origin),52);raw[60]=0;sf.objects[ids[3]].set_raw_data(bytes(raw))
        rr=rootrect.read_typetree();rr['m_Children'].append({'m_FileID':0,'m_PathID':ids[1]});rootrect.save_typetree(rr)
        put('assets/bin/Data/'+h,dump(sf));audit['season'].append({'farm':'origin official logo + blue city compatibility background','new_objects':ids,'main_prefab':'UI_BattlePass_Main retained'})
    # Static drawing is the user's explicit choice; the original incomplete
    # Spine stays bypassed, not replaced by a fabricated official animation.
    sm=skin.patch(apk,ROOT/'tools/assets/izanagi_skin_1223003.png',output/'skin',max_dimension=1408);manifest.update(sm)
    bridge=ROOT/'tools/savemanager/client/libx2save.so';manifest['lib/arm64-v8a/libx2save.so']=str(bridge.resolve())
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')
    (output/'audit.json').write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf8')
    print('PATCH_READY',len(manifest),'entries',len(audit['backgrounds']),'background references audited')


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('apk',type=Path);p.add_argument('output',type=Path);a=p.parse_args();patch(a.apk,a.output)
