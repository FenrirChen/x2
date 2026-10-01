"""Read-only comparison of saved bonuses and the latest battle receipt."""
import argparse
import json
import sqlite3
from pathlib import Path
from types import SimpleNamespace

from x2server.messages.battle import BATTLE_SCHEMAS, FIGHT_DATA, FIGHT_HERO, HERO_ATTR
from x2server.messages.core import HERO_GOD_EQUIP
from x2server.player.battle_bonuses import artifact_attributes, other_attributes, GOD_EQUIP_ATTR, JEWEL_ATTR, LONG_PAIR
from x2server.player.progression import hero_attributes


def decode_bonus(blob):
    value = GOD_EQUIP_ATTR.decode(blob)
    jewels = []
    for entry in value.get('jewelAttr', []):
        row = JEWEL_ATTR.decode(entry)
        jewels.append({'attribute': LONG_PAIR.decode(row.get('effect1', b'')), 'passives': row.get('effect2', [])})
    return {'artifact': [LONG_PAIR.decode(r) for r in value.get('godAttr', [])], 'jewels': jewels}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--database', type=Path, required=True)
    parser.add_argument('--player', type=int, required=True)
    args = parser.parse_args()
    with sqlite3.connect(args.database.resolve().as_uri() + '?mode=ro', uri=True) as db:
        db.row_factory = sqlite3.Row
        snapshot = json.loads(db.execute('SELECT snapshot FROM players WHERE id=?', (args.player,)).fetchone()[0])
        entry = db.execute('SELECT uuid,response FROM battle_entries WHERE player_id=? ORDER BY created_at DESC,rowid DESC LIMIT 1', (args.player,)).fetchone()
        heroes = FIGHT_DATA.decode(BATTLE_SCHEMAS['L2C_FightData'].decode(entry['response'])['data'])['fightHeros'] if entry else []
        report = {'player': args.player, 'latest_battle': entry['uuid'] if entry else None, 'heroes': []}
        for blob in heroes:
            wire = FIGHT_HERO.decode(blob)
            h = next(h for h in snapshot['heroes'] if h['id'] == wire['id'])
            god = HERO_GOD_EQUIP.decode(wire.get('heroGodEquip', b''))
            report['heroes'].append({'id': h['id'], 'bare_stats': hero_attributes(dict(h, id=h.get('battle_base_id', h['id']))),
                'saved_bonuses': decode_bonus(artifact_attributes(h)),
                'saved_fetter_college': other_attributes(SimpleNamespace(db=db), args.player, h),
                'receipt_base_stats': HERO_ATTR.decode(wire.get('heroAttrCount', b'')),
                'receipt_bonuses': decode_bonus(god.get('godEquipAttr', b'')),
                'receipt_beastlords': len(wire.get('heroEquip', [])), 'receipt_suits': len(wire.get('equipSuitAttr', []))})
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
