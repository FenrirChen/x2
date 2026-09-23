from __future__ import annotations

import json
from collections import Counter, defaultdict
from pathlib import Path

from audit_probe import data as base, lang, meta as base_meta
from targeted_probe import data as extra, meta as extra_meta

OUT = Path(__file__).resolve().parent
gift = {r['GiftGroup']: r for r in extra['Gift']}
items = {r['ItemID']: r for r in base['Item']}
conditions = {r['TaskConditionID']: r for r in base['TaskCondition']}
quickbuy = defaultdict(list)
for r in base['Item']:
    if r.get('QuickBuyID'):
        quickbuy[r['QuickBuyID']].append(r['ItemID'])

def item_summary(i):
    r = items.get(i)
    return {'item_id': i, 'name': lang.get(r.get('NameID')) if r else None,
            'type': (r.get('ItemType') or {}).get('enum') if r else None,
            'status': 'RESOLVED' if r else 'UNRESOLVED'}

def reward(gid):
    r = gift.get(gid)
    if not r:
        return {'target_table': 'Gift', 'target_id': gid, 'status': 'UNRESOLVED'}
    return {'target_table': 'Gift', 'target_id': gid,
            'award_type': (r.get('AwardType') or {}).get('enum'),
            'entries': [{'item': item_summary(i), 'count': n,
                         'weight_or_probability': (r.get('Probability') or [None]*len(r.get('GiftValue',[])))[idx] if idx < len(r.get('Probability',[])) else None}
                        for idx, (i,n) in enumerate(zip(r.get('GiftValue',[]),r.get('Num',[])))],
            'status': 'RESOLVED' if all(i in items for i in r.get('GiftValue',[])) else 'PARTIAL'}

drop_records=[]
for s in base['SectionTable']:
    drop_records.append({'source_table':'SectionTable','source_id':s['SectionID'],
                         'name':s.get('NameChina'),'chapter_id':s.get('ChapterID'),
                         'drop_value_id':s.get('DropValueID'),
                         'first_reward_group_ids':s.get('FirVReward',[]),
                         'normal_reward_group_ids':s.get('VReward',[]),
                         'mop_reward_group_ids':s.get('MopReward',[]),
                         'chest_reward_group_id':s.get('ChestReward'),
                         'expert_chest_reward_group_id':s.get('ExpertChestReward'),
                         'random_drop_status':'UNRESOLVED' if s.get('DropValueID') else 'NOT_REFERENCED'})

shop_by_group=defaultdict(list)
for s in base['ShopConfig']:
    for field in ('GoodsGroupId','SeasonGoodsGroupId'):
        for group in s.get(field,[]): shop_by_group[group].append({'shop_id':s['ShopID'],'group_field':field})
shop_records=[]
for g in base['ShopGoodsGroup']:
    candidates=[item_summary(i) for i in quickbuy[g['GoodsID']]]
    shop_records.append({'source_table':'ShopGoodsGroup','source_id':g['GoodsID'],
                         'group_id':g['GroupID'],'shop_refs':shop_by_group[g['GroupID']],
                         'price':g.get('ItemPrice'),'currency_type':g.get('ShopResourceType'),
                         'limit_period':g.get('Limited'),'condition':g.get('Condition'),
                         'condition_param':g.get('ConditionParam'),
                         'item_candidates_from_Item_QuickBuyID':candidates,
                         'item_count':None,'item_status':'PARTIAL_REVERSE_LINK' if candidates else 'UNRESOLVED'})

task_records=[]
for t in extra['DailyTask']:
    c=conditions.get(t['TaskConditionID'])
    task_records.append({'source_table':'DailyTask','source_id':t['DailyTaskID'],
                         'cycle':(t.get('RefreshCycle') or {}).get('enum'),
                         'name':lang.get(t.get('TaskName')),'description':lang.get(t.get('TaskDescribe')),
                         'accept_level':t.get('AcceptLevel'),'predecessor':t.get('LastTask'),
                         'condition_id':t['TaskConditionID'],'condition':c,
                         'reward':reward(t['GiftGroup']),
                         'season_reward':reward(t['GiftGroupSeason']) if t.get('GiftGroupSeason') else None,
                         'battlepass_exp':t.get('BattlepassExp'),
                         'confidence':'CONFIRMED_CLIENT_STATIC'})

used_groups=set()
for s in drop_records:
    for f in ('first_reward_group_ids','normal_reward_group_ids','mop_reward_group_ids'):
        used_groups.update(s[f])
    for f in ('chest_reward_group_id','expert_chest_reward_group_id'):
        if s[f]:used_groups.add(s[f])
for t in task_records:
    used_groups.add(t['reward']['target_id'])
    if t['season_reward']: used_groups.add(t['season_reward']['target_id'])
for t in base['MissionTable']: used_groups.update(t.get('Award',[]))
for t in base['Achievement']: used_groups.update(t.get('GiftGroup',[]))

def write(name, obj):
    (OUT/name).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

write('drop_tables.json',{'sources':{'SectionTable':base_meta['SectionTable'],'DropProp':extra_meta['DropProp'],'DropBase':{'file':'phase3_output/raw_tables/DropBase__3c651c6fa1ab43a4f9a4bcf8074e62fb.bin','count':6}},'records':drop_records,
                          'drop_prop_count':len(extra['DropProp']),'note':'DropValueID to DropProp.DropClass or Item is unresolved; fixed Section reward group IDs are expanded in reward_links.json.'})
write('shop_tables.json',{'sources':{'ShopConfig':base_meta['ShopConfig'],'ShopGoodsGroup':base_meta['ShopGoodsGroup'],'Item':base_meta['Item']},
                          'shops':[{'shop_id':s['ShopID'],'name':s.get('ShopNameChina'),'shop_type':s.get('ShopType'),
                                    'unlock_type':s.get('UnlockType'),'unlock_params':[s.get('ShopParam1'),s.get('ShopParam2'),s.get('ShopParam3')],
                                    'goods_group_ids':s.get('GoodsGroupId',[]),'season_goods_group_ids':s.get('SeasonGoodsGroupId',[]),
                                    'refresh_times':s.get('ShopRefreshTime',[]),'manual_refresh':s.get('CanManualRefresh'),
                                    'refresh_currency_type':s.get('RefreshCurrencyType'),'refresh_price':s.get('RefreshPrice',[])} for s in base['ShopConfig']],
                          'goods':shop_records,
                          'note':'ShopGoodsGroup has price/currency but no product ItemID or count field. Item.QuickBuyID supplies only 17 reverse links; product count and remaining products unresolved.'})
write('task_tables.json',{'sources':{'DailyTask':extra_meta['DailyTask'],'TaskCondition':base_meta['TaskCondition'],'TaskControl':extra_meta['TaskControl'],'Gift':extra_meta['Gift'],'Item':base_meta['Item']},
                          'cycle_counts':dict(Counter(x['cycle'] for x in task_records)),
                          'control':extra['TaskControl'][0],
                          'records':task_records,
                          'other_task_tables':{n:extra_meta[n] for n in ('TaskEndlessWeek','TaskChapter','TaskHappy','TaskSeven','ActivityTask','FavorabilityDailyTask','TaskConditionLine')}})
write('reward_links.json',{'sources':{'Gift':extra_meta['Gift'],'Item':base_meta['Item']},
                           'section_reward_reference_counts':{f:sum(len(s.get(f,[])) for s in base['SectionTable']) for f in ('FirVReward','VReward','MopReward')},
                           'referenced_gift_groups':[reward(i) for i in sorted(used_groups)],
                           'note':'Gift AwardType may be random/pick; entries and raw weights are listed but final selection rules are not inferred.'})
print('wrote',len(drop_records),'sections',len(shop_records),'goods',len(task_records),'daily/weekly tasks',len(used_groups),'reward groups')
