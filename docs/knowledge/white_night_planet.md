---
Document-Type: Current Knowledge
Domain: College/GrowthBase
Status: EVIDENCE-BOUNDED BLUEPRINT — not runtime-complete
Updated: 2026-09-27
Evidence: official 2.4 decoded tables; dump.cs/script.json/libil2cpp.so; analysis/white_night_planet/*
---

# 白夜行星

## Identity

显示名“白夜行星”在官方语言表 Key 1499039 的设施说明中出现；Key 2820171 明言玩家获得进入其**基地**的权限。客户端内部主模块是 `CollegeModule`，数据根名 `GrowthBase`，子模块为 `CollegeUpgradeModule`、`CollegeAlchemyModule`、`CollegeWonderModule`。入口 `FunctionOpen` 21902=`E_Base`（19 级）、21912=`E_Wonder`（25 级）。没有可信的“白夜行星 ActivityID”；`activity.json` 的 28001 与 College 键域不连。别名及易混淆文案见 [aliases.md](../../analysis/white_night_planet/aliases.md)。以上为 A 级客户端证据。

## Entry / Unlock

`CollegeEntry.OnOpen/OnShow` → `CollegeModule.SendQueryGrowthBase` (579/584)；`CollegeMainEntry.OnOpen` → `CollegeAlchemyModule.SendAlchemyMainData` (590/591) 与 `CollegeModule.SendUnlockExploreRuin` (622/623)。`MainHallFSM.UpdateLoadModule` 同时检查客户端与服务器功能关闭开关。`CollegeModule.IsCollegeEnable` 读玩家数据及双端功能开关。19/25 是静态开放等级，其他剧情门/服务器开关值需进一步取证。当前测试账号等级 60，故等级本身不是入口不能加载的充分解释。

## Static Tables

官方静态索引 [static_catalog.json](../../analysis/white_night_planet/static_catalog.json) 对每张表列行数、主键、关联 ID 和外键：`CollegeBuilding` 16 行（701–708 八座普通建筑、721–728 八座奇迹；728 无 `BuildingOpen` 字段）；`CollegeLevel` 555 行；`CollegeStarLevel` 95 行；`CollegeWonderSkill` 54 行；`CollegeExplore` 15 行（34001–34015）；`CollegeRecipe` 60 行；`CollegeQuest` 120 行；`CollegeCustomer` 42 行；`CollegeEquibReset` 5 行，以及引用到的 FunctionOpen/Gift/Item。关系图在 [state_machine.md](../../analysis/white_night_planet/state_machine.md)。

这些是展示、候选、等级效果、物料和奖励引用的客户端证据。**单有静态候选不表示客户端抽取随机结果，也不表示官方服务器收费公式已知。**建筑升级费用、刷新/退费与星能生成上限仍需服务器侧证据或显式兼容决策。

## Client Classes

主要方法、RVA、直接调用和模块字段见 [client_code_map.md](../../analysis/white_night_planet/client_code_map.md)。重点：`CollegeModule.InitData` `0x1AF78D4`、`SendQueryGrowthBase` `0x1AFB594`、`OnGetQueryGrowthBaseData` `0x1AF8850`、`CollegeEntry.OnOpen` `0x1BAFF2C`、`CollegeMainEntry.OnOpen` `0x1AF3EFC`。服务器入门数据不止 579，还依赖 590 与 622。

## Protocol

[protocol_matrix.csv](../../analysis/white_night_planet/protocol_matrix.csv) 共 **32 条基地相关请求链**：30 条 `REAL_SEND`（客户端协议目录存在 Send 实例且 College 子模块有具体发送方法），2 条公会协助 `INDIRECT`（请求对象在构造器缓存，发送路径尚须逐指令闭环）。主根：579/584、622/623；建筑：233/244、234/245、235/246、271/272；星能：238/249；派遣：242/253、239/250、236/247、624/625；训练：259/262、258/261、257/260；奇迹祈祷：369/373、366/370、368/372、367/371；炼金：590–605、824/825、826/827；洗炼：1055/1056、1057/1058；协助：879/880、881/882。

矩阵的“Response fields used”列目前列 **官方 L2C 类型声明字段**，已明确标注哪些尚未完成逐字段 native 读审计；不能把“字段存在”冒充“UI 确实读取”。对应处理函数 RVA 已定位。响应值（尤其 `code`、时间、rewardData）需下一轮按 ARM64 字段偏移校验后才可写严格服务端编码。

### Push / 后续依赖

客户端存在 `L2C_TrainingUpdate(562)` → `CollegeModule.OnReceiveTrainingUpdateMsg`、`L2C_UpLevelBuildingId(507)` → `OnReceiveUpLevelBuildingIdMsg`、`L2C_ExtraPower(695)` → `OnReceiveExtraPowerMsg`、`L2C_PrayEnd(514)` → `CollegeWonderModule.OnReceivePrayEndMsg`（A）。`BuildingUpdate(559)`、`ExploreUpdate(561)`、`QueryGrowthBaseAlchemy(617)` 也是与基地结构相符的 L2C 类型，但注册及主动触发关系尚未完全闭环（B/UNKNOWN）。领奖后的通用 `PlayerDataProto` / `ItemUpdate` 应作为服务器交付和 UI 同步的待验证依赖，不能凭空断言官方每次的推送顺序。

## State Machine

真实模型是建筑、探险派遣、训练、炼金、祈祷、洗炼的**并行队列和账户状态**。状态、转移、权威字段与客户端缓存分离见 [state_machine.md](../../analysis/white_night_planet/state_machine.md)。`L2C_Login.growthBase` 与 579/584 共享 `L2C_QueryGrowthBase` 结构；服务器必须重登可恢复，而 `CurWonderIndex`/最近配方只是客户端 UI 偏好。

## Battle Flow

没有发现 College 子模块发送 `FightData(126)` 或 `CheckoutMainMissionSign(887)` 的直接调用。15 个 `CollegeExplore.ID` 与全部 `SectionID` 无交集；派遣是带 `WaitTimes` 的服务器计时事务，`FinishExplore(239/250)` 交付奖励和遗迹经验。主线“白夜大厅”“白夜崩解”是同名故事关卡，不属于基地。也不应把独立的训练场战斗接到 `StartTrain(259)`。

## Reward Flow

派遣的 `CollegeExplore.Reward` 指 Gift 组 761001–761015，最终由 `L2C_FinishExplore.rewardData` 交付；`ruinId/exp` 是另一条进度。炼金生产/交易回包 603/599、一键收取 827、祈祷领奖 372 分别含 `rewardData`。`CollegeQuest.AwardGroup` 仅在 `AwardType=E_Gift` 时是顾客任务 Gift 引用；`E_Gold/E_Buff` 行另有数值语义。静态 Gift 决定候选内容，不决定服务器应采用的随机、倍率或是否一次性。派遣、生产、顾客订单与祈祷都需要独立的幂等领取账本。当前证据未显示基地积分、赛季排名、赛季宝箱或单独排行榜奖励；不得创造。

## Persistence

服务端需持久化：建筑/奇迹等级与星级、星能与金币仓库及结算时点、额外体力、遗迹解锁/经验、派遣/训练/建造/祈祷/炼金的槽位及结束时间、英雄占用、顾客订单、配方经验、洗炼日次数、奖励领取凭证。客户端 `CollegeModule.growthData` 是同步快照，不能当权威。`L2C_Login.growthBase`、579/584、590/591、相关 push 应同源。

## Reset / Season

客户端明示多个倒计时和 `washingCountDay`；具体日切时区、星能/仓库上限、取消退费、队列并发限制与帮助次数为 `SERVER_ONLY_UNKNOWN`，除非进一步 native 代码证明。没有基地专属季节/排名协议的正证据，不应套用活动赛季模板。`FunctionOpen` 级别和建筑 `BuildingOpen` 是固定客户端配置；服务器功能开关属于实时态。若未来选择常驻开放，应单独登记 `REVIVAL_COMPATIBILITY`，本轮未做决定。

## Server Dependencies / Coverage

[server_gap_matrix.csv](../../analysis/white_night_planet/server_gap_matrix.csv) 对 32 条逐项审计：**COMPLETE 0；PARTIAL 1（579/584）；STUB 1（622/623）；MISSING 30**。579 已读取独立 SQLite `college_state`，以官方 `CollegeBuilding` 初始等级/星级建立新账号状态；`Login.growthBase` 同源，状态可重登恢复。622 仍返回错误 13，590/591 炼金入口及其他基地请求尚无完整处理。Phase 0 的实际读取字段及未知项见 [phase0_response_audit.md](../../analysis/white_night_planet/phase0_response_audit.md)。基地入口仍为 PARTIAL。

## Official Unknowns

1. 建筑/奇迹官方消耗、星能产速与上限、取消/加速价格、队列并发和社交协助规则。
2. 派遣掉落的官方随机算法、顾客生成/偏好概率、洗炼随机属性与锁定的权威算法。
3. GrowthBase 下游 UI 字段最小集，559/561/617 的注册与发送触发，原服 push 顺序。
4. `BuildingOpen` 缺失的 728 及额外故事门如何在原服开放。
5. 原服日切、退款及错误码边界。不得把缺失信息写成官方规则。

## Revival Compatibility Needed

若官方服务器专属值无法恢复，须为星能产出、建筑资源消耗、派遣奖励权重、顾客/洗炼随机、取消退费和协助限制分别提出可审查的兼容参数；注明依据和经济影响后由项目决策层确定。本次未新增这些兼容值，也未重置活跃存档。

**兼容设计提案（尚未批准、未实施）：**[college_growthbase_compatibility_PROPOSAL.md](../decisions/compatibility/college_growthbase_compatibility_PROPOSAL.md)。官方 Item 表证实 1237831–1237835 是建筑加速卡（10 分钟至 8 小时）；“时之痕”五档的材料 Gift 对应 1237801–1237806 建筑/奇迹升级材料。提案据此使用现有材料与加速卡设计成本和计时，附参数表与模拟；正式 College 覆盖状态未改变。

## Implementation Plan

| 阶段 | 请求/响应及 push | 静态与持久化 | 测试 / DoD |
|---|---|---|---|
| 0. 证据封口 | 逐字段审计 584/591/623、559/561/562/617、所有领奖回包；实机抓至少一轮入口 | 确认 728、功能开关、赠礼随机与日切未知项 | `Response fields used` 改成真实读取集合；push 顺序有线包或标 UNKNOWN |
| 1. 双入口与一致快照 | 579/584、622/623、590/591；507/559/561/562/617 有证据才推 | `college_state`、建筑/奇迹、遗迹、星能结算时点、炼金基础快照；官方 Building/Level/Star/Explore 表 | 两入口、重登、无效等级/开关、定时恢复实机通过；不返回伪空成功 |
| 2. 建筑/奇迹与资源 | 233/244、234/245、235/246、271/272、238/249、695 | 建造队列、费用账本、星能/体力事务；CollegeLevel/StarLevel/WonderSkill；缺公式先决策 | 资源不足拒绝、不扣重、进阶上限/完工/重登、时钟跳跃测试通过 |
| 3. 派遣与训练 | 242/253、236/247、624/625、239/250；259/262、257/260、258/261 | 派遣/训练槽、英雄占用、结束时间、遗迹经验、Gift 奖励领取凭证 | 同英雄不重复占用、到时/未到时、取消/加速、重试幂等、重登恢复；RewardGrant 对账 |
| 4. 炼金与顾客 | 590–605、824–827，必要的 617 | 配方/生产槽/顾客订单/材料/经验；CollegeRecipe/Quest/Customer | 制作扣料与收取原子化，交易价格不信客户端，一键收取幂等，离线完成可恢复 |
| 5. 祈祷与洗炼 | 366–373、514、1055–1058 | 祈祷队列、装备属性、日次数；CollegeEquibReset/WonderSkill | 奖励只领一次、装备实例一致、日切有明确兼容决策 |

社交协助 879–882 的协议考古保留，但用户于 2026-09-27 决定：若非基础玩法必需，则不实施。现有入口与核心流程未显示其硬依赖，因此它不在上述实施路线中。五类待定收益/结果的含义见 [兼容草案](../decisions/compatibility/college_growthbase_compatibility_PROPOSAL.md#收益结果待定具体指什么)。

**推荐下一步：**先完成阶段 0 的客户端逐字段与线包证据，再单独开实现阶段 1。当前分析产物可直接作服务端接口和数据库设计输入，但不等于玩法已实现。
