"""Export native combat bonus tables from the canonical 2.4 APK."""
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from analysis.progression.probe import read_tables, resources, UnityPy, ROOT as CLIENT_ROOT
from phase3_protobuf import convert_data_bytes, parse_message


def export():
    names = ['ArtifactBase', 'ArtifactFuse', 'JewelBase', 'PlayerAttrib',
             'CollegeBuilding', 'CollegeStarLevel', 'CollegeWonderSkill', 'FavorabilityFetters']
    tables, sources, missing = read_tables(names)
    if missing:
        raise ValueError(missing)
    entry = resources['table/globalparamstring']
    with zipfile.ZipFile(CLIENT_ROOT / 'X2_Eclipse_v2_4.apk') as apk:
        env = UnityPy.load(apk.read('assets/bin/Data/' + entry['source_hash']))
        obj = next(o.read() for o in env.objects if o.type.name == 'TextAsset')
        blob = obj.m_Script
        if isinstance(blob, str):
            blob = blob.encode('utf-8', 'surrogateescape')
        wrapper, _ = parse_message(convert_data_bytes(blob)[4:])
        rows = [parse_message(v.value)[0] for v in wrapper if v.field == 2]
        inversion = next(r for r in rows if next(v.value for v in r if v.field == 1) == b'InversionWonderSkill')
        inversion = [int(i) for i in next(v.value for v in inversion if v.field == 2).decode().split('|')]
    data = {'provenance': 'CONFIRMED_CLIENT_STATIC; ClientProperty 0x1491e48/0x1492df8/0x1492520',
            'sources': sources, 'inversion_skills': inversion}
    data['heroes'] = {str(r['ID']): {'profession': r.get('Profession', 0),
        'origin': r.get('Origin', {}).get('value', 0)} for r in tables['PlayerAttrib']}
    data['artifacts'] = {str(r['ArtifactID']): {k: v for k, v in r.items()
        if k.startswith(('ArtifactAttr', 'AttrValue', 'SeniorAttr', 'SenAttrValue'))} for r in tables['ArtifactBase']}
    data['fuses'] = {f"{r.get('FuseID', 0)}:{r['ProfEnum']}": {k: r.get(k, 0)
        for k in ('AttrRate', 'MaxAttrRate')} for r in tables['ArtifactFuse']}
    data['jewels'] = {str(r['JewelID']): {k: r.get(k, [] if k == 'JewelEffect2' else 0)
        for k in ('JewelEffect1', 'EffectValue1', 'JewelEffect2')} for r in tables['JewelBase']}
    data['fetters'] = {f"{r['HeroID']}:{r['FettersID']}": {k: r.get(k, 0)
        for k in ('IsOpen', 'Attribid', 'AttribValue')} for r in tables['FavorabilityFetters']}
    data['wonders'] = {str(r['ID']): {'origin': r['BuildType']['value'], 'stars': r['StarID']}
        for r in tables['CollegeBuilding'] if r['BaseType']['value'] == 2 and r['BuildType']['value'] <= 7}
    data['wonder_stars'] = {str(r['BuildID']): r.get('StarEffectValue1', [])
        for r in tables['CollegeStarLevel'] if r['BaseType']['value'] == 2}
    data['wonder_skills'] = {str(r['AddID']): {'attribute': r['AttributeType'], 'values': r['AttributeValue']}
        for r in tables['CollegeWonderSkill']}
    (ROOT / 'src/x2server/data/battle_bonuses.json').write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    export()
