"""Recover repeated official table fields discarded by the old scalar export."""
import hashlib
import json
import re
from pathlib import Path

from _client_table_wire import parse_message, parse_table_container

root = Path('D:/demo/x2')
dump = (root / 'tools/Il2CppDumper-bin/dump.cs').read_text(encoding='utf8')
tables = {}
sources = {}
for name in ('CollegeBuilding', 'CollegeLevel', 'CollegeStarLevel', 'CollegeRecipe', 'CollegeExplore'):
    block = dump.split('public class ' + name + ' //')[1].split('// Methods')[0]
    fields = re.findall(r'public ([\w<>]+) (\w+);', block)
    reference = json.loads((root / f'college_tables/final/{name}.json').read_text())
    for source in sorted((root / 'college_tables').glob(name + '_*.bytes')):
        rows = []
        for raw in parse_table_container(source.read_bytes())['items']:
            row = {}
            for value in parse_message(raw)[0]:
                kind, key = fields[value.field - 1]
                entry = value.value
                if kind in ('string', 'List<string>'):
                    entry = entry.decode('utf8')
                if kind.startswith('List<'):
                    row.setdefault(key, []).append(entry)
                else:
                    row[key] = entry
            rows.append(row)
        scalar = [{k: v[-1] if isinstance(v, list) and isinstance(v[0], int) else v
                   for k, v in row.items()}
                  for row in rows]
        if name == 'CollegeExplore':
            for row in scalar:
                row['Icon'] = [row['Icon']]
        if scalar == reference:
            tables[name] = rows
            sources[name] = {'file': source.name, 'sha256': hashlib.sha256(source.read_bytes()).hexdigest()}
            break
    else:
        raise ValueError('No source matches previous export: ' + name)
catalog = {'sources': sources, 'buildings': tables['CollegeBuilding'],
           'levels': tables['CollegeLevel'], 'stars': tables['CollegeStarLevel'],
           'recipes': tables['CollegeRecipe'], 'explores': tables['CollegeExplore']}
target = Path('src/x2server/data/college_upgrade_catalog.json')
target.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
from align_alchemy_recipe_costs import main as align_recipe_costs
align_recipe_costs()
print('Exported', {key: len(value) for key, value in catalog.items() if isinstance(value, list)})
print('Building 701:', catalog['buildings'][0])
print('Level 2:', catalog['levels'][1])
