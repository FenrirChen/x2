---
Document-Type: Current Knowledge
Domain: Rewards
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - (none; still authoritative)
---

# Server 修复精确方案（只写方案，不实施）

2026-09-25。依据：reward_semantics_reverse_engineering.md 及 analysis/reward_reverse/。
每项含：现状 → 客户端/官方确认行为 → 所需改动 → 静态依据 → 协议依据 → 持久化 → 推送 →
测试 → 风险。优先级按"语义错误 → 交付差距 → 扩展"排序。

## FIX-1（P0，语义错误）：Gift 加权抽取去掉 Σ=100 约束

- **Current**：仅 AwardType 可执行且 ΣProbability=100 的组发放；34 个 Section 被标不可执行。
- **Confirmed client behavior**：`GlobalFun.GetProbability` 按权重和归一化（先求和再
  Range(0,sum) 逐项扣除）——任意正权重合法；E_Random=单次加权抽取一个 GiftValue。
- **Required change**：随机 Gift 统一改为"权重和归一化单次抽取"；删除 Σ=100 门槛；
  E_material 保持整表直出。
- **Static source**：Gift 表（AwardType/Probability/GiftValue/Num）。
- **Protocol source**：L2C_CheckoutMainMission.rewardData / L2C_SecSweep.rewardData。
- **Persistence**：economy_grants 照旧；审计记录记录抽取所用的权重和。
- **Push**：ItemUpdate/PlayerData（现有管线）。
- **Tests**：①E_Random 权重 [2,8,36,1,2,2]（Σ=51）可执行且频率≈归一化；②重复结算幂等不变；
  ③E_Pick/E_BlindBox 仍拒绝（语义未恢复）。
- **Risk**：低。E_RandomInterval 的 Num 维度未证实——先按单次抽取+Num 原值，标注兼容规则。

## FIX-2（P0，定性纠错）：ChallengeReward1 移出奖励字段清单

- **Current**：section_reward 覆盖口径把 ChallengeReward1 列为"独立奖字段"（127 关）。
- **Confirmed**：它是 Language 文案 key（21101515="111%月钻掉落奖励…"）。
- **Required change**：从奖励源清单/文档中移除；保留为关卡挑战说明文案引用。
- **Static source**：Language 表 + SectionTable.0x70。
- **Tests**：目录重生成后无 ChallengeReward1 奖励槽位。
- **Risk**：无。

## FIX-3（P1，交付差距）：装备实例真正生成与交付

- **Current**：1240xxx 进 pending_reward_instances，不创建 HeroEquip，不发 EquipUpdate。
- **Confirmed client behavior**：官方=服务器生成整装 HeroEquip（Id/Star/Param 全服务器侧），
  经 RewardData.rewardEquip 随 152 下发；客户端零生成。
- **Required change**：
  1) 实例生成器：Id=服务器分配（持久账本）；**Star 不按 TypeId 随机**——TypeId(1240|SS|P)
     无星级维度（2026-09-25 修订，旧"按 Revival 分布 roll Star"表述废弃）；Star 从掉落上下文
     确定（战斗掉落=outsideItems.quality 载体，B 级待实机固化；Gift/无载体场景=Revival 兼容规则）。
     EquipParam：主属性按 EquibBase.MainAttrChance 加权选 MainAttrType、值取 EquibAttribBD[Star]
     区间；**副词条条数=EquibStage[Star].MinorListMin（1/2/3/3/4/4，官方规则 A 级，非自定）**、
     类型按 MinorAttrChance 选、值取 EquibAttribBD；Lock1..6=0。
     详见 docs/equipment_instance_server_fix_plan.md 与
     docs/knowledge/equipment/equipment_id_star_mapping.md。
  2) 交付：结算事务内生成 → RewardData.rewardEquip 放入 152 响应 → 持久化装备账本 →
     补发场景走 L2C_EquipUpdate(536)。
  3) 失败/重复请求幂等沿用 battle_receipts。
- **Static source**：EquibBase/EquibAttribBD/EquibStage/EquibExp/Item(1240xxx)。
- **Protocol source**：RewardData(152 内嵌)/L2C_EquipUpdate(536)/L2C_EquipAll(555)。
- **Persistence**：equipment_instances（已有表）+ 实例 ID 账本；pending_reward_instances 转交付。
- **Push**：L2C_EquipUpdate；登录 L2C_EquipAll。
- **Tests**：①掉落 1240xxx 结算后 EquipAll 出现新实例且 Id 唯一；②重登保持；
  ③Param 数值落在 EquibAttribBD 区间；④重复结算不重复生成；⑤权威账本无孤儿。
- **Risk**：中。掉落星级在带内的分布、词条数值 roll 分布仍为 Revival 自定（须标兼容规则）；
  初始词条**条数**已是官方规则（非自定）。AttrID 语义需对照 AttribType 表校验；
  quality=星级载体（B）待实机样本固化。

## FIX-4（P1）：失败战斗物品放行位掩码

- **Current**：失败战斗一律拒绝 outsideItems。
- **Confirmed**：官方客户端在 mode∈{E_ShuangHanBattle(11), E_ActivityBattle(15)} 失败时仍上报
  物品列表（SetCheckout_BattleItem 位掩码 0x80840000）。
- **Required change**：结算校验按 SectionType 放行这两类的失败战斗物品（当前两类不可入场，
  属预防性修正，可与 Battle Entry 扩展同批落地）。
- **Tests**：构造 11/15 类型失败 run 携带物品 → 不拒绝（或明确拒绝并记录类型差异）。
- **Risk**：低（当前无实害，防止未来扩展时误判客户端作弊）。

## FIX-5（P2）：宝箱物品与任务条件 42

- **Current**：ChestReward/ExpertChestReward 仅登记数据源。
- **Confirmed**：两者是 E_Chest 物品 ID（1203501/1203701 系）；ExpertChest 获取由任务条件
  E_GetExpertChest(42) 追踪；开启=物品使用（服务器解析）。
- **Required change**（依赖背包物品使用通道实现）：①章节宝箱条件达成→发宝箱物品入背包；
  ②接入 E_GetExpertChest 任务事件；③宝箱开启服务（roll 内容→RewardData 或 push）。
- **Static source**：Item(E_Chest)/Gift（宝箱内容组）/TaskCondition(42)。
- **Risk**：开启通道的 C2L 未在 Send 泛型清单中出现（B/C 级），需实机或热更证据后再接。

## FIX-6（P2）：mazeItems 对账增强（可选）

- **Current**：忽略 887.mazeItems。
- **Confirmed**：mazeItems{id,num,quality,eNum=场内获取计数}为官方反作弊/一致性载体。
- **Required change**：落库 battle_checkout_wire 已有；可增加 eNum 与服务器侧战斗遥测的对账
  审计（不阻断结算）。
- **Risk**：低；仅审计用途。

## FIX-7（P3，与 Battle Entry 扩展联动）

Tower（927/929）、Battlepass（935/941/949/939/1059）、WorldBoss 全链、Race(1106)、
Collection(588)、活跃宝箱(310) 均为 CLAIM_BUTTON 族：先实现"查询+领取+幂等账本"骨架，
奖励解析复用 FIX-1 的 Gift 管线。每族按 special_reward_state_machines.md 的状态图逐个落地，
不把静态表当触发条件。

## 明确不做

- 不恢复 DropValueID→内容映射（服务器数据失传，维持未解账本）。
- 不猜测 E_Pick/E_BlindBox/宝箱开启的交互语义。
- 不把 WeeklyDungeon 里程碑并入 VReward（触发模型 UNKNOWN）。
- 不宣称星级/词条分布为官方概率。
