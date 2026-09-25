---
Document-Type: Current Knowledge
Domain: Equipment
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - 本文件 2026-09-25 早前版本（"初始=MinorListMin"标为 A 级、AttribBD=Max 行无解释两处已修正：
    MinorListMin 客户端 0 读者（A 级新证据），初始条数=AtribBD 行常量（A 级新证据），选行规则=服务器未知）
  - 同日"选行概率=服务器未知"孤立状态（已补充 Revival 65/35 兼容策略，USER_DECISION 2026-09-25）
Evidence-IDs: CLIENT_IL2CPP_2_4, CLIENT_FULL_TABLES_2_4, CLIENT_DUMP_CS
---

# 兽主初始副词条语义（决定链已闭环；官方选行概率未知，Revival 采用 65/35 兼容策略）

机器可读：`analysis/equipment/minor_list_min_xrefs.json`、`minor_list_max_xrefs.json`、
`minor_attr_num_xrefs.json`、`equib_attrib_bd_lookup_xrefs.json`、`affix_count_models.json`、
`equip_param_slot_consumers.json`。

## 1. 槽位语义（A 级，GetAttrNum 0x1C30E28 全量反汇编复核）

`EquipParam{At1..At6, Av1..Av6, Lock1..Lock6}`：At1/Av1=主属性槽（不计数）；
**"已有副词条数" = Av2..Av6 中非零 Av 的个数**（最多 5 条）。

## 2. 条数由什么决定（本轮修正后的决定链）

**条数 = 官方服务器装备工厂所选 `EquibAttribBD` 行的 `MinorAttrNum`**（A 级）。
证据：GM 协议 `C2L_Cheat{opt=15, values=[equipId, attrbdId]}`（GMMainPage.GetEquip 0x13A1F1C 全量
反汇编）表明官方服务器以 **AttrbdID 行**为构建规格；行内
`EquibQuality(=Star) + MinorAttrNum(=初始条数) + MinorAttrType/Value(池) + MinorAttrStreNum/StreValue(强化增量)`
是完整参数集。客户端对 MinorAttrNum **零游玩消费**（EquibAttribBDManager.GetItem 仅 GM UI 两处调用）。

同星多行不是条数随机，而是**构建规格档**（B4）：
| 档 | AttrbdID 模式 | MinorAttrNum |
|---|---|---|
| base 档 | QQ000000（+空池变体） | = MinorListMin（1/2/3/3/4/4） |
| Max 档 | QQ000100 | = MinorListMax（仅 4/5/6★ 有：14000100=4、15000100=5、16000100=5） |
| 填池变体 | QQ000101..106 | 4★ 行=3（Min），5★/6★ 行=5（Max） |
| 赛季/活动档 | 16151100-122（6★） | 4 或 5，StreNum/StreValue 非零 |

## 3. 星级 → 合法条数范围（A 级：客户端强制 + 双静态表一致）

| Star | MinorListMin | MinorListMax | AttribBD 行 MinorAttrNum |
|---:|---:|---:|---|
| 1★ | 1 | 1 | {1} |
| 2★ | 2 | 2 | {2} |
| 3★ | 3 | 3 | {3} |
| 4★ | 3 | 4 | {3, 4} |
| 5★ | 4 | 5 | {4, 5} |
| 6★ | 4 | 5 | {4, 5} |

- **MinorListMax（A 级，0x1C30E04）**：`CheckSubAttruib` 在强化事件节点
  （EquibExp[level+1].IsEvent==1，即 +3/6/9/12/15）返回 `GetAttrNum >= MinorListMax`——
  未满才允许新增一条。Max = 强化可补到的上限（同时约束初始 ≤ Max）。
- **MinorListMin（本轮修正）**：**客户端全二进制 0 读者**（184,213 方法扫描，
  EquibStageManager.GetItem 六个调用点无一读 0x14）。它不是客户端执行的规则，而是
  静态数据锚点/服务器输入——**不能以客户端代码证明"初始一定=Min"**。
- 三层判定：
  | 层 | 结论 | 级别 |
  |---|---|---|
  | INITIAL_MINOR_COUNT_ALLOWED_RANGE | Star→[Min,Max]（上表） | **A** |
  | INITIAL_MINOR_COUNT_DETERMINISTIC_RULE | 条数=所选 AttribBD 行 MinorAttrNum（A）；官方掉落路径选行规则未知（SERVER_ONLY），**Revival 兼容策略：base/Min 档 65% / Max 档 35%（仅 4/5/6★；1-3★ 固定唯一档）——REVIVAL_COMPATIBILITY/USER_DECISION，非官方概率** | A/选行 REVIVAL_COMPAT |
  | INITIAL_MINOR_COUNT_PROBABILITY | 官方选行概率不可恢复（客户端无证据）；Revival 已采用 65/35 兼容策略（见 decisions/compatibility/equip_attribbd_tier_selection.md） | 官方 SERVER_ONLY_UNKNOWN / Revival 已决策 |

## 4. 初始 vs 强化（B7/B8 复核）

- **初始**：Level=0 件由服务器工厂生成——条数=所选条数档行 MinorAttrNum；**类型** ∈
  EquibBase[typeId].MinorAttrType（加权）；**数值** ∈ EquibAttrib[star, src2, type] 3 档阶梯
  （取档服务器侧，见 equipment_initial_value_semantics.md）。固定发放件则整只按 AttribBD 盘值写入。
- **强化**：仅 `EquibExp[level+1].IsEvent==1` 节点检查 `GetAttrNum < MinorListMax`，未满则
  **新增一条**（客户端门控 0/1/-1；实际写入由服务器完成）。1-3★ Min==Max 永不新增；
  4★ 可 +1（3→4）；5★/6★ 可 +1（4→5）。初始生成与强化新增是两条路径，不混淆。

## 5. 合法范围（供 Server 兼容实现）

`Star=S` 的实例：Av2..Av6 非零条数 ∈ [EquibStage[S].MinorListMin, MinorListMax]；
每条 AtK ∈ EquibBase[typeId].MinorAttrType（加权），AvK ∈ EquibAttrib[star, src2, AtK] 3 档阶梯
（离散档位非连续域）；Av1=主属性（EquibBase.MainAttrType 单候选，值 ∈ EquibAttrib[star, src0, type]
阶梯）；Level=0 时强化增量（src3/盘 StreValue）未应用。
**已知未知（收窄）**：官方掉落/发放路径的 AttribBD 选行概率（Min 档 vs Max 档触发条件）与
数值 roll 分布。Revival 侧选行已决策为 **base 65% / max 35%**（仅 4/5/6★ 两档星级；
REVIVAL_COMPATIBILITY/USER_DECISION，非官方概率，见
[decisions/compatibility/equip_attribbd_tier_selection.md](../../decisions/compatibility/equip_attribbd_tier_selection.md)）。
