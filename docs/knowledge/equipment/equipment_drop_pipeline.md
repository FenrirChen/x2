---
Document-Type: Current Knowledge
Domain: Equipment / Drop
Status: AUTHORITATIVE
Updated: 2026-09-26
Evidence-IDs: CLIENT_IL2CPP_2_4, CLIENT_FULL_TABLES_2_4, LIVE_RUNTIME_VERIFIED
---

# 兽主掉落管线（实机已通）与 dropValues 预算机制

机器可读：`analysis/equipment/equipment_initial_value_semantics.json`、
`analysis/equipment/judge_drop_item_cfg.md`、`analysis/equipment/droop_limit_xrefs.json`。
实现：`src/x2server/player/equipment_factory.py`、`src/x2server/data/equipment_tables.json`。
实机验证：2026-09-26 兽主本（2133101）两场，54/49 件实例生成+落库+下发，用户确认掉落正常。

## 1. 完整掉落管线（全部 A 级反汇编 + 实机验证）

```
[客户端战斗内]
Unit.DC → DropProp(ADC 1301101..) → GetDropItemByGroup：
  Section.DroopLimit 白名单里选 1240xxx（ADC 权重 10000/ItemValue）
  → AddItems 建 ItemStruct{quality=-1, needIdentify=(ItemQuality==E_Unsure(7))}
  → IdentifyItem(item, level, dropProp)：DropBase 档位掷星（见 §4）
  → JudgeDropItem(item, isEqt)：
      ① DroopLimit3=[min,max] 星级带（超上收敛/低于下拒绝）
      ② DroopLimit.Contains(id)（E_Outside 件）
      ③ dropValues[AddADCGroup] 组价值预算（见 §2）——预算空=全灭
  → DropItem(quality) → 拾取 PickItem → FightItemBag.AddItem(id, quality, …)
[结算]
SetCheckout_BattleItem → outsideItems{id,num,quality,eNum=0} → 887
[服务器 Revival]
RuntimeDropResolver 分流 E_Equip → EquipmentInstanceFactory
  （Star=quality；条数档 65/35；ValueSec 逐段链）→ equipment_instances 落库
  → 152.rewardEquip + L2C_EquipUpdate(536) 推送 → 客户端背包可见
```

## 2. dropValues 预算（本轮深挖结论）

**本质：服务器权威的"本场战斗每组(AddADCGroup)可掉落总价值"配额。**

- **载体**：`BattleInfo.dropValues`（+0xC0，List<int>，按 AddADCGroup 索引）。
- **灌入（次通道）**：130 入场响应 `FightData.dropData.dropValues` →
  `BattleInfo.SetSceneInfo(0x19A25B4)` 清空后 AddRange。
- **更新（主通道）**：客户端战斗中上报 **264 C2L_FightDropData**（类 13430，
  包含 missionId/chapterId/layer 等字段；13422 是内嵌 FightDropData，不能混淆）
  → 服务器应答 **266 L2C_FightDropData{result:10, data=FightDropData{dropValues,missionId}}** →
  `FightModule.OnFightDropData(0x1447E1C)` 校验 result==10 → 反序列化 data →
  `LogicX2Command.UpdateDropValue`（字段 0x18=dropValues）→ `LogicBattle.OnInput(0x1448224)`
  入帧同步队列 → **`LogicBattle.OnUpdateDropValue(0x18FA700)`：
  `BattleInfo.dropValues = cmd.dropValues` 整表直接替换（str x19,[x20,#0xC0]）**。
- **消费**：`JudgeDropItem`：(a) 结构门 `budget.Count > item.addADCGroup`；
  (b) 价值门 累计 `DropItemManager.DropValueList`（偏移 0x48，按组）+ delta ≤ budget[组]；
  delta：装备 = `EquibStage[Star].EquibValue × Item.ItemValue / 1000 × num`（星级加权！），
  其他物品 = `Item.ItemValue × num`。累计器由 `InitDropValueList(budget.Count)` 清零建立。
- **权威性**：整表替换意味着**服务器是预算的唯一权威**——客户端每场战斗上报累计消耗，
  服务器回发新配额（可动态收紧/放宽）；客户端只执行。这也是官方的掉落量反作弊上限。
- **发送时机（实机）**：每场战斗至少一次（2133101 两场各一次，约进场后 15s，
  处于 `BattleX2.OnEnterNextLater → FightModule.RefreshDropLimit` 家族触发链；
  精确触发条件未完全钉死）。264→266 是握手循环：OnFightDropData 同时构造下一个
  上报包（FightDropData.ctor 全二进制仅此一个调用点）。
- **恢复**：`SetCurItemValueTotal`（唯一调用方 RecoverBattleData）从恢复的背包重放累计，
  使续战账目与预算一致。

## 3. Revival 实现（运行中）

| 环节 | 实现 | 性质 |
|---|---|---|
| 264 应答 dropValues | **分级预算：LOW 1000 / MID 3000 / HIGH 5000**（官方 DifficultyLevel 1-3/4-6/7+；无难度默认 MID；27 组同值；decisions/compatibility/equip_dropvalues_budget.md） | 分级边界 **REVIVAL_COMPAT/USER_DECISION**（官方数值 SERVER_DATA_LOST） |
| 130 入场 dropData | 同一分级预算表（次通道，SetSceneInfo 消费） | REVIVAL_COMPAT |
| Star | = outsideItems.quality，不重掷 | **官方语义（A）** |
| 条数档 | 1-3★ 固定；4-6★ base 65% / max 35% | base/max 值=官方（AttribBD 行派生）；比例 **REVIVAL_COMPAT/USER_DECISION** |
| 数值 | EquibAttrib[Star,src0/src2,type] ValueSec 逐段升级链 | 阶梯=官方；链 **REVIVAL_COMPAT/USER_DECISION** |
| 类型 | EquibBase 池加权（主属性 40 部件多候选；副词条无放回） | 官方 |
| E_ReportCurrency 代理折算 | EffData=[桶,单件值] → 账户货币（68/68 表派生映射），原物不入包/不入 rewardItem；折算金替代旧金币本手打 MopReward 兼容 | 折算存在=强B；公式 **REVIVAL_COMPAT/USER_DECISION**（equip_report_currency_conversion.md） |
| 幂等 | receipt 缓存 + marker=drop:{run_uuid}:{ordinal} INSERT OR IGNORE 复用 | Revival 实现 |
| 推送 | 152.rewardEquip + L2C_EquipUpdate(536) 双通道 | 536=官方"后续变化"通道；**客户端实际接纳哪个通道未隔离验证** |

**数据文件**：`equipment_tables.json`（126 EquibBase / 384 EquibAttrib 含 AttribSRC /
66 EquibAttribBD / 6 EquibStage + 条数档派生，由 tools/dev/export_equipment_tables.py 生成，
含官方性声明：条数比例与链式 roll 不在数据文件内）。

## 3.1 预算的值从哪来（2026-09-26 深挖）

- **客户端：无任何本地来源**。BattleInfo.dropValues 的全部写入者只有三个：ctor 空表、
  SetSceneInfo 从 wire 拷贝、OnUpdateDropValue 整表替换——均来自服务器下发。
  实证：应答为空 ⇒ 零掉落（旧服务端行为）。
- **官方服务器：按 DropValueID 键取配置**。结构已破解（全量 341 组验证）：
  **`DropValueID = 10600000 + SectionID % 100000`**（310/341 直接命中；
  85 组为有意共享——活动/印郇变体复用本体预算（如 216030x → 1061070x）、
  个别错位（2110104 → 10610105）为手工授权痕迹）。
  即 DropValueID 不是独立 ID 族，而是"本关卡在服务器侧的掉落配置键"，
  很可能就是 264/266 预算（及掉落计划）的配置来源（B 级推断）。
- **官方数值形态推断**：每组预算 ≈ 该关卡设计的掉落总价值上限
  （兽主本组 5 ≈ 设计件数 × 每件星级加权价值）。精确数值在官方服务器数据中，已失传。
- **Revival 当前取值**：难度 1–3 为每组 1000、4–6 为 3000、7+ 为 5000；
  无难度默认 3000，共 27 组——REVIVAL_COMPATIBILITY/USER_DECISION。
  旧 27 组 × 1,000,000 已于 2026-09-26 废弃。
  若未来要做"官方量级"预算，需按关卡配置预算表（如 组5 = 设计件数 × 560）。

## 4. 残留未知 / 注意事项

### 2026-09-30 第一章月相核对

原 APK SectionTable 的 2110851..2110860 星级范围依次为
`[1,3], [1,3], [2,4], [2,4], [2,5], [3,5], [3,6], [3,6], [3,6], [3,6]`。
预算分别为 `1000×3, 3000×3, 5000×4`（每组值）。预算限制累计价值，
不直接抽取星级；高月相允许 6★，不保证每件都是 6★。
服务端将客户端 outsideItems.quality 原样作为实例 star 落库并下发，不重抽星级。
十个月相的入场及 264 查询预算一致性回归通过。
修复掉落查询在缺少、过期或关卡不匹配的战斗记录下调用未定义函数的问题，
现在正常返回 result=13，并记录拒绝原因及正常查询的难度、实际预算。

1. **低星来源矛盾（新）**：实机 [1,3] 带本掉出 1★×73 / 2★×9 / 3★×21——
   `IdentifyItem` 只能产出 3-6★（DropBase 6/5/4、兜底 3），1-2★ 必然来自另一条
   未追明的低带路径（疑似低带段改用 DropBase 1/2/3 或带内直接 roll）。
   → equipment_star_quality_semantics.md 的"1-2★ 不经战斗掉落"结论已被推翻（见 SUPERSEDED）。
2. 官方每组预算数值未知；DropValueID(106xxxxx) 是否即官方预算的配置来源未证（B 级猜想）。
3. 264 发送的精确触发条件未钉死（家族=OnEnterNextLater/RefreshDropLimit）。
4. 客户端对 152.rewardEquip 的接纳 vs 536 推送未隔离验证（两通道都在用）。
5. 月钻(1101060) 客户端贴图显示为光能——纯客户端资源映射，无功能影响。
