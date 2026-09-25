---
Document-Type: Current Knowledge
Domain: Equipment
Status: AUTHORITATIVE (PLAN ONLY — 未实施，PART F 约束)
Updated: 2026-09-25
---

# 兽主实例服务器修复方案（Star/quality + 初始词条）

依据：[equipment_star_quality_semantics.md](equipment_star_quality_semantics.md)（A）、
[equipment_initial_affix_semantics.md](equipment_initial_affix_semantics.md)、
[judge_drop_item_cfg](../../../analysis/equipment/judge_drop_item_cfg.md)。
现状：`economy.settle` 已把 outsideItems 写入 `pending_reward_instances{item_id, quantity, quality}`
（UNRESOLVED_INSTANCE_DELIVERY），`EquipmentService` 只有测试实例，无工厂。

## FIX-E1（P0）：outsideItems.quality → HeroEquip.Star

- 语义：对 `ItemType==E_Equip` 的 outsideItem，**Star = quality**（1..6），无需重掷。
  quality ≤ 0 的异常记录 `battle_unresolved_rewards` 并跳过（官方语义下不会出现）。
- TypeId 合法性：`quality ∈ [DroopLimit3.min, DroopLimit3.max]` 的带已由客户端收敛；
  服务器只做防御校验（1..6、Section 带内），不重复 roll（避免双重随机偏离官方分布）。

## FIX-E2（P0）：AttrBD 档位选择 = 初始词条数；数值 = EquibAttrib 阶梯

- 官方规则（A 级）：条数 = 所选条数档行的 `MinorAttrNum`；**base/max 行全部数值=0——
  行只决定条数，数值另有来源**（见 [equipment_initial_value_semantics.md](equipment_initial_value_semantics.md)）。
- **数值来源（本轮闭环）**：类型按 `EquibBase[typeId]` 池；数值按 `EquibAttrib[star, src, type]`
  3 档阶梯（src0=主基础、src2=副基础；src1=主成长、src3=副强化增量）。**取档官方映射未知**
  （ChanceSec 客户端零消费；[60,40]/[80,20] 权重是表结构事实），Revival 以逐段升级链兼容
  （见下与 decisions/compatibility/equip_valuesec_tier_roll.md）。
- **选条数档策略（REVIVAL_COMPATIBILITY / USER_DECISION 2026-09-25，
  见 decisions/compatibility/equip_attribbd_tier_selection.md）**：
  4★/5★/6★ base/Min 档 65% / Max 档 35%；1★/2★/3★ 固定唯一档；非官方概率。
- **数值取档策略（REVIVAL_COMPATIBILITY / USER_DECISION 2026-09-25，
  见 decisions/compatibility/equip_valuesec_tier_roll.md）——逐段升级链**：
  - 主属性初始值：`EquibAttrib[star, src0, type]`——ValueSec[0] 起步，ChanceSec[0]% 升档、
    再 ChanceSec[1]% 升档（src0 ChanceSec=[60,40] → 档位分布 40%/36%/24%）；
  - 副词条初始值：`EquibAttrib[star, src2, type]` 同链（src2=[80,20] → 20%/64%/16%）；
  - 强化增量：`EquibAttrib[star, src3, type]` 同链，每次强化事件各掷一次
    （实施时替换现行 strengthen catalog 的 min-max 均匀 roll——现行为同为兼容实现）；
  - **逐段升级链不是官方已恢复算法**（ChanceSec 客户端零消费，官方映射不可恢复），
    任何文档/代码不得表述为官方。
- 固定发放件（活动/邮件/GM）：整只按 `EquibAttribBD` 盘值写入（GM opt=15 语义），
  seed catalog 的 150001xx/160001xx 预设即此用法（官方值、兼容用途）。

## FIX-E3（P1）：工厂落位与交付

- 新建 `EquipmentInstanceFactory`：输入 (typeId, star, source)；输出完整 HeroEquip
  （Id=AUTOINCREMENT 分配、Level=0、Exp=0、LockState/TimeSec/SeasonId=0）。
- 交付：`settle()` 消费 `pending_reward_instances` → 组装 `RewardData.rewardEquip` 进
  `L2C_CheckoutMainMission(152)` 响应；落库 `equipment_instances`（现表结构已含 star/param）。
- 失败路径：工厂异常时保持现有 UNRESOLVED_INSTANCE_DELIVERY 审计行为，不静默丢件。

## FIX-E4（P1）：强化衔接

- `EquipmentService.strengthen` 现按 `next_level % 3 == 0` 增强已有词条——与官方
  `EquibExp.IsEvent` 事件节点对齐（该表已恢复），并在
  `GetAttrNum(当前) < EquibStage[Star].MinorListMax` 时**新增**一条（取池），
  满 Max 后仅增强已有。初始条数=Min 档（65% 情形）时：4★ 在 +3 或 +6 补到 4 条，5★/6★ 补到 5 条；
  初始=Max 档（35% 情形）则任何事件节点都不再新增。

## FIX-E5（P2）：dropValues 预算（可选）

- 官方客户端按 `BattleInfo.dropValues[AddADCGroup]` 预算收敛掉落（每件扣
  `EquibStage[Star].EquibValue × ItemValue/1000 × num`）。Revival 服务器不重算（掉落已由客户端
  决定），但可校验上报的 outsideItems 组合是否超预算（防作弊，非阻塞）。
- 预算值本身的官方来源（264/266 dropValues 填充）仍未知；校验用保守上限或跳过。

## 明确不做（本轮约束）

- 不实现 887→rewardEquip 之外的 reward pipeline 改动；不改 DropProp 战斗结算。
- 不模拟 IdentifyItem（星级已在客户端掷出并经带收敛，重掷会偏离官方分布）。

## 待实机验证

1. 实机掉落样本核对 `outsideItems.quality` == 展示星级（FIX-E1 语义固化）。
2. 官方件初始条数抽样（Min 档 vs Max 档出现频率）——用于**校准或替换** FIX-E2 的 65/35
   兼容常数（替换需新的 USER_DECISION，见 decisions/compatibility/equip_attribbd_tier_selection.md）。
