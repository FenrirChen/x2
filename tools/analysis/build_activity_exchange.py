"""User-supplied exchange lists, 2026-10-10. No inferred reward quantities."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Short labels are only source shorthand; delivered items use verified APK IDs.
ITEMS = dict(wish=1237914, pure=1237925, power=1237900, gold=1237901,
    exp=1237907, beast=1237906, moon=1237912, dust=1237801, branch=1237802,
    iron=1237803, soil=1237804, wood=1237805, alloy=1237806,
    speed10=1237831, speed1=1237832, speed2=1237833, speed4=1237834, speed8=1237835,
    soul1=1238100, soul2=1238101, soul3=1238102, soul4=1238103, soul5=1238104, soul6=1238105,
    air=1238047, copper=1238048, silver=1238049, particle_gold=1238050, crystal=1238051,
    gift1=1203001, gift2=1203002, gift3=1203003, random3=1203000,
    tools=1204048, battery=1237922, blank=1202080, sword=1202081, cup=1202082,
    star=1202083, wand=1202084, paraiba=1251070, horus=1251140, kushan=1251170,
    sun3=1250073, moon3=1250083, cat3=1250093, green3=1250103,
    storage=1204054, sand=1202085, shard=1203004, bird=1204044,
    guitar=1204045, light=1221003, traveller=1260007, shadow_gift=1203010)
for tier, start in [('c', 1238052), ('s', 1238056), ('g', 1238060), ('x', 1238064)]:
    for part, offset in [('sword', 0), ('wand', 1), ('cup', 2), ('star', 3)]:
        ITEMS[tier + part] = start + offset
for n in range(1, 25):
    ITEMS[f'memory{n}'] = 1290100 + n

# label, amount delivered per exchange, period stock, cost per exchange.
WINTER = [
'''wish 1 2 450; power 20 25 25; gold 5000 40 25; exp 400 25 10;
dust 4 25 15; branch 4 25 30; speed10 2 72 10; speed1 1 24 30;
soul1 4 30 10; soul2 4 30 20; air 2 18 15; copper 1 18 15;
tools 1 5 300; csword 6 6 75; cwand 6 6 75; ccup 6 6 75; cstar 6 6 75;
gift1 1 20 150; battery 20 5 50; gold 1000 9999 10''',
'''wish 1 3 450; power 20 50 25; gold 10000 50 50; exp 400 50 10;
iron 2 40 30; soil 2 30 60; speed2 1 12 60; speed4 1 6 120;
blank 1 5 150; sword 1 5 300; cup 1 5 300; star 1 5 300; wand 1 5 300;
soul3 3 30 30; soul4 3 20 60; copper 1 18 15; silver 1 12 30;
sun3 1 1 2250; moon3 1 1 2250; tools 1 8 300;
ssword 6 6 150; swand 6 6 150; scup 6 6 150; sstar 6 6 150;
gift2 1 15 300; battery 20 5 50; gold 1000 9999 10''',
'''paraiba 1 50 500; random3 1 1 18000; wish 1 5 450; power 60 25 75;
gold 10000 80 50; exp 400 50 10; wood 1 30 60; alloy 1 12 150;
speed8 1 6 240; blank 1 5 150; sword 1 5 300; cup 1 5 300; star 1 5 300; wand 1 5 300;
soul5 3 20 120; silver 1 24 30; particle_gold 1 18 60;
cat3 1 1 2250; green3 1 1 2250; tools 1 12 300;
gsword 1 18 50; gwand 1 18 50; gcup 1 18 50; gstar 1 18 50;
gift3 1 10 300; battery 20 5 50; sand 1 9999 50; gold 1000 9999 10''']

OSIRIS = [
'''wish 1 1 324; pure 1 1 324; power 30 10 27; dust 10 5 27; branch 10 5 54;
speed10 3 10 12; speed1 3 6 66; air 3 6 18; copper 3 6 33;
csword 4 6 36; cwand 4 6 36; ccup 4 6 36; cstar 4 6 36;
soul1 10 12 18; soul2 10 12 36; gift1 1 10 108;
gold 10000 8 36; beast 1000 5 90; exp 5000 4 90; moon 100 5 72''',
'''wish 1 1 324; pure 1 1 324; power 30 15 27; horus 1 15 360;
iron 5 10 54; soil 5 10 108; speed2 1 12 44; silver 3 6 65;
ssword 3 6 54; swand 3 6 54; scup 3 6 54; sstar 3 6 54;
soul3 10 12 72; soul4 10 12 144; blank 1 5 108;
sword 1 5 216; cup 1 5 216; star 1 5 216; wand 1 5 216;
gift2 1 10 216; gold 10000 12 36; beast 1000 5 90; exp 5000 4 90; moon 100 5 72''',
'''wish 1 1 324; pure 1 1 324; power 30 20 27; horus 1 15 360;
wood 3 10 130; speed4 1 6 87; particle_gold 3 6 130;
gsword 3 6 108; gwand 3 6 108; gcup 3 6 108; gstar 3 6 108;
soul5 10 12 288; blank 1 5 108; sword 1 5 216; cup 1 5 216; star 1 5 216; wand 1 5 216;
gift3 1 10 540; gold 10000 15 36; beast 1000 5 90; exp 5000 6 90; moon 100 5 72''',
'''wish 1 2 324; pure 1 2 324; power 30 25 27; random3 1 1 12960;
horus 1 20 360; alloy 2 10 260; speed8 1 4 173; crystal 2 6 260;
xsword 2 6 216; xwand 2 6 216; xcup 2 6 216; xstar 2 6 216;
soul6 5 12 432; blank 1 10 108; sword 1 10 216; cup 1 10 216; star 1 10 216; wand 1 10 216;
storage 1 10 360; gold 10000 15 36; beast 1000 5 90; exp 5000 6 90; moon 100 5 72;
sand 1 999 36''']

SAKURA1 = '''wish 1 1 180; pure 1 1 180; power 30 10 15; dust 10 6 15; branch 10 6 30;
beast 1000 5 50; gold 10000 8 20; exp 5000 4 50; moon 100 5 40;
speed10 3 10 6; speed1 3 6 36; air 3 6 9; copper 3 6 18;
csword 4 6 20; cwand 4 6 20; ccup 4 6 20; cstar 4 6 20;
soul1 10 12 10; soul2 10 12 20; gift1 1 10 60'''

MOON = [
'''power 30 10 15; gold 10000 10 20; exp 1000 10 10; dust 10 10 15; branch 5 10 15;
speed10 1 100 2; speed1 1 50 12; moon 100 50 40; gift1 1 10 60''',
'''power 30 20 15; gold 10000 20 20; exp 1000 10 10; iron 5 10 30; speed2 1 25 24;
soul1 5 30 5; air 5 20 15; moon 200 50 80; gift2 1 10 120; wish 1 2 180;
shard 1 15 200; blank 1 20 60''',
'''power 60 30 30; gold 20000 30 40; exp 2000 10 20; soil 5 10 60; speed4 1 10 48;
soul2 5 20 10; copper 5 10 30; csword 5 10 25; cwand 5 10 25; ccup 5 10 25; cstar 5 10 25;
beast 200 50 10; gift3 1 10 300; bird 1 10 200; wish 1 3 180; shard 1 15 200;
sword 1 10 120; cup 1 10 120; star 1 10 120; wand 1 10 120; light 1 1 2400''',
'''power 60 40 30; gold 20000 40 40; exp 2000 20 20; wood 3 10 72; speed8 1 10 96;
soul3 5 20 20; silver 3 10 36; ssword 3 10 30; swand 3 10 30; scup 3 10 30; sstar 3 10 30;
beast 500 50 25; gift1 1 10 60; gift2 1 10 120; gift3 1 10 300; guitar 1 10 200;
wish 1 4 180; shard 1 20 200; sword 1 10 120; cup 1 10 120; star 1 10 120; wand 1 10 120;
shadow_gift 1 999 100; random3 1 1 7200; traveller 1 1 1200''']


def parse(text):
    return [(label, int(amount), int(stock), int(price))
            for label, amount, stock, price in (chunk.split() for chunk in text.split(';') if chunk.strip())]


def main():
    static = json.loads((ROOT / 'src/x2server/data/activity_rotation_catalog.json').read_text(encoding='utf8'))
    item_rows = {r['ItemID']: r for r in static['tables']['Item']}
    shops = []
    themes = [(7, '冬至万物', 860, 1237985, 985, WINTER),
              (33, '伪生樱之岛', 871, 1237978, 982, [SAKURA1] + OSIRIS[1:]),
              (13, '全景裂隙', 876, 1237982, 982, OSIRIS),
              (99, '日月盈仄', 887, 1237989, 989, MOON)]
    for group, title, start_shop, currency, currency_type, stages in themes:
        for stage, source in enumerate(stages, 1):
            shop_id = start_shop + stage - 1
            rows = parse(source)
            if group == 99 and stage < 4:
                rows += [(f'memory{n}', 1, 1, 660) for n in range(stage * 6 + 1, (stage + 1) * 6 + 1)]
            goods = []
            for index, (label, amount, stock, price) in enumerate(rows, 1):
                item = ITEMS['kushan' if group == 33 and label == 'horus' else label]
                if item not in item_rows:
                    raise ValueError(f'missing item {label}/{item}')
                derived = group == 33 and stage > 1
                if derived:
                    price = max(1, price * 5 // 9)
                goods.append({'goodsId': 9000000 + shop_id * 100 + index, 'itemId': item,
                    'num': amount, 'canBuyTimes': stock, 'price': price,
                    'currencyItemId': currency, 'currencyType': currency_type,
                    'goodsTag': 3, 'limited': 5,
                    'provenance': 'USER_DECISION: Osiris * 5/9 floor; Horus -> Kushan' if derived else 'USER_SUPPLIED 2026-10-10'})
            if group == 99:
                unlock = {'kind': 'memory_count', 'count': stage * 6}
            elif stage == 1:
                unlock = {'kind': 'none'}
            elif group == 33:
                unlock = {'kind': 'period_item', 'items': [1104001 + 10 * (stage - 1)],
                          'source': 'ShopConfig.ShopParam2/3'}
            else:
                chapter = ({2: 2060251, 3: 2060261} if group == 7 else
                           {2: 2060511, 3: 2060521, 4: 2060531})[stage]
                unlock = {'kind': 'chapter_pass', 'chapter': chapter,
                          'source': 'ShopConfig.ShopParam2' if group == 7 else 'REVIVAL_COMPAT: previous chapter'}
            shops.append({'group': group, 'theme': title, 'shopId': shop_id, 'stage': stage,
                          'unlock': unlock, 'goods': goods})
    data = {'status': 'USER_SUPPLIED / USER_DECISION',
            'sakura_price_ratio': {'numerator': 5, 'denominator': 9, 'rounding': 'floor'},
            'notes': ['Winter fallback gold consumes 10 wooden parts in every stage.',
                      'Winter refresh ticket is 1202085.', 'Sakura raw jewel is 1251170.',
                      'Moon stage 4 mini gift cost is the supplied unit price 60; total 6000 is an arithmetic typo.',
                      'Moon 原石碎片 aliases 原石残片 1203004.',
                      'Goods IDs in the 9-million range are stable compatibility identifiers; client acceptance must be verified before advertisement.'],
            'shops': shops}
    target = ROOT / 'src/x2server/data/activity_exchange_catalog.json'
    target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
    print([(s['shopId'], len(s['goods'])) for s in shops])


if __name__ == '__main__':
    main()
