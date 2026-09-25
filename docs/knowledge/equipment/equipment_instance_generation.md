---
Document-Type: Current Knowledge
Domain: Equipment
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - 本文件 2026-09-25 早前版本（"Star=SERVER_ROLLED（对同一 TypeId 随机）"、
    "quality/eNum 都不是星级参数"、"初始词条数量公式未证实"三处已被推翻/精化）
  - 本文件同日"quality 是星级载体（B 级）"表述（已升级为 Star=quality，A 级，IdentifyItem 闭环）
Corrections:
  - 数值来源已精化（2026-09-25 第二轮）：EquibAttribBD base 行全部数值=0（非数值源）；随机件数值宇宙 = EquibAttrib 3 档阶梯（src0 主基础/src1 主成长/src2 副基础/src3 副增量）；AttribBD filled/seasonal 行=固定发放盘。详见 equipment_initial_value_semantics.md
  - Star 不是对 TypeId 的随机维度：TypeId(1240|SS|P) 无星级字段；Star 由客户端 IdentifyItem
    在掉落时刻掷出（DropBase 档位公式）并经 Section.DroopLimit3 带收敛，outsideItems.quality 直接携带
  - 初始副词条数量已闭环（A）：= 所选 EquibAttribBD 行 MinorAttrNum（行选择服务器侧）；
    合法范围 = EquibStage.MinorListMin..MinorListMax（base 行=Min，双表一致）；上限=强化事件补足
---

# 兽主（Equipment）实例生成链

2026-09-25。证据级：A/B/C/D。机器可读：`analysis/reward_reverse/equipment_instance_writers.json`、
`equipment_attribute_rng.json`；星级编码与词条规则详见
[equipment_id_star_mapping.md](equipment_id_star_mapping.md)、
[equipment_initial_affix_semantics.md](equipment_initial_affix_semantics.md)。

## 1. HeroEquip 完整实例模型（A，PlayerDbData.HeroEquip + CommandX2 同名 wire 类）

| 字段 | 偏移 | 含义 |
|---|---|---|
| Id | 0x10 | 实例唯一 ID |
| TypeId | 0x14 | = Item 1240\|SS\|P（EquibId；**末位=部位 1-6，无星级维度**） |
| Level / Exp | 0x18 / 0x1C | 强化等级/经验（初始 0） |
| Star | 0x20 | 星级（1-6；**独立实例属性，来自掉落上下文，非 TypeId 派生**） |
| Param | 0x28 | EquipParam{At1/Av1=主属性, At2..6/Av2..6=副词条×5, Lock1..6} |
| LockState | 0x30 | 锁定状态 |
| TimeSec | 0x34 | 时效（限时装备） |
| SeasonId | 0x38 | 赛季装备标记 |

## 2. 实例从哪里"出生"（A/B）

- **客户端没有任何本地 HeroEquip 构造路径**：无 ctor 符号、无写入点；实例只经 protobuf
  反序列化出现。GM 工具（GMMainPage.GetEquip 0x13A1F1C）也不本地构造——它校验
  equipId（EquibBase）与星级/属性档（EquibAttribBD）后发 `C2L_Cheat{opt=15,
  values=[equipId, attrbdId]}`，由服务器生成（**equipId 与星级是两个独立输入**）。
- **服务器整只下发**：`RewardData.rewardEquip = List<HeroEquip>`，随
  `L2C_CheckoutMainMission(152)`、`L2C_SecSweep(1028)`、邮件等到达；
  后续变化走 `L2C_EquipUpdate(536)` push，全量走 `L2C_EquipAll(555)`。
- **结论：Id = SERVER_ASSIGNED；Star = 客户端 IdentifyItem 掷出后经 quality 携带、服务器直接采用
  （Star=quality，A）；初始词条数 = 所选 EquibAttribBD 行 MinorAttrNum（选行服务器侧，
  base 行=MinorListMin）；词条数值 roll 在服务器（A/B）。**

## 3. 掉落→实例的完整状态机（B10；2026-09-25 星级决定链 A 级闭环，详见
[equipment_star_quality_semantics.md](equipment_star_quality_semantics.md) 与
[../../../analysis/equipment/judge_drop_item_cfg.md](../../../analysis/equipment/judge_drop_item_cfg.md)）

```
战斗内 ADC 掉落：DropProp 组 → GetDropItemByGroup 选 TypeId → AddItems 建
  ItemStruct{id, num, quality=-1, itemValue, addADCGroup=Item.AddADCGroup,
             needIdentify=(Item.ItemQuality==E_Unsure(7))}
  ↓ InitDrop（对 needIdentify 件）
IdentifyItem(item, level, dropProp)：DropBase 6(Legendary)→5(Epic)→4(Rare) 逐档掷骰，
  cap=min(trunc((Value−(level−NeedLevel)/Div)·128·(1−Cv/1024)·100/(magicFind+玩家MF+100)),
          ThresholdValue)，Next(1,cap)<129 命中；失败下探，兜底 3★
  → ItemStruct.quality ∈ {3..6}                        [A]
  ↓ JudgeDropItem(item, isEqt=ItemType==E_Equip)
DroopLimit3=[min,max] 星级带（超上收敛/低于下拒绝，Count 必须=2）；
DroopLimit.Contains(id)（E_Outside 物品）/ DroopLimit2.Contains(addADCGroup)（E_Maze 物品）；
组价值预算：Σ EquibStage[quality].EquibValue×ItemValue/1000×num ≤ BattleInfo.dropValues[组]  [A]
  ↓ DropItem.Init(…, quality, …) → 拾取
FightItemBag.AddItem(id, quality, num, …, source=FIGHT) → FightItemData.quality          [A]
  ↓ 结算
SetCheckout_BattleItem: source==FIGHT ∧ ItemUseScence==E_Outside → outsideItems{id,num,quality,eNum=0}
  ↓ C2L_CheckoutMainMissionSign(887)
官方服务器：接收 1240xxx+quality → 生成 HeroEquip
  （分配 Id；Star = quality，无需重掷；初始词条数 = 所选条数档（base=Min / max，选档服务器侧）；
    词条类型按 EquibBase 池、数值按 EquibAttrib 3 档阶梯（服务器取档；固定件用 AttribBD 盘值））
  ↓ L2C_CheckoutMainMission(152).rewardData.rewardEquip
客户端：反序列化 → 合并本地装备快照（EquipUpdate/EquipAll 同步）
  ↓ 服务器持久化
装备账本（id 唯一，Param 6 槽 + Lock）
```

- 客户端在 887 里交出 **typeId + 数量 + quality（=Star，A 级）**；具体词条数值 roll 在服务器。
- quality/eNum 语义（A，2026-09-25 闭环）：**对兽主掉落，quality 就是 Star**；
  eNum 仅迷宫物品填写场内获取计数，outside 物品恒 0。
- +3/+6/+9/+12/+15 属性事件（EquibExp.IsEvent）属**强化路径**：
  `CheckSubAttruib` 门控（当前词条数 < EquibStage[Star].MinorListMax 才新增），
  与初始实例生成是两套逻辑，不得混用（B8）。

## 4. 实例生成的官方静态依据（全部在我方 265 表内）

| 输入 | 表 | 状态 |
|---|---|---|
| 部位/套装/主属性候选+权重 | EquibBase{EquibPart, EquibSuit, MainAttrType[], MainAttrChance[], MinorAttrType[], MinorAttrChance[]} | A |
| **初始副词条数（按所选行）** | **EquibAttribBD 行 MinorAttrNum（行选择=服务器）；合法范围 EquibStage[Star].MinorListMin..MinorListMax；base 行=Min（双表一致）** | **A（行级）/选行 SERVER_ONLY** |
| 星级→主属性值/副词条数值域 | **EquibAttrib[star, src0/src2, type] 3 档阶梯（数值宇宙）；EquibAttribBD 盘=固定发放值（base 行全零值，非数值源）** | A（详见 [equipment_initial_value_semantics.md](equipment_initial_value_semantics.md)） |
| **掉落时刻星级** | **客户端 IdentifyItem 掷骰 + DroopLimit3 带收敛；outsideItems.quality 直接携带（Star=quality）** | **A** |
| 星级掷骰概率公式 | DropBase 4/5/6 + DropProp.Legendary/Epic/RareCv + level/NeedLevel + magicFind/E_MF | A（公式恢复，运行时输入可观测） |
| 星级→价值（组预算扣减） | EquibStage.EquibValue（800/1200/1680/2800/3600/5000）× ItemValue/1000 | A |
| 组价值预算上限 | BattleInfo.dropValues[AddADCGroup]（**填充方未定位**） | 消费端 A / 填充 UNKNOWN |
| 强化成本/事件节点 | EquibExp（IsEvent=1 于 +3/6/9/12/15） | A |
| 属性名/上下限 | AttribType | A |
| **数值 3 档取档算法（ChanceSec 用法）** | —（服务器侧；阶梯表已恢复） | **UNKNOWN（宇宙已恢复）** |

## 5. pending_reward_instances 交付差距（B11，已按新结论更新）

| 类别 | 内容 |
|---|---|
| CURRENTLY_KNOWN_FIELDS | typeId(=1240\|SS\|P)、quality(**=Star，A**)、num、来源 Section/run |
| MISSING_FIELDS | **Id 分配、EquipParam(At/Av/Lock)、Level=0、Exp=0、LockState=0、TimeSec=0、SeasonId=0**（Star 已由 quality 携带） |
| SERVER_MUST_GENERATE | Id；**条数档选择**（65/35 兼容决策）；初始词条数=档位行 MinorAttrNum（**A**）；词条类型按 EquibBase 池、数值按 EquibAttrib[star, src0/src2, type] 3 档阶梯（取档=兼容决策；固定件=AttribBD 盘值） |
| CLIENT_ALREADY_GENERATES | 无（零参与；客户端只消费 wire Star/Param） |
| UNKNOWN | AttribBD 选行官方概率（Revival 已定 65/35）；数值 3 档取档算法（数值宇宙已恢复）；BattleInfo.dropValues 填充方 |

**结论**：交付已安全可行——服务器按上表生成完整 HeroEquip、以 `RewardData.rewardEquip`
入 152 响应（或作为补偿走 L2C_EquipUpdate）、持久化 id 账本即可。Star 与初始词条数规则均已
闭环（Star=quality 为官方语义；条数=行常量，仅"选行规则"属 Revival 兼容，须标注）。
实施要点见 `docs/knowledge/equipment/equipment_server_fix_plan.md`。
