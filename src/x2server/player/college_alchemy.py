"""Persisted CollegeRecipe production and capped official element recovery."""
from collections import Counter
from functools import lru_cache
from importlib.resources import files
import hashlib
import json
import random
import struct
import uuid
import math

# MainModule.ServerData ctor 0x13cd238 supplies Energy=600. CollegeModule
# IsEnergyRecover uses it as SECONDS, although its UI timer polls in milliseconds.
ENERGY_PERIOD = 600


def settle_energy(state, now, catalog):
    anchor = int(state.get('star_gain_time', 0))
    if anchor <= 0 or anchor > now:
        anchor = now
    cap = catalog.effect(state, 702, 5)[0]
    speed = catalog.effect(state, 702, 4, star=True)[0]
    number = max(0, min(cap, int(state.get('star_energy', 0))))
    ticks = (now - anchor) // ENERGY_PERIOD
    number = min(cap, number + ticks * speed)
    state['star_energy'] = number
    state['star_gain_time'] = now if number == cap else anchor + ticks * ENERGY_PERIOD

from x2server.messages.college import ALCHEMY_RECIPE_BAR_DATA
from x2server.messages.lobby import ELEMENT, MISSION_PAIR, PRODUCTION_BAR
from x2server.network.dispatcher import OutboundMessage
from .college_upgrade import UpgradeCatalog, _catalog


@lru_cache(maxsize=1)
def rules():
    return json.loads(files('x2server').joinpath('data/college_alchemy_rules.json').read_text(encoding='utf8'))


def settle_elements(state, now, catalog):
    """Keep fractional periods; full stores never bank overflow or decades of time."""
    alchemy = state.setdefault('alchemy', {})
    from .task_calendar import task_period
    day, _ = task_period(1, now)
    old_day = alchemy.get('element_buy_day', day)
    alchemy['element_buy_day'] = day
    existing = {r['elementId']: r for r in alchemy.get('elements', [])}
    speeds = catalog.effect(state, 703, 16)
    capacities = catalog.effect(state, 706, 12)
    elements = []
    for index, element_id in enumerate(range(991, 997)):
        cap, speed = capacities[index], speeds[index]
        row = dict(existing.get(element_id, {}))
        anchor = int(row.get('lastRecoverTime', alchemy.get('element_epoch', now)))
        if anchor <= 0 or anchor > now:
            anchor = now
        number = max(0, min(cap, int(row.get('num', 0))))
        period = int(rules()['params'][f'Element{index + 1:02}'])
        ticks = (now - anchor) // period
        number = min(cap, number + ticks * speed)
        anchor = now if number == cap else anchor + ticks * period
        elements.append({'elementId': element_id, 'num': number,
                         'lastRecoverTime': anchor,
                         'buyTimesDay': int(row.get('buyTimesDay', 0)) if old_day == day else 0})
    alchemy['elements'] = elements


class AlchemyService:
    FLOWS = ('MakeItem', 'AlchemyCollect', 'AlchemyOnekeyCollect', 'MakIngSpeed',
             'AlchemyFinish', 'AlchemyBuy', 'AlchemyButtonClick')
    # USER_DECISION 2026-10-02: one proficiency point per collected item.
    # The official Exp vector supplies thresholds, not the gain amount.
    EXPERIENCE_PER_ITEM = 1

    def __init__(self, repository, economy, snapshot):
        self.repo, self.economy, self.snapshot = repository, economy, snapshot
        self.db = repository.store.db
        self.recipes = {r['RecipeID']: r for r in _catalog()['recipes']}
        self.element_items = {r['ItemID']: r['EffData'][0] for r in rules()['items']}
        with repository.transaction():
            self.db.execute('''CREATE TABLE IF NOT EXISTS college_alchemy_receipts (
                player_id INTEGER NOT NULL, receipt_key TEXT NOT NULL, digest TEXT NOT NULL,
                response TEXT NOT NULL, PRIMARY KEY(player_id,receipt_key))''')

    @staticmethod
    def phase(recipe, exp):
        # Preserve the client's display phase, which caps at Count - 1.
        thresholds = recipe.get('Exp', [])
        return min(sum(exp >= threshold for threshold in thresholds), max(0,len(thresholds)-1))

    def effects(self, recipe, exp, kind):
        phase = self.phase(recipe, exp)
        # The server restores the fifth-slot yield perk when the final threshold
        # is met, without changing the client's displayed phase semantics.
        if kind == 5 and recipe.get('Exp') and exp >= recipe['Exp'][-1]:
            phase = 5
        values = []
        for index in range(1, phase + 1):
            if recipe.get(f'RecipeEffect{index}') == kind:
                values.extend(recipe.get(f'RecipeEffectParam{index}', []))
        return values

    def recipe_exp(self, state):
        alchemy = state['alchemy']
        exp = {int(pair['Key']): int(pair['Value']) for pair in alchemy.get('recipe_exp', [])}
        for recipe in self.recipes.values():
            if recipe['RecipeLevel'] == 1:
                exp.setdefault(recipe['RecipeID'], 0)
        # Building 707's E_Building07Recipe governs furnace recipes (292xx),
        # not CollegeRecipe (360xx). Native RefreshRecipeMaxUnlock 0x189caa4
        # derives alchemy tiers exclusively from non-negative recipe experience.
        # Walk to a fixed point so an existing save can recover an entire chain
        # without another collection or losing its accumulated experience.
        pending = [(rid, value) for rid, value in exp.items() if rid in self.recipes and value >= 0]
        visited = set()
        while pending:
            rid, value = pending.pop()
            if rid in visited:
                continue
            visited.add(rid)
            for unlocked in self.effects(self.recipes[rid], value, 3):
                if unlocked in self.recipes:
                    if exp.get(unlocked, -1) < 0:
                        exp[unlocked] = 0
                    pending.append((unlocked, exp[unlocked]))
        alchemy['recipe_exp'] = [{'Key': rid, 'Value': value} for rid, value in sorted(exp.items())]
        return exp

    def slots(self, state):
        return self.repo.catalog.effect(state, 701, 7, star=True)[0]

    def production_wire(self, bar):
        return PRODUCTION_BAR.encode({'recipeId': bar.get('recipeId', 0),
            'endTime': bar.get('endTime', 0), 'buffId': bar.get('buffId') or [0]})

    def snapshot_fields(self, state):
        exp = self.recipe_exp(state)
        bars = state['alchemy'].get('production_bars', [])
        # Presence in the native dictionary means unlocked. Negative placeholders
        # also collide with CheckRecipeUpgrade.Dictionary.Add on collection.
        return {'recipeIdExp': [MISSION_PAIR.encode({'Key': rid, 'Value': value})
                    for rid, value in sorted(exp.items()) if rid in self.recipes and value >= 0],
                'productionBars': [self.production_wire(bars[pos] if pos < len(bars) and bars[pos] else {})
                                   for pos in range(self.slots(state))],
                'elements': [ELEMENT.encode(row) for row in state['alchemy']['elements']]}

    def _make(self, player_id, state, request):
        pos, rid = request.get('posIndex', 0), request.get('recipeId', 0)
        values = {'code': 13, 'posIndex': pos}
        exp = self.recipe_exp(state)
        recipe = self.recipes.get(rid)
        if not 0 <= pos < self.slots(state) or not recipe or exp.get(rid, -1) < 0:
            return values
        bars = state['alchemy'].setdefault('production_bars', [])
        if pos < len(bars) and bars[pos]:
            return dict(values, code=206)
        costs = Counter()
        for item, count in zip(recipe['ItemGroup'], recipe['ItemNum'], strict=True):
            costs[item] += count
        reductions = self.effects(recipe, exp[rid], 1)
        for item, count in zip(reductions[::2], reductions[1::2], strict=True):
            costs[item] -= count
        costs = {item: count for item, count in costs.items() if count > 0}
        elements = {r['elementId']: r for r in state['alchemy']['elements']}
        for item, count in costs.items():
            if item in self.element_items and elements[self.element_items[item]]['num'] < count:
                return dict(values, code=22)
        other_costs = {item: count for item, count in costs.items() if item not in self.element_items}
        from .college_upgrade import BuildingUpgradeService
        code = BuildingUpgradeService._charge(self, player_id, self.repo.store.get(player_id)['snapshot'], other_costs)
        if code != 10:
            return dict(values, code=code)
        for item, count in costs.items():
            if item in self.element_items:
                elements[self.element_items[item]]['num'] -= count
        duration = max(0, recipe['WaitTimes'] - sum(self.effects(recipe, exp[rid], 4)))
        bar = {'recipeId': rid, 'endTime': self.repo.clock.now() + duration,
               'buffId': [0], 'production_id': uuid.uuid4().hex, 'costs': costs}
        while len(bars) <= pos:
            bars.append(None)
        bars[pos] = bar
        return dict(values, code=10, productionBar=self.production_wire(bar).hex())

    def _speed(self, player_id, state, request):
        pos, kind = request.get('posIndex', 0), request.get('type', 0)
        values = {'code': 13, 'posIndex': pos}
        bars = state['alchemy'].get('production_bars', [])
        if kind not in (1, 2) or not 0 <= pos < self.slots(state) or pos >= len(bars) or not bars[pos]:
            return values
        bar = bars[pos]
        remaining = bar['endTime'] - self.repo.clock.now()
        if remaining <= 0:
            return dict(values, code=205)
        if kind == 1:
            # OnInit overrides the ctor default with GlobalParamString.
            rate = int(rules()['params']['AlchemySpeedConsume'])
            cost = (remaining + rate - 1) // rate
            if state['star_energy'] < cost:
                return dict(values, code=22)
            state['star_energy'] -= cost
        else:
            recipe = self.recipes[bar['recipeId']]
            duration = max(1, recipe['WaitTimes'])
            cost = (recipe['Pay'] * remaining + duration - 1) // duration
            from .college_upgrade import BuildingUpgradeService
            code = BuildingUpgradeService._charge(self, player_id,
                self.repo.store.get(player_id)['snapshot'], {1237902: cost})
            if code != 10:
                return dict(values, code=code)
        bar['endTime'] = self.repo.clock.now()
        return dict(values, code=10)

    def _collect(self, player_id, state, flow, request):
        positions = ([request.get('posIndex', 0)] if flow == 'AlchemyCollect'
                     else list(request.get('posIndex', [])))
        values = {'code': 13}
        if not positions or len(positions) != len(set(positions)):
            return values
        bars = state['alchemy'].get('production_bars', [])
        for pos in positions:
            if not 0 <= pos < self.slots(state):
                return values
            if pos >= len(bars) or not bars[pos]:
                return dict(values, code=204, posIndex=pos)
            if bars[pos]['endTime'] > self.repo.clock.now():
                return dict(values, code=205)
        exp = self.recipe_exp(state)
        before = dict(exp)
        rewards, groups = Counter(), {}
        for pos in positions:
            bar = bars[pos]
            rid = bar['recipeId']
            recipe = self.recipes[rid]
            # kind 5 doubles the haul with the slot's per-mille chance. The roll
            # uses immutable production identity, so speed-ups, replays and
            # account migration cannot alter the roll.
            product_num = recipe['ProductNum']
            bonus = self.effects(recipe, exp.get(rid, 0), 5)
            if bonus and random.Random(
                    'college-double:' + bar['production_id']
            ).randrange(1000) < bonus[0]:
                product_num *= 2
            reward = {recipe['ProductID']: product_num}
            self.economy._grant(player_id, 'college-production:' + bar['production_id'], reward)
            rewards.update(reward)
            exp[rid] = min(recipe['Exp'][-1], exp.get(rid, 0)
                           + product_num * self.EXPERIENCE_PER_ITEM)
            groups.setdefault(rid, []).append(pos)
            bars[pos] = None
        state['alchemy']['recipe_exp'] = [{'Key': rid, 'Value': value} for rid, value in sorted(exp.items())]
        self.recipe_exp(state)
        values.update(code=10, rewardData=self.economy.reward_bytes(rewards).hex())
        if flow == 'AlchemyCollect':
            rid = next(iter(groups))
            values.update(posIndex=positions[0], recipeId=rid, exp=exp[rid])
        else:
            values['barData'] = [ALCHEMY_RECIPE_BAR_DATA.encode({'recipeId': rid,
                'expBefore': before.get(rid, 0), 'exp': exp[rid], 'posIndex': positions}).hex()
                for rid, positions in sorted(groups.items())]
        return values

    def _trade(self, player_id, state, request):
        pos, action = request.get('posIndex', 0), request.get('type', 0)
        values = {'code': 13, 'type': action, 'posIndex': pos}
        # OnSendTransaction sends action=1, distinct from CustomerInfo.type=2.
        if not 0 <= pos < self.customer_count(player_id):
            return values
        if action == 2:
            # OnSendRegist (0x1ba6fec) sends type=2 and may carry stale price
            # toggles. Refusal charges nothing; 599 triggers a fresh 592 query.
            rotations = state['alchemy'].setdefault('customer_rotations', {})
            rotations[str(pos)] = int(rotations.get(str(pos), 0)) + 1
            state['alchemy'].setdefault('customer_orders', {}).pop(str(pos), None)
            return dict(values, code=10, alchemyType=2, rewardData='')
        plus, discount = request.get('plusPrice', False), request.get('discountPrice', False)
        if action != 1 or (plus and discount):
            return values
        customer = self.customer(player_id, pos, state)
        if customer['type'] != 2:
            return values
        exp = self.recipe_exp(state)
        products = {r['ProductID']: r for r in self.recipes.values()}
        costs, gold, base_gold = Counter(), 0, 0
        for item, quantity in zip(customer['itemId'], customer['itemNum'], strict=True):
            recipe = products.get(item)
            if not recipe or quantity <= 0 or quantity % recipe['ProductNum']:
                return values
            costs[item] += quantity
            bonus = self.effects(recipe, exp.get(recipe['RecipeID'], 0), 2)
            price = recipe['Gold']
            if bonus:
                # GetRecipeSell uses only the first effect and float32 arithmetic.
                f32 = lambda n: struct.unpack('<f', struct.pack('<f', n))[0]
                price = int(f32(f32(price) * f32(1 + f32(f32(bonus[0]) * f32(0.001)))))
            gold += price * (quantity // recipe['ProductNum'])
            base_gold += recipe['Gold'] * (quantity // recipe['ProductNum'])
        if not costs or gold <= 0:
            return values
        params = rules()['params']
        energy = self.price_param(base_gold, 'AlchemyPriceParam') if plus else 0
        if state['star_energy'] < energy:
            return dict(values, code=38)
        favor_gain = self.price_param(base_gold, 'AlchemyDiscountParam', divisor=2) if discount else 0
        multiplier = self.f32(int(params['AlchemyPriceNum']) * self.f32(0.001)) if plus else 1
        if discount:
            multiplier = self.f32(int(params['AlchemyDiscountNum']) * self.f32(0.001))
        gold = math.floor(gold * multiplier)
        from .college_upgrade import BuildingUpgradeService
        code = BuildingUpgradeService._charge(self, player_id,
            self.repo.store.get(player_id)['snapshot'], costs)
        if code != 10:
            return dict(values, code=code)
        state['star_energy'] -= energy
        reward = {1237901: gold}
        source = 'college-trade:' + uuid.uuid4().hex
        self.economy._grant(player_id, source, reward)
        # 每日/周常 炼金任务: 本服务端顾客一律是 CustomerInfo.type==2 的普通交易委托, 一次
        # 成交同时满足「交易」与「完成 1 次委托」两种读法 (与 economy 里「一次购买既算
        # E_BuyGood 又算 E_BuyGold」同一设计), 对应 630027/630028(日) 与 630113/630114(周)。
        # A recurring customer is a new trade. Transport retries are already
        # protected by the College receipt; share this trade's unique grant key.
        self.economy.record_event(
            player_id, source + ':deal', self.economy.TASK_EVENT_ALCHEMY_DEAL, 0, 1)
        self.economy.record_event(
            player_id, source + ':quest', self.economy.TASK_EVENT_ALCHEMY_QUEST, 0, 1)
        # 成就 662300「在炼金实验室中，收获金币数量达到 N」按**金币数量**累计 (不是次数):
        # 记本单实际发出的金币 (加价/打折后的值)。source 是本单的唯一 grant 键, 重放/重发
        # 同一笔成交不会重复累加。
        if gold > 0:
            self.economy.achievements.record(
                player_id, source + ':gold', self.economy.ACHV_EVENT_ALCHEMY_GOLD, gold)
        change = self.discount_favor(player_id, customer, favor_gain)
        # The next single-customer query starts a fresh order using the latest
        # unlocked tiers, while the customer's identity and neighbours stay fixed.
        state['alchemy'].setdefault('customer_orders', {}).pop(str(pos), None)
        pinned = state['alchemy'].get('customer_positions', {}).get(str(pos), {})
        for field in ('itemId', 'itemNum', 'adviseItemId'):
            pinned.pop(field, None)
        result = dict(values, code=10, alchemyType=2,
                      rewardData=self.economy.reward_bytes(reward).hex())
        if change:
            result['_favor_change'] = change.hex()
        return result

    @staticmethod
    def f32(value):
        return struct.unpack('<f', struct.pack('<f', value))[0]

    def price_param(self, price, key, divisor=1):
        denominator, amount = map(int, rules()['params'][key].split('|'))
        # Native GetAddPriceStarEnergy/GetDiscountFavory/GetAdvanceStarEnengy
        # use float32 divide/multiply followed by GameAPI.CeilToInt.
        return math.ceil(self.f32(self.f32(self.f32(price) / self.f32(denominator * divisor))
                                  * self.f32(amount)))

    def recipe_price(self, state, item):
        recipe = next((r for r in self.recipes.values() if r['ProductID'] == item), None)
        if not recipe:
            return None, 0
        exp = self.recipe_exp(state).get(recipe['RecipeID'], 0)
        bonus = self.effects(recipe, exp, 2)
        price = recipe['Gold']
        if bonus:
            price = int(self.f32(self.f32(price) * self.f32(1 + self.f32(self.f32(bonus[0]) * self.f32(.001)))))
        return recipe, price

    def _suggest(self, player_id, state, request):
        pos, action = request.get('posIndex', 0), request.get('type', 0)
        values = {'code': 13, 'type': action, 'posIndex': pos}
        if action != 1 or not 0 <= pos < self.customer_count(player_id):
            return values
        customer = self.customer(player_id, pos, state)
        recommendation = customer['adviseItemId']
        recipe, _ = self.recipe_price(state, recommendation)
        if customer['type'] != 2 or not recipe or recommendation == customer['itemId'][0]:
            return values
        # Refresh reads the recommended CollegeRecipe.Gold, not the old
        # order's Gold or its proficiency-adjusted selling price.
        energy = self.price_param(recipe['Gold'], 'AlchemyAdviceParam')
        if state['star_energy'] < energy:
            return dict(values, code=38)
        state['star_energy'] -= energy
        rotation = int(state['alchemy'].get('customer_rotations', {}).get(str(pos), 0))
        state['alchemy'].setdefault('customer_orders', {})[str(pos)] = {
            'rotation': rotation, 'questId': customer['questId'],
            'itemId': [recommendation], 'itemNum': [recipe['ProductNum']],
            'adviseItemId': customer['itemId'][0]}
        # 601 first swaps itemId[0] to the OLD adviseItemId and installs result
        # as the next recommendation. Keep a valid product: Refresh looks up
        # Item[result] to draw its icon and read Used[0] for the energy price.
        return dict(values, code=10, result=customer['itemId'][0], param=0)

    def discount_favor(self, player_id, customer, gain):
        if gain <= 0:
            return None
        from .favor import catalog, favor_state
        from x2server.messages.favor import FAVOR_CHANGE_INFO
        customer_meta = json.loads(files('x2server').joinpath('data/college_alchemy_catalog.json').read_text(encoding='utf8'))
        meta = next((r for r in customer_meta['customers'] if r['sellQuestId'] == customer['questId']), None)
        player = self.repo.store.get(player_id)
        hero = next((h for h in player['snapshot']['heroes'] if meta and h['id'] == meta['heroId'] and h['state'] == 2), None)
        data = catalog()
        row = next((r for r in data['favorabilityhero'] if hero and r['HeroID'] == hero['id']), None)
        if not row:
            return None
        before = favor_state(hero, row['InitialLevel']).copy()
        after = dict(before, exp=before['exp'] + gain)
        levels = {r['FavorLevel']: r for r in data['favorabilitylevel']}
        # Match FavorService._advance, including required favor breakthroughs.
        while after['level'] < row['LevelLimit']:
            level = after['level']
            if levels[level].get('IsBreak') and level not in hero.get('favor_breaks', []):
                break
            if after['exp'] < levels[level + 1]['Exp']:
                break
            after['level'] += 1
        hero['favor'] = after
        self.economy.save_snapshot(player_id, player['snapshot'])
        return FAVOR_CHANGE_INFO.encode({'beforeLevel': before['level'], 'beforeExp': before['exp'],
            'afterLevel': after['level'], 'afterExp': after['exp'], 'heroID': hero['id'], 'type': 13})

    def _buy_elements(self, player_id, state, request):
        kind, element = request.get('type', 0), request.get('typeId', 0)
        if kind not in (1, 2) or element not in range(991, 997):
            return {'code': 13}
        row = next(r for r in state['alchemy']['elements'] if r['elementId'] == element)
        cap = self.repo.catalog.effect(state, 706, 12)[element - 991]
        missing = cap - row['num']
        if missing <= 0:
            return {'code': 14}
        params = rules()['params']
        gain, energy, limit = map(int, params[f'Element{element - 990:02}Param'].split('|'))
        if kind == 1:
            if row['buyTimesDay'] >= limit:
                return {'code': 13}
            if state['star_energy'] < energy:
                return {'code': 38}
            state['star_energy'] -= energy
            row['num'] = min(cap, row['num'] + gain)
            row['buyTimesDay'] += 1
        else:
            # Refresh divides the warehouse deficit by ElementXXPay then ceils.
            rate = int(params[f'Element{element - 990:02}Pay'])
            cost = (missing + rate - 1) // rate
            from .college_upgrade import BuildingUpgradeService
            code = BuildingUpgradeService._charge(self, player_id,
                self.repo.store.get(player_id)['snapshot'], {1237902: cost})
            if code != 10:
                return {'code': code}
            row['num'] = cap
        # A full warehouse cannot bank passive overflow for later consumption.
        if row['num'] == cap:
            row['lastRecoverTime'] = self.repo.clock.now()
        return {'code': 10}

    def handle(self, context, packet, flow, request):
        player_id = context.session.player_id
        key = f'{context.session.session_id}:{packet.header.request_id}:{flow}'
        digest = hashlib.sha256(packet.body).hexdigest()
        with self.repo.transaction():
            state = self.repo.load(player_id)
            self.repo.settle(state)
            receipt = self.db.execute('SELECT digest,response FROM college_alchemy_receipts WHERE player_id=? AND receipt_key=?',
                                     (player_id, key)).fetchone()
            if receipt:
                values = json.loads(receipt[1]) if receipt[0] == digest else {'code': 13}
            else:
                values = (self._suggest(player_id, state, request) if flow == 'AlchemyButtonClick'
                          else self._buy_elements(player_id, state, request) if flow == 'AlchemyBuy'
                          else self._trade(player_id, state, request) if flow == 'AlchemyFinish'
                          else self._speed(player_id, state, request) if flow == 'MakIngSpeed'
                          else self._make(player_id, state, request) if flow == 'MakeItem'
                          else self._collect(player_id, state, flow, request))
                if values['code'] == 10:
                    self.db.execute('INSERT INTO college_alchemy_receipts VALUES (?,?,?,?)',
                                    (player_id, key, digest, json.dumps(values)))
            self.repo.save(player_id, state)
        change = values.pop('_favor_change', None)
        for field in ('rewardData', 'productionBar'):
            if field in values:
                values[field] = bytes.fromhex(values[field])
        if 'barData' in values:
            values['barData'] = [bytes.fromhex(row) for row in values['barData']]
        # Collect handlers compare old/new proficiency; install 591 AFTER their
        # callback, then refresh resources and newly unlocked recipes.
        pushes = ((self.snapshot(player_id), *self.economy.pushes(player_id))
                  if values['code'] == 10 else ())
        if change:
            from .hero import encode_hero_data
            pushes += (OutboundMessage('L2C_FavorChangeInfo', {'data': [bytes.fromhex(change)]}),
                       OutboundMessage('L2C_HeroUpdate', {'code': 10, 'heros': [
                           encode_hero_data(h, season=self.economy.season, player_id=player_id) for h in self.repo.store.get(player_id)['snapshot']['heroes']]}))
        before = ((OutboundMessage('L2C_QueryGrowthBase', self.repo.growth_base(player_id)),)
                  if flow in ('MakIngSpeed', 'AlchemyFinish', 'AlchemyButtonClick') and values['code'] == 10 else ())
        if flow == 'AlchemyBuy' and values['code'] == 10:
            # 605 immediately refreshes/closes its window: resources must already
            # be installed before that callback, not after it.
            before = (OutboundMessage('L2C_QueryGrowthBase', self.repo.growth_base(player_id)),
                      *pushes)
            pushes = ()
        return OutboundMessage('L2C_' + flow, values, pushes=pushes, before_response=before)
