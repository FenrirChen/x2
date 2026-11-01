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
    # Compatibility policy (PR #87): 影域交易所的「影域礼包」(1203010) 不再限购。
    # 客户端的 CommonShopView_GoodsItem_SetData 把 canBuyTimes 当总库存、
    # 剩余 = canBuyTimes - hasBuyTimes，剩余 <= 0 就地画成售罄；所以「无上限」
    # 必须下发一个大正数而不是 0。背包与回执仍按真实购买次数记账。
    UNLIMITED_ITEM_IDS = frozenset({1203010})
    # Rolling display allowance also respects the server single-request maximum.
    UNLIMITED_STOCK = 9999

    def __init__(self, activity, appearance=None):
        self.activity = activity
        self.economy, self.store, self.rotation = activity.economy, activity.store, activity.rotation
        # 皮肤/外观货品买下后要向客户端补一次形象推送, 见 handle() 里的说明。
        self.appearance = appearance
        data = json.loads(files('x2server').joinpath('data/activity_exchange_catalog.json').read_text(encoding='utf8'))
        # One effective price feeds listing, popup, receipt and actual spending.
        for shop in data['shops']:
            for offer in shop['goods']:
                offer['price'] //= 2
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
        if self.activity.shop_unlock_override(period):
            return True
        rule = shop['unlock']
        if rule['kind'] == 'none':
            return True
        if rule['kind'] == 'period_item':
            return all(self.rotation.get(player, period, 'obtained-item', i, 0) > 0 for i in rule['items'])
        if rule['kind'] == 'chapter_pass':
            sections = self.activity.chapters[rule['chapter']].get('SectionID', [])
            return bool(sections) and all(self.rotation.get(player, period, 'clear', s, 0) > 0 for s in sections)
        if rule['kind'] == 'item_count':
            # Native YueXiModule.GetHaveChipNum counts distinct owned IDs;
            # duplicates and period receipt counters are not extra souls.
            items = set(rule['items'])
            owned = self.store.db.execute(
                'SELECT item_id,quantity FROM inventory WHERE player_id=?', (player,))
            return sum(item in items and quantity > 0 for item, quantity in owned) >= rule['count']
        if rule['kind'] == 'memory_count':
            # Fragments do not cease being collected when their story item is used.
            return sum(bool(self.rotation.get(player, period, 'obtained-item', 1290100 + n, 0))
                       for n in range(1, 25)) >= rule['count']
        return False

    def count(self, player, period, goods):
        return self.rotation.get(player, period, 'shop-count', goods, 0)

    def stock(self, offer, bought=0):
        """单件商品的库存上限; 不限购的商品返回大正数 (见 UNLIMITED_ITEM_IDS)。"""
        if offer['itemId'] in self.UNLIMITED_ITEM_IDS:
            return min(2147483647, bought + self.UNLIMITED_STOCK)
        return offer['canBuyTimes']

    def goods_values(self, player, period, row):
        bought = self.count(player, period, row['goodsId'])
        return {'goodsId': row['goodsId'], 'itemId': row['itemId'], 'num': row['num'],
                'price': row['price'], 'originalPrice': row['price'], 'currencyType': row['currencyType'],
                'canBuyTimes': self.stock(row, bought), 'hasBuyTimes': bought,
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
            if offer['itemId'] not in self.UNLIMITED_ITEM_IDS and bought + count > self.stock(offer):
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
            # Broadcast authoritative purchases to all task systems.
            # This prefix excludes supply-shop-only achievement counters.
            event_key = f'activity-shop-buy:{request_key}'
            if getattr(self.economy, 'activity', None) is not self.activity:
                self.activity.event(player, event_key, 24, goods_id, count, shop_id, period=period)
            self.economy._event(player, event_key, 24, goods_id, count, shop_id)
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
            # 购买成功后不再补推整包 L2C_ActivityShop。客户端 ShopModule.ReceiveActivityShop
            # (@0x17A7B10) 收完会把商品写进缓存并 FireEvent(0xb9)，CommonShopView 对 0xb9
            # 注册的处理器是 RefreshShopData (@0x01844014)，它重建整个 LoopListView2 并
            # MovePanelToItemIndex(GetCurrentShopIndex(), 0)，于是每买一次列表就被拉回
            # 当前页顶部 (「每次兑换后位置重置」)。L2C_BuyGoods 回执本身已把 hasBuyTimes
            # 写回活动商店缓存条目并触发 0x29，客户端只刷新被买的格子
            # (CommonShopView.OnHandleBuyGoodsRes)，所以回执足够。
            # 副作用: 活动阶段「解锁状态」不再随购买即时重绘, 要重进活动页才重算;
            # 整包里锁着的阶段本来也照常下发 (listing(preview=True)), 解锁判定在客户端
            # 本地按持有物计算, 因此通常无感。赛季商店与本仓库离线端 router.cpp 的
            # C2L_BuyGoods 同样只回购买回执、不推活动商店列表。
            pushes = []
            # 皮肤/外观货品: 客户端的外观页只按 L2C_HeroSkinAll / L2C_HeroSkinUpdate
            # 重读已拥有的形象 (见 player/appearance_shop.py 售出后的推送, 以及离线端
            # router.cpp 买皮肤后两条都推)。只回 L2C_BuyGoods 的话, 货确实进了背包,
            # 但外观页会一直显示「未获得」, 直到重新登录。
            pushed_item = result.get('itemId') if isinstance(result, dict) else None
            if self.appearance is not None and pushed_item in self.appearance.skins:
                from x2server.messages.appearance import HERO_SKIN
                hero = self.appearance.skins[pushed_item]['hero_id']
                skin_list = self.appearance.skin_values(player)['skinList']
                pushes.append(OutboundMessage('L2C_HeroSkinAll', {'skinList': skin_list}))
                entry = next((value for value in skin_list
                              if HERO_SKIN.decode(value)['heroId'] == hero), None)
                if entry is not None:
                    pushes.append(OutboundMessage('L2C_HeroSkinUpdate', {'skin': entry}))
            pushes = tuple(pushes)
        return OutboundMessage(response, result, pushes=pushes,
                               before_response=self.economy.pushes(player) if name == 'C2L_BuyGoods' else ())
