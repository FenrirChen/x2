---
Document-Type: Server Fix Plan (proposal only — do NOT implement without approval)
Domain: Equipment
Status: SUPERSEDED — 由 docs/knowledge/equipment/equipment_server_fix_plan.md 取代（2026-09-25 本轮
  星级/quality 决定链 A 级闭环后重写；本文 EQX-1 的"B 级载体"与 EQX-2 的"初始=MinorListMin(A)"
  表述已过时）
Updated: 2026-09-25
---

# EquipmentInstanceFactory 修复方案（基于星级编码全量验证）

依据：`docs/knowledge/equipment/equipment_id_star_mapping.md`、
`equipment_initial_affix_semantics.md`、`analysis/equipment/*`。

## EQX-1（P0）：移除"随机 Star"语义，改为掉落携带/上下文决定

- **Current behavior**：知识库旧表述"Server roll Star"——对同一 TypeId 随机星级。
- **Confirmed client behavior (A)**：TypeId(1240|SS|P) 无星级维度；Star 是掉落时刻决定的
  独立属性（战斗 ADC 流程按 Section 星级带选择，quality 是其载体通道）；
  HeroEquip.Star 由服务器下发，客户端用其索引 EquibStage/EquibAttribBD。
- **Required change**：
  1. REMOVE：任何"TypeId → 随机 Star"逻辑。
  2. REPLACE WITH：`Star = f(掉落上下文)`：
     - 战斗掉落（outsideItems）：`Star = outsideItems.quality`（B 级载体，需实机样本验证后升 A；
       验证前可保留 quality 并记录）。
     - Gift/邮件等奖励（GiftValue 只给 1240 部位级 id，无星级载体）：按 Revival 兼容规则
       在 [1..6] 或活动语义内确定，标注 REVIVAL_COMPATIBILITY。
  3. 掉落层的"星级带"（DroopLimit2/3）属于 Drop System 的星级选择，不在实例工厂重复实现。

## EQX-2（P0）：初始副词条按官方静态规则生成

- **Confirmed (A)**：初始条数 = EquibStage[Star].MinorListMin（1/2/3/3/4/4）；
  上限 = MinorListMax（1/2/3/4/5/5）；强化事件（IsEvent=1）未满上限才新增。
- **Required change**：实例生成时 `Av2..Av6` 恰好填 `MinorListMin` 条：
  - 类型从 `EquibBase[typeId].MinorAttrType`（或 EquibAttribBD[star] 行池）不重复抽取；
  - 数值取 `EquibAttribBD` 同星级行 `MinorAttrValue` 域；
  - `Av1/At1` = 主属性（EquibBase.MainAttrType 按 MainAttrChance 加权）；
  - `Lock1..6 = 0`；`Level=0; Exp=0`。
- **REVIVAL_COMPATIBILITY 残留（仅此处允许自定）**：
  1) 4★/5★/6★ 初始条数是否可能 = Max（AttribBD 存在 =Max 行）——默认取 Min；
  2) 数值在域内的具体 roll 分布；3) Gift 发放时的 Star 选择。
- **禁止**：宣称以上分布为官方概率。

## EQX-3（P1）：TypeId 校验

- 实例 TypeId 必须 ∈ EquibBase 键集（1240|SS|P 且 Item 存在的 108 个 id）；
  拒绝 1245|SS|S 套装星级物品作为实例 TypeId（它们无部位/无 EquibBase 行，
  仅用于掉落展示/图鉴）。

## EQX-4（P1）：强化边界对齐

- 强化新增词条的条件与客户端 `CheckSubAttruib` 完全一致：
  `EquibExp[level+1].IsEvent==1 且 当前GetAttrNum < EquibStage[Star].MinorListMax`；
  否则只升级现有词条。确保服务器强化逻辑与该门控一致（防客户端/服务器状态分歧）。

## Persistence / Push / Tests

- 持久化：equipment_instances 增加 star 显式列（或保持 type_id+star 组合唯一性校验）。
- Push：RewardData.rewardEquip（152/1028 内嵌）为主通道；后续 L2C_EquipUpdate(536)。
- Tests：
  1) 掉落 1240|SS|P + quality=q → 实例 Star 与 Param 词条数 = 规则表；
  2) 4★ 实例 Av 非零数=3，强化到 +3 后 ≤4；
  3) 1-3★ 强化永不新增词条；
  4) TypeId=1245xxx 被拒绝；
  5) 重登/幂等不变。
- Risk：中——`quality=Star 载体` 为 B 级，需实机样本（带 quality 的真实掉落）确认后再
  固化为 A；在此之前把 Star 生成保留为可替换函数。
