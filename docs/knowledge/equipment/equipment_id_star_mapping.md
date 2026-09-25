---
Document-Type: Current Knowledge
Domain: Equipment
Status: AUTHORITATIVE
Updated: 2026-09-25
Evidence-IDs: CLIENT_FULL_TABLES_2_4, CLIENT_IL2CPP_2_4, CLIENT_DUMP_CS
Supersedes:
  - 旧结论"Server 在实例生成阶段对同一 TypeId 随机 Star"（部分推翻——见下）
---

# 兽主 ID / 星级映射（全量审计结论）

数据源：Item(3,026)/EquibBase(126)/EquibStage(6)/EquibAttribBD(66) 全量 +
GMMainPage.GetEquip / CheckSubAttruib / GetAttrNum 反汇编。
机器可读：`analysis/equipment/equipment_id_matrix.csv`（228 件）、
`equipment_star_exceptions.json`（18 条例外）、`hero_equip_star_consumers.json`。

## 1. 两族物品结构（A 级，全量验证）

| 族 | 数量 | 编码 | 末位含义 | EquibBase 行 | 用途 |
|---|---:|---|---|---:|---|
| `1240\|SS\|P` 部位级 | 108 | 套装序号 SS(00-19)+部位 P(1-6) | **部位** | 有（逐行属性池） | 实例 TypeId / Gift 奖励 |
| `1245\|SS\|S` 套装星级级 | 120 | 套装序号 SS(00-19)+星级 S(1-6) | **星级** | **无** | 掉落展示(DroopDisplay 64 处)/图鉴 |

- 名称佐证：1240 族 = "奇美拉·一/二/…/六"（**·N=部位**）；1245 族 = "奇美拉(4★)套装"
  （1-3★ 名字不带★，4-6★ 带；品质 E_White→E_Red 精确对应 1-6 星）。
- **20 个套装星级组全部完整（1-6★ 无缺星）**；例外 18 条 = EquibBase 有行但无 Item 的
  套装 407/408（12 行）与测试套装 499/1244991-96（6 行）。
- ItemID 末位 == Star **仅对 1245 展示族成立**；对实例 TypeId（1240 族）**不成立**（末位=部位）。

## 2. Star 到底存在哪（A 级）

| 表 | 星级维度 | 证据 |
|---|---|---|
| EquibBase | **无星级字段**（EquibId/Part/Suit/属性池+权重） | 字段清单 |
| EquibStage | `Stage` 1-6（=星级） | CheckSubAttruib 用 `equip.Star` 作键（A） |
| EquibAttribBD | `EquibQuality` 1-6（=星级）；GM 直接以星值为键取行 | GMMainPage.GetEquip 反汇编（A） |
| Item | 无星级字段（IMQualityLevel≠星级：九头蛇各部位 1/3/5/6/7/7） | 全量分布 |

正式映射：**Star（1-6）是独立维度 → EquibStage[Star]（词条数上下限）与
EquibAttribBD[Star]（初始词条数+属性池）**。TypeId→EquibBase（部位/套装/主副属性候选池）。

## 3. HeroEquip.Star 的客户端消费（A 级）

- `CheckSubAttruib(HeroEquip)`（0x1C30CFC）：`EquibExp[level+1].IsEvent==1`（+3/6/9/12/15）
  时取 `equip.Star` → `EquibStage[Star].MinorListMax`，与 `GetAttrNum(equip)` 比较——
  **客户端直接信任 wire 上的 Star**，且用它索引静态表。
- `GetAttrNum(HeroEquip)`（0x1C30E28）：**副词条数 = Av2..Av6 中非零的个数**
  （At1/Av1 是主属性槽，不计数）。
- **无任何 `HeroEquip.Star = static(TypeId)` 赋值**；客户端无本地实例构造
  （GM 工具发 `C2L_Cheat{opt=15, values=[equipId, attrbdId]}` 让服务器生成——
  **equipId 与星级/属性档是两个独立输入**）。

## 4. 最终模型（对应任务问题 1-6）

**MODEL C 精确化（2026-09-25 星级链闭环后）**：
- 实例 TypeId（1240\|SS\|P）**不确定** Star —— 同 (套装,部位) 只有一个 TypeId，星级不在其中。
- 1245\|SS\|S **确定** (套装,星级) 但**不确定部位**，且无 EquibBase 行 → 不能作为实例 TypeId。
- **HeroEquip.Star 是掉落/发放时刻的独立属性**：战斗内客户端 `IdentifyItem`（DropBase
  6/5/4 档位掷骰）掷出 quality∈{3..6}，`JudgeDropItem` 以 `SectionTable.DroopLimit3=[min,max]`
  带收敛后，quality 就是 Star，经 outsideItems 携带给服务器（**A 级，原 B 级推导已闭环**）。
 详见 [equipment_star_quality_semantics.md](equipment_star_quality_semantics.md)。
- **Server 无需重掷 Star**（Star=quality；仅"无星级载体的发放场景"需 Revival 自定规则），
  但**不能**从 TypeId 派生；官方 GM 工具把 equipId 与星级/属性档（attrbdId）作为两个独立输入。
- "6★兽主掉率"属于**掉落层**（IdentifyItem 公式 + DroopLimit3 带），与实例工厂无关（PART E）；
  公式与静态参数已恢复（judge_drop_item_cfg.md）。
