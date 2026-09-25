"""Knowledge reorg step 4: write the authoritative docs/knowledge/ entries."""
from __future__ import annotations

import time
from pathlib import Path

REPO = Path(r"D:\demo\x2\x2_revive_workspace")
K = REPO / "docs" / "knowledge"
TODAY = "2026-09-25"

def doc(rel, domain, body, supersedes=None, extra=""):
    p = K / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    sup = "\n".join(f"  - {s}" for s in (supersedes or [])) or "  - (none)"
    header = (f"---\nDocument-Type: Current Knowledge\nDomain: {domain}\nStatus: AUTHORITATIVE\n"
              f"Updated: {TODAY}\nSupersedes:\n{sup}\n"
              f"Evidence-IDs: see evidence/manifests/evidence_manifest.json\n{extra}---\n\n")
    p.write_text(header + body, encoding="utf-8")
    print("wrote", rel)

doc("architecture/system_overview.md", "Architecture", """# 系统总览

Revival 项目 = 官方《解神者》2.4 客户端 + 本地兼容服务器（`src/x2server/`）。

```
官方客户端(Revival v0.2, 仅改 Login_Url/packageType)
  ├─ HTTP Bootstrap: 登录身份/地址下发        (src/x2server/bootstrap/)
  ├─ TCP 长连接: protobuf 子集协议, 消息注册   (src/x2server/network/, protocol/, messages/)
  └─ 业务域: 登录/大厅/物品/英雄/装备/魂器/技能/战斗/结算/任务/商店/抽卡/聊天
                                        (src/x2server/player/)
持久化: 单 SQLite (players.snapshot 主体 + 24 张业务表)   (src/x2server/player/store.py 等)
静态数据: 服务器内置目录 + analysis/ 静态表目录           (src/x2server/data/)
```

权威领域文档索引见 [../../PROJECT_INDEX.md](../../../PROJECT_INDEX.md)（仓库根）。
服务器结构细节: [server_architecture.md](server_architecture.md)。
""", ["docs/history/2026-09-22_04_first_contact_plan.md"])

doc("client/client_architecture.md", "Client", """# 客户端架构要点（2.4）

- **IL2CPP 原生层**：业务 Module/Manager（FightModule/ChapterModule/StatsManager…）在
  `libil2cpp.so`；dump.cs 提供全部类/字段/RVA（Evidence: CLIENT_DUMP_CS）。
- **ILRuntime 热更层**：框架/入口存在但程序集未随包（phase2 结论）——原生代码中的孤立
  辅助函数（如 GlobalFun.GetItemByGiftGroup）可能原为热更调用对象。
- **静态表**：ResourceManager 注册 265 张 `table/*`；自定义保护层（RSA 首块+双轮 XOR）
  包裹 protobuf-like 数据；canonical 解码 = `D:/demo/x2/analysis/drop_archaeology/full_tables/`
  （Evidence: CLIENT_FULL_TABLES_2_4）。
- **网络**：MarsNetManager(主)/ChatNetManager/CardGameNetManager/WorldBossNetManager 四通道；
  Send/SendBattle 泛型实例化清单是判断"客户端真的会发什么"的权威（Evidence: PROTOCOL_CATALOG）。
- **表 Manager 模式**：每表一个生成 Manager（Load/GetItem/GetAllItem）；GetItem 常被编译器内联，
  字节级 xref 找不到调用点属正常。
""", ["docs/history/2026-09-22_05_milestones.md"])

doc("protocol/protocol_overview.md", "Protocol", """# 协议总览

- 枚举 `ERequestTypes`：**395 个 C2L / 444 个 L2C**（921 个 ID）。
- **348 个 C2L 有真实发送实例化点**；**47 个 NO_SEND_POINT_IN_2_4**（含 150/151/323/217 等）
  —— 给枚举写 handler 前必须查 `analysis/protocol/protocol_catalog.json` 的
  `client_status/send_channels`（Evidence: PROTOCOL_CATALOG）。
- 服务器已注册 64 个 C2L；61 个 L2C push。
- 战斗通道（SendBattle）专用消息：FightData/CheckoutSign/FightKillInfo/FightDropData/
  CheckFightProfile 等；商店/任务/活动走普通 Send。
- 887 `C2L_CheckoutMainMissionSign` 内嵌完整 150 `C2L_CheckoutMainMission` 载荷
  （checkout 字段 + battleFile），150 从不裸发。
- 消息字段结构查询：[message_catalog_guide.md](message_catalog_guide.md)。
""", ["docs/history/2026-09-25_01_project_knowledge_index.md"])

doc("protocol/message_catalog_guide.md", "Protocol", """# 消息目录使用指南

1. 全量目录：`analysis/protocol/protocol_catalog.json`（Evidence: PROTOCOL_CATALOG）
   —— 每条含 message_id / protobuf_fields / send_channels / paired_response /
   client_status / server_registered / business_domain。
2. 重新生成：`python tools/analysis/build_protocol_catalog.py`。
3. 服务器侧注册：`src/x2server/protocol/registry.py` + `src/x2server/messages/*`；
   dispatcher 只调用显式注册的 handler，未实现消息回空。
4. 未实现但客户端会发的高价值清单：`analysis/protocol/unhandled_high_value.json`
   （按业务域分组并附静态数据可得性注记）。
5. 纪律：`NO_SEND_POINT_IN_2_4` 的消息不写 handler；enum 存在 ≠ 客户端会发。
""")

doc("battle/battle_architecture.md", "Battle", """# 战斗架构

- **入场**：`BattleEntryCatalog.resolve`（src/x2server/player/battle_entry.py）按 Section.Type
  分流；当前运行态入口仅 E_Normal(78 线性主线) 与 E_Daily(20/141) 子集。
- **战斗模拟**：客户端权威模拟（帧同步命令 UpdateDropValue/FightItemBag_AddGold/SetDropLimit），
  服务器存 run/收据并在 887 结算校验。
- **结算**：887(内嵌 150) → 152 `L2C_CheckoutMainMission{rewardData…}`；316 FightKillInfo
  在结算后到达（遥测）；264/266 dropValues 语义仍未解（见 known_unknowns）。
- **掉落**：客户端运行时抽 DropProp（服务器不重抽），见 rewards/drop_system.md。
- 类型全集/样本：[section_types.md](section_types.md)（Evidence: SECTION_TYPE_CATALOG）。
""", ["docs/history/2026-09-24_03_phase_battle_entry_domain.md"])

doc("battle/section_types.md", "Battle", """# SectionType 全集

24 种 Type（含 79 个未设置的 E_UNSET），共 3,203 关。
最大未实现类型：E_Battlepass 2,400 关（74.9%）。

| Type | 数量 | 运行态 |
|---|---:|---|
| E_Normal | (主线线性) | PARTIAL：78 关可入场结算 |
| E_Daily | 147 | PARTIAL：20 关可交付（其余因多候选/实例/特殊目标阻断） |
| E_Battlepass / E_Challenge / E_PointOfView / E_Activity* / E_TowerDefense / … | 其余 | 已分类未实现 |

每类代表样本、支撑表、体力/掉落字段统计：
`analysis/battle/section_type_catalog.json`（Evidence: SECTION_TYPE_CATALOG）。
覆盖详情：[battle_variant_coverage.md](battle_variant_coverage.md)。
""")

doc("rewards/reward_system.md", "Rewards", """# 奖励体系（五层权威模型）

| 层 | 内容 | 计算 | 随机 | 保存 | 发奖 |
|---|---|---|---|---|---|
| 1 ROGUELITE_LOCAL_STATE | 场内银币(903)/神迹/塔道具/Buff/mazeItems | 客户端 | 客户端(战斗RNG) | 内存 | 无（仅遥测） |
| 2 BATTLE_PERSISTENT_DROP | Unit.DC→DropProp→FightItemBag(source=FIGHT)→887.outsideItems | 客户端 | 客户端 | 战斗包 | 服务器入账 |
| 3 SECTION_SETTLEMENT_REWARD | FirVReward/VReward/MopReward→Gift→**RewardData** | 服务器 | 服务器 | 服务器 | 服务器 |
| 4 SPECIAL_GAME_MODE_REWARD | Chest(物品)/Tower/Battlepass/WorldBoss/Race/Collection/活跃宝箱 | 服务器 | 服务器 | 服务器 | CLAIM_BUTTON/AUTO 混合 |
| 5 ACCOUNT_INSTANCE_REWARD | HeroEquip 整装（Id/Star/Param 全服务器） | 服务器 | 服务器 | 服务器 | RewardData.rewardEquip |

关键判定（全部有原生证据，详见子文档）：
- 层2→层1 的过滤：`source==FIGHT ∧ ItemUseScence==E_Outside`（outsideItems）；
  eNum 仅迷宫物品填写获取计数。
- 层3 的客户端解析器（GetItemByGiftGroup）存在但孤立；发放永远是服务器 RewardData。
- 层5 客户端零生成——HeroEquip 整只从 wire 反序列化。

子文档：[drop_system.md](drop_system.md) · [gift_system.md](gift_system.md) ·
[special_rewards.md](special_rewards.md) · [section_reward_system.md](section_reward_system.md) ·
[server_fix_plan.md](server_fix_plan.md)。
详细逆向过程记录：[reward_semantics.md](reward_semantics.md)（历史级证据链）。
""", ["docs/history/2026-09-24_07_deep_drop_archaeology.md",
      "docs/history/2026-09-25_02_external_dataset_crosscheck.md"])

doc("rewards/drop_system.md", "Rewards", """# 掉落系统（DropProp 层，与 DropValueID 层严格分离）

**链路（A 级）**：Unit.DC(62 值 100%∈DropClass) / NpcEvent / buff →
`GetDropItemByGroup(DropProp, level)`（0x1E4845C，完整 ARM64 还原）→
FightItemBag.AddItem(source=FIGHT) → checkout outsideItems。

**算法（A/B 级，见 [drop_algorithm.md](drop_algorithm.md)）**：
- 正 Picks：NoDrop + ΣProb 构成权重池，每 pick 互斥选一（先 Range(0,NoDrop+ΣProb) 空奖门控，
  再 GetProbability 选候选）；期望 P(empty)=NoDrop/T, P(i)=Prob[i]/T，T=NoDrop+ΣProb。
- 负 Picks：Prob=确定重复次数（不读 NoDrop）。
- 嵌套 DropClass：LIFO 栈展开；IsADC 组走动态候选（10000/Item.ItemValue 权重，依赖
  SectionTable.DroopLimit 等战斗上下文）。
- **Prob 不是百分比**：原始 332 行中 208 行 NoDrop+ΣProb≠100（合计 1~209）。
- Item.DropLimit/DropLimitParam(417 物品) + DropItemManager.CheckItemLimit = 每物品掉落上限。

**DropValueID 是另一层**：Section.DropValueID（341 值，10600000–10660999）与 DropProp 零交集、
在全部 249 张静态表零命中、第三方独立资料同样无映射（Evidence: DROPVALUE_CROSS_SCAN、
EXTERNAL_CROSSCHECK）——其运行时展开在服务器，语义未解（known_unknowns）。

**ExtraDroop**：SectionGroup→ExtraParam1/ExtraGiftID 的额外掉落桥（26 行，含每日限次 NumLimit），
触发业务未恢复，不自动发放。

图与逐行数据：Evidence: DROP_GRAPH / CLIENT_FULL_TABLES_2_4。
""", ["docs/history/2026-09-24_07_deep_drop_archaeology.md",
      "docs/history/2026-09-24_03_deep_drop_archaeology.md"])

doc("rewards/gift_system.md", "Rewards", """# Gift 系统

`Example.Gift{GiftGroup, AwardType, Probability[], GiftValue[], Num[], GiftShow[], ItemNum, EquibNum}`；
`GiftEAwardType={None=0, material=1, Random=2, RandomInterval=3, Pick=4, BlindBox=5}`。

| AwardType | 已确认语义 | 证据级 |
|---|---|---|
| E_material | 固定：GiftValue 直出（客户端解析器与服务器发放一致） | A |
| E_Random | **单次加权抽取**：GetProbability(rng, Probability) 选一个 GiftValue；**无 Σ=100 约束** | A（原生函数）/B（调用方孤立） |
| E_RandomInterval / E_Pick / E_BlindBox | 未恢复（Num 维度/交互语义未知） | UNKNOWN |

- **发放=SERVER_EXECUTED**：结算/扫荡/邮件全部以解析后的 RewardData 到达客户端；
  客户端 33 处 GiftManager 调用全为 UI 预览，checkout 路径零调用。
- 服务器按表发奖=重建官方服务器行为（REVIVAL_COMPATIBILITY 层面成立），当前实现应去掉
  ΣProbability=100 约束（见 [server_fix_plan.md](server_fix_plan.md) FIX-1）。
- 消费者图谱与解析器反汇编：[gift_runtime_semantics.md](gift_runtime_semantics.md)。
""", ["docs/history/2026-09-25_04_gift_runtime_semantics.md"])

doc("rewards/special_rewards.md", "Rewards", """# 特殊玩法奖励（触发模型）

**字段定性纠错（A 级）**：
- `ChallengeReward1` = **Language 文案 key**（如 21101515="111%月钻掉落奖励…"）——不是奖励。
- `ChestReward`/`ExpertChestReward` = **E_Chest 宝箱物品 ID**（1203501/1203701 系，101 关）
  —— 奖励=给宝箱物品，开启走物品使用（服务器解析）。

**触发模型**（发送通道事实来自 PROTOCOL_CATALOG）：
| 模型 | 玩法 | 协议 |
|---|---|---|
| CLAIM_BUTTON | 活跃宝箱 / 塔 / Battlepass / 赛段 / 收藏 / PickChest 翻牌 | 310, 927+929, 935/941/949/939/1059, 1106, 588, 1073 |
| AUTO_ON_CLEAR | 主线/资源本结算、扫荡 | 152 / 1028 RewardData |
| ITEM_USE | Chest 物品开启 | 未在 Send 泛型清单独立出现（B/C） |
| TASK_EVENT | E_GetExpertChest(42) | 任务条件系统 |
| QUERY_PLUS_CLAIM | WorldBoss 全链 | 679/415/701/417/407/409/419/471 |
| UNKNOWN | WeeklyDungeon 里程碑 | 无独立枚举项 |

Activity/Battlepass 与战斗结算是**两套系统**：E_ActivityBattle/E_Battlepass 关卡的战斗结算
仍走 887→152，活动进度奖励走各自协议族。
状态图：[special_reward_state_machines.md](special_reward_state_machines.md)。
""", ["docs/history/2026-09-25_05_special_reward_state_machines.md"])

doc("equipment/equipment_system.md", "Equipment", """# 兽主（Equib/Equipment）系统

**OFFICIAL_STRUCTURE（A）**：`HeroEquip{Id, TypeId=1240xxx, Level, Exp, Star,
Param=EquipParam{At1..6,Av1..6,Lock1..6}, LockState, TimeSec, SeasonId}`；
实例整只由服务器经 `RewardData.rewardEquip` 下发（152/1028/邮件），后续 L2C_EquipUpdate(536)，
全量 L2C_EquipAll(555)。客户端零生成、零随机。

**掉落→实例**：战斗掉 1240xxx（E_Outside）→ outsideItems{id,num,quality} →
服务器生成实例（Id 分配、Star roll、EquipParam 生成）→ RewardData.rewardEquip。
quality/eNum 是战斗包遥测，不是星级/词条参数。

**官方静态参数（服务器 roll 的输入，全部在 265 表内）**：
EquibBase（部位/套装/主副属性候选+权重）、EquibAttribBD（品质+等级→数值域）、
EquibStage（星级预设/喂养）、EquibExp（强化成本）、AttribType（属性名/上下限）。

**UNKNOWN_OFFICIAL_DISTRIBUTION**：官方星级分布、初始副词条数量公式
（EquibStage.MinorListMin/Max 疑似相关未证实）。
**REVIVAL_COMPATIBILITY**：星级分布与副词条数量为 Revival 自定规则，须标注，不得写成官方。

成本/曲线细节：[../../history/2026-09-23_00_client_progression_data_audit 摘要见
progression_system.md](../progression/progression_system.md)；
生成链详情：[equipment_instance_generation.md](equipment_instance_generation.md)。
""", ["docs/history/2026-09-25_03_equipment_instance_generation.md"])

doc("economy/economy_system.md", "Economy", """# 经济系统

**货币（A，CurrencyType 表 46 行）**：901=E_Gold→Item 1237901(金币)；902=E_Money→1237902(光辉)；
903=E_Silver→1237903（**迷宫/场内银币，非账号金币**）；900→1237900(因果)。战斗内
FightItemBag.AddGold 只写场内桶，账号入账靠服务器按 CurrencyType.ItemID 落账。

**固定奖励**：FirVReward(619 关)/VReward(2439 关)/MopReward(41 关 E_Daily)→Gift→Item
静态闭环（Evidence: SECTION_REWARD_CATALOG）。E_Random 按 FIX-1 归一化权重执行。

**商店**：25 店/1,567 商品行有价格/货币/周期；**GoodsID→ItemID/Num 客户端无映射**
（仅 17 条 Item.QuickBuyID 反查）——商品内容由服务器 L2C_Goods 决定（第三方独立资料同结论）。
商店当前固定拒绝（防成功空列表崩溃客户端）。

**体力**：每小节按 ManualValue 扣费（用户指定规则），失败退款；自然恢复/购买未实现。

**日周任务/活跃**：40 任务静态全解；事件源部分接入；活跃宝箱 310 已有发送点但 boxId
索引语义需实测样本。细节：[missing_evidence_followup.md](missing_evidence_followup.md)、
[client_economy_data_audit.md](client_economy_data_audit.md)、根 NEED.md。
""", ["docs/history/2026-09-23_01_client_economy_data_audit.md"])

doc("shop/shop_system.md", "Shop", """# 商店系统

- **静态（A）**：ShopConfig 25 店（ShopID/类型/刷新/条件）、ShopGoodsGroup 1,567 行
  （GoodsID=19xxxxx 合成 id、价格、货币枚举、限购周期、条件）——第三方工作簿逐字段互证 100%。
- **缺口（SERVER_ONLY）**：GoodsID→ItemID/Num、库存、限购次数、刷新执行、随机店抽取。
  唯一价格样本=第三方"随机商店(实测)"22 条（玩家口述，未验证，
  Evidence: EXTERNAL_WORKBOOK_X2_LOCAL_SERVER）。
- **当前运行**：查询/购买/刷新固定拒绝（code 13）——官方客户端在成功空商品时
  `ShopModule.OnRefreshShoppingMall` 空引用崩溃，必须走错误码分支（NEED.md 实机依据）。
- 关键方法：OnReceiveShopGoodsMsg(0x17A5660)、OnRefreshShoppingMall、GetInterval(0x17A7450)、
  CalNumPrice(0x1797A08)——RefreshInterval 是**数量分档阈值**不是刷新时间。
""", ["docs/history/2026-09-24_06_shop_recovery_from_workbook.md"])

doc("persistence/persistence_model.md", "Persistence", """# 持久化模型

- **主体**：`players.snapshot`（JSON，乐观 revision 并发控制）承载账号状态：
  gold/crystal/exp/hero_exp/equip_exp/日周活跃/main_chapter/main_section/mobility/heroes[]；
  每次登录 `snapshot_push` 全量回送（login.py:64-85）。
- **业务表 24 张**（economy/battle/equipment/progression/shop/wish 模块内建）：
  收据类（battle_receipts/sweep_receipts/economy_checkouts/wish_receipts/progression_receipts）
  保证幂等；账本类（economy_grants/pending_rewards/task_history）记录不可重放事实。
- **重登恢复**：inventory/equip/wish/task/hero 在登录组装（RESTORED_AT_LOGIN）；
  5 张表 PERSISTED_NOT_RESTORED（多为账本）；14 张 QUERY_ONLY。
- **推送**：ItemUpdate(553)/HeroUpdate(549)/EquipUpdate(536)/TaskUpdate(558)/PlayerData(1000)。
- 全部 schema/生命周期矩阵：`analysis/persistence/`（Evidence: SQLITE_SCHEMA_CATALOG/STATE_LIFECYCLE），
  审计：[persistence_relog_audit.md](persistence_relog_audit.md)。
活跃库=runtime/phase14/player.sqlite3，禁覆盖。
""", ["docs/history/2026-09-25_00_persistence_relog_audit.md"])

doc("progression/README_placeholder_check.md", "Progression", "", [])  # removed below if empty
(K / "progression/README_placeholder_check.md").unlink()

doc("coverage/known_unknowns.md", "Coverage", """# Known Unknowns（截至 2026-09-25 仍未解）

| # | Domain | Unknown | Why unknown | Evidence searched | 当前处理 | 阻塞 | 下一步 |
|---|---|---|---|---|---|---|---|
| 1 | Drop | DropValueID→掉落内容运行时映射 | 341 值全静态域零命中；第三方同结论；官方服务器数据失传 | 249 表全字段索引+二进制扫描+dump.cs xref+第三方 workbook | 未解账本，不生成 | 高（真实随机掉落） | 无静态路；只有官方报文样本可解 |
| 2 | Drop | 264/266 dropValues 准确语义（门控值=DropValueID 还是展开值） | JudgeDropItem Contains 用法只到 B 级 | OnFightDropData/JudgeDropItem 反汇编 | 空掉落兼容 | 中 | Revival 下发非空 dropValues 实机观察 |
| 3 | Equipment | 官方星级分布 / 初始副词条数量公式 | 服务器 roll 无静态痕迹；EquibStage.MinorListMin/Max 语义未证实 | EquibBase/AttribBD/Stage 表+wire 结构 | Revival 兼容分布 | 中 | FIX-3 落地后实机对照掉落展示 |
| 4 | Gift | E_RandomInterval/E_Pick/E_BlindBox 语义 | 解析器 Num 维度未展开；交互 UI 未逆向 | GetItemByGiftGroup/GetItemNumByGiftGroup | 拒绝执行 | 低 | 定点 disasm GetItemNumByGiftGroup |
| 5 | Special | WeeklyDungeon 里程碑触发 | 无独立协议枚举项 | protocol_catalog | 不并入 VReward | 低 | 等热更 DLL 或实机样本 |
| 6 | Special | 宝箱开启 C2L（E_Chest 物品使用通道） | Send 泛型清单无独立出现 | PROTOCOL_CATALOG | 只登记数据源 | 中 | 物品使用通道逆向（ItemOpt/热更） |
| 7 | Shop | GoodsID→ItemID/Num、库存/限购/刷新执行、随机店抽取 | 客户端无映射（17 条 QuickBuy 反查除外）；原服数据失传 | reference_graph+第三方互证 | 固定拒绝 | 高 | 历史非空 L2C_ShopGoods 样本 |
| 8 | Task | 宝箱 boxId 索引基数/季节切换 | 需非空 boxList 实测 | OnBoxReadyStateClick 链 | 不开放领取 | 中 | 实机抓 310 |
| 9 | Battle | CheckFightProfile 续战语义 | 固定 false 兼容 | 447 结构 | 拒绝续战 | 中 | 447/399 样本 |
| 10 | Client | ILRuntime 热更程序集本体 | 未随包（乐变下载链失传） | phase2 全量扫描 | 原生层足够 | 信息级 | 无 |
""")

doc("coverage/README_note.md", "Coverage", """Coverage 域文档：runtime_coverage.md（76 feature 矩阵）、runtime_backlog.md（P0-P3）、
runtime_coverage_static_reaudit.md（静态重审）、false_complete_audit.md / false_complete_elimination.md
（假完成审计与消除）、known_unknowns.md（未解清单）。""", [])
(K / "coverage/README_note.md").unlink()

doc("mission/README.md", "Mission", """# Mission/Chapter 域（证据不足，暂只保留入口）

已确认：L2C_QueryMission{OtherChapter,mainMission,story}；main_section/main_chapter 持久化推进；
ChallengeReward1=文案 key。章节星/宝箱/剧情状态机未恢复（见 known_unknowns）。
参考：`analysis/static_dictionary/reference_graph.json` 的 Mission 关系、battle/section_types.md。
""")

doc("tasks/README.md", "Tasks", """# Task 域（证据不足，暂只保留入口）

已确认：40 日/周任务静态全解（DailyTask/TaskCondition/TaskControl）、E_GetExpertChest(42)
任务事件、PickTreasureBox(310) 有发送点。未解：宝箱索引语义、更多事件源。
参考：economy/missing_evidence_followup.md、`analysis/static_dictionary/` Task 域关系。
""")

doc("CURRENT_STATE.md", "Coverage", """# 当前状态快照（2026-09-25）

- **可运行**：登录/大厅/物品/英雄(1003)/装备测试实例/魂器基础/技能/抽卡/固定奖励结算/
  主线 78 关 + 资源本 20 关/扫荡(41 关静态)/日周任务/聊天空频道。
- **测试**：226 passed（隔离 SQLite）。
- **已恢复领域**：见 knowledge/ 各域文档；运行态口径：coverage/runtime_coverage.md。
- **主要 PARTIAL**：Battle Entry 扩展类型、DailyDungeon 剩余变体、装备实例交付、Mission 真进度。
- **主要 known unknowns**：coverage/known_unknowns.md（10 项）。
- **兼容决策**：docs/decisions/compatibility/。
- **下一步推荐**：reward_system_server_fix_plan.md 的 FIX-1/2/3。
- **禁改**：Reference APK、活跃 SQLite（runtime/phase14/player.sqlite3）、已有备份。
""")

print("knowledge docs done")
