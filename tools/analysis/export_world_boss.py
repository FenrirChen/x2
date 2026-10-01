"""Export native WorldBoss exploration, questions, boxes and combat parameters."""
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from analysis.progression.probe import read_tables, resources, UnityPy, ROOT as RESOURCE_ROOT
from phase3_protobuf import parse_table_container, parse_message


def mail_templates(ids):
    # MailInfo is a server table left in the APK without an IL2CPP class.
    # Decode its actual wire fields; do not infer awards from item previews.
    resource=resources['table/mailinfo']
    source='assets/bin/Data/'+resource['source_hash']
    with zipfile.ZipFile(RESOURCE_ROOT/'X2_Eclipse_v2_4.apk') as apk:
        env=UnityPy.load(apk.read(source))
        asset=next(o.read() for o in env.objects if o.type.name=='TextAsset')
        blob=asset.m_Script
        if isinstance(blob,str):blob=blob.encode('utf-8','surrogateescape')
    result=[]
    for raw in parse_table_container(bytes(blob))['items']:
        fields={f.field:f.value for f in parse_message(raw)[0]}
        if fields.get(1) not in ids:
            continue
        if fields.get(9)!=1 or type(fields.get(10)) is not int:
            raise ValueError('unrecognized Boss mail reward fields')
        result.append({'id':fields[1],'sender_group':fields.get(4,0),
            'title':fields[6].decode('utf-8'),'body':fields[8].decode('utf-8'),
            'gift':fields[10]})
    if {r['id'] for r in result}!=ids:
        raise ValueError('missing Boss mail templates')
    return result,{'source':source,'wire_fields':{'id':1,'sender_group':4,
        'title':6,'body':8,'award_kind':9,'gift':10}}

def export():
    tables, sources, missing = read_tables(['WorldBossInfo','WorldBossExplore','WorldBossEvent',
        'AnswerConfig','BoxConfig','Activity','PlayerAttrib','MonsterLevelBonus'])
    if missing:
        raise ValueError(missing)
    bosses = tables['WorldBossInfo']
    units = {b['MonsterID'] for b in bosses}
    activity = next(r for r in tables['Activity'] if r['ActivityID'] == 28001)
    mail_ids={i for b in bosses for i in b['ChallengeReward']}
    mail_ids.update(b['FindReward'] for b in bosses if b.get('FindReward'))
    templates,meta=mail_templates(mail_ids)
    sources['MailInfo']=meta
    return {'sources': sources, 'activity': activity, 'bosses': bosses,
        'explore': tables['WorldBossExplore'], 'events': tables['WorldBossEvent'],
        'answers': tables['AnswerConfig'], 'boxes': tables['BoxConfig'],
        'attributes': [r for r in tables['PlayerAttrib'] if r['ID'] in units],
        'level_bonus': tables['MonsterLevelBonus'],'mail_templates':templates,
        'compatibility':{'opening':'all_day','boss_listing':'one_fixed_world_per_player_no_respawn','daily_boss_id':2040101,
            'timezone':'Asia/Shanghai','start':'first_authenticated_join','charge':'first_combat_confirmation'}}

if __name__ == '__main__':
    path = ROOT / 'src/x2server/data/world_boss.json'
    path.write_text(json.dumps(export(), ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(path)
