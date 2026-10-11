"""Atomic, period-limited purchases from the user-recovered themed shops."""
import hashlib
import json
from importlib.resources import files

from x2server.messages.activity import encode
from x2server.messages.economy import ECONOMY_SCHEMAS, GOODS
from x2server.network.dispatcher import OutboundMessage
from x2server.protocol.errors import ProtocolError
from .economy import UnresolvedEconomy


class ActivityExchange:
    def __init__(self, activity):
        self.activity = activity
        self.economy, self.store, self.rotation = activity.economy, activity.store, activity.rotation
        data = json.loads(files('x2server').joinpath('data/activity_exchange_catalog.json').read_text(encoding='utf8'))
        self.shops = {s['shopId']: s for s in data['shops']}
        self.goods = {g['goodsId']: (s, g) for s in data['shops'] for g in s['goods']}
        if len(self.goods) != sum(len(s['goods']) for s in data['shops']):
            raise ValueError('duplicate activity goods IDs')
        for _, row in self.goods.values():
            if (row['itemId'] not in self.economy.items or row['currencyItemId'] not in self.economy.items
                    or any(type(row[k]) is not int or row[k] <= 0 for k in ('price', 'num', 'canBuyTimes'))):
                raise ValueError('invalid activity shop offer')

    def owns(self, name, request):
        return (request.get('shopId') in self.shops or
                name == 'C2L_QueryGoodsInfo' and request.get('goodsId') in self.goods)

    def unlocked(self, player, period, shop):
        if shop['group'] != period.theme['group']:
            return False
        rule = shop['unlock']
        if rule['kind'] == 'none':
            return True
        if rule['kind'] == 'period_item':
            return all(self.rotation.get(player, period, 'obtained-item', i, 0) > 0 for i in rule['items'])
        if rule['kind'] == 'chapter_pass':
            sections = self.activity.chapters[rule['chapter']].get('SectionID', [])
            return bool(sections) and all(self.rotation.get(player, period, 'clear', s, 0) > 0 for s in sections)
        if rule['kind'] == 'memory_count':
            # Fragments do not cease being collected when their story item is used.
            return sum(bool(self.rotation.get(player, period, 'obtained-item', 1290100 + n, 0))
                       for n in range(1, 25)) >= rule['count']
        return False

    def count(self, player, period, goods):
        return self.rotation.get(player, period, 'shop-count', goods, 0)

    def goods_values(self, player, period, row):
        return {'goodsId': row['goodsId'], 'itemId': row['itemId'], 'num': row['num'],
                'price': row['price'], 'originalPrice': row['price'], 'currencyType': row['currencyType'],
                'canBuyTimes': row['canBuyTimes'], 'hasBuyTimes': self.count(player, period, row['goodsId']),
                'startTime': period.start, 'endTime': period.end, 'goodsTag': row['goodsTag'], 'limited': row['limited']}

    def listing(self, player, shop_id, *, preview=False):
        period = self.activity.period(player)
        shop = self.shops.get(shop_id)
        if (shop is None or shop['group'] != period.theme['group']
                or not preview and not self.unlocked(player, period, shop)):
            raise UnresolvedEconomy('activity shop is closed or locked')
        return {'code': 10, 'shopId': shop_id, 'NextRefreshTime': period.end,
                'RefreshTimes': 0, 'RefreshPrice': 0,
                'goods': [GOODS.encode(self.goods_values(player, period, r)) for r in shop['goods']]}

    def activity_listing(self, player, activity_type):
        period = self.activity.period(player)
        family = 2 if period.theme['group'] == 7 else 1 if period.theme['group'] == 99 else 3
        if activity_type != family:
            raise UnresolvedEconomy('wrong activity family')
        # The native shop navigation needs locked stages too. Listing is a
        # preview; querying purchasable details and buying still enforce gates.
        rows = [self.listing(player, s['shopId'], preview=True)
                for s in sorted(self.shops.values(), key=lambda s: s['stage'])
                if s['group'] == period.theme['group']]
        if not rows:
            raise UnresolvedEconomy('no recovered exchange shop for current theme')
        return {'code': 10, 'activityType': activity_type,
                'goodsList': [encode('ActivityShopGoods', {key: value for key, value in r.items()
                                                         if key != 'code'}) for r in rows]}

    def buy(self, player, shop_id, goods_id, count, request_key):
        period = self.activity.period(player)
        # Same request replays the original response, including when it arrived
        # just before the boundary. It never buys again in the next period.
        cached = self.store.db.execute('''SELECT message,response FROM activity_receipts
            WHERE player_id=? AND request_key=?''', (player, request_key)).fetchone()
        if cached:
            if cached['message'] != 'L2C_BuyGoods':
                raise UnresolvedEconomy('receipt belongs to another operation')
            return ECONOMY_SCHEMAS['L2C_BuyGoods'].decode(cached['response'])
        match = self.goods.get(goods_id)
        if (match is None or match[0]['shopId'] != shop_id or type(count) is not int
                or not 1 <= count <= 9999 or not self.unlocked(player, period, match[0])):
            raise UnresolvedEconomy('unknown, locked or mismatched offer')
        _, offer = match
        with self.economy.transaction():
            bought = self.count(player, period, goods_id)
            if bought + count > offer['canBuyTimes']:
                raise UnresolvedEconomy('activity stock exhausted')
            self.activity.spend(player, period, offer['currencyItemId'], offer['price'] * count,
                                f'shop-spend:{request_key}')
            rewards = {offer['itemId']: offer['num'] * count}
            # Jewels are stackable bag entries already supported by JewelCompose.
            kind = self.economy.items[offer['itemId']].get('ItemType', {}).get('value')
            if kind == 11:
                from .progression import jewel_ids
                if offer['itemId'] not in jewel_ids():
                    raise UnresolvedEconomy('unrecognized jewel')
            rewards = self.economy._grant(player,
                self.activity.source(period, 'shop', request_key), rewards,
                stackable_types=(11,) if kind == 11 else ())
            self.activity.obtained(player, period, rewards, f'shop:{request_key}')
            self.rotation.put(player, period, 'shop-count', goods_id, bought + count)
            self.activity.event(player, f'shop-buy:{request_key}', 24, goods_id, count, period=period)
            result = {'code': 10, 'shopId': shop_id, 'goodsId': goods_id,
                'itemId': offer['itemId'], 'itemNum': offer['num'] * count, 'buyNum': count,
                'price': offer['price'], 'originalPrice': offer['price'], 'hasBuyTimes': bought + count,
                'rewardData': self.economy.reward_bytes(rewards)}
            self.store.db.execute('INSERT INTO activity_receipts VALUES (?,?,?,?,?)',
                (player, request_key, period.index, 'L2C_BuyGoods', ECONOMY_SCHEMAS['L2C_BuyGoods'].encode(result)))
        return result

    async def handle(self, context, packet, name, request):
        player = context.session.player_id
        if player is None:
            raise ProtocolError('activity shop requested before login')
        response = name.replace('C2L_', 'L2C_', 1)
        try:
            if name == 'C2L_ShopGoods':
                result = self.listing(player, request.get('shopId', 0))
            elif name == 'C2L_QueryGoodsInfo':
                match = self.goods.get(request.get('goodsId'))
                if match is None:
                    raise UnresolvedEconomy('unknown goods')
                shop, offer = match
                period = self.activity.period(player)
                if not self.unlocked(player, period, shop):
                    raise UnresolvedEconomy('shop locked')
                values = self.goods_values(player, period, offer)
                result = {'code': 10, 'shopId': shop['shopId'], 'itemNum': offer['num'],
                    **{key: values[key] for key in ('goodsId', 'price', 'originalPrice',
                        'hasBuyTimes', 'canBuyTimes', 'currencyType')}}
            elif name == 'C2L_BuyGoods':
                key = hashlib.sha256(f'{context.session.session_id}:{packet.header.request_id}:{name}'.encode()
                                     + packet.body).hexdigest()
                result = self.buy(player, request.get('shopId', 0), request.get('goodsId', 0),
                                  request.get('buyNum', 0), key)
            else:
                raise UnresolvedEconomy('activity stock refresh is not supported')
        except UnresolvedEconomy:
            return OutboundMessage(response, {'code': 13, **request})
        pushes = ()
        if name == 'C2L_BuyGoods':
            # Refresh the owning activity module's entire stock cache, including
            # its selected popup item, rather than only the visible shop cell.
            period = self.activity.period(player)
            family = 2 if period.theme['group'] == 7 else 1 if period.theme['group'] == 99 else 3
            pushes = (OutboundMessage('L2C_ActivityShop', self.activity_listing(player, family)),)
        return OutboundMessage(response, result, pushes=pushes,
                               before_response=self.economy.pushes(player) if name == 'C2L_BuyGoods' else ())
