"""Align CollegeRecipe material vectors with the client's ResourceManager table."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from analysis.progression.probe import read_tables

def main():
    data, metadata, missing = read_tables(['CollegeRecipe'])
    assert not missing
    path = Path(__file__).resolve().parents[2] / 'src/x2server/data/college_upgrade_catalog.json'
    catalog = json.loads(path.read_text(encoding='utf8'))
    rows = {row['RecipeID']: row for row in data['CollegeRecipe']}
    changes = []
    for recipe in catalog['recipes']:
        canonical = rows[recipe['RecipeID']]
        assert recipe['ItemGroup'] == canonical['ItemGroup']
        if recipe['ItemNum'] != canonical['ItemNum']:
            changes.append(recipe['RecipeID'])
        recipe['ItemNum'] = canonical['ItemNum']
    catalog['sources']['CollegeRecipe']['materialVectorSource'] = metadata['CollegeRecipe']['source']
    path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print('Aligned material vectors:', changes)

if __name__ == '__main__':
    main()
