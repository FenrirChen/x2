import json, sys, bisect
from pathlib import Path
sys.path[:0] = ['.', 'D:/demo/x2/.phase3_deps']
from capstone import Cs, CS_ARCH_ARM64, CS_MODE_LITTLE_ENDIAN
from analysis.progression.probe import read_tables
root = Path('D:/demo/x2')
methods = json.loads((root/'tools/Il2CppDumper-bin/script.json').read_text())['ScriptMethod']
names = {m['Address']:m['Name'] for m in methods}
addresses = sorted(names)
binary = (root/'apk/lib/arm64-v8a/libil2cpp.so').read_bytes()
out=[]
for m in methods:
    name=m['Name']
    if not (('CollegeCustomerDetil$$' in name and any(x in name for x in ('.ctor','OnAddPrice','OnDiscount','OptSuggestion','RefreshPirce','RefreshFavor','RefreshChat','OnGetCustomerButton','$$Refresh')))
            or ('CollegeAlchemyModule$$' in name and any(x in name for x in ('ButtonClick','Customer','Favor','Price','Advice','Suggest','AdvanceStar')))
            or ('CollegeWonderModule.Civilization$$' in name and 'Refresh' in name)
            or ('CommandX2.L2C_AlchemyButtonClick$$Serialize' in name)):
        continue
    start=m['Address']; end=addresses[bisect.bisect_right(addresses,start)]
    out.append(f'\n===== {name} {start:#x} =====')
    for i in Cs(CS_ARCH_ARM64,CS_MODE_LITTLE_ENDIAN).disasm(binary[start:end],start):
        label=names.get(int(i.op_str[1:],16),'') if i.mnemonic in ('b','bl') and i.op_str.startswith('#0x') else ''
        out.append(f'{i.address:x}: {i.mnemonic} {i.op_str} ; {label}')
Path('runtime/college_followup_native.txt').write_text('\n'.join(out),encoding='utf8')
tables,meta,missing=read_tables(['Item','CollegeCustomer','CollegeQuest','CollegeFavor','SectionTable','ChapterTable','Gift'])
tables['Item']=[r for r in tables.get('Item',[]) if 1202000 <= r.get('ItemID',0) <= 1202030]
Path('runtime/college_followup_tables.json').write_text(json.dumps({'tables':tables,'missing':missing},ensure_ascii=False,indent=2),encoding='utf8')
print('native',len(out),'tables',[(k,len(v)) for k,v in tables.items()],'missing',missing)
import zipfile
from analysis.progression.probe import resources, UnityPy
from phase3_protobuf import parse_message, convert_data_bytes
entry=resources['table/globalparamstring']
with zipfile.ZipFile(root/'X2_Eclipse_v2_4.apk') as apk:
    env=UnityPy.load(apk.read('assets/bin/Data/'+entry['source_hash']))
    blob=next(o.read() for o in env.objects if o.type.name=='TextAsset').m_Script
    if isinstance(blob,str): blob=blob.encode('utf8','surrogateescape')
    wrapper,_=parse_message(convert_data_bytes(blob)[4:])
    params={}
    for v in wrapper:
        if v.field==2:
            row=parse_message(v.value)[0]
            fields={f.field:f.value.decode() for f in row}
            params[fields[1]]=fields.get(2,'')
Path('runtime/college_global_all.json').write_text(json.dumps(params,ensure_ascii=False,indent=2),encoding='utf8')
print('PARAMS',json.dumps({k:v for k,v in params.items() if any(s in k.lower() for s in ('price','favor','suggest','advise','energy','customer','chat'))}))
lang=json.loads(Path('runtime/college_pray_language.json').read_text(encoding='utf8'))
print('LANG_KEYS',list(lang))
print('SECTIONS',json.dumps([{k:v for k,v in r.items() if k in ('SectionID','DifficultyLevel','NameChina','NameMoreChina','DropValueID','DroopLimit3','ADC','DropBuff')} for r in tables['SectionTable'] if 2133101 <= r.get('SectionID',0) <= 2133110]))
