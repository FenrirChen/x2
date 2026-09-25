---
Document-Type: Current Knowledge
Domain: Rewards
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - (none; still authoritative)
---

# X2 真实奖励体系（三层→五层重构总图）

2026-09-25。本轮为客户端原生逻辑还原轮的总结：PART A/B/C 的全部证据
（`analysis/reward_reverse/` 八份 JSON）收敛为一张体系图 + Server 语义审查 + 20 问终答。

## 1. 五层奖励体系图（PART D）

```
┌─ 1. ROGUELITE_LOCAL_STATE ─────────────────────────────────────────────┐
│ 场内银币(903)·神迹(RelicItem)·塔道具·Buff·E_Maze 物品/mazeItems        │
│ 计算:客户端 │ 随机:客户端(战斗RNG) │ 保存:内存 │ 发奖:无 │ 持久化:无    │
│ 出口:仅 mazeItems+eNum 遥测(887 field 50)，不入账号                      │
└──────────────────────────────────────────────────────────────────────┘
┌─ 2. BATTLE_PERSISTENT_DROP ────────────────────────────────────────────┐
│ Unit.DC→DropProp(客户端 GetDropItemByGroup 完整还原)·buff Gift→        │
│ FightItemBag(source=FIGHT)·E_Outside 过滤→887.outsideItems             │
│ 计算/随机:客户端 │ 保存:战斗包 │ 发奖:无 │ 校验数据:eNum/getItemData   │
└──────────────────────────────────────────────────────────────────────┘
┌─ 3. SECTION_SETTLEMENT_REWARD ─────────────────────────────────────────┐
│ FirVReward/VReward/MopReward → Gift →【官方服务器解析】→ RewardData     │
│ {rewardItem, rewardEquip, transformHero} 经 152/1028 下发              │
│ 计算/随机:服务器(客户端解析器 GetItemByGiftGroup 存在但孤立)           │
│ 保存:服务器 │ 发奖:服务器                                              │
└──────────────────────────────────────────────────────────────────────┘
┌─ 4. SPECIAL_GAME_MODE_REWARD ──────────────────────────────────────────┐
│ Chest(E_Chest 物品+ITEM_USE)·ExpertChest(E_GetExpertChest=42 任务事件) │
│ Tower/Battlepass/Race/Collection/活跃宝箱=CLAIM_BUTTON 协议族           │
│ WorldBoss=QUERY_PLUS_CLAIM 全链 │ 周本里程碑=UNKNOWN                   │
│ 计算/随机:服务器 │ 触发:客户端点击(有发送点为证)                        │
└──────────────────────────────────────────────────────────────────────┘
┌─ 5. ACCOUNT_INSTANCE_REWARD ───────────────────────────────────────────┐
│ 兽主 HeroEquip{Id,TypeId,Star,Param(6×At/Av+Lock),LockState,TimeSec…}  │
│ 来源:RewardData.rewardEquip 整只下发 │ 客户端零生成零随机              │
│ 服务器依据:EquibBase 候选/权重+EquibAttribBD 数值域(官方参数表)         │
└──────────────────────────────────────────────────────────────────────┘
```

## 2. Server 语义审查（PART E，不改代码）

| 当前行为 | 判定 | 依据 |
|---|---|---|
| FirVReward/VReward 按 Gift 固定值入账 | LIKELY_CORRECT | RewardData=服务器解析（协议 A 级）；固定 Gift 直出与 GetItemByGiftGroup 的 E_material 分支一致 |
| MopReward 扫荡独立请求+服务器解析 | CONFIRMED_CORRECT | C2L/L2C_SecSweep 结构（A） |
| outsideItems 逐项验证后入账 | CONFIRMED_CORRECT | 与 SetCheckout_BattleItem 过滤链一致 |
| 拒绝失败战斗的 outsideItems | POTENTIALLY_WRONG（局部） | 官方客户端在 E_ShuangHanBattle(11)/E_ActivityBattle(15) 失败时仍上报（位掩码 0x80840000）；当前两类未实现，暂无实害 |
| Gift.E_Random 仅执行 ΣProbability=100 的组 | **WRONG（约束无据）** | 客户端 GetProbability 按权重和归一化，任意正权重合法；该约束把 34 个 Section 误标不可执行 |
| 装备型奖励只进 pending_reward_instances | COMPATIBILITY（已知差距） | 官方流程=服务器生成整装 HeroEquip；参数表已齐备，可安全交付 |
| ChallengeReward1 计入"独立奖字段" | WRONG（定性错误） | 是 Language 文案 key（A 级证据） |
| pending_rewards/未解账本不伪造 | CONFIRMED_CORRECT | 与"服务器数据不可恢复"边界一致 |
| 忽略 mazeItems | LIKELY_CORRECT | 遥测/校验载体，非交付清单；可用于未来对账 |

## 3. 二十问终答（PART J）

1. **FightItemBag 局内状态**：mItemList（source 标记）、mMoney/mTrueMoney 货币桶、
   RelicItem/TowerItem/TowerLib、银币计数、增益倍率、profileDropItems 遥测。
2. **哪些 Item 能进 outsideItems**：source==FIGHT ∧ ItemUseScence==E_Outside ∧ Item 表存在。
3. **局内资产为何不带出**：货币在桶不在列表；神迹/塔在独立列表；E_Maze 进 mazeItems 遥测；
   E_Alchemy/未设置被丢弃；非 FIGHT 来源被过滤。
4. **SetCheckout_BattleItem 真正规则**：见 fightitembag_persistence_boundary.md §2 伪代码
   （含失败放行位掩码 0x80840000 与 eNum 钳制）。
5. **FirVReward 谁读取**：服务器结算（RewardData 下发）；客户端仅 UI 预览链（B）。
6. **VReward 谁读取**：同上；战斗结算不本地解析（A）。
7. **MopReward 谁读取**：服务器扫荡解析（L2C_SecSweep.rewardData，A）。
8. **Gift 谁执行**：发放=SERVER_EXECUTED；客户端解析器存在但孤立。
9. **Gift.E_Random 谁计算**：算法=单次加权抽取（GetProbability，无 Σ=100 约束）；
   2.4 原生无业务调用者（疑似缺失热更 DLL）；实际发放由服务器完成。
10. **当前 Server Gift 发奖是否符合原逻辑**：属于"重建官方服务器行为"的兼容实现（B 类），
    方向正确；但 Σ=100 约束违反客户端算法证据（WRONG），E_Pick/E_BlindBox 语义未恢复。
11. **兽主掉落后客户端拿到的原始数据**：ItemDataP{id=1240xxx, num, quality(=星级载体，B), eNum=0}。
12. **HeroEquip.id 谁生成**：SERVER_ASSIGNED（RewardData.rewardEquip 整只下发）。
13. **quality 是什么**：战斗包物品品质；**对兽主掉落是星级载体**（掉落管线以 quality 索引
    EquibStage，B 级强推导，待实机样本固化）——2026-09-25 修正，旧表述"与星级无关"已撤。
14. **eNum 是什么**：迷宫物品的场内获取计数（StatsManager.getItemData），outside 物品恒 0。
15. **星级谁决定**：掉落时刻决定（客户端战斗 ADC 在 Section 星级带 DroopLimit2/3 内选定，
    quality 为载体）→ 实例 Star 由服务器按掉落上下文确定后下发；**不可由 TypeId 派生**
    （1240|SS|P 无星级维度）。详见 equipment/equipment_id_star_mapping.md。
16. **初始随机词条谁生成**：SERVER_GENERATED（EquipParam 全量在 wire 上）；**条数规则已恢复
    （A）**：= EquibStage[Star].MinorListMin（1/2/3/3/4/4），上限 MinorListMax；类型/数值按
    EquibBase/EquibAttribBD 池 roll。
17. **新装备走什么 L2C**：RewardData.rewardEquip 内嵌于 152/1028 响应；后续 L2C_EquipUpdate(536)；
    全量 L2C_EquipAll(555)。
18. **Chest/Challenge reward 自动还是手领**：Chest/ExpertChest=给 E_Chest 宝箱物品
    （物品使用开启，ExpertChest 另有任务条件 42 追踪）；ChallengeReward1=文案 key，非奖励。
19. **Tower/WorldBoss/Activity 触发模型**：Tower=CLAIM_BUTTON(927/929)；WorldBoss=
    QUERY_PLUS_CLAIM 全链(679/415/701/417/407/409/419/471)；Activity 进度=活动协议族
    (618/620/858/1112 等)，与战斗结算两套系统；Battlepass=CLAIM_BUTTON 族(935/941/949/939/1059)。
20. **当前 Server 的理解偏差**：ChallengeReward1 误当奖励字段；Gift.E_Random Σ=100 约束
    无据；装备实例未真正交付；失败战斗物品一刀切拒绝（对 11/15 类型与官方不符）；
    其余主链（固定 Gift/outsideItems/扫荡/幂等）方向正确。

## 4. 本轮证据文件

`analysis/reward_reverse/`：fightitembag_methods.json、item_use_scene_consumers.json、
gift_consumers.json、gift_random_algorithm.json、equipment_instance_writers.json、
equipment_attribute_rng.json、special_reward_consumers.json、special_reward_protocols.json。
重建脚本：`tools/analysis/build_reward_reverse.py`（确定性、可重跑）。
配套文档：fightitembag_persistence_boundary / gift_runtime_semantics /
equipment_instance_generation / special_reward_state_machines / reward_system_server_fix_plan。
