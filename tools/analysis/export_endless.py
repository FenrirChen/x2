"""Export temporal gate rows and referenced task conditions from the canonical APK."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from analysis.progression.probe import read_tables


def export():
    tables, sources, missing = read_tables(['WeeklyDungeon','EndlessDungeonTask','TaskCondition','TaskConditionLine'])
    if missing:
        raise ValueError(missing)
    line = {r['AchievementConditionID']: r for r in tables['TaskConditionLine']}
    single = {r['TaskConditionID']: r for r in tables['TaskCondition']}
    rows = []
    for row in tables['EndlessDungeonTask']:
        condition = dict(line.get(row['TaskConditionID'], single.get(row['TaskConditionID'], {})))
        if not condition:
            raise ValueError(f'Missing condition {row}')
        targets = condition['CompleteNum']
        condition['CompleteNum'] = targets if isinstance(targets, list) else [targets]
        rows.append({**row, 'condition': condition})
    (ROOT/'src/x2server/data/endless.json').write_text(json.dumps(
        {'sources': sources, 'weekly': tables['WeeklyDungeon'], 'tasks': rows},
        ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    export()
