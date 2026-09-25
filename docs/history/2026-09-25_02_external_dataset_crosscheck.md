---
Document-Type: Historical Report
Date: 2026-09-25
Status: CURRENT_AT_TIME
Superseded-By:
  - docs/knowledge/rewards/ (domain docs)
Note: moved from D:/demo/x2/docs/ into the repository during knowledge reorg
---

# 第三方数据集交叉验证报告（《解神者本地单服-数据对照表.xlsx》）

2026-09-25。对象：另一开发者公开发布的 232-sheet 数据对照工作簿。
定位：**INDEPENDENT_EXTERNAL_DATASET**——只有能被我方 APK 独立复现的内容才可升为可用证据。
本轮只覆盖掉落与商店两域；未修改 Server/APK/SQLite，未导入任何第三方数值。

## 总评

第三方工作簿的掉落与商店静态层**大体上确实来自真实客户端数据**：
掉落组/掉落明细/关卡掉落/商店/商店商品五个核心 sheet 与我方独立解码达到 99%–100% 逐字段一致
（掉落组 329/332、掉落明细 452/453、关卡掉落 3202/3202、商店商品 1567/1567）。
分歧集中在 6 处，全部可仲裁为我方原始字节正确（第三方存在未申报的规则性修复与解析噪声）。
商店**商品内容映射双方都没有**——第三方亦确认 GoodsID→ItemID 由服务端决定，与我方结论互证。

## 分 sheet 评分

| Sheet | 行数(数据) | Exact | Derived | External only | Conflict | Assessment |
|---|---:|---:|---:|---:|---:|---|
| 掉落组 (DropProp) | 332 | 329 | 0 | 0 | 3 | 99.1% 逐字段一致；3 处为其未申报的 Σ=100 修复（见 conflicts.json） |
| 掉落明细 (DropProp 展开) | 453 | 452 | 0 | 0 | 1 | 99.8%；展开口径与我方 drop_graph 相同（嵌套组标"→ 掉落组"） |
| 掉落品质 (DropBase) | 1 | 0 | 0 | 0 | 1 | 仅列 ID6 且 ThresholdValue=18553 与客户端 51200 冲突（其行界错位；×128 数列规律判客户端胜） |
| 关卡掉落 (SectionTable 掉落列) | 3202 | 3202 | 0 | 0 | 0 | 100%：DropValueID/掉落展示/首通/通关奖励全对 |
| 商店 (ShopConfig) | 25 | 24 | 0 | 0 | 1 | 96%；801 的季节组关联在其解析中丢失（24 组/64 条目被标"未引用"） |
| 商店商品 (ShopGoodsGroup) | 1567 | 1567 | 0 | 0 | 0 | 100%：GoodsID 集合与 ItemPrice 逐一相等 |
| 商店可购道具 (ItemSource 整理) | 355 | 0 | 355 | 0 | 0 | B 级 DERIVED_MATCH：202 个道具是我方 itemsource.json(234) 真子集，0 条第三方独有 |
| 迷宫商店 (MazeShop) | 127 | 123 | 0 | 0 | 4 | 96.9%；4 行为其解析噪声（越界值 1554822 等） |
| 外观商店 (AppearanceShop 整理) | 47 | 46 | 1 | 0 | 0 | 其人工修值 15232→1280 与我方 canonical 解码一致（B 级互证） |
| 随机商店(实测) | 22 | 0 | 0 | 22 | 0 | C 级 NEW_EXTERNAL_DATA：唯一非客户端来源的成交价记录（用户口述） |
| 兽主掉率(自定) | 104 | 0 | 104 | 0 | 0 | 其自建模型（STAR_RATIO r=0.5 自选），非官方数据；基础倍数引自我方已验证的关卡文案 |
| 卡池概率 / 充值档位 / 礼包 等 | — | — | — | — | — | 本轮范围外，未核 |

## 掉落数据核心判定（Part A）

1. **概率口径（2026-09-25 IL2CPP 复核）：RAW_PROB_PARAMETER。** 第三方“掉落概率%”
   列只是 DropProp.Prob 原值加“%”呈现，不能当作真实百分比。其“实测
   NoDrop+ΣProb=100”作为不变量是错的：原始 332 行中 208 行不满足（合计分布
   1–209，仅 124 行=100）。ARM64 已证实：普通正 Picks 组中 Prob 是与 NoDrop
   竞争的权重，每次候选 i 的条件化、限额前概率为 Prob[i]/(NoDrop+ΣProb)；负 Picks
   组中 Prob[i] 是确定重复次数；IsADC 组需动态候选上下文。此前“10000 用于普通
   GetDropItemByGroup 抽取、语义未复原”的判断已撤销；10000 实际出现在 IsADC
   `CheckItem` 的 `10000/Item.ItemValue` 动态候选权重中。见
   [定点算法报告(../knowledge/rewards/drop_algorithm.md)。最终游戏掉率
   仍受候选过滤、限额及服务端结算影响，不能直接由静态字段当百分比读取。
2. **递归展开：双方结构一致。** 掉落明细 453 行 = 我方 drop_graph 的 258 ITEM + 112 嵌套 +
   83 零占位（453），嵌套引用逐个 ID 相等。
3. **IsADC 83 组：一致。** 双方均为 IsADC=E_ADC 且 ItemList=[0]；ARM64 已证实该分支
   调用 `AddMetaLoot` 动态构造物品候选。最终物品率须结合战斗上下文，现有静态表不能给出。
4. **DropValueID：无映射（见 external_dropvalue_evidence.md）。** 341 值仅出现在关卡掉落
   上下文中；第三方独立复述了与我方相同的否定结论——双向互证。
5. **第三方独有掉落数据：无。** 未发现任何我方没有的掉落映射/数量表/服务器 dropValues。

## 商店数据核心判定（Part B）

1. **可信度基线拉满：** ShopConfig 24/25、ShopGoodsGroup 1567/1567 逐字段一致，
   包括价格、货币枚举、限购周期、条件。
2. **商品内容映射：双方均无。** 第三方明确写道"客户端没有任何表把 GoodsID 映射到道具，
   具体卖什么由服务端 L2C_Goods.itemId 决定（原服数据已随停运丢失）"——与我方
   economy_missing_evidence_followup 的 LIKELY_SERVER_ONLY 判定互证。
   我方 17 条 QuickBuyID 反查仍是唯一静态线索；第三方 0 条新增。
3. **随机商店(实测) 22 条是本轮唯一真正的外部增量**：商店 801 随机格的商品名/数量/实测价
   （如 1★神格碎片×3 @22500 金币，可因果购买）。价格与我方静态默认价（光辉 20/60/120…）
   完全不同且货币不同，佐证"成交价=服务端计算"。**未验证、未导入**，仅登记为
   shop_external_only.json 的候选样本。
4. **版本漂移：未发现。** 价格/ID/结构全部对上 2.4；无旧版本特征。

## 反向检索我们遗漏的数据（Part D）

第三方结构化字段逐一反向对照：
- IsMaze/Related/IsActivity：客户端 DropProp 类字段确实存在（dump.cs 0x48/0x4C/0x50），
  我方 decode 中线上无值（全表默认）——不是遗漏。
- 掉落品质"容器杂项 3:[48],4:[15],5:[6144]"：经核对为第三方行界错位把 ID5 的值混入 ID6 行，
  非未知字段；我方 DropBase 6 行 5 字段零剩余。
- ShopGoodsGroup 无商品内容字段：双方一致，确认非提取遗漏。
- 未发现任何"我提取了表但没理解字段"的新证据。

## 6 处冲突仲裁（全部判客户端原始数据胜，详见 conflicts.json）

| 冲突 | 客户端 | 第三方 | 仲裁依据 |
|---|---|---|---|
| DropBase ID6 ThresholdValue | 51200 | 18553 | ID1–5 呈 Value×128 恒定比 |
| DropProp 1309064 NoDrop | 48 | 50 | 原始字节+其修复规则不成立+未登记 |
| DropProp 1309176 NoDrop | 25 | 95 | 同上 |
| DropProp 1309250 Prob | 1 | 99 | 同上 |
| MazeShop ID1/26/64/131 | 连续组段 | 越界/破序 | 数列规律 |
| ShopConfig 801 季节组 | 24 组已关联 | 标未引用 | SeasonGoodsGroupId 在我方 decode 完整存在 |

## 可采性结论

- **可升为 CLIENT_CONFIRMED（B 级互证）**：外观商店 1980007 价格 1280（双方一致）；
  兽主星级区间文案 vs f27 的差异描述（与我方 DroopLimit2/3 数据域一致）。
- **可作为线索保留（C 级）**：随机商店(实测) 22 条成交价样本——若未来实现商店 801，
  这是唯一的数量/价格参照，但必须标注为"口述实测，非官方确认"。
- **不采纳**：3 处 DropProp 修复值、DropBase 18553、MazeShop 4 行、商店 801"未引用"判定。
- **本轮无任何数据直接写入 Server。**

## 交付物

- `analysis/external_crosscheck/drop_prop_diff.csv` — 332 行逐字段 diff
- `analysis/external_crosscheck/drop_external_only.json` — 第三方修复行/叙述性声明核查
- `analysis/external_crosscheck/shop_goods_mapping.csv` — 1567 行 GoodsID 对照（含 QuickBuy 线索标记）
- `analysis/external_crosscheck/shop_external_only.json` — 随机商店实测 22 条
- `analysis/external_crosscheck/conflicts.json` — 6 冲突 + 1 互证仲裁
- `analysis/external_crosscheck/source_fingerprint.json` — 工作簿指纹与来源自述
- `docs/external_dropvalue_evidence.md` — A7 专项
- 复核脚本：`analysis/external_crosscheck/crosscheck_drop.py`、`crosscheck_shop.py`
