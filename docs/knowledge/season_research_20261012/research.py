import sys,json,re,hashlib
from pathlib import Path
sys.dont_write_bytecode=True
SRC=Path('D:/demo/x2');OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(SRC/'moni/tools/vendor'))
from phase3_analyze import class_blocks,parse_fields,enum_blocks
dump=(SRC/'tools/Il2CppDumper-bin/dump.cs').read_text('utf8')
blocks=class_blocks(dump);enums=enum_blocks(dump)
def write(n,obj):(OUT/n).write_text(json.dumps(obj,ensure_ascii=False,indent=2),'utf8')
season={f'{ns}.{name}':b for (ns,name),b in blocks.items() if 'season' in name.lower()}
write('season_classes.json',season)
write('season_fields.json',{k:[{a:f[a] for a in ['name','type','repeated','element_type']} for f in parse_fields(v)] for k,v in season.items()})
write('season_enums.json',{k:v for k,v in enums.items() if 'season' in k.lower()})
write('season_protocol_ids.json',{str(k):v for k,v in enums.get('ERequestTypes',{}).items() if 'season' in v.lower()})
meta=json.loads((SRC/'tools/Il2CppDumper-bin/script.json').read_text('utf8'))
write('season_methods.json',[r for r in meta['ScriptMethod'] if 'season' in r['Name'].lower()])
owners={name for (ns,name),b in blocks.items() if 'SeasonConfig' in b['body'] and 'Season' not in name and not name.endswith('Binding')}
write('season_owners.json',{f'{ns}.{name}':b for (ns,name),b in blocks.items() if name in owners})
index=json.loads((SRC/'moni/data/resource_index.json').read_text('utf8'))
keys={k:v for k,v in index.items() if any(t in k.lower() for t in ['season','achv','talent','rank'])}
write('resource_candidates.json',keys)
lang=json.loads((SRC/'moni/data/raw/Language.json').read_text('utf8'))
words=[r for r in lang if any(t in r.get('Chinese','') for t in ['赛季','季节兽主','光辉之阶'])]
write('season_language.json',words)
print('Season classes',len(season),'resource candidates',len(keys),'language evidence',len(words))
write('battlepass_module.json',{f'{ns}.{n}':b for (ns,n),b in blocks.items() if n in ['BattlePassModule','BattlePassAchievementModule','ClientSeasonProperty']})
write('battlepass_protocol_ids.json',{str(k):v for k,v in enums.get('ERequestTypes',{}).items() if any(t in v.lower() for t in ['battlepass','talent','fetter','goldequip'])})
write('battlepass_classes.json',{f'{ns}.{n}':b for (ns,n),b in blocks.items() if 'battlepass' in n.lower()})
for (ns,n),b in blocks.items():
    if n in ['BattlePassModule','BattlePassAchievementModule','ClientSeasonProperty']:
        pass
import zipfile
sys.path[:0]=[str(SRC/'.phase2_deps')]
import UnityPy
from phase3_analyze import decode_record
from phase3_protobuf import parse_table_container
classes={n:parse_fields(b) for (ns,n),b in blocks.items()}
langmap={r['Key']:r.get('Chinese','') for r in lang}
tableindex=[]
with zipfile.ZipFile(SRC/'X2_Eclipse_v2_4.apk') as apk:
    for key,digest in index.items():
        if not key.startswith('table/') or not (any(t in key for t in ['battlepass','seasonconfig']) or key.split('/')[-1] in ['activityreal','chapterinfo','sectiontable','gift','shopconfig','shopgoodsgroup','taskcondition','activitytask']):continue
        name=key.split('/')[-1]
        env=UnityPy.load(apk.read('assets/bin/Data/'+digest))
        obj=next(o.read() for o in env.objects if o.type.name=='TextAsset')
        blob=obj.m_Script
        if isinstance(blob,str):blob=blob.encode('utf8','surrogateescape')
        folder=OUT/'tables';folder.mkdir(exist_ok=True)
        (folder/(name+'.bin')).write_bytes(blob)
        record={'name':name,'asset':digest,'sha256':hashlib.sha256(blob).hexdigest()}
        try:
            schema=next(v for k,v in classes.items() if k.lower()==name)
            rows=[decode_record(item,schema,enums,classes)[0] for item in parse_table_container(blob)['items']]
            write('tables/'+name+'.json',rows)
            record.update(count=len(rows),status='RAW_FIELDS_DECODED')
            print('TABLE',name,len(rows))
        except Exception as e:record.update(status='UNRESOLVED',error=str(e))
        tableindex.append(record)
write('table_manifest.json',tableindex)
bp=json.loads((OUT/'tables/battlepass.json').read_text('utf8'))
print('SEASON_NAMES',[(r['BattlepassID'],r['BattlepassName'],langmap.get(r['BattlepassName'])) for r in bp])
print('UI_WORDS',[(r['Key'],r.get('Chinese','')) for r in words if 13430000<=r['Key']<=13431000])
write('source_manifest.json',{'dump_cs_sha256':hashlib.sha256(dump.encode('utf8')).hexdigest(),
    'script_json_sha256':hashlib.sha256((SRC/'tools/Il2CppDumper-bin/script.json').read_bytes()).hexdigest(),
    'apk_declared_sha256':json.loads((SRC/'moni/data/manifest.json').read_text('utf8'))['apk_sha256'],
    'scope':'Packaged Android 2.4 resources, no final hot-update precedence claim'})
