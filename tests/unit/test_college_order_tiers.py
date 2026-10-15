"""Orders use manufacturing unlocks and remain stable through the trade callback."""
import pytest
from tests.unit.test_college_upgrade import game,quantity
from tests.unit.test_college_alchemy import send
from x2server.player.college import CollegeService,CollegeStateRepository
from x2server.player.economy import EconomyService
from x2server.player.store import PlayerStore

def seed_levels(game,levels):
    _,_,repo,service,_=game
    repo.growth_base(1)
    state=repo.load(1)
    state['alchemy']['recipe_exp']=[{'Key':r['RecipeID'],'Value':0 if r['RecipeLevel']<=levels[r['RecipeType']] else -1} for r in service.alchemy.recipes.values()]
    repo.save(1,state)

def product(service,item):
    return next(r for r in service.alchemy.recipes.values() if r['ProductID']==item)

@pytest.mark.parametrize('level',[1,2,4,7,10])
def test_each_element_requests_highest_unlocked_tier_never_negative_placeholders(game,level,monkeypatch):
    _,clock,_,service,_=game
    levels={element:max(1,level-(element%3)) for element in range(991,997)}
    seed_levels(game,levels)
    cursor=[0]
    def choose(owned,highest,exclude=None):
        candidates=[r for r in highest if r['productId']!=exclude]
        if exclude is None:
            row=candidates[cursor[0]%len(candidates)];cursor[0]+=1
            return row
        return candidates[0]
    monkeypatch.setattr(service,'_choose_customer_product',choose)
    seen=set()
    for day in range(8):
        clock.value+=86400
        for pos in range(5):
            order=service._customer_for(1,pos)
            recipe=product(service,order['itemId'][0])
            seen.add(recipe['RecipeType'])
            assert recipe['RecipeLevel']==levels[recipe['RecipeType']]
            advice=product(service,order['adviseItemId'])
            assert advice['RecipeLevel']<=levels[advice['RecipeType']]
            assert advice['ProductID']!=recipe['ProductID']
    assert seen==set(range(991,997))

def test_recipe_threshold_unlock_closure_is_used_without_extra_collection(game):
    _,_,repo,service,_=game
    repo.growth_base(1)
    state=repo.load(1)
    state['alchemy']['recipe_exp']=[{'Key':r['RecipeID'],'Value':r['Exp'][0]} for r in service.alchemy.recipes.values() if r['RecipeLevel']==1]
    repo.save(1,state)
    for pos in range(5):
        order=service._customer_for(1,pos)
        assert product(service,order['itemId'][0])['RecipeLevel']==2

def test_displayed_order_survives_unlock_restart_then_trade_refreshes_to_highest(game):
    store,clock,repo,service,_=game
    before=[service._customer_for(1,pos) for pos in range(5)]
    seed_levels(game,{element:10 for element in range(991,997)})
    assert [service._customer_for(1,pos) for pos in range(5)]==before
    restored=PlayerStore(store.path)
    try:
        rebuilt=CollegeService(CollegeStateRepository(restored,clock),economy=EconomyService(restored,clock.now))
        assert rebuilt._customer_for(1,0)==before[0]
    finally:restored.close()
    old=before[0];item=old['itemId'][0]
    with store.db:store.db.execute('INSERT INTO inventory VALUES (?,?,?)',(1,item,old['itemNum'][0]))
    result=send(game,'AlchemyFinish',seq=51,type=1,posIndex=0)
    assert result.values['code']==10 and quantity(store,item)==0
    new=service._customer_for(1,0)
    assert product(service,new['itemId'][0])['RecipeLevel']==10
    assert [service._customer_for(1,pos) for pos in range(1,5)]==before[1:]
    assert send(game,'AlchemyFinish',seq=51,type=1,posIndex=0).values==result.values
    assert service._customer_for(1,0)==new

def test_high_tier_suggestion_trade_and_refusal_form_closed_loop(game):
    store,_,repo,service,_=game
    seed_levels(game,{element:10 for element in range(991,997)})
    old=service._customer_for(1,0)
    assert product(service,old['adviseItemId'])['RecipeLevel']==10
    state=repo.load(1);state['star_energy']=100000;repo.save(1,state)
    suggested=send(game,'AlchemyButtonClick',seq=60,type=1,posIndex=0)
    assert suggested.values['code']==10
    new=service._customer_for(1,0)
    assert new['itemId']==[old['adviseItemId']] and new['adviseItemId']==old['itemId'][0]
    recipe=product(service,new['itemId'][0])
    with store.db:store.db.execute('INSERT INTO inventory VALUES (?,?,?)',(1,recipe['ProductID'],recipe['ProductNum']))
    gold=store.get(1)['snapshot']['gold']
    assert send(game,'AlchemyFinish',seq=61,type=1,posIndex=0).values['code']==10
    assert store.get(1)['snapshot']['gold']==gold+recipe['Gold']
    assert quantity(store,recipe['ProductID'])==0
    assert send(game,'AlchemyFinish',seq=62,type=2,posIndex=0).values['code']==10
    assert product(service,service._customer_for(1,0)['itemId'][0])['RecipeLevel']==10

def test_legacy_locked_advice_is_replaced_by_real_unlocked_product(game):
    _,_,repo,service,_=game
    old=service._customer_for(1,0)
    state=repo.load(1)
    state['alchemy'].setdefault('customer_orders', {})['0']={**state['alchemy']['customer_positions']['0'],'itemId':old['itemId'],'itemNum':old['itemNum'],'adviseItemId':1280012}
    repo.save(1,state)
    order=service._customer_for(1,0)
    assert product(service,order['adviseItemId'])['RecipeLevel']==1


def test_order_candidates_filter_locked_inventory_and_visible_recipes(game):
    store,_,repo,service,_=game
    seed_levels(game,{element:3 for element in range(991,997)})
    recipes=list(service.alchemy.recipes.values())
    owned=next(r for r in recipes if r['RecipeType']==991 and r['RecipeLevel']==1)
    locked=next(r for r in recipes if r['RecipeType']==991 and r['RecipeLevel']==4)
    with store.db:
        store.db.execute('INSERT INTO inventory VALUES (?,?,?)',(1,owned['ProductID'],99))
        store.db.execute('INSERT INTO inventory VALUES (?,?,?)',(1,locked['ProductID'],99))
    available,stock,highest=service._customer_candidates(1,repo.load(1))
    assert {r['productId'] for r in stock}=={owned['ProductID']}
    assert locked['ProductID'] not in {r['productId'] for r in available}
    assert {r['element'] for r in highest}==set(range(991,997))
    assert {r['level'] for r in highest}=={3}


@pytest.mark.parametrize('index',range(7))
def test_order_equal_weight_unique_candidates(game,monkeypatch,index):
    store,_,repo,service,_=game
    seed_levels(game,{element:3 for element in range(991,997)})
    first=next(r for r in service.alchemy.recipes.values() if r['RecipeType']==991 and r['RecipeLevel']==1)
    with store.db:store.db.execute('INSERT INTO inventory VALUES (?,?,?)',(1,first['ProductID'],999))
    _,owned,highest=service._customer_candidates(1,repo.load(1))
    bounds=[]
    def choose(bound):
        bounds.append(bound)
        return index
    monkeypatch.setattr('secrets.randbelow',choose)
    row=service._choose_customer_product(owned,highest)
    expected=sorted({r['productId'] for r in (*owned,*highest)})
    assert bounds==[7]
    assert row['productId']==expected[index]


def test_highest_owned_product_has_only_one_candidate_slot(game,monkeypatch):
    _,_,repo,service,_=game
    _,_,highest=service._customer_candidates(1,repo.load(1))
    bounds=[]
    monkeypatch.setattr('secrets.randbelow',lambda n:(bounds.append(n) or 0))
    service._choose_customer_product([highest[0]],highest)
    assert bounds==[6]


def test_locked_cached_order_and_suggestion_are_replaced(game):
    store,_,repo,service,_=game
    old=service._customer_for(1,0)
    locked=next(r for r in service.alchemy.recipes.values() if r['RecipeType']==991 and r['RecipeLevel']==10)
    state=repo.load(1)
    pinned=state['alchemy']['customer_positions']['0']
    pinned.update(itemId=[locked['ProductID']],itemNum=[locked['ProductNum']],adviseItemId=locked['ProductID'])
    state['alchemy']['customer_orders']={'0':dict(pinned)}
    repo.save(1,state)
    order=service._customer_for(1,0)
    assert order['itemId']!=[locked['ProductID']]
    assert order['adviseItemId']!=locked['ProductID']
