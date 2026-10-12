"""Period-scoped food businesses: staffing, paid cooking, sales and upgrades."""
from .activity import enum
from .economy import UnresolvedEconomy
from x2server.messages.activity import encode


class ActivityCafe:
    def __init__(self, activity):
        self.a, self.e, self.r = activity, activity.economy, activity.rotation
        self.levels = {(r['Type'], r['Level']): r for r in activity.tables['NewYearCafe']}
        self.recipes = {r['RecipeID']: r for r in activity.tables['NewYearFood']}

    def context(self, player, store_type):
        period = self.a.period(player)
        row = self.r.of_type(27, period)
        if row is None or store_type not in row['ActivityParam1']:
            raise UnresolvedEconomy('food store is not active')
        state = self.r.get(player, period, 'cafe', store_type,
            {'level': 1, 'exp': 0, 'unlocked': False, 'employees': {}, 'queues': [], 'revenue': 0})
        return period, row, state

    def save(self, player, period, store_type, state):
        self.r.put(player, period, 'cafe', store_type, state)

    def owns_recipe(self, player, item):
        # Native CheckStoreCanUnlock/GetHaveFoodRecipe use current bag counts,
        # including recipes retained from a previous occurrence of the theme.
        return bool(self.a.store.db.execute('''SELECT 1 FROM inventory
            WHERE player_id=? AND item_id=? AND quantity>0''', (player, item)).fetchone())

    def settle(self, player, period, store_type, state):
        now = int(self.e.clock())
        remaining = []
        for q in state['queues']:
            if q['end'] > now:
                remaining.append(q)
                continue
            state['revenue'] += q['revenue']
            state['exp'] += q['exp']
            recipe = self.recipes[q['recipe']]
            self.a.event(player, f"E_CookFood:{q['token']}", 99,
                recipe['RecipeID'], recipe['ProductNum'], period=period)
            self.a.event(player, f"E_FoodShopSell:{q['token']}", 101,
                store_type, q['revenue'], period=period)
        state['queues'] = remaining
        self.save(player, period, store_type, state)

    def values(self, player, store_type):
        period, _, state = self.context(player, store_type)
        self.settle(player, period, store_type, state)
        queues = [self.queue_wire(q) for q in state['queues']]
        # The client uses List.Count for both queue capacity and staff-busy
        # checks. Idle placeholders make an empty shop full and unstaffable.
        # The activity UI fix initializes absent lists in CafeStoreInfo's
        # native deserializers, so transmit only actual cooking orders.
        return {'type': store_type, 'lockState': int(state['unlocked']), 'level': state['level'],
                'exp': state['exp'], 'revenue': state['revenue'], 'cafeStoreQueueInfo': queues,
                'employeeInfo': [encode('CafeStoreEmployee', {'position': p,
                    'heroId': state['employees'].get(str(p), 0)}) for p in (1, 2, 3)]}

    def queue_wire(self, q):
        return encode('CafeStoreQueue', {'cd': max(0, q['end'] - int(self.e.clock())),
            'preRevenue': q['revenue'], 'recipeId': q['recipe'], 'state': 1, 'inQueueTime': q['start']})

    def buff(self, store_type, state, kind):
        value = 0
        for r in self.a.tables['NewYearCafeBuff']:
            if (enum(r['EffectType']) == kind and store_type in r['EffectParam2']
                    and state['employees'].get(str(r['EffectParam1'])) == r['UnitID']):
                value += r['EffectParam4']
        return value

    def handle(self, player, operation, request, token):
        period = self.a.period(player)
        food = self.r.of_type(27, period)
        if food is None:
            raise UnresolvedEconomy('no food activity')
        if operation == 'CafeStoreInfo':
            return {'code': 10, 'storeInfo': [encode('CafeStoreInfo', self.values(player, t))
                                            for t in food['ActivityParam1']]}
        store_type = request.get('storeType', 0)
        period, food, state = self.context(player, store_type)
        self.settle(player, period, store_type, state)
        config = self.levels[store_type, state['level']]
        result = {'code': 10, 'storeType': store_type}
        if operation == 'CafeStoreUpdate':
            result['storeInfo'] = encode('CafeStoreInfo', self.values(player, store_type))
            return result
        if operation == 'CafeStoreUnLock':
            if not state['unlocked']:
                if any(not self.owns_recipe(player, item)
                       for item in config['CafeUnlockCon']):
                    raise UnresolvedEconomy('food store unlock recipe not obtained')
                state['unlocked'] = True
            result['lockState'] = 1
        else:
            if not state['unlocked']:
                raise UnresolvedEconomy('food store locked')
            if operation == 'CafeStorePositionSet':
                if state['queues']:
                    raise UnresolvedEconomy('cannot change staff while cooking')
                hero, position = request.get('heroId', 0), request.get('position', 0)
                owned = {h['id'] for h in self.a.store.get(player)['snapshot'].get('heroes', []) if h['state'] == 2}
                if position not in (1, 2, 3) or hero and hero not in owned:
                    raise UnresolvedEconomy('invalid staff')
                # One hero can occupy one position across this activity's stores.
                for other_type in food['ActivityParam1']:
                    _, _, other = self.context(player, other_type)
                    for p, existing in list(other['employees'].items()):
                        if hero and existing == hero:
                            self.settle(player, period, other_type, other)
                            if other['queues']:
                                raise UnresolvedEconomy('staff is cooking in another store')
                            other['employees'][p] = 0
                    if other_type == store_type:
                        state['employees'] = other['employees']
                    else:
                        self.save(player, period, other_type, other)
                state['employees'][str(position)] = hero
            elif operation == 'CafeStoreCooking':
                recipe = self.recipes.get(request.get('recipeID'))
                # ShowRank is the display sort order, not a shop assignment.
                # Both native recipe views offer all recipes in their activity
                # and SendCafeStoreCooking uses the currently selected shop.
                if (recipe is None or not set(recipe['ItemGroup']).issubset(food['ActivityParam2'])
                        or not self.owns_recipe(player, recipe['UnlockItem'])
                        or len(state['queues']) >= config['QueueNum']
                        or not state['employees'].get('1')):
                    raise UnresolvedEconomy('recipe locked, queue full or chef absent')
                for item, num in zip(recipe['ItemGroup'], recipe['ItemNum'], strict=True):
                    self.a.spend(player, period, item, num, f'cook:{token}:{item}')
                duration = max(1, recipe['WaitTimes'] * max(100, 1000 - self.buff(store_type, state, 5)) // 1000)
                revenue = recipe['SellPrice'] * (1000 + config.get('CafeSellAdd', 0) + self.buff(store_type, state, 3)) // 1000
                exp = recipe['CafeExp'] * (1000 + self.buff(store_type, state, 4)) // 1000
                q = {'start': int(self.e.clock()), 'end': int(self.e.clock()) + duration,
                     'revenue': revenue, 'exp': exp, 'recipe': recipe['RecipeID'], 'token': token}
                state['queues'].append(q)
                result['queue'] = self.queue_wire(q)
            elif operation == 'CafeStoreReceiveRevenue':
                if state['revenue'] <= 0:
                    raise UnresolvedEconomy('no completed food revenue')
                currency = next(i for i in self.e.items.values()
                    if i.get('EffData') == [config['CafeStoreCurr']] and enum(i.get('ItemType')) == 16)['ItemID']
                rewards = self.e._grant(player, self.a.source(period, 'cafe-sale', token), {currency: state['revenue']})
                self.a.obtained(player, period, rewards, self.a.source(period, 'cafe-sale', token))
                state['revenue'] = 0
                result['rewardData'] = self.e.reward_bytes(rewards)
            elif operation == 'CafeStoreLevelUp':
                if (store_type, state['level'] + 1) not in self.levels or state['exp'] < config.get('Exp', 2**31):
                    raise UnresolvedEconomy('food level/experience requirement')
                currency = next(i for i in self.e.items.values()
                    if i.get('EffData') == [config['CafeStoreCurr']] and enum(i.get('ItemType')) == 16)['ItemID']
                self.a.spend(player, period, currency, config['CafeStoreNum'], f'cafe-level:{token}')
                state['exp'] -= config['Exp']
                state['level'] += 1
                result.update(level=state['level'], exp=state['exp'])
            else:
                raise UnresolvedEconomy('unknown cafe operation')
        self.save(player, period, store_type, state)
        if operation == 'CafeStorePositionSet':
            # 839 only carries code and the refreshed store list; unlike the
            # other store responses it has no storeType field.
            result.pop('storeType')
            result['storeInfo'] = [encode('CafeStoreInfo', self.values(player, t)) for t in food['ActivityParam1']]
        elif operation == 'CafeStoreReceiveRevenue':
            result['storeInfo'] = encode('CafeStoreInfo', self.values(player, store_type))
        return result
