---
Document-Type: Current Knowledge
Domain: Persistence
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - (none; still authoritative)
---

# SQLite / Repository / 持久化 / 重登 审计

静态解析 `src/x2server`（未打开活跃库）。共 24 张表。机器可读：`analysis/persistence/sqlite_schema_catalog.json` 与 `state_lifecycle.json`。

| 表 | 模块 | 主键 | 写入函数 | 事务 | 幂等 | 重登恢复 | 模块内 push |
|---|---|---|---|---|---|---|---|
| battle_costs | economy.py | uuid | 1 | yes | yes | QUERY_ONLY | L2C_GameTask,L2C_ItemUpdate,L2C_TaskUpdate |
| battle_entries | battle.py | player_id,request_key | 1 | yes | unknown | QUERY_ONLY | L2C_CheckoutMainMission,L2C_DelFightProfile,L2C_FightData |
| battle_receipts | battle.py | uuid | 1 | yes | yes | QUERY_ONLY | L2C_CheckoutMainMission,L2C_DelFightProfile,L2C_FightData |
| battle_unresolved_rewards | economy.py | uuid,reward_group | 1 | yes | unknown | PERSISTED_NOT_RESTORED | L2C_GameTask,L2C_ItemUpdate,L2C_TaskUpdate |
| economy_checkouts | economy.py | player_id,digest | 1 | yes | yes | PERSISTED_NOT_RESTORED | L2C_GameTask,L2C_ItemUpdate,L2C_TaskUpdate |
| economy_clears | economy.py | player_id,section_id | 1 | yes | unknown | QUERY_ONLY | L2C_GameTask,L2C_ItemUpdate,L2C_TaskUpdate |
| economy_events | economy.py | player_id | 1 | yes | yes | PERSISTED_NOT_RESTORED | L2C_GameTask,L2C_ItemUpdate,L2C_TaskUpdate |
| economy_grants | economy.py | created_at | 1 | yes | yes | QUERY_ONLY | L2C_GameTask,L2C_ItemUpdate,L2C_TaskUpdate |
| economy_runs | economy.py | uuid | 2 | yes | yes | QUERY_ONLY | L2C_GameTask,L2C_ItemUpdate,L2C_TaskUpdate |
| economy_tasks | economy.py | claimed | 2 | yes | yes | QUERY_ONLY | L2C_GameTask,L2C_ItemUpdate,L2C_TaskUpdate |
| equipment_enhancements | equipment.py | player_id,equip_id,level | 1 | yes | unknown | PERSISTED_NOT_RESTORED | L2C_EquipAll,L2C_EquipStrengthen,L2C_EquipUpdate |
| equipment_instances | equipment.py | id | 1 | yes | yes | RESTORED_AT_LOGIN | L2C_EquipAll,L2C_EquipStrengthen,L2C_EquipUpdate |
| inventory | economy.py | player_id,item_id | 3 | yes | unknown | RESTORED_AT_LOGIN | L2C_GameTask,L2C_ItemUpdate,L2C_TaskUpdate |
| pending_rewards | economy.py | player_id,source,item_id | 1 | yes | unknown | PERSISTED_NOT_RESTORED | L2C_GameTask,L2C_ItemUpdate,L2C_TaskUpdate |
| players | store.py | id | 5 | yes | yes | RESTORED_AT_LOGIN | — |
| progression_receipts | progression.py | player_id,request_key | 1 | yes | yes | QUERY_ONLY | L2C_HeroUpdate |
| shop_purchase_counts | shop.py | player_id,goods_id | 1 | yes | unknown | QUERY_ONLY | L2C_BuyGoods |
| shop_receipts | shop.py | request_key | 1 | yes | yes | QUERY_ONLY | L2C_BuyGoods |
| task_history | economy.py | player_id,kind,start,task_id | 1 | yes | unknown | QUERY_ONLY | L2C_GameTask,L2C_ItemUpdate,L2C_TaskUpdate |
| task_periods | economy.py | player_id,kind | 1 | yes | unknown | QUERY_ONLY | L2C_GameTask,L2C_ItemUpdate,L2C_TaskUpdate |
| wish_last_result | wish.py | player_id,pool_id | 1 | yes | unknown | RESTORED_AT_LOGIN | L2C_CardPool,L2C_HeroUpdate,L2C_LuckDraw |
| wish_pity | wish.py | player_id,category | 2 | yes | unknown | QUERY_ONLY | L2C_CardPool,L2C_HeroUpdate,L2C_LuckDraw |
| wish_receipts | wish.py | player_id,request_key | 1 | yes | yes | RESTORED_AT_LOGIN | L2C_CardPool,L2C_HeroUpdate,L2C_LuckDraw |
| wish_state | wish.py | player_id,pool_id | 1 | yes | unknown | QUERY_ONLY | L2C_CardPool,L2C_HeroUpdate,L2C_LuckDraw |

## Snapshot 实体（players.snapshot JSON）

全部账号级状态（gold/crystal/exp/hero_exp/equip_exp/日周活跃/main_chapter/main_section/mobility/heroes 数组）存于 `players.snapshot`，每次登录经 `snapshot_push` 全量回送（login.py:64-85）；写入走 `save_snapshot` 乐观并发校验（revision 冲突回滚）。

## 风险标注

### PERSISTED_NOT_RESTORED

- `battle_unresolved_rewards`（src/x2server/player/economy.py）
- `economy_checkouts`（src/x2server/player/economy.py）
- `economy_events`（src/x2server/player/economy.py）
- `equipment_enhancements`（src/x2server/player/equipment.py）
- `pending_rewards`（src/x2server/player/economy.py）

### QUERY_ONLY（登录不回送，仅查询时读取）

- `battle_costs`
- `battle_entries`
- `battle_receipts`
- `economy_clears`
- `economy_grants`
- `economy_runs`
- `economy_tasks`
- `progression_receipts`
- `shop_purchase_counts`
- `shop_receipts`
- `task_history`
- `task_periods`
- `wish_pity`
- `wish_state`

### 其他已知边界（引用既有报告）

- battle profile / CheckFightProfile 固定不存在（runtime_coverage_matrix I 域 STUB）。
- Guide/Mail/Achievement/Shop/Activity/Friend/Club 无状态表——客户端请求这些域时无持久化。
- pending_rewards 是待发账本：只登记不自动入包（NEED.md）。
