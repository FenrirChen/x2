"""Origin Paradox's user-approved shop, scoped to the season instance."""
import hashlib
import json
import logging
from importlib.resources import files

from x2server.messages.economy import ECONOMY_SCHEMAS, GOODS
from x2server.network.dispatcher import OutboundMessage
from .economy import UnresolvedEconomy


class SeasonShop:
    def __init__(self, season):
        self.s, self.e, self.store = season, season.e, season.store
        data = json.loads(files('x2server').joinpath('data/origin_season_shop.json').read_text('utf8'))
        self.shop_id = data['shopId']
        self.currency = data['currencyItemId']
        self.currency_type = data['currencyType']
        self.goods = {r['goodsId']: r for r in data['goods']}
        if len(self.goods) != len(data['goods']):
            raise ValueError('duplicate season goods')
        for row in self.goods.values():
            if row['itemId'] not in self.e.items or any(type(row[k]) is not int or row[k] <= 0 for k in ('num', 'price', 'canBuyTimes')):
                raise ValueError(f'invalid season offer {row}')

    def owns(self, name, request):
        return request.get('shopId') == self.shop_id or name == 'C2L_QueryGoodsInfo' and request.get('goodsId') in self.goods

    def unlocked(self, state, row):
        return state['exp'] >= row['unlockLevel'] * self.s.bp['LevelExp']

    def values(self, state, row):
        calendar = self.s.calendar()
        return {'goodsId': row['goodsId'], 'itemId': row['itemId'], 'num': row['num'],
                'price': row['price'], 'originalPrice': row['price'], 'currencyType': self.currency_type,
                'canBuyTimes': row['canBuyTimes'], 'hasBuyTimes': state.get('shop_counts', {}).get(str(row['goodsId']), 0),
                'startTime': calendar['start_sec'], 'endTime': calendar['end_sec'], 'goodsTag': 3, 'limited': 5}

    def listing(self, player):
        self.s.require(player)
        state = self.s.state(player)
        # Original ShopParam2 gates are tied to static GoodsGroupId. Only expose
        # server-unlocked goods, including the extra level-20 speed-card slot.
        rows = sorted(self.goods.values(), key=lambda r: (r['stage'], r['goodsId']))
        return {'code': 10, 'shopId': self.shop_id, 'NextRefreshTime': self.s.calendar()['end_sec'],
                'RefreshTimes': 0, 'RefreshPrice': 0,
                'goods': [GOODS.encode(self.values(state, r)) for r in rows if self.unlocked(state, r)]}

    def activity_listing(self, player):
        from x2server.messages.activity import encode
        listing = self.listing(player)
        return {'code': 10, 'activityType': 4,
                'goodsList': [encode('ActivityShopGoods', {k: v for k, v in listing.items() if k != 'code'})]}

    def buy(self, player, request, key):
        schema = ECONOMY_SCHEMAS['L2C_BuyGoods']
        with self.e.transaction():
            self.s.require(player)
            receipt = self.store.db.execute('SELECT message,response FROM season_receipts WHERE player_id=? AND instance_id=? AND request_key=?',
                                           (player, self.s.instance, key)).fetchone()
            if receipt:
                if receipt['message'] != 'L2C_BuyGoods':
                    raise UnresolvedEconomy('season receipt type mismatch')
                return schema.decode(receipt['response'])
            row = self.goods.get(request.get('goodsId'))
            num = request.get('buyNum', 0)
            state = self.s.state(player)
            if (request.get('shopId') != self.shop_id or row is None or type(num) is not int or not 1 <= num <= 999
                    or not self.unlocked(state, row)):
                raise UnresolvedEconomy('invalid or locked season offer')
            used = state.get('shop_counts', {}).get(str(row['goodsId']), 0)
            if used + num > row['canBuyTimes']:
                raise UnresolvedEconomy('season stock exhausted')
            self.s.spend(player, self.currency, row['price'] * num)
            rewards = self.e._grant(player, f'season:{self.s.instance}:shop:{key}', {row['itemId']: row['num'] * num})
            # _grant also updates season achievements. Reload before writing
            # stock, preserving those rewards/experience/talent changes.
            state = self.s.state(player)
            state.setdefault('shop_counts', {})[str(row['goodsId'])] = used + num
            self.s.write(player, state)
            result = {'code': 10, 'shopId': self.shop_id, 'goodsId': row['goodsId'],
                      'itemId': row['itemId'], 'itemNum': row['num'] * num, 'buyNum': num,
                      'price': row['price'], 'originalPrice': row['price'], 'hasBuyTimes': used + num,
                      'changeItemID': self.currency, 'rewardData': self.e.reward_bytes(rewards)}
            self.e._event(player, f'season-shop:{self.s.instance}:{key}', 24, row['goodsId'], num, self.shop_id)
            self.store.db.execute('INSERT INTO season_receipts VALUES (?,?,?,?,?)',
                                 (player, self.s.instance, key, 'L2C_BuyGoods', schema.encode(result)))
            return result

    async def handle(self, context, packet, name, request):
        player = context.session.player_id
        reply = name.replace('C2L_', 'L2C_', 1)
        try:
            self.s.require(player)
            if name == 'C2L_ShopGoods':
                result = self.listing(player)
            elif name == 'C2L_QueryGoodsInfo':
                row = self.goods.get(request.get('goodsId'))
                state = self.s.state(player)
                if not row or not self.unlocked(state, row):
                    raise UnresolvedEconomy('locked season goods')
                offer = self.values(state, row)
                result = {k: offer[k] for k in ('goodsId', 'price', 'originalPrice', 'hasBuyTimes', 'canBuyTimes', 'currencyType')}
                result.update(code=10, shopId=self.shop_id, itemNum=row['num'])
            elif name == 'C2L_BuyGoods':
                key = hashlib.sha256(f'{context.session.session_id}:{packet.header.request_id}:season-shop'.encode() + packet.body).hexdigest()
                result = self.buy(player, request, key)
            else:
                raise UnresolvedEconomy('season shop has no manual refresh')
        except UnresolvedEconomy as exc:
            logging.getLogger('x2.season').info('season shop rejected player=%s operation=%s reason=%s', player, name, exc)
            return OutboundMessage(reply, {'code': 13, **{k: request[k] for k in ('shopId', 'goodsId', 'buyNum') if k in request}})
        return OutboundMessage(reply, result, pushes=self.e.pushes(player) if name == 'C2L_BuyGoods' else ())
