---
Document-Type: Historical Report
Date: 2026-09-24
Status: CURRENT_AT_TIME
Superseded-By:
  - docs/knowledge/rewards/ (domain docs)
Note: moved from D:/demo/x2/docs/ into the repository during knowledge reorg
---

# 深层掉落数据考古报告（X2 2.4 客户端静态）

2026-09-24。本轮为纯静态数据考古：未改 APK/服务器/存档，未运行游戏。
方法：APK 全量 zip 清单 → ResourceManager 注册表全量 dump → 265 张注册表全部从 APK 原字节
解码（canonical RSA+XOR+protobuf 解析器）→ 249 张含 schema 表约 25 万条记录建立全字段
数值索引 → DropValueID/DropClass/CurrencyType 全量交叉扫描 → dump.cs + libil2cpp.so
ARM64 定点反汇编与全 .text BL/B 字节级 xref。

## 13 个问题的回答

### 1. APK 是否存在尚未提取的数据资产？ — 是（本轮已全部提取并归档）

ResourceManager 注册 **265 个唯一 `table/*` 资产**（另有 table_158/392/410 三个备用命名空间
共 189 个条目）。此前各阶段只提取过 56 张。**209 张从未提取的表本轮全部解码成功**
（`analysis/drop_archaeology/table_registry_extract.json`，记录级零错误）。
非表资产：2,638 个 Unity Data TextAsset（861 BSON 行为树、769 protobuf-like、905 binary、
68 text、7 JSON、16 XML、12 JSON-like）与 1,526 个 bundle（phase2 已扫，本轮未重复）。
异常表已定性：`device`=1 条设备白名单、`globalparamstring`=512 个参数名、
`gmadvanceaccount`=31 条 GM 命令模板、`eventtable`=43 条场景事件显示配置
（随机商店/火焰祭坛，field7 引用 NpcEvent/Quest 域）——均与掉落无关（D 级死路）。

### 2. canonical extractor 是否遗漏 Table？ — 是，遗漏 209 张

重点掉落相关遗漏（本轮新提取）：**ExtraDroop(26)**、CurrencyType(46)、CurrencyDisplay(53)、
ItemSource(234)、NpcEvent(408)、MonsterEventTable(2,630)、MonsterEventGroup(1,948)、
MonsterWave(41)、MonsterLevelBonus(1,000)、Quest(1,098)、DynamicGradeSuppression(90)、
RaceReward(100)、WeeklyDungeon(5)、ActivityDungeon、EndlessDungeonTask、ChallengeTask、
WorldBossEvent/Explore/Info、Tower×6、Fishing、Snatch、Escort 等。
12 张表无 Example 类（herodamagefactor、itemgetandconsume、vip 等），3 张解析失败已定性。

### 3. DropValueID 是否在其他文件出现？ — 否（A 级负面证据）

341 个 DropValueID（10600000–10660999）在 249 张解码表约 25 万条记录的全字段数值索引中
**零命中**（SectionTable 自身 3,043 处除外）。二进制扫描（global-metadata.dat、libil2cpp.so、
globalgamemanagers 的 u32-LE 与 varint）数百个命中经核对全部为 4 字节/变长编码巧合噪声，
无聚类、无伴随 ID 群，不构成数据结构。见 `dropvalue_hits.csv`、`binary_id_hits.json`。

### 4. DropValueID 是否能映射 DropProp？ — 不能（静态）

DropValueID ∩ DropProp.DropClass = 0；∩Item = 0；∩Unit = 0；∩Gift = 0；∩DropBase = 0。
不存在名为 DropValue 的表。ExtraDroop 是按 SectionGroup 绑定的掉落加成配置，
不携带 DropValueID。映射若存在，只能在服务器运行时。

### 5. DropProp 能否递归到最终 Item/Currency？ — 能，闭包 COMPLETE（A 级）

332 行 DropProp：子节点 258 个 ITEM + 112 个嵌套 DROP_GROUP + 83 个哨兵 0
（ItemList=[0]，"无物品"），**无任何其他未归属取值**。
147 个被外部引用的根节点递归展开后，叶节点 = 133 ITEM + 92 哨兵 0。
例：1309024→1302601→…→具体 Item。见 `drop_graph.json` 与 `docs/drop_graph_audit.md`。
注意：DropProp 抽取发生在客户端战斗运行时（GetDropItemByGroup 调用随机函数），
Prob/Picks/NoDrop 是抽取参数，不是服务端权威概率的证明。

### 6. Section → Scene → Unit → DC → DropProp 是否闭环？ — 闭环（A 级）

UnitBase.DC：494/1,912 个单位携带、62 个不同值、**100% ∈ DropClass 域**。
载体分布 E_Normal 230 / E_Elite 126 / E_BOSS 97 / E_DestructibleObj 32 / 其他 9——
是全游戏通用机制，不限于金币本。金币本罐子 7025–7027→1309024、7030–7032→1309029、
精英哥布林 4020→1309026 与此前记录一致。Scene/Room→Unit 的房间级映射在 BSON 行为树内
（861 个），本轮未展开房间粒度。

### 7. outsideItems 来源是什么？ — 已解决（A 级）

`FightModule.Send`（0x1441914，由 SendBattleResult 0x144185C 调用）→
`SetCheckout_BattleItem`（0x1442894）遍历 `LogicBattle.FightItemBag.ItemList`，
逐项 `ItemManager.GetItem(id)` 过滤后构造 `CommandX2.ItemDataP{ID,Num,Quality}` →
`C2L_CheckoutMainMission.outsideItems`（字段 3）→ 内嵌于 `C2L_CheckoutMainMissionSign(887)`
（`checkout` 字段 + battleFileBytes + battleFileString + sendTag）经
`MarsNetManager.SendBattle` 发送。**150 从不发裸包**：887 是唯一出口。
辅助方法 `FightItemBag.GetPersistentItemsList`（0x1E51A54）同语义
（过滤器 `Item.ItemUseScence==E_Outside(1)`），反汇编确认其构造 ItemDataP，
但无直接 BL 调用者（2.4 实际走 SetCheckout_BattleItem）。

### 8. FightDropInfo itemNum 来源是什么？ — 323 在 2.4 客户端无发送点（A 级负面）

`C2L_FightDropInfo(323)` 全 dump.cs 仅类定义与枚举号，**无任何 Send/SendBattle 泛型实例化**。
与实机两场金币本未出现 323 的观察吻合。此前"逐次拾取上报"假设应标 D 级死路。
真实上报通道是：887（outsideItems + killMonster + npcEventOnNumber）与
**264 C2L_FightDropData**：`FightModule..ctor` 预构造 `c2l_FightDropDataPacket`，
`RefreshDropLimit`（0x1447C64）发送（FightModule 四个 SendBattle 调用点按排除法闭合：
Send→887、SendStatsInfo→316（C2L_FightKillInfo ctor 0x1446620）、
SaveActivityProgress→ActivityMissionRecordSave、RefreshDropLimit→264）。
其 `dropItem: List<ProfileDropItem{itemId,quality,itemNum}>` 来自战斗包
（FightItemBag.GetCurrentItems 语义，反汇编确认返回 ProfileDropItem 列表；直接填充方法
未被 BL xref 命中，为 B 级残留细节）。响应 266 的 dropValues 经 `OnFightDropData`
（0x1447E1C）→ `UpdateDropValue` 帧命令 → `LogicBattle.OnInput` 注入战斗。

### 9. 901/903/1237901 是否存在转换链？ — 静态映射存在（A 级），转换时机在服务器

新提取的 **CurrencyType 表（46 行）**：`TpyeId 900→Item 1237900(因果)`、
`901(E_Gold)→1237901(金币)`、`902(E_Money)→1237902(光辉)`、`903(E_Silver)→1237903`。
Item 表侧：1237901 `E_Currency, EffData=[901]`；1237903 `E_MazeCurrency, EffData=[903]`
（**903 是迷宫/场内银币，不是账号金币**——此前判断再次确认）。
代码侧：`FightItemBag.AddGold(num, itemID=903)`（0x1E526CC）只写 mMoney[903] 并
Publish GetMoneyInGame，**内部无转换**；`AddItem`（0x1E46DAC）内含 901/903/907 分流常量
（0x385/0x387/0x38B），货币进入战斗包货币桶，持久化时按 CurrencyType.ItemID 落账。
`AddGold` 的 10 个调用点：塔攻防×3、Unit.CheckHPSubRes×2、Unit.UseSkill、
RecoverBattleData、TowerDefenseSpawner、TowerDefenseModuleNeo、TriggerActions.SilverOpera。

### 10. 是否发现真正意义上的"官方掉落表"？ — 发现三处官方掉落相关静态数据，无概率主表

1. **ExtraDroop（26 行，新）**：DroopType ∈ {E_DroopValue, E_DroopUP, E_GoldDroopUP}；
   例 ID 100002 绑定金币本 2130101–2130105、ExtraParam1=[1237901]、NumLimit=10、
   RefreshCycle=1、ResourceNum=10、DroopUPParam=[100]——官方"资源本额外掉落/掉落加成+
   每日限次"配置，含物品 ID 与数量上限。
2. **Item.DropLimit/DropLimitParam（417 个物品）**：每物品掉落上限，由
   DropItemManager.CheckItemLimit + mItemDayNumCache 消费。
3. **DropProp 全图闭包到 Item（已知表，本轮补全闭包与全部引用者）**。
没有发现按关卡–概率–数量的"主掉落表"；DropValueID 映射确认为服务器侧。

### 11. 哪些数据可以确认客户端持有？ — 见 `table_registry_extract.json` 全 265 表

掉落相关：DropProp(332，含 Pick/NoDrop/Prob/嵌套)、DropBase(6 品质阈值)、ExtraDroop(26)、
Item.DropLimit(417)、CurrencyType(46)、UnitBase.DC(494 单位)、NpcEvent(408，含 E_DropItem 类)、
MonsterEventTable/Group(2,630/1,948)、MonsterWave(41)、ItemSource(234 物品来源指引)。
战斗运行时结构：FightItemBag/ProfileDropItem/ProfileCurrency/ProfileNpc/FightDataProfile。
协议：887 内嵌 150 全字段、264/266、447 存档。

### 12. 哪些数据仍高度可能属于服务器端？

DropValueID→掉落内容展开、权威概率 roll、金币本罐子/金币怪的动态金币量、
商店商品内容/库存、任务实例与领奖、装备实例词条生成、活动时效状态。
（"高度可能"基于客户端零证据 + 对应请求/响应结构存在，非官方源码证明。）

### 13. 下一步最值得做的唯一动态验证

**在 Revival 服务器向 `L2C_FightData` 的 FightDataProfile 下发一次非空 dropValues，
实机观察客户端战斗内是否出现对应掉落物，并在结算/RefreshDropLimit 时抓
264 C2L_FightDropData 的 ProfileDropItem 内容。** 这一步同时验证：
JudgeDropItem 的 Contains 门控语义、264 的组装/发送时机、以及 dropValues 是否为
DropValueID 本体或其展开值——是整条掉落链中唯一无法静态确定语义的输入。

## 证据分级汇总

| 级别 | 结论 |
|---|---|
| A | Q1/2（209 表遗漏并补齐）、Q3（DropValueID 无静态出现）、Q4（无静态映射）、Q5（DropProp 闭包 COMPLETE）、Q6（DC→DropClass 100%）、Q7（outsideItems 链）、Q8 前半（323 无发送点）、Q9（CurrencyType 映射） |
| B | dropValues 运行时语义（门控+值 roll，反汇编链完整未逐指令复原）、264 包字段填充细节（tempDropItem 填充方法未 BL 命中）、RefreshDropLimit→264 的类型归属（排除法） |
| C | 二进制候选命中（全部判噪声）、eventtable field7 的 NpcEvent/Quest 关联方向 |
| D | device/globalparamstring/gmadvanceaccount/eventtable 为掉落来源、"323=逐次拾取上报"假设、任何从 1302601 之类数值猜测 Item 归属的旧疑虑 |

## 交付物

- `analysis/drop_archaeology/all_data_assets.json` — APK 12,644 条目 + 133,478 Unity 对象 + 2,637 表容器文件清单
- `analysis/drop_archaeology/table_registry_extract.json` — 265 张注册表逐张解析记录（209 张新增）
- `analysis/drop_archaeology/full_tables/` — 249 张表完整解码记录（含全部新表）
- `analysis/drop_archaeology/dropvalue_hits.csv` — 341 个 DropValueID 的表/二进制命中
- `analysis/drop_archaeology/dropvalue_cross_scan.json` — 全表数值交叉扫描
- `analysis/drop_archaeology/binary_id_hits.json` — 二进制候选命中（含上下文字节）
- `analysis/drop_archaeology/string_hits.json` — 25 个术语 × dump.cs/字符串字面量/表值
- `analysis/drop_archaeology/drop_graph.json` — 332 节点全图 + 147 根展开
- `analysis/drop_archaeology/daily_drop_sources.csv` — 25 个 DailyDungeon × 176 Section 静态事实
- `analysis/drop_archaeology/id_namespaces.md` / `id_namespace_report.json` — 命名空间审计
- `docs/drop_graph_audit.md`、`docs/dropvalue_code_path.md`
- 本报告
