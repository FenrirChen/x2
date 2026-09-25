---
Document-Type: Current Knowledge
Domain: Rewards
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - docs/history/2026-09-24_07_deep_drop_archaeology.md
  - docs/history/2026-09-24_03_deep_drop_archaeology.md
Evidence-IDs: see evidence/manifests/evidence_manifest.json
---

# 掉落系统（DropProp 层，与 DropValueID 层严格分离）

**链路（A 级）**：Unit.DC(62 值 100%∈DropClass) / NpcEvent / buff →
`GetDropItemByGroup(DropProp, level)`（0x1E4845C，完整 ARM64 还原）→
FightItemBag.AddItem(source=FIGHT) → checkout outsideItems。

**算法（A/B 级，见 [drop_algorithm.md(drop_algorithm.md)）**：
- 正 Picks：NoDrop + ΣProb 构成权重池，每 pick 互斥选一（先 Range(0,NoDrop+ΣProb) 空奖门控，
  再 GetProbability 选候选）；期望 P(empty)=NoDrop/T, P(i)=Prob[i]/T，T=NoDrop+ΣProb。
- 负 Picks：Prob=确定重复次数（不读 NoDrop）。
- 嵌套 DropClass：LIFO 栈展开；IsADC 组走动态候选（10000/Item.ItemValue 权重，依赖
  SectionTable.DroopLimit 等战斗上下文）。
- **Prob 不是百分比**：原始 332 行中 208 行 NoDrop+ΣProb≠100（合计 1~209）。
- Item.DropLimit/DropLimitParam(417 物品) + DropItemManager.CheckItemLimit = 每物品掉落上限。

**DropValueID 是另一层**：Section.DropValueID（341 值，10600000–10660999）与 DropProp 零交集、
在全部 249 张静态表零命中、第三方独立资料同样无映射（Evidence: DROPVALUE_CROSS_SCAN、
EXTERNAL_CROSSCHECK）——其运行时展开在服务器，语义未解（known_unknowns）。
注意：Section.DropValueID 与战斗内 `BattleInfo.dropValues` 是两回事——后者是
**按 AddADCGroup 的掉落价值预算表**（JudgeDropItem 消费端 A 级：每次装备掉落扣
`EquibStage[quality].EquibValue×ItemValue/1000×num`，超组预算拒绝；BattleInfo 构造器置空表，
填充方未定位，见 known_unknowns #2）。

**SectionTable 掉落字段语义（A 级，JudgeDropItem 0x1E49838 还原 + 3203 关全量验证，2026-09-25）**：
- `DroopLimit` = E_Outside 物品 **id 白名单**（装备=1240xxx TypeId；2011 关含装备）；
- `DroopLimit2` = **AddADCGroup 白名单**，仅适用于 `ItemUseScence==E_Maze` 的迷宫物品；
- `DroopLimit3` = 装备掉落的 **[minStar, maxStar] 星级带**（Count 必须=2；超上限收敛、
  低于下限拒绝；2610 关的带分布见 analysis/equipment/droop_limit_xrefs.json）；
- 星级掷骰由客户端 `IdentifyItem` 完成（DropBase 6/5/4 档公式），带只做收敛——
  详见 equipment/equipment_star_quality_semantics.md。

**ExtraDroop**：SectionGroup→ExtraParam1/ExtraGiftID 的额外掉落桥（26 行，含每日限次 NumLimit），
触发业务未恢复，不自动发放。

图与逐行数据：Evidence: DROP_GRAPH / CLIENT_FULL_TABLES_2_4。
