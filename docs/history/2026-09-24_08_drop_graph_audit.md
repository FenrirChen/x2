---
Document-Type: Historical Report
Date: 2026-09-24
Status: CURRENT_AT_TIME
Superseded-By:
  - docs/knowledge/rewards/ (domain docs)
Note: moved from D:/demo/x2/docs/ into the repository during knowledge reorg
---

# DropProp 递归图审计

2026-09-24。数据源：`analysis/drop_archaeology/drop_graph.json`（全部 332 条 DropProp 展开）、
`full_tables/`（APK 直接解码）。节点类型判定完全来自真实表 ID domain（见 id_namespaces.md），
未按数字大小猜。

## 1. 总量

- DropProp 表 332 行，332 个不同 DropClass（1301101–1309250）。
- 被其他表引用的根节点：**147 个**。引用来源表：unitbase 610 次、npcevent 80、
  passivespelltb 80、x2buffbase 2、fishing 5。
- 嵌套：28 个 DropClass 出现在其他 DropProp 的 ItemList 中（DROP_GROUP→DROP_GROUP）。

## 2. 全部条目（332 行 × ItemList）的子节点类型

| 子节点类型 | 数量 | 判定依据 |
|---|---:|---|
| ITEM（Item.ItemID） | 258 | 值 ∈ item 表 3,026 个 ItemID |
| DROP_GROUP（嵌套 DropClass） | 112 | 值 ∈ dropprop 表 DropClass |
| UNKNOWN | 83 | 唯一取值 **0**（ItemList=[0]，"无物品"哨兵） |

即：**除哨兵 0 外没有任何未归属子节点**。

## 3. 147 个根节点的递归闭包

从 147 个被引用根递归展开（深度上限 8，含环检测），叶节点统计：

| 叶类型 | 数量 |
|---|---:|
| ITEM | 133 |
| UNKNOWN（全为哨兵 0） | 92 |

**结论：递归闭包 COMPLETE。** 每条 DropProp 链最终都落到具体 `Item.ItemID` 或空哨兵 0；
不存在"DropProp→DropProp→…永不落地"的断链，也没有落到 Unit/NPC/其他 namespace 的边。
金币本的 1309024→1302601、1309026→1301201 等嵌套组全部展开到 Item。

## 4. 需要澄清的语义（非掉落清单的部分）

- `Picks`/`NoDrop`/`Prob` 是抽取参数（Prob 权重基数见 DropItemManager 常量
  DROP_WEIGHT_PARAM=10000，dump.cs 0x1E47E30 区域），但**抽取发生在客户端战斗运行时**
  （GetDropItemByGroup 调用随机函数），结果仅作为上报，不是服务端权威概率。
- `Level` 字段参与 IdentifyItem（品质/等级修正），具体公式在原生代码内，本轮未逐指令还原。
- Item 表自带 `DropLimit`/`DropLimitParam`（417 个物品配置了每日/每局上限），
  由 DropItemManager.CheckItemLimit + mItemDayNumCache 消费，是掉落上限的官方配置点。

## 5. 哨兵 0 的语义

83 行 `ItemList=[0]`（Picks 通常配 NoDrop），表示"该组可能什么都不掉"。
这是配置约定，不是解析失败：所有 83 行都能完整 decode。
