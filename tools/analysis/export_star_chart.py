"""Export star chart rules from the indexed 2.4 client tables."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from analysis.progression.probe import read_tables


def export():
    tables, sources, missing = read_tables([
        'StarChartsBase', 'StarChartsSkill', 'StarChartsParam', 'ChapterInfo', 'SectionTable'])
    if missing:
        raise ValueError(missing)
    chapters = {r['ChapterNumber'] - 1: r for r in tables['ChapterInfo']
                if r.get('StageID') and 2 <= r.get('ChapterNumber', 0) <= 6}
    # UnlockDescID 390004/391004/392004/394004/393004 explicitly names
    # chapters 1..5. ChapterInfo includes the prologue as ChapterNumber 1.
    abilities = []
    for row in tables['StarChartsBase']:
        if row.get('OpenType', {}).get('value') != 1:
            continue
        chapter = chapters[row['Order']]
        abilities.append({**row, 'unlock_section': chapter['StageID'][-1]})
    data = {'provenance': 'CONFIRMED_CLIENT_STATIC; unlock chapters from UnlockDescID text',
            'sources': sources, 'abilities': abilities, 'skills': tables['StarChartsSkill'],
            'charge_costs': tables['StarChartsParam'][0]['DefultConsume'],
            'auto_sections': {str(r['SectionID']): {
                'condition': r.get('AutoFightCondition', {}).get('value', 0),
                'cost': r.get('ContinueFightConsume', 0)} for r in tables['SectionTable']
                if r.get('IsAutoFightMode', {}).get('value') == 1}}
    (ROOT / 'src/x2server/data/star_chart.json').write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    export()
