"""Check packaged season configuration and reward references."""
import json,sys
from pathlib import Path
from collections import Counter
sys.dont_write_bytecode=True
OUT=Path(__file__).resolve().parent;SRC=Path('D:/demo/x2')
def table(n):return json.loads((OUT/'tables'/f'{n}.json').read_text('utf8'))
lang={r['Key']:r.get('Chinese','') for r in json.loads((SRC/'moni/data/raw/Language.json').read_text('utf8'))}
acts=[r for r in table('activityreal') if r.get('ActivityID') in [74001,74004,74007]]
print('ACTIVITIES',acts)
seasonconfig=table('seasonconfig')
print('CONFIG_GROUPS',dict(Counter((tuple(r.get('SeasonID',[])),r.get('Type',{}).get('value',0)) for r in seasonconfig)))
sections={r['SectionID']:r for r in table('sectiontable')}
ids={i for r in seasonconfig for i in r.get('SectionGroup',[])}
print('LINKED_SECTIONS',len(ids),'missing',sorted(ids-sections.keys()),'types',dict(Counter(sections[i].get('Type',{}).get('value',0) for i in ids if i in sections)))
print('SECTIONS_EXAMPLES',[(i,{k:sections[i].get(k) for k in ['NameChina','Maps','ChapterID','GamePlayType']}) for i in sorted(ids)[:2]])
print('GAMEPLAY_NAMES',[(k,v) for k,v in lang.items() if any(w in v for w in ['终极梦境','试炼梦境','梦境深处','赛季神迹','蚀化魂器','乐园迷途者','乐园污染者'])][:40])
for n in ['battlepassrank','battlepassrankreward','battlepassaward','battlepasslevel','shopgoodsgroup']:
    print('TABLE_SAMPLE',n,table(n)[:1])
giftids={r['GiftGroup'] for r in table('gift')}
rewardrefs=set()
for n in ['battlepassachievement','battlepassaward','battlepassexrankreward','battlepassrankreward','battlepasslevel','battlepasstask']:
    for r in table(n):
        for k,v in r.items():
            if k in ['GiftID','GiftGroup','GiftGroup01','GiftGroup02','GiftGroup03'] and v:
                rewardrefs.update(v if isinstance(v,list) else [v])
print('REWARD_REFERENCES',len(rewardrefs),'missing',sorted(rewardrefs-giftids))
fields=json.loads((OUT/'season_fields.json').read_text('utf8'))
print('SEASON_RELIC_FIELDS',fields['CommandX2.L2C_SeasonRelic'])
print('FIELDS_SEASON_EQUIP',fields['PlayerDbData.SeasonEquipData'])
cls=json.loads((OUT/'battlepass_classes.json').read_text('utf8'))
print('QUERY_INFO',cls['CommandX2.L2C_QueryBattlePassInfo']['body'].split('// Properties')[0].split('// Methods')[0])
index=json.loads((SRC/'moni/data/resource_index.json').read_text('utf8'))
with __import__('zipfile').ZipFile(SRC/'X2_Eclipse_v2_4.apk') as z:
    ui={k:{'asset':v,'present':('assets/bin/Data/'+v in z.namelist())} for k,v in index.items() if k.startswith('ui/') and 'battlepass' in k}
(OUT/'battlepass_ui_assets.json').write_text(json.dumps(ui,ensure_ascii=False,indent=2),'utf8')
summary={'activities':acts,'season_config_groups':[{'seasons':list(k[0]),'type':k[1],'count':v} for k,v in Counter((tuple(r.get('SeasonID',[])),r.get('Type',{}).get('value',0)) for r in seasonconfig).items()],
    'linked_sections':len(ids),'missing_sections':sorted(ids-sections.keys()),'reward_groups':len(rewardrefs),'missing_reward_groups':sorted(rewardrefs-giftids),'packaged_ui_count':len(ui)}
(OUT/'linkage_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),'utf8')
