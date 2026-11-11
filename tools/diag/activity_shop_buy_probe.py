"""只读探针: 逐个商品试买活动兑换商店, 打印失败原因。

客户端把 code != 10 全显示成「操作失败」, 单看截图无法区分是 shopId 不匹配、
库存耗尽、解锁未达成还是发奖异常。这个脚本在**存档副本**上把每个商品各买一次并
打印真实原因, 用来验证修复。

用法 (仓库根目录):
    python tools/diag/activity_shop_buy_probe.py --db ../save/demo.sqlite3
    python tools/diag/activity_shop_buy_probe.py --db save.sqlite3 --shops 876 877
"""
import argparse
import os
import sqlite3
import sys
import tempfile
from pathlib import Path


def snapshot_database(source, target):
    """Include committed WAL data while leaving the inspected source read-only."""
    with sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True) as origin:
        with sqlite3.connect(target) as destination:
            origin.backup(destination)

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'src'))

from x2server.player.activity import ActivityService            # noqa: E402
from x2server.player.activity_exchange import ActivityExchange  # noqa: E402
from x2server.player.activity_rotation import ActivityRotation   # noqa: E402
from x2server.player.economy import EconomyService, UnresolvedEconomy  # noqa: E402
from x2server.player.store import PlayerStore                    # noqa: E402


def find_period_start(store, group):
    """找到主题 group 匹配的活动周期起点。"""
    rotation = ActivityRotation(store, lambda: 0)
    for index in range(0, 21):
        start = rotation.ANCHOR + index * rotation.SECONDS
        period = rotation.at(start)
        if period is not None and period.theme['group'] == group:
            return start, period
    raise SystemExit(f'no activity period with group {group} in the next 21 slots')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, help='存档 sqlite 路径 (会被复制, 不会写原库)')
    parser.add_argument('--player', type=int, default=None, help='玩家 ID, 默认取最小的一个')
    parser.add_argument('--shops', type=int, nargs='*', default=[876, 877, 878, 879])
    parser.add_argument('--group', type=int, default=13, help='活动主题组号, 默认 13 (全景裂隙)')
    parser.add_argument('--no-grant', action='store_true', help='不预先补足货币, 保持原样')
    args = parser.parse_args()

    os.environ.pop('X2_ACTIVITY_ANCHOR', None)
    source = Path(args.db).resolve()
    if not source.exists():
        raise SystemExit(f'missing db: {source}')
    workdir = Path(tempfile.mkdtemp(prefix='shop-probe-'))
    copy = workdir / source.name
    snapshot_database(source, copy)
    print(f'copy: {copy}')

    store = PlayerStore(copy)
    players = [row[0] for row in store.db.execute('SELECT id FROM players ORDER BY id')]
    player = args.player if args.player is not None else players[0]
    if player not in players:
        raise SystemExit(f'player {player} not in {players}')

    start, period = find_period_start(store, args.group)
    economy = EconomyService(store)
    economy.clock = lambda: start + 60
    activity = ActivityService(economy)
    exchange = ActivityExchange(activity)
    snapshot = store.get(player)['snapshot']
    if snapshot.get('level', 0) < 17:
        store.save_snapshot(player, dict(snapshot, level=60), store.get(player)['revision'])
    print(f'player={player} period={period.index} theme={period.theme["title"]} group={period.theme["group"]}')
    print(f'goods catalog: {len(exchange.goods)} offers in {len(exchange.shops)} shops')

    if not args.no_grant:
        for shop_id in args.shops:
            shop = exchange.shops.get(shop_id)
            if shop is None:
                continue
            currency = shop['goods'][0]['currencyItemId']
            economy._grant(player, f'probe:currency:{shop_id}', {currency: 5_000_000})

    failures = 0
    for shop_id in args.shops:
        shop = exchange.shops.get(shop_id)
        if shop is None:
            print(f'shop {shop_id}: NOT IN CATALOG')
            continue
        print(f'\n== shop {shop_id} (stage {shop["stage"]}, unlock {shop["unlock"]["kind"]}) ==')
        for goods in shop['goods']:
            key = f'probe:{shop_id}:{goods["goodsId"]}'
            try:
                result = exchange.buy(player, shop_id, goods['goodsId'], 1, key)
                print(f'  {goods["goodsId"]} item={goods["itemId"]:<9} OK   code={result["code"]}')
            except UnresolvedEconomy as exc:
                failures += 1
                print(f'  {goods["goodsId"]} item={goods["itemId"]:<9} FAIL {exc}')
            except Exception as exc:  # noqa: BLE001 - 探针需要暴露任何异常
                failures += 1
                print(f'  {goods["goodsId"]} item={goods["itemId"]:<9} FAIL {type(exc).__name__}: {exc}')
    print(f'\nfailures: {failures}')
    store.close()
    print(f'(temp copy kept at {workdir})')


if __name__ == '__main__':
    main()
