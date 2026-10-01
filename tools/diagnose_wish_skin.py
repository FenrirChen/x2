"""Read-only balances, equipped skins and recent battle payloads; no services initialized."""
import argparse
import json
import sqlite3
import subprocess
import sys
from contextlib import closing
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from x2server.messages.battle import BATTLE_SCHEMAS, FIGHT_DATA, FIGHT_HERO


def diagnose(database, player_id):
    database = Path(database).resolve()
    report = {'database': str(database), 'player_id': player_id}
    try:
        report['commit'] = subprocess.check_output(
            ['git', '-C', str(ROOT), 'rev-parse', 'HEAD'], text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        report['commit'] = 'unavailable'
    with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True)) as db:
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        row = db.execute('SELECT snapshot FROM players WHERE id=?', (player_id,)).fetchone()
        if row is None:
            raise ValueError('player not found')
        snapshot = json.loads(row[0])
        report['crystal'] = snapshot.get('crystal', 0)
        if 'inventory' in tables:
            report['wish_currencies'] = dict(db.execute(
                'SELECT item_id,quantity FROM inventory WHERE player_id=? AND item_id IN (1237914,1237913,1237925)',
                (player_id,)))
        if 'appearance_wear' in tables:
            report['worn_skins'] = [dict(zip(('hero', 'type', 'skin'), r)) for r in db.execute(
                'SELECT hero_id,type,skin_id FROM appearance_wear WHERE player_id=? ORDER BY hero_id,type', (player_id,))]
        else:
            report['worn_skins'] = 'table_missing'
        if 'battle_entries' in tables:
            report['recent_battles'] = []
            for uuid, created, raw in db.execute(
                    'SELECT uuid,created_at,response FROM battle_entries WHERE player_id=? ORDER BY created_at DESC,rowid DESC LIMIT 5',
                    (player_id,)):
                entry = {'uuid': uuid, 'created_at': created}
                try:
                    response = BATTLE_SCHEMAS['L2C_FightData'].decode(raw)
                    data = FIGHT_DATA.decode(response['data'])
                    entry['mission'] = data.get('missionId')
                    entry['heroes'] = [{k: hero.get(k, 0) for k in ('id', 'battleSkinId')}
                        for hero in map(FIGHT_HERO.decode, data.get('fightHeros', []))]
                except (ValueError, KeyError):
                    entry['decode'] = 'unavailable'
                report['recent_battles'].append(entry)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--player', type=int, required=True)
    args = parser.parse_args()
    print(json.dumps(diagnose(args.database, args.player), ensure_ascii=False, indent=2))
