---
Document-Type: Current Knowledge
Domain: Equipment
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - equipment_id_star_mapping.md §4 中"quality 是星级载体（B 级强推导）"
  - equipment_instance_generation.md 旧版"客户端战斗模拟选定 Star（B 级）"表述
Evidence-IDs: CLIENT_IL2CPP_2_4, CLIENT_FULL_TABLES_2_4, CLIENT_DUMP_CS
---

# 兽主星级 / quality 语义（掉落管线 A 级闭环）

机器可读：`analysis/equipment/quality_write_xrefs.json`、`quality_consumers.json`、
`judge_drop_item_cfg.md`（含 IdentifyItem 公式）、`droop_limit_xrefs.json`、`equib_value_xrefs.json`、
`callgraph_bl.json`（全二进制 184,213 方法 BL 图）。

## 1. quality 的产生：IdentifyItem（A，0x1E49578）

`DropItemManager$$AddItems` 对每个掉落物建 `ItemStruct{quality=-1, needIdentify=(Item.ItemQuality==E_Unsure(7))}`。
全部 108 个部位级 1240xxx 装备 Item 行均为 `E_Equip(10)+E_Unsure(7)+E_Outside`（item.json 全量验证），
因此**每件战斗掉落装备都走 identify**：

`InitDrop(0x1E48D14)`：`ItemStruct.quality = IdentifyItem(item, level, dropProp)`，逐档尝试
DropBase **6(Legendary)→5(Epic)→4(Rare)**，失败下探，兜底 **3**（1-2★ 不经战斗 ADC 掉落产生）。

每档命中条件（完整公式，见 judge_drop_item_cfg.md §3）：

```
diff = DropBase.Value - (battleLevel - Item.NeedLevel) / DropBase.Divisor
cap  = min( trunc((diff·128)·(1 − Cv/1024)·100 / (magicFind + playerMF + 100)), DropBase.ThresholdValue )
cap < 1 → 128；命中 ⇔ System.Random.Next(1, cap) < 129
```

- DropBase：{6: 400/3/51200, 5: 48/15/6144, 4: 18/20/2304}（Value/Divisor/ThresholdValue）
- Cv 来自 DropProp.LegendaryCv/EpicCv/RareCv：83 个 IsADC 装备组**全部为 0**；仅 13 个 1309xxx
  特殊组非零（Cv=1024 ⇒ 该档必中）
- MF（magicFind/玩家 E_MF=82 属性）提升星率；level>NeedLevel 提升星率
- **概率基准（Cv=0、MF=0、battleLevel≤NeedLevel）**：此时 computed cap ≥ ThresholdValue 被截顶，
  `Next(1,cap)` 上界不含 ⇒ 单档**条件**命中率为**最低基准**：6★ 128/51199≈**0.2500%**、
  5★ 128/6143≈**2.0837%**、4★ 128/2303≈**5.5580%**；level/MF/Cv 使 cap 下降、命中率上升
  （cap≤129 该档必中）。这是"轮到该档"的**条件**命中率——**边际分布**需乘前档失败概率：
  无带时 P(6)≈0.2500%、P(5)=(1−p6)·p5≈**2.0785%**、P(4)=(1−p6)(1−p5)·p4≈**5.4286%**、
  P(3)≈**92.243%**；边际结果再经 DroopLimit3 收敛/拒绝（§2，见 judge_drop_item_cfg.md §4）。

## 2. quality 的收敛：JudgeDropItem（A，0x1E49838）

装备掉落（`isEqt = Item.ItemType==E_Equip`）依次过三道门（完整伪代码见 judge_drop_item_cfg.md §1）：

1. **DroopLimit3（SectionTable+0xB0）= 星级带 [min, max]**：Count 必须 == 2；
   quality > max → **收敛到 max**；quality < min → **拒绝**。
   静态数据：2610 关卡全部为长度 2 的带（[3,6]×1982、[3,5]×251、[3,4]×240、[1,3]×41、[2,6]×27、
   [2,4]×22、[2,5]×20、[1,4]×18、[1,5]×9）。
2. **DroopLimit（+0xA0）= 物品 id 白名单**（装备=1240xxx TypeId）；**DroopLimit2（+0xA8）=
   AddADCGroup 白名单**，仅适用于 `ItemUseScence==E_Maze` 的迷宫物品——**不是星级带**（旧结论拆分）。
3. **组价值预算**：`EquibStage[quality].EquibValue × Item.ItemValue / 1000 × num` 计入
   `DropItemManager.DropValueList[AddADCGroup]`，不得超过 `BattleInfo.dropValues[AddADCGroup]`。

## 3. quality == Star（分类：QUALITY_IS_STAR，掉落管线内 A 级）

- quality 由 IdentifyItem 按 Star 档（DropBase 6/5/4 ↔ Legendary/Epic/Rare）掷出，值域 3..6；
- JudgeDropItem / SetCurItemValueTotal 以 quality 为 **EquibStage 键**（Stage 1-6=星级）；
- 1245|SS|S 展示族 Item.ItemQuality = E_White(1)..E_Red(6) 与星精确对应，quality=-1 时
  `DropItem.Init` 兜底取该静态品质（DropItem.Init 0x1E46798）；
- 传递链：`IdentifyItem → ItemStruct.quality → DropItem.mQuality → PickItem →
  FightItemBag.AddItem(id, quality, …) → FightItemData.quality → SetCheckout_BattleItem →
  887.outsideItems{id, num, quality, eNum=0}`（写入点 2 个、消费点全表见
  quality_write_xrefs.json / quality_consumers.json）。

**结论：对兽主掉落，quality 就是 Star 本身（不是并行档位、不是纯视觉品质）。
Server 收到 outsideItems 后无需重掷 Star，直接 `Star = quality`（band 已由客户端收敛）。**

## 4. Star 概率可恢复性

STAR_RESULT_SEMANTICS = RESOLVED（客户端公式 A 级）。
STAR_PROBABILITY = RESOLVED_FORMULA（客户端动态）：P(6/5/4/3) 由上式给出；运行时输入只有
battleLevel、Item.NeedLevel(全表=10)、DropProp.Cv(ADC 全 0)、magicFind、玩家 E_MF——
**没有结构性未知**。关卡带（DroopLimit3）在 roll 之后做最后收敛。

## 5. 分层归属（PART D）

| 步骤 | 归属 |
|---|---|
| DropClass→候选装备 TypeId（GetDropItemByGroup） | 客户端（掉落层，另见 drop_system.md） |
| Star/quality 掷骰（IdentifyItem） | 客户端 + 静态表（DropBase/DropProp/Item） |
| 星级带收敛（DroopLimit3）+ id/组门（DroopLimit/2） | 客户端 + 静态表（SectionTable） |
| 组价值预算（EquibValue × dropValues[组]） | 客户端执行；**预算表 dropValues 的填充方未定位**（known unknown #2 精化） |
| outsideItems{id, num, quality} 上报 | 客户端 → 887 |
| HeroEquip 工厂：Id、**AttrBD 行选择（Min/Max 档）**、数值 roll | **服务器**（官方选行概率未知；Revival 兼容 65/35，见 initial_affix_semantics.md + decisions/compatibility） |
| 初始词条数 | **= 所选 EquibAttribBD 行的 MinorAttrNum**（行选择服务器侧，见 initial_affix_semantics.md） |
| 实例下发/强化/展示 | wire Star/Param；CheckSubAttruib 强制 Max 上限 |
