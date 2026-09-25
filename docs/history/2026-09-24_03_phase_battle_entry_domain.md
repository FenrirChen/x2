---
Document-Type: Historical Report
Date: 2026-09-24
Status: CURRENT_AT_TIME
Superseded-By:
  - (read alongside current knowledge)
---

# Phase — Battle Entry 按类型分流

日期：2026-09-24。范围为战斗入场及资源本奖励变体。没有修改 APK、清空存档或重扫 bundles；迁移前以 SQLite backup API 保存 `runtime/backups/before-battle-entry-20260924-091231.sqlite3`。Battle Entry 整域仍为 **PARTIAL**：已建立类型分流与统一 run，MainMission 与 DailyDungeon 共用固定奖励/通关事务；资源本普通掉落另按 Section 独立处理，其他类型、开放日/次数、实例掉落和续战另列。

## 架构与 SectionType dispatch

`tools/dev/export_battle_entry_catalog.py` 从已选定的 `SectionTable`、`DailyDungeon` 索引导出 `battle_entry_catalog.json`：3,203 个 Section、25 个 Dungeon。运行时 `BattleEntryCatalog.resolve` 按 `SectionID → SectionTable.Type → EntryPolicy → Map/Scene → Team/Cost → BattleEntryContext`，最后由 `BattleService.enter` 共用 FightData、UUID、run/entry 持久化。没有按单个 SectionID 写入场特判。MainMission 继续使用已有经济目录中 78 行及原固定奖励路径；DailyDungeon 仅准许类型为 E_Daily 且关联在 DailyDungeon 列表的行。类型不支持时在状态变更前明确拒绝。

`BattleEntryContext` 保存玩家、Section/Type、Chapter、已选 Map 与完整 Maps、来源、Hero IDs、体力成本及成本类型、次数上限、解锁条件、retry/profile/battle mode 和静态来源。队伍来自客户端 `ProfileHero`，验证已拥有、已解锁、最多 3 人且不重复；真实资源本 run 保存的队伍为 `[1028]`，说明本路径没有固定 1003。MainMission 原 Battle Hero 属性及 checkout 路径保留。

| SectionType | 行数 | 入场状态 | 当前边界 / 依据 |
|---|---:|---|---|
| Normal / MainMission | 79 | PARTIAL，78 行可支持 | 1 行 `2110706` 不在既有奖励目录；完整章节解锁与 profile 分支待补 |
| Daily | 147 | PARTIAL，20 行可交付固定奖励和临时普通掉落 | 141 行关联 25 个 DailyDungeon；121 行因多候选、实例目标等缺口入场前拒绝，6 行孤立；开放日/次数为兼容规则 |
| Endless | 1 | NOT_YET_IMPLEMENTED | 有独立客户端页/保存分支；run/profile 规则未恢复 |
| Challenge | 101 | NOT_YET_IMPLEMENTED | 类型与地图存在，排名/准入/结算仍未定 |
| PointOfView | 89 | NOT_YET_IMPLEMENTED | ChapterModule 的 POV 开放/章节分支独立 |
| Training | 4 | NOT_YET_IMPLEMENTED | 训练入口/规则需独立验证 |
| WorldBoss | 11 | BLOCKED_BY_MISSING_DATA | `QueryWorldBossOpenTime` 当前空兼容；在线时段与多人/排名状态缺 |
| EndlessWeekly | 8 | NOT_YET_IMPLEMENTED | 周期保存与奖励状态未恢复 |
| ActivityWave / ActivityBoss | 4 / 6 | NOT_YET_IMPLEMENTED | 活动开放与关卡前置状态未恢复 |
| ShuangHanStory / ShuangHanBattle | 21 / 21 | NOT_YET_IMPLEMENTED | 活动/剧情专用分支未恢复 |
| GuildChallenge | 52 | BLOCKED_BY_MISSING_DATA | 依赖尚未恢复的社团及挑战状态 |
| StoryExperience | 18 | NOT_YET_IMPLEMENTED | 剧情/试用编队约束未恢复 |
| ActivityStory / ActivityBattle | 82 / 62 | NOT_YET_IMPLEMENTED | 活动档期、任务及战斗结算独立 |
| ActivityGamePlay1 / ActivityGamePlay2 | 3 / 7 | NOT_YET_IMPLEMENTED | 活动玩法语义待证据 |
| NewBloodMoon | 10 | NOT_YET_IMPLEMENTED | 独立进入成本/状态待证据 |
| TowerDefense | 64 | NOT_YET_IMPLEMENTED | 波次与地图/编队分支待证据 |
| Battlepass | 2,400 | NOT_YET_IMPLEMENTED | 静态行很多，不能当作普通主线批量开放 |
| MoonChapter / Monopoly / Memory | 2 / 4 / 7 | NOT_YET_IMPLEMENTED | 各有独立活动/玩法状态；Memory 行部分被 DailyDungeon 引用但 Type 非 Daily，明确拒绝 |

`MatchEnter(1082)` 的字段是 `cardGroupId/robot`，属于 `CardGameUIModule` 的配卡匹配；`BattleEnter(1085)` 为 `playerId/token`，属于卡牌对战网络管理器。二者**不是**普通 Section 入场，当前分类为在线卡牌模式 `NOT_YET_IMPLEMENTED`。`SecSweep(1027)` 为 `sectionId/sweepCount`，返回含 rewardData；它是免战斗的独立结算入口，需通关/体力/次数/奖励规则，当前 `NOT_YET_IMPLEMENTED`，未塞进 FightData handler。

## DailyDungeon 请求链和静态链

客户端已包含 25 行 DailyDungeon 本地列表；实际打开资源本时，服务端先见 `ButtonClick(376)` 与 `CheckFightProfile(447)`，选关后收到 `C2L_FightData(126)`，没有发现专用列表查询或 `PrepareMainMission(151)`。09:07:12 原版服务收到 `missionId=2130101, chapter=2030100, sceneId=2230101`，请求体 141 字节，因旧目录不含该 Section 返回 `L2C_FightData.result=13`。09:19:11 新版服务又收到 `2130201/2030200/2230201`，返回 10，之后收到 `DelFightProfile(399)` 与 `FightDropData(264)`；客户端进一步发送 `CheckoutMainMissionSign(887)`，证明该资源本沿用 152 结算回包。第一版仍拒绝结算，随后增加兼容空奖收据，未把这次失败说成胜利结算验收。09:24:50 再次实机收到 `2132001/2032000/2232001`，返回 10，run 保存 Type=3、Source=DailyDungeon、Map=2232001、Team=`[1028]`，静态体力费 6 已入 `battle_costs`。

静态样例链：`DailyDungeon.ID=2030100 → SectionID=[2130101,2130102,2130103,2130104,2130105] → SectionTable(2130101).Type=E_Daily/Maps=[2230101]/NextSectionID=2130102/OpenType=E_Level/OpenParam=11/ManualValue=6 → FirVReward 730001 → Gift → 光辉(1237902)×30；VReward 730071 → Gift → 解神者经验(1237908)×6、神格经验(1237907)×60`。`MopReward` 另含 `795201 → 金币×2078`，属于尚未实现的扫荡；`DropValueID=10630101` 的掉落映射仍缺。该 Dungeon 的 OpenTime 为七个 1、Limit=-1；其他行有不同日历和值为 3 的 Limit。25 个 Dungeon 共关联 176 个 Section，其中 141 是 E_Daily，其余为活动/Memory/Battlepass Type；147 个 E_Daily 中有 6 个孤立行。当前导出的全部 3,203 行都只有一个 Map；选择时仍验证 scene 属于 Maps，未来多 Map 未指定 scene 将拒绝并标 `MULTI_MAP_UNRESOLVED`，不默默取首项。

## 准入、COMPAT 和 run

- MainMission：原 `ManualValue` 扣费、失败退款、固定奖励与重复结算幂等保持；经济目录外的普通关卡拒绝。完整章节解锁仍为现有最小规则。
- DailyDungeon：`E_Level` 用玩家等级、`E_Stage` 用已通关记录校验；按 `DailyDungeon.SectionID` 顺序要求前节通关，必须关联该 Dungeon 且 Chapter/Scene 匹配。`ManualValue` 是 **STATIC_COST**，入场扣费，失败或放弃旧 run 退款。当前 `schedule=always_open`、`attempt_limit=None` 是明确的 **REVIVAL_COMPAT**；不冒称原服星期与次数规则。首个实测体力费是 6。
- Daily 胜利结算：撤销早期空奖路径。`EconomyService.settle` 现在按 `Section → FirVReward/VReward → Gift → Item` 与主线共用解析、`_grant` 交付及收据事务；首通才加 FirVReward，重复胜利只发 VReward。写入 `economy_clears`，不修改主线 frontier；`QueryMission.OtherChapter` 按 `DailyDungeon.SectionID` 连续通关顺序返回 `{type=3, missionData: DungeonID→最后已通 SectionID}`。客户端 `ChapterModule.OnHandleQueryMission` 将 type=3 写入 `DailyMissionDic`，`CheckDailySectionFirstChallenge`（RVA `0x16BABC0`）对当前与已通 Section 在有序列表中的索引作比较。失败结算退体力；重复 checkout 读同一 receipt，不重复发奖。
- 缺少确定性 Gift 规则或奖励目标的 Daily Section 在入场前拒绝，避免扣体力后才发现无法结算。`FightDropData` 的空值仅代表 `DropValueID` 随机掉落链缺证据，不替代固定奖励。早期实机 `2132001` 的空奖收据是历史兼容结果，本轮没有擅自补发或修改该收据。
- 同请求重试返回既有 response/UUID；同 Section 已有活动 run 时新请求拒绝，其他 Section 入场会按原规则放弃并退款旧 run。`isFromProfile/expertMode/checkGm` 仍明确拒绝；新的 retry、下一节、续战语义为 `NOT_YET_IMPLEMENTED`，未复用旧 run 领奖。
- `battle_entries` 加 `section_type/entry_source/map_id/team_json`，`economy_runs` 加 `section_type/entry_source`；幂等 `PRAGMA table_info → ALTER TABLE` 迁移，旧记录默认 MainMission。活动状态仍用 `economy_runs.settled`。隔离库重开及活跃库 `PRAGMA quick_check=ok` 已核对，存档未 wipe。

## 回归与仍需探测

新增 `test_battle_entry_domain.py` 涵盖主线入场、Daily 入场/体力、首通三种真实奖励与实际存档、重复通关不再发首通、失败退款、同 run 收据幂等、通关记录、下一节前置、QueryMission OtherChapter、重登后的下一节入场，以及未知 Section/Type、非法 Hero、缺 Map、旧 schema 重复迁移。既有 Phase20 测试覆盖主线连续小节、固定奖励、重复结算。当前全套 **188 passed**；独立 [`daily_dungeon_coverage.json`(../../analysis/coverage/daily_dungeon_coverage.json) 扫描 25 个 Dungeon：12 个副本全组的确定性固定奖励链可解析；141 个关联 E_Daily 中 110 行可执行固定奖励并准入，31 行奖组/目标未解析而预先拒绝，6 个 E_Daily 孤立。8 个副本含 `Gift.E_Random`、5 个含未恢复货币目标、5 个引用非 E_Daily 类型；分类可重叠。

纠偏前实机已确认 `FightData`、战斗场景、静态体力扣费、`FightDropData`、`CheckoutMainMissionSign` 与随后 `QueryMission` 请求。新版 `2030100/2130101` 已由用户实测结算与下一节解锁正常；SQLite `economy_grants` 实际记录光辉 30、解神者经验 6、神格经验 60。用户同时确认普通战斗未获金币。`SectionTable.DroopDisplay=[1237901]` 是金币预览来源，`VReward` 不含金币，`MopReward` 的 2078 金币仅供扫荡；缺的是普通战斗 NORMAL_DROP。该缺口及 25 个 Dungeon 各自的奖励预览见 [`daily_dungeon_reward_audit.md`(2026-09-24_02_daily_dungeon_reward_audit.md)。主线改造后的实机入场仍待确认。绝不因固定奖励/通关成功就标记 Daily COMPLETE。

## 开发规则

已有官方静态数据足以形成 `Section→Gift→Item`、体力或进度链时，禁止以 empty/stub/compat/固定成功代替。若仍需兼容，须先写明为什么静态证据不能使用、具体 blocker，并取得用户允许。本轮保留的 COMPAT 仅是开放日常开、每日次数不限；`DropValueID` 随机掉落是单独的 `BLOCKED_BY_MISSING_DATA`。固定奖励、体力及可恢复的 Section 顺序必须真实执行。

## 2026-09-24 同关重入修复

用户重启服务后点击 `2130103` 两次均收到 `L2C_FightData.result=13`。日志显示该关前一次暂停的 run 仍处于 `settled=0`；旧实现只要同一 Section 存在活动 run 就直接拒绝，且不记录拒绝原因。随后用户改进 `2130102`，旧 run 按跨关路径退款并结清，证明不是第三关静态配置、关卡顺序或奖励表故障。现统一采用已有跨关替换事务：无论同关还是换关，新请求先验证队伍、地图、准入和奖励，再将未完成 run 退款、标记结清，扣新 run 的体力并持久化新 UUID；相同 request-key 重发仍返回同一个 UUID。测试覆盖同关重入不重复扣体力，且逐一模拟 78 个已收录主线关卡入场、4 个已支持资源本的 20 关顺序入场与结算。其余 SectionType 与数据缺口仍按上文边界，不能因这次修复宣称全项目战斗入场 COMPLETE。

## 资源本专属掉落补充审计（同日后续）

上文关于“110 行可入场、31 行随机 Gift 阻塞、188 passed”的数字是普通掉落补齐前的历史检查口径。现在 `Gift.E_Random` 使用已提取的 `Probability`（所引用 71 行的权重均合计 100）并在结算收据事务中抽取；`DailyDungeonRewardCatalog` 以 DungeonID/SectionID 记录首通固定、普通固定、普通掉落预览与扫荡四条独立路径。普通掉落只在 `DroopDisplay` 唯一、Item 可入账时采用用户授权的 **Revival 临时数量 1**，并与固定奖合并入同一次结算事务。金币本 2130101 因此新增金币 1；2030200 的 2130201 则得到该节预览的 1238100 ×1，另保留它自己的普通固定奖励。未把 `MopReward` 挪入普通战斗，也没有全局 E_Daily 金币特判。

定点核查见 [`daily_dungeon_reward_audit.md`(2026-09-24_02_daily_dungeon_reward_audit.md)：客户端 `DropProp` 有局部抽取逻辑，但与资源本预览 ItemID/`DropValueID` 无映射；服务响应 `FightDropData.dropValues` 会写入客户端战斗状态。因此官方 NORMAL_DROP 数量/概率不能从当前资料恢复，也不能断言全部怪物掉落都由服务器直接决定。当前可完整交付临时规则的是 4 个 Dungeon/20 个 E_Daily Section；其余 121 个关联 E_Daily 因多候选、实例生成或特殊目标未解，在入场前拒绝。5 个仅含其他 SectionType 的 Dungeon 仍另列。战斗内 `FightDropData` 可视掉落尚未恢复，新规则目前只保证胜利结算到账。更新后的单元套件 **171 passed**；用户更新服务后实际完成 2130102，反馈正常，SQLite 收据包含金币 +1。
