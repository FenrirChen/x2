"""Recover combat identity, skills and bare attributes for canonical trial units."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from analysis.progression.probe import read_tables


def export():
    path = ROOT / 'src/x2server/data/trial_units.json'
    data = json.loads(path.read_text(encoding='utf8'))
    tables, metadata, missing = read_tables(['UnitBase', 'PlayerAttrib', 'Appearance'])
    if missing:
        raise ValueError(missing)
    units = {row['ID']: row for row in tables['UnitBase']}
    attributes = {row['ID']: row for row in tables['PlayerAttrib']}
    fields = json.loads((ROOT / 'src/x2server/data/battle_hero_base.json').read_text(encoding='utf8'))['1007'].keys()
    identities = {row['TrialHeroID'] for row in data['units']}
    assert identities <= units.keys() and identities <= attributes.keys()
    data['unit_skills'] = {str(identity): units[identity]['SKill']
                           for identity in sorted(identities | {row['UnitID'] for row in data['units']})}
    data['unit_attributes'] = {str(identity): {field: attributes[identity].get(field, 0) for field in fields}
                              for identity in sorted(identities)}
    skins = {row.get('AppearanceID', 0) for row in data['units']}
    data['appearance_units'] = {str(row['AppearanceID']): row['UnitBaseID']
                                for row in tables['Appearance'] if row['AppearanceID'] in skins}
    data['sources'].update(metadata)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print('Recovered trial combat identities:', len(identities))


if __name__ == '__main__':
    export()
