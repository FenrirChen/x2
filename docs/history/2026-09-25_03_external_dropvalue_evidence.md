---
Document-Type: Historical Report
Date: 2026-09-25
Status: CURRENT_AT_TIME
Superseded-By:
  - docs/knowledge/rewards/drop_system.md (DropValueID 层结论已并入)
Note: moved from D:/demo/x2/docs/ during knowledge reorg
---

# DropValueID 第三方证据核查（A7 专项）

2026-09-25。对象：第三方工作簿《解神者本地单服-数据对照表.xlsx》（232 个 sheet）。

## 搜索范围

对全部 232 个 sheet 的每个单元格做数值扫描，查找我方 341 个 Section.DropValueID
（10600000–10660999，含金币本 10630101–10630105）。

## 结果

| 事实 | 结果 |
|---|---|
| 出现 DropValueID 的 sheet | **仅「关卡掉落」1 个**（341/341 值齐全，3,202/3,202 行与我方 SectionTable.DropValueID 逐一相等） |
| DropValueID → DropClass 映射 | **不存在**（与深挖考古结论一致：两段 ID 无交集） |
| DropValueID → 概率/物品 | **不存在**（任何 sheet 均无 106xxxxx 与掉落物/权重并列出现） |
| 第三方对两者的关系陈述 | 其「说明」页明确写道：DropValueID 是 106xxxxx 段，DropClass 是 130xxxx 段，**没有直接交集** |

## 判定

第三方独立工作同样得出"DropValueID 无法静态映射掉落内容"的结论，
与我方 `deep_drop_archaeology.md` 的 A 级负面证据**双向互证**。
该工作簿不包含任何 DropValueID→掉落映射、server dropValues 样本或关卡实际掉落数量表。

第三方与我方一致指出的真实落点：
- 关卡可见掉落 = `DroopDisplay`（掉落展示）与 `DroopDisplayProbability`（随机兽主，1209162–65）；
- 关卡额外掉落 = `ExtraDroop`（SectionGroup→ExtraParam1/ExtraGiftID）。

**结论：无新映射可导入。DropValueID 的运行时语义仍是唯一服务器侧未知项。**
