"""Recover course equipment quality from Gift.GiftShow -> Item.ItemQuality."""
import json
from pathlib import Path

from analysis.progression.probe import read_tables


def main():
    target = Path(__file__).resolve().parents[2] / 'src/x2server/data/activity_center.json'
    data = json.loads(target.read_text(encoding='utf-8'))
    tables, _, _ = read_tables(['Gift', 'Item'])
    items = {r['ItemID']: r for r in tables['Item']}
    groups = {g for track in ('freeGiftGroups', 'paidGiftGroups')
              for gifts in data['courseActivity'][track] for g in gifts}
    stars = {}
    for row in tables['Gift']:
        if row['GiftGroup'] not in groups:
            continue
        if not any(items[i]['ItemType']['value'] == 10 for i in row['GiftValue']):
            continue
        for item, display in zip(row['GiftValue'], row.get('GiftShow', []), strict=True):
            if items[item]['ItemType']['value'] != 10:
                continue
            quality = items[display]['ItemQuality']['value']
            assert 1 <= quality <= 6
            stars.setdefault(str(row['GiftGroup']), {})[str(item)] = quality
    data['courseActivity']['equipmentGiftStars'] = stars
    data['courseActivity']['equipmentGiftStarsSource'] = 'Canonical Gift.GiftShow -> Item.ItemQuality; 710050/51=4, 710038/39=5, 710044/45=6.'
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(stars)


if __name__ == '__main__':
    main()
