# 客户端经济静态数据审计

2026-09-23。对象：官方简中 2.4 客户端。仅复用 Phase 2–5 的索引、`dump.cs`、保护层解析器和已提取表；对索引中已知的少数表按精确资源路径定点读取。未启动游戏或模拟器，未改 APK、存档、服务器业务。

## 1. 总结

| 系统 | 结果 | 边界 |
|---|---|---|
| 关卡固定首通/普通/扫荡奖励 | **完整静态引用**，`CONFIRMED_CLIENT_STATIC` | `SectionTable → Gift → Item` 可展开；发放与结算仍由服务器负责 |
| 关卡随机/怪物掉落 | **部分**，`CLIENT_PARTIAL` | `DropValueID → DropProp/Item` 未找到映射 |
| 商店 | **部分**，`CLIENT_PARTIAL` | 商店、分组、商品 ID、价格、货币枚举与刷新字段可读；大多数商品没有静态物品 ID/数量映射 |
| 每日任务 | **完整静态定义**，`CONFIRMED_CLIENT_STATIC` | 26 条 `E_Day`；实例进度、重置执行由服务器维护 |
| 每周任务 | **完整静态定义**，`CONFIRMED_CLIENT_STATIC` | 14 条 `E_Week`；实例进度、重置执行由服务器维护 |
| Reward → Item | **固定奖励已解析；整体部分** | 引用的固定 Gift 多数可落到 Item；随机战斗掉落仍断链，部分 Gift 奖种有非 Item 值 |

这里的“完整静态定义”表示客户端有任务类型、门槛、条件目标与奖励，并不表示服务器行为、日历时区或历史实例已恢复。`TaskControl.DailyRefresh=5`、`WeeklyRefresh=5` 是原始值，未证明它们的时间单位或时区。

## 2. 关卡掉落与固定奖励

| 表 | 原始 TextAsset 路径 | 记录数 | 关键字段 |
|---|---|---:|---|
| SectionTable | `phase3_output/raw_tables/SectionTable__cca5f3cc8525b59459bdebf586c887fb.bin` | 3,203 | `FirVReward`, `VReward`, `MopReward`, `ChestReward`, `ExpertChestReward`, `DropValueID` |
| Gift | `assets/bin/Data/97f907f95af754641b60175964616b99` | 10,930 | `GiftGroup`, `AwardType`, `GiftValue`, `Num`, `Probability` |
| DropProp | `assets/bin/Data/57b23c8d19adf034aabf5bbe59cb8d71` | 332 | `DropClass`, `Group`, `Level`, `Picks`, `ItemList`, `Prob` |
| DropBase | `phase3_output/raw_tables/DropBase__3c651c6fa1ab43a4f9a4bcf8074e62fb.bin` | 6 | 品质阈值，**不是**掉落清单 |
| Item | `phase3_output/raw_tables/Item__e49ddfae661db9147b8823552f01df41.bin` | 3,026 | `ItemID`, `NameID`, `ItemType` |

3,203 个 Section 中，619 个有首通奖励、2,439 个有普通奖励、41 个有扫荡奖励。`FirVReward` 的 941 次引用、`VReward` 的 4,521 次引用、`MopReward` 的 149 次引用全部命中 `Gift.GiftGroup`。这三类引用展开出 12,804 个 `GiftValue`，全部命中 `Item.ItemID`。这是**固定奖励**的静态闭环，未证明实际结算一定按表原样发放。

| Section | 固定奖励引用链 | 随机掉落入口 |
|---|---|---|
| `2110001` 疯狂之船 | 首通 `730001 → Gift → 1237902 光辉 ×30`；普通 `730000 → 1237908 解神者经验 ×12、1237907 神格经验 ×120、1237901 金币 ×180` | `DropValueID=10610001` → **UNRESOLVED** |
| `2110103` 雅娜的幻影 | 首通 `730001` 光辉 ×30、`710046` 奇美拉·一 ×1、`730113` 浮士德碎片 ×3；普通 `730000` 同上 | `10610103` → **UNRESOLVED** |
| `2130101` 咻咻的宝藏秘境（资源本） | 首通 `730001` 光辉 ×30；普通 `730071` 解神者经验 ×6、神格经验 ×60；扫荡另引用 `795201` 金币 ×2,078 | `10630101` → **UNRESOLVED** |

当前实际可操作首关 `2110801` 也可查到：首通 `730001` 光辉 ×30 加 `730811` 贝黑莫斯碎片 ×5；普通 `730000` 与上例相同；`DropValueID=10610801` 未解析。`2160561` 特殊关卡的首通 `776355/776357` 可展开为电流装置、干扰装置、病毒装置各 1，以及数据记录 ×2。

`DropValueID` 出现在 3,043 个 Section，只有 341 个不同值；与 332 条 `DropProp.DropClass` **零交集**，与 6 条 `DropBase.ID` 也零交集，与 `Gift.GiftGroup` 零命中。`DropProp` 本身有掉落组和概率字段，但没有证据把某个 Section 的 `DropValueID` 指向其中的行。引用链断在 `Section.DropValueID → 掉落组/DropClass`；不能从当前客户端资料独立恢复关卡随机掉落或怪物掉落概率。战斗消息中运行时的 `FightDataProfile.DropValues`、`FightDropData` 和结算 `RewardData` 只能证明下游数据形状，不能补出这一步映射。

## 3. 商店

| 表 | 原始 TextAsset 路径 | 记录数 | 关键字段 |
|---|---|---:|---|
| ShopConfig | `phase3_output/raw_tables/ShopConfig__0a5189b8d93663c4aa152623435068da.bin` | 25 | `ShopID`, `GoodsGroupId`, `SeasonGoodsGroupId`, `ShopResourceType`, `ShopRefreshTime`, `UnlockType`, `RefreshPrice` |
| ShopGoodsGroup | `phase3_output/raw_tables/ShopGoodsGroup__aac0936a434fe66428248f5b70f452fc.bin` | 1,567 | `GoodsID`, `GroupID`, `ShopResourceType`, `ItemPrice`, `Limited`, `Condition`, `RefreshInterval` |
| Item | 上表 | 3,026 | `QuickBuyID` 提供 17 条反向线索 |

25 个商店包含随机、友情、勋章、月钻、票据、社团、活动与测试店。`ShopConfig.GoodsGroupId` 的 610 次引用全部命中 `ShopGoodsGroup.GroupID`；连同季节分组共 634 次引用。`ShopGoodsGroup` 的价格与货币是业务字段，不是 UI 文案或图片。例：商店 `801` 的 `ShopRefreshTime=[5,18]`、可手动刷新、刷新货币枚举 `902/E_Diamond`、价格阶梯 `[50,50,100,200,400,600]`。时间值的单位与时区未证实。`Limited=E_Day/E_Week` 表示周期类别，**没有**限购次数数值。

| Shop → Group → Goods | 商品线索 | 价格 | 完整性 |
|---|---|---:|---|
| `801 → 957 → 2001501` | `Item.QuickBuyID` 反向命中 `1237913 光能` | `902/E_Diamond ×60` | 数量 **UNRESOLVED** |
| `801 → 971 → 2006901` | 反向命中 `1237925 纯晶石` | `902/E_Diamond ×180` | 数量 **UNRESOLVED** |
| `809 → 326 → 1933001` | 反向命中 `1281001 石雕面具` | `902/E_Diamond ×1` | 数量 **UNRESOLVED** |
| `809 → 327 → 1933002` | 反向命中 `1281002 星象盘` | `902/E_Diamond ×1` | 数量 **UNRESOLVED** |
| `809 → 328 → 1933003` | 反向命中 `1281003 石刻飞船` | `902/E_Diamond ×1` | 数量 **UNRESOLVED** |

这 17 个 `Item.QuickBuyID → ShopGoodsGroup.GoodsID` 是反向线索，并非完整商品定义。`ShopGoodsGroup` 不含卖出物品 ID 或数量字段；例如 `801 → 1 → 1900101` 只能确认价格 `E_Diamond ×20`、`Limited=E_Day`，卖出什么、多少均 **UNRESOLVED**。货币 `902` 是 `ShopResourceType` 枚举值，不能直接当作 `ItemID=902`。服务器的 `L2C_Goods` 和购买响应是动态商品内容的潜在来源，当前静态证据不足以填充全店。

## 4. 每日与每周任务

| 表 | 原始 TextAsset 路径 | 记录数 | 关键字段 |
|---|---|---:|---|
| DailyTask | `assets/bin/Data/e6d80a2256e2cd4498e5f4df42a60a5b` | 40 | `RefreshCycle`, `TaskConditionID`, `AcceptLevel`, `LastTask`, `GiftGroup`, `GiftGroupSeason`, `BattlepassExp` |
| TaskCondition | `phase3_output/raw_tables/TaskCondition__3ee9401d542d7bf43b6b6786500040ed.bin` | 1,728 | `CompleteType`, `CompleteValue1/2`, `CompleteNum` |
| TaskControl | `assets/bin/Data/ed2d8be6f9f17924c9f2532627d10336` | 1 | 每日/每周刷新原始值、活跃度阈值及奖励 GiftGroup |

`DailyTask.RefreshCycle` 明确分为 **26 条 `E_Day`、14 条 `E_Week`**。40/40 条任务的条件 ID 命中 `TaskCondition`，40/40 个主要奖励命中 `Gift`，这些奖励的物品值均命中 `Item`。任务描述通过 `Language` 的 `Chinese` 字段解析。由此客户端静态定义足以生成任务的候选清单和目标；哪些任务对哪个账号激活、计数、领奖状态及重置执行仍属服务器实例状态。

| 周期/任务 | 条件与目标 | 奖励（Gift → Item） |
|---|---|---|
| 日 `630001` 勤奋的一天 | `600900/E_ConsumePowerToday`，累计消耗因果 120，1 级 | `760201`：日活跃度 20、金币 1,200、神格经验 500 |
| 日 `630003` 兽主强化 | `601200/E_UpgradeEquipment`，强化 1 次，1 级 | `760203`：日活跃度 5、金币 800、兽魂 100 |
| 日 `630006` 奇迹祈神 | `604801/E_BaseBless`，祈神 1 次，25 级 | `760206`：日活跃度 5、金币 800、祈神符 1 |
| 周 `630101` 我很努力 | `610201/E_KillMonsterType`，本周击杀怪物 1,000，1 级 | `760301`：周活跃度 30、金币 2,000、神格经验 1,000 |
| 周 `630102` 精英的覆灭 | `610202/E_KillMonsterType`，本周击杀精英 100，1 级 | `760302`：周活跃度 30、金币 3,000、神格经验 1,000 |
| 周 `630103` 资源战 | `610301/E_CustomsPass`，指定资源战关卡通关 5 次，11 级 | `760303`：周活跃度 15、金币 2,000、神格经验 1,000 |

`TaskControl` 有每日活跃度阈值 `[20,40,60,80,100]` 对应 Gift `760001–760005`；每周阈值 `[30,60,90,120,150]` 对应 `760010–760014`，这些 Gift 可继续展开到 Item。另有独立的 `TaskEndlessWeek` 54 条，它的 `ResetType=E_ActivePeriod`，不能混作上述 `E_Week` 日常周任务。

## 5. Reward → Item 与其他经济表

`Gift` 是固定奖励的核心中介。其 10,930 条分为 `E_material` 10,033、`E_Random` 885、`E_Pick` 10、`E_BlindBox` 2。`GiftValue` 总计 28,220 个值，其中 28,016 命中 `Item.ItemID`；非 Item 值主要在随机类，不能把它们硬解释成物品。`Gift.Probability` 只有部分记录提供原始权重；此处不推断最终概率或抽取算法。`Item.NameID → Language.Chinese` 可提供名称，`Item.ItemType` 可提供类型。

其他直接相关表已确认存在：`DailyDungeon` 25 条将资源/特殊副本关联到 Section；`ChapterInfo` 13 条含章节 DP 点阈值与奖励 ID；`Achievement` 318 条含条件与 GiftGroup；`DrawRules`、`DrawParam` 各 48 条含抽卡奖项、消费和保底相关字段；`ActivityTask` 314 条、`ActivityBoxGoods` 693 条以及 `TaskChapter`、`TaskSeven`、`FavorabilityDailyTask` 等可作后续定点研究。本轮不把这些系统的业务规则宣称完整。

## 6. 服务端仍缺失什么

| 系统 | 客户端已足够 | Revival Server 仍需维护或重建 |
|---|---|---|
| 固定关卡奖励 | Section→Gift→Item/数量 | 通关有效性、首通判断、结算发放、背包/货币持久化、幂等 |
| 随机掉落 | Section `DropValueID`，独立 `DropProp` 结构 | **`DropValueID` 到掉落组/DropClass 的映射**及权威抽取、掉落状态 |
| 商店 | 商店/分组、价格货币枚举、部分刷新字段与少量反向物品线索 | 商品 ID→实际物品/数量、库存与限购次数、刷新执行、支付与购买记录 |
| 日/周任务 | 40 条候选任务、条件、目标、奖励、周期、门槛 | 账号任务实例、进度事件、激活条件、重置时点/时区、领奖与幂等 |
| 奖励通用 | 固定 Gift 绝大部分可映射 Item | 随机/Pick/BlindBox 选取语义与非 Item 值的具体发放处理 |

玩家当前任务实例、购买次数、掉落结果、已领奖状态不属于这些静态表。上述缺口是当前客户端证据下的边界，不等同于证明原官方实现一定只在服务器。

## 7. 对后端实现的事实结论

固定关卡奖励和日/周任务的**静态定义**已可从客户端恢复；服务器需要实现权威状态与发放。随机掉落仍不能依据客户端 `DropValueID` 独立生成真实掉落。商店可以恢复价格和分组，但多数商品的物品 ID 与数量未落地，不能据此实现完整购买规则。

机器可读摘要位于 `analysis/economy/drop_tables.json`、`shop_tables.json`、`task_tables.json`、`reward_links.json`；脚本 `build_audit.py` 可从现有提取结果与定点资源路径重建。未复制大体积原始资产。
