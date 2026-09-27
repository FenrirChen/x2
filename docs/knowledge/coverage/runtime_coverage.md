---
Document-Type: Current Knowledge
Domain: Coverage
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - docs/history/2026-09-25_02_project_knowledge_index.md
---

# X2 Revival Runtime Coverage 交叉审计

> 2026-09-25 Section 奖励结算更新：3203/3203 Section 与 24/24 Type 已建立奖励来源目录；887 的 `outsideItems` 已接入有效 run 的事务结算，`SecSweep` 已有独立 MopReward 路径。金币手打兼容仅覆盖五个官方金币本，并读取各自扫荡 Gift；旧单预览 ×1 已删除。装备实例仍待发、逐关刷怪白名单及特殊奖励仍未恢复，奖励域仍 **PARTIAL**，Battle Entry 状态不变。见 [系统说明(../rewards/section_reward_system.md)与[覆盖明细(../rewards/section_reward_coverage.md)。下方旧表保留历史审计口径。

> 2026-09-25 假完成清理第一批：DailyDungeon 单 ID 门控、Hero1003 技能读模型/升级门控、主线默认 2110001、登录 Show1003 回退已移除；参见 [清理清单(false_complete_elimination.md)。DailyDungeon、Hero、Skill、Mission、Battle 整域仍为 PARTIAL；普通掉落 ×1 仍是明确的 Revival 兼容规则。下方 2026-09-24 数量和具体变体描述为历史审计快照，不能用作当前全部关卡入口状态。

审计日期：2026-09-24。范围：客户端 2.4 `ERequestTypes`、已恢复的 `Module/Manager/FSM`、现有静态表索引、Revival 运行服务及测试。**只读审计**；没有改 APK、功能代码或当前测试存档。机器可读逐功能矩阵与完整请求清单见 [`analysis/coverage/runtime_coverage.json`(../../../analysis/coverage/runtime_coverage.json)。

后续校正：本表下方的“资源本 110/141 固定奖可解析、31 阻断”是普通掉落接入前的历史静态口径。当前可交付固定奖与逐 Section 临时普通掉落的实际准入为 **20/141**，分属 4 个 Dungeon；其余 121 行因多候选、实例或特殊目标未解而阻断。`Gift.E_Random` 已按静态权重处理。见 [DailyDungeon 奖励审计(../../history/2026-09-24_02_daily_dungeon_reward_audit.md)。

## 口径与总览

状态严格按本轮定义：`COMPLETE` 要求主要已知变体、状态、持久化、重登和即时刷新均闭环；`PARTIAL` 是真实实现但未闭环；`STUB` 是空成功、空列表、兼容确认或固定拒绝；`MISSING` 是明确客户端能力而无实现；`UNKNOWN` 是证据不足；`INTENTIONALLY_UNSUPPORTED` 只用于已有明确 Null Chat 范围决定。单个请求存在 handler 不等于业务完整。静态配置完整与运行时完整分别记录。`BLOCKED_BY_MISSING_DATA` 是阻塞备注，仍保留上述主状态。

| 指标 | 数量 | 口径 |
|---|---:|---|
| Domains | 23 | A–W 业务域，含独立 DailyDungeon |
| Business features | 76 | 下述按业务能力拆分的矩阵行 |
| COMPLETE | 0 | 严格 DoD 下尚无整项闭环的业务特性 |
| PARTIAL | 42 | 有真实运行逻辑但缺变体、同步或规则 |
| STUB | 10 | 空值、固定拒绝、兼容确认 |
| MISSING | 22 | 客户端能力已明确，业务实现缺席 |
| UNKNOWN | 1 | 停服活动的具体恢复范围/运行规则未定 |
| INTENTIONALLY_UNSUPPORTED | 1 | 完整实时聊天；当前项目只选 Null Chat |
| Client C2L enum | 395 | `dump.cs` 的 395 个唯一 `EC2L_*` ID；枚举存在不等于 UI 当前可达 |
| Server handlers | 58 | `tools/local_game_server.py` 实际装配的 HTTP 以外 C2L 路由，含聊天端口 |
| Unhandled client requests | 337 | 395 与实际 handler 的差集；逐项在 JSON `client_requests` |
| Unknown owner requests | 40 | 无足够证据定位具体 Module；JSON 保留 `UNKNOWN` owner |
| Registered but unhandled | 3 | `C2L_PrepareMainMission`、`C2L_CheckoutMainMission`、`C2L_GuideStep` |

**证据级别：** `dump.cs` 的 enum 与生成类确认协议能力；模块名称有些来自类/方法，有些仅按请求名归属，JSON 用 `owner_evidence=name_inference` 标出。高价值路径另以已有静态审计及服务端方法交叉核对。无官方历史服务端源码或全量真实报文；不能从“未注册”推断客户端一定在目前账号/日历实际发送。

## 从客户端到持久化的覆盖矩阵

表内为各域的主要功能束；76 个逐功能条目拥有请求/响应 ID、handler、状态变化、SQLite、重登和刷新字段，可在 JSON 按域筛选。

| 域 | 客户端能力与主要 C2L | 当前运行态 | 主要遗漏 / 判定 |
|---|---|---|---|
| A Bootstrap / Login / Session | controlInfo、loginwithpw/httpLogin、`54 Login`、`337 ReConnect`、心跳、`945 ServerTableConfig` | PARTIAL | 单账号临时 token；进程重启后重登，重连不重放业务增量；登录快照有空字段 |
| B Lobby / Navigation / Guide | MainHallFSM、ButtonClick `376`、GuideStep `374`、大厅初始化 | PARTIAL / MISSING | ButtonClick 仅确认；GuideStep 有 registry 无 handler；Tito、UI stack、功能开放未持久化 |
| C Inventory / Item / Currency | ItemAll `556`、ItemUpdate push、ItemOpt `111` | PARTIAL / MISSING | 已支持库存/部分币种事务；实例型物品、锁定、时效、通用物品操作缺 |
| D Hero | HeroAll `546`、HeroOpt `109`、角色显示/选择 | PARTIAL | 39 个原型可合成；角色选择等变体、完整属性叠加与实时 UI 验证缺 |
| E Artifact | Artifact `143`、JewelCompose `144`、GodSlotLock `1030` | PARTIAL / MISSING | 解锁、进度、熔合、基础镶嵌有存档；属性/孔位开放、合成和特殊锁缺 |
| F Equipment | EquipAll `539`、DoEquip `118`、DoUnEquip `540`、Strengthen `115` | PARTIAL / MISSING | 测试实例/强化可持久化；掉落实例生成、喂养、品质、锁、套装效果缺 |
| G Skill | UpHeroSkill `131`、StarSkillUp `413` | PARTIAL / MISSING | `hero.id == 1003` 硬限制；其他角色、批量、神权等未闭环 |
| H Battle Entry | FightData `126`、PrepareMainMission `151`、SecSweep `1027`、Match/BattleEnter | PARTIAL / MISSING | 3,203 Section 已按 Type 索引；主线 78/79、资源本 110/141 关联行可执行确定性固定奖励并入场；挑战/活动/扫荡/续战仍缺，详见 `phase_battle_entry_domain.md` |
| I Battle Runtime | FightDropData `264`、FightKillInfo `316`、CheckFightProfile `447` | PARTIAL / STUB | UUID/run 有 SQLite；掉落为空、击杀仅确认、续战档案固定不存在 |
| J Battle Checkout | CheckoutMainMissionSign `887`→`152`、CheckoutMainMission `150` | PARTIAL / MISSING | Main 与 Daily 共用 Section→Gift→Item 首通/普通奖励事务及收据；其他类型、Gift 随机组、DropValue/扫荡/实例奖缺 |
| K Mission / Chapter | QueryMission `574`、章节/剧情 | PARTIAL / MISSING | mainMission 与 Daily `OtherChapter` 进度可回送；其他类型、story、星/宝箱缺 |
| L DailyDungeon / Resource Dungeon | 25 个 `DailyDungeon` 配置，E_Daily Section、FightData、SecSweep | PARTIAL / MISSING | 已关联且固定奖励可解析的资源本支持静态体力、首通/普通奖励、通关记录与下一节进度；开放日/次数兼容，Gift 随机组及 6 个孤立 E_Daily 缺 |
| M Task | GameTask `351`、FinishGameTask `350`、PickTreasureBox `310` | PARTIAL / STUB | 日周实例/部分事件/领奖有持久化；击杀、社交、探索等事件与活跃箱缺 |
| N Shop | ShopGoods `221`、BuyGoods `219`、RefreshShop `220` | PARTIAL / REVIVAL_COMPATIBILITY | 可安全发放商品查询购买、限购、收据、重登闭环；目录商品映射非官方，804 与刷新池未闭环 |
| N1 Collection | QueryCollectionAward `586`、GetCollectionAward `588` | PARTIAL | 26 条官方条件与账本已接；25 个 Gift 可领取，133103 的 E_Medal 奖励目标未支持而拒绝 |
| N2 Affection | AddFavor `274`、档案 `500–503`、联结 `498`、突破 `651`、手账 `657` | PARTIAL | 状态/查询/重登与 3 种单值礼物事务闭环；双值偏好、触摸和突破规则仍未知，拒绝未知变更 |
| O Achievement | AchvOverView `345`、AchvReward `346`、点数奖 `358` | MISSING | 318 条静态成就；进度、领奖、持久化均无 |
| P Draw / Gacha | CardPool `305`、LuckDraw `303`、结果 `381` | PARTIAL | 有轮换、花费、收据、保底；48 个 DrawParam 与当前 43 个轮换池不等；保底 UI/图片仍需实机核对 |
| Q Mail | MailData `196`、ReadMail `204`、ReceiveAttachment `197`、DelMail `207` | MISSING | 邮件实例、附件幂等及清理未做 |
| R Friend | UpdateFriends `449`、SendFriendReq `453`、SendFriendCoin `434` | MISSING | 好友关系、体力/友情币和关联任务未做；尚未正式决定不恢复 |
| S Club / Guild | CreateClub `742`、加入/审批/捐赠/活动 | MISSING | 社团状态、挑战、奖励未做；尚未正式决定不恢复 |
| T Chat / Comet / Snowflake | ChatJoin `521`、ChatAway `527`、ChatEvent `339` | STUB / INTENTIONALLY_UNSUPPORTED | Null Chat 只保证节点与空连接兼容；完整内容/私聊/社交广播不在当前目标 |
| U Activity / Event | QueryActivity `615`、ActivityMissionData `858`、ActivityShop `684`、Boss/Tower/Season 等 | STUB / MISSING / UNKNOWN | 静态活动表/模块很多；列表空成功，任务、商店、战斗和奖励缺；停服活动需逐个决定 |
| V Tutorial / Guide | NoviceFinish `217`、GuideStep163 `871`、TitoGuideModule | MISSING | 当前跳教程靠预置章/节，guide flags 与功能开放可能不一致 |
| W Growth / Progression | RoleExp、PlayerLevelBonus、PlayerStage、ArtifactFuse、EquibExp、SkillLevel | PARTIAL | 静态曲线与运行 handler 分离；等级礼包、全角色技能、套装/属性管线未闭环 |

### 战斗入口变体清单

客户端 `SectionTableEType` 明列普通关、Endless、Challenge、Daily、PointOfView、Training、WorldBoss、EndlessWeekly、ActivityWave/Boss/Story/Battle、ShuangHan、GuildChallenge、StoryExperience、TowerDefense、Battlepass、MoonChapter、Monopoly、Memory 等。3,203 个 Section 与 25 个 DailyDungeon 行现已从既有静态索引导出为运行目录，并由 `BattleEntryCatalog.resolve` 按 Type 分流；经济奖励目录覆盖 78 个主线与 141 个关联 E_Daily Section。普通主线 79 行中 1 行缺奖励目录；147 个 E_Daily 中 141 行由 DailyDungeon 关联、6 行孤立。141 行中 110 行固定奖组可执行，其余 31 行在入场前明确拒绝并列出阻塞。资源本开放日和次数仍采用独立 Revival 兼容配置。静态表本版所有 3,203 行均只有一个 Map；代码在将来出现多 Map 而客户端未指定场景时明确拒绝，不再默默取 `Maps[0]`。Challenge、活动、续战和扫荡仍未实现，故 Battle Entry 整域仍 `PARTIAL`。

## False-complete risks

1. **战斗系统**：`FightData` 现可进入部分主线与已关联资源本，但挑战、活动、续战、扫荡和将来多地图语义未覆盖；`CheckFightProfile` 固定无档。
2. **结算奖励**：Main 与确定性 Daily 固定 Gift/首通有事务；随机 Gift、DropValue 和扫荡仍缺，主线装备实例及特殊币种可进入 `pending_rewards`。
3. **大厅初始化**：26+ 查询能够让大厅显示，但大量 `code=10` 空状态；`ButtonClick` 不保存导航或引导状态。
4. **Hero/技能**：HeroAll 可显示多角色，但技能升级只允许 1003；属性整合不包含魂器/兽主套装的完整效果。
5. **装备**：背包有测试实例、六部位可佩戴，不代表真实掉落、品质、喂养、锁和套装规则可用。
6. **任务**：列表和固定奖励可用，但事件来源只覆盖一部分；活跃宝箱固定拒绝。
7. **商店**：809 的直接映射及 B 包 116 格可发放兼容商品可买；商品内容非官方，804 与刷新池未覆盖。
8. **重登**：英雄/物品/装备/日周/抽卡会重建；邮件、活动、引导、战斗续档等状态未建模。

## VARIANT_GAPS

| 已覆盖变体 | 明确遗漏 | 证据 / 最小探测 |
|---|---|---|
| 主线普通战斗 | DailyDungeon 入场已补；Challenge、Endless、Activity、WorldBoss、Tower、训练、retry、next、sweep 仍缺 | `SectionTableEType`、`DailyDungeon`、`C2L_SecSweep`；资源本请求链已实机捕获，见阶段报告 |
| 主线及确定性 Daily 固定奖励 | 其他 SectionType、Daily 随机 Gift 组、扫荡、随机怪物掉落、装备实例 | `SectionTable`/Gift 奖励字段已扩展；`DropValueID` 链仍断，见 Daily 覆盖扫描 |
| Hero 1003 技能升级 | 其余 38 个开放 Hero、前置/批量/神权 | `progression.py` 明确 `hero["id"] != 1003` |
| 魂器基础成长 | 宝石合成、孔位开放、属性同步、特殊 GodSlot | enum `144/215/725/1030` 与当前仅 `143` handler |
| 兽主穿戴/强化 | 多实例掉落、喂养、锁、品质/套装、预设方案 | enum `114/122/423–429/883`；测试实例目录 |
| 日周任务 | 击杀、探险、训练、社交等来源及活跃箱 | 40 个 `TaskCondition` 与 `_event` 调用来源差集 |
| CardPool 轮换抽取 | 全 48 静态池、艺术资源与额外抽卡变体 | `DrawParam` 48、当前 catalog 分组 43；客户端缺 `22702` 图 |
| QueryMission 主线 ID | 章节星/胸、剧情、OtherChapter、活动章节 | L2C_QueryMission protobuf 有未填字段 |

## 协议差集与 owner 不明

395 个 enum 请求中 58 个有实际 handler，337 个没有。项目 registry 有 61 个 C2L 名称，其中 `C2L_GuideStep(374)`、`C2L_PrepareMainMission(151)`、`C2L_CheckoutMainMission(150)` 仍未装配 handler。`CheckoutMainMissionSign(887)` 在客户端通过 `L2C_CheckoutMainMission(152)` 回包；不能误算“缺少 L2C_CheckoutMainMissionSign”。

高价值未处理请求：`134 FetchMobilityPower`、`144 JewelCompose`、`215 GodEqupJewelCompose`、`217 NoviceFinish`、`344/345/346` 成就、`196/197/204/207` 邮件、`413 StarSkillUp`、`423–429` 兽主方案、`1027 SecSweep`、`1030 GodSlotLock`、`1038 SceneGlobalParam`、`1082 MatchEnter`、`1085 BattleEnter`。40 个请求尚不能可靠定位 Module，JSON 逐条列名；不可用请求名推定为已恢复业务。大部分剩余请求属于社交/社团/历史活动，不宜只看差集数量定开发顺序。

## 持久化、重登与刷新缺口

| 状态路径 | 已证实 | 缺口 |
|---|---|---|
| `request → SQLite` | players.snapshot/revision、inventory、equipment_instances、wish_state/pity/receipts、economy_tasks/periods/history、battle_entries/receipts/runs/clears、shop receipts/counts、collection_awards、hero favor snapshot | Guide、Mail、Achievement、Activity、Friend、Club 无状态表；`pending_rewards` 仅待发不入背包 |
| 事务/幂等 | 部分成长、固定奖、任务领奖、抽卡、战斗结算有事务或收据 | 装备穿戴 `save_snapshot` 单独提交；跨业务一致性、所有错误重试未普遍验收；普通 `CheckoutMainMission` 无 handler |
| `disconnect → reconnect/login` | 登录回送 heroAll/equipAll/itemAll/taskDaily/taskWeekly/cardPool 及 PlayerData；同进程 token 重连 | 重启失效 token；重连只回 `id/serverTime`，不重放状态；战斗 profile 固定不存在；任务挑战/引导/邮件/活动为空 |
| 即时客户端刷新 | HeroUpdate、EquipUpdate、ItemUpdate、TaskUpdate、PlayerData 在部分修改后推送 | Mission 变化无专门 mission push；Guide/Shop/Activity/Achievement/Mail 无刷新协议实现；部分页面可能只靠重开/重登 |

## 静态配置与运行逻辑分离

- **固定 Section→Gift→Item**：静态引用完整；运行奖励目录覆盖 78 个主线和 141 个已关联 E_Daily Section。主线实例奖仍可能待发；Daily 确定性 Gift 会实际入账，含随机 Gift/未恢复目标的关卡在入场前拒绝。状态 `PARTIAL`。
- **随机掉落**：`DropValueID` 到 `DropProp` 的映射仍断链；`FightDropData` 空兼容。备注 `BLOCKED_BY_MISSING_DATA`，不能自造官方概率。
- **Shop**：25 个店、1,567 行静态分组；809 的 15 格沿用原证据映射，其余使用 B 包兼容目录中的可交付商品，购买/扣币/计数/收据/重登已实现。官方商品内容仍 `SERVER_ONLY_UNKNOWN`；804 和刷新池未闭环。
- **Task**：40 日周任务的静态条件/Gift 可用；运行事件来源、活跃箱、活动任务不完整。状态 `PARTIAL/STUB`。
- **Growth**：RoleExp/PlayerLevelBonus/PlayerStage/ArtifactFuse/EquibExp/SkillLevel 曲线已恢复到可验证程度；运行 handler 的角色、属性、奖励/材料变体仍 `PARTIAL`。

**测试覆盖信号：** 现有 Battle、Economy、Phase20 与 `test_battle_entry_domain.py` 覆盖主线及 `2030100` 的入场、扣费、固定奖励、通关、下一节、重登与收据；`SecSweep`、邮件、成就、好友和社团仍无运行测试。测试存在不能代替各客户端变体的实机判定。

## NEED_RUNTIME_PROBE

1. **资源本完成态**：`2030100/2130101` 实战一次，核对首通光辉/经验、体力、`QueryMission.OtherChapter` 与第二节可点击；退出重进及重登核对。
2. **挑战/特殊关**：打开可达的一个挑战入口→准备页→记录 `Prepare/FightData` 与类型字段。
3. **魂器镶嵌**：用两个相邻孔位各镶一枚不同绮石，退出重进核对位置及属性；只在备份后操作。
4. **绮石保底 UI**：同组两池切换后查看横幅数字，单抽一次，比较 `CardPool.securityNum/failCount` 与显示。
5. **主线重试/下一节**：在不强制战斗的前提下抓准备页/失败页请求；需要实际战斗时由用户操作。
6. **活动/商店**：活动仍只查询可见入口及空状态；商店可实测已列出的兼容商品，记录扣款、发放和重登表现。

## DOC_STATUS_CORRECTIONS

| 旧文档措辞 | 当前应如何读 | 建议后续更新 |
|---|---|---|
| README“已实现协议核心、登录/大厅、日周任务和基础养成” | 仅对应已验证路径；全域状态分别 PARTIAL/STUB | README 增加本矩阵链接，并明确 coverage 口径 |
| README“M5 最小登录”“M6 大厅” | 历史 milestone 正确；不表示所有 Login/Lobby 变体完成 | 保留历史，旁注全域 PARTIAL |
| SESSION_HANDOFF“26 对大厅消息已恢复” | 主要是空状态或只读确认，GuideStep 等未处理 | 后续交接注明 26 对协议覆盖与业务覆盖不同 |
| Phase 20“连续主线推进/固定奖励已实现” | 限 78 个运行目录 Section 与主线普通结算 | 后续报告明确 DailyDungeon/Challenge/Activity 独立缺口 |
| 旧 handoff“未实现武器/兽主实例” | 此句已被近期测试实例、魂器、穿戴、强化工作部分替代 | 下次交接按当前 `PARTIAL` 重写，不改历史段落 |

## 新 Definition of Done

- **Battle**：全部主要 SectionType/入口已分别标支持或明确不支持；支持入口有协议、准入/失败/重试/结算/掉线测试，关卡与英雄不隐藏硬编码，登录后状态一致，无未知请求。
- **Hero**：所有开放原型的查询、合成、等级/星级、属性、选择、材料事务、HeroUpdate 与重登可验；特殊角色例外显式记录。
- **Artifact**：解锁、进度、熔合、镶嵌/更换/卸下、孔位、消耗、属性、HeroGodEquip push/登录对所有已支持角色闭环。
- **Equipment**：实例生成、多实例、六部位穿戴/替换、强化/随机节点、喂养/品质/锁/套装、消耗、push、重登均有规则与测试。
- **Task**：每种开放任务的事件来源、进度、日周换期、领奖幂等、活跃箱、任务 push 和重登均验证；关闭的任务明确列出。
- **Mission**：当前/已通/可解锁章与节、星/宝箱/剧情、首次与重复奖励、分支和重登一致，不依赖仅按表顺序推进。
- **Inventory**：货币、堆叠材料、碎片、实例物品分别有发放/消耗/负余额校验、事务、ItemUpdate/PlayerData 与重登；待发账本可真正交付。

后续开发须以“业务域的主要已知变体与跨层状态闭环”为完成标准；单条 happy path 成功只证明该变体。

## 静态数据重审（2026-09-25 增补）

基于深层掉落数据考古新解码的 209 张客户端表，76 个 feature 的 `static_data_status` 已逐项重审：
2 个 missing → `FOUND_BUT_UNMAPPED`，4 个 unknown → `FOUND_BUT_UNMAPPED`，63 个 partial/complete 增补静态表备注。
**runtime_logic_status 全部未动**。逐项明细见 [runtime_coverage_static_reaudit.md(runtime_coverage_static_reaudit.md)；
机器可读差异在 `analysis/coverage/runtime_coverage.json` 的 `static_data_reaudit` 节。
