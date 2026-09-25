"""Knowledge reorg step 5: PROJECT_INDEX, history overlays, decisions, governance, migration path map."""
from __future__ import annotations

from pathlib import Path

REPO = Path(r"D:\demo\x2\x2_revive_workspace")
TODAY = "2026-09-25"

# ---------------- PROJECT_INDEX.md ----------------
(REPO / "PROJECT_INDEX.md").write_text(f"""# READ THIS FIRST — X2 Revival 项目知识索引

**第一次进入本项目：**
1. 先读本文件（PROJECT_INDEX.md）
2. 再读 `docs/knowledge/`（当前权威知识）
3. 只有研究历史时才读 `docs/history/`
4. 需要原始证据时才进 `evidence/`（先用 `evidence/manifests/evidence_manifest.json` 定位）
5. **不允许用 historical report 覆盖 current knowledge**；被推翻的结论见
   `docs/history/SUPERSEDED_KNOWLEDGE.md`

## A. 项目一句话目标

以官方《解神者：X2》2.4 客户端为唯一依据，建立可本地运行的兼容服务器（Revival）；
缺失的官方数据以明确标注的兼容规则补齐，绝不冒充官方。

## B. 当前版本 / 客户端

- Reference Client：`D:/demo/x2/X2_Eclipse_v2_4.apk`（官方 2.4 / versionCode 202，永久原样）
- Revival Client：v0.2（仅改 Login_Url/packageType）；主试玩环境 MuMu 12（127.0.0.1:7555）
- 活跃存档：`runtime/phase14/player.sqlite3`（60 级测试账号；**禁覆盖/重置**）

## C. 核心目录

| 目录 | 作用 |
|---|---|
| `docs/knowledge/` | **当前权威知识**（按领域：architecture/battle/rewards/equipment/economy/progression/shop/persistence/coverage/mission/tasks/dev/protocol/client） |
| `docs/history/` | 开发与研究历史（YYYY-MM-DD_NN_topic.md；含 PROJECT_TIMELINE / SUPERSEDED_KNOWLEDGE） |
| `docs/decisions/` | 决策记录（adr/ + compatibility/） |
| `evidence/` | 证据层：raw（原始，勿动）/ derived（可再生）/ external（第三方隔离）；入口 `evidence/manifests/evidence_manifest.json` |
| `analysis/` | 脚本生成的分析产物（canonical 路径登记在 evidence manifest） |
| `tools/analysis/` | 确定性生成器/审计脚本（可重跑） |
| `src/x2server/` | 服务器源码（业务实现） |
| `tests/` | 226 passed（隔离 SQLite） |
| `runtime/`, `release/` | 运行数据 / 分发 |

仓库外的上游资料（不搬动）：`D:/demo/x2/phase2_output`、`phase3_output`、
`analysis/drop_archaeology/`、`analysis/external_crosscheck/`、`tools/Il2CppDumper-bin/`。

## D. 权威文档导航（docs/knowledge/）

| 领域 | 入口 |
|---|---|
| 总览 | architecture/system_overview.md · CURRENT_STATE.md |
| 协议 | protocol/protocol_overview.md · protocol/message_catalog_guide.md |
| 战斗 | battle/battle_architecture.md · battle/section_types.md · battle/battle_variant_coverage.md |
| 奖励 | rewards/reward_system.md（五层总模型）· rewards/drop_system.md · rewards/gift_system.md · rewards/special_rewards.md · rewards/section_reward_system.md |
| 装备 | equipment/equipment_system.md · equipment/equipment_instance_generation.md |
| 经济 | economy/economy_system.md · economy/missing_evidence_followup.md |
| 商店 | shop/shop_system.md |
| 成长 | progression/progression_system.md |
| 持久化 | persistence/persistence_model.md · persistence/persistence_relog_audit.md |
| 覆盖 | coverage/runtime_coverage.md · coverage/runtime_backlog.md · coverage/known_unknowns.md |
| 客户端 | client/client_architecture.md · client/static_table_dictionary.md |
| 服务器开发 | dev/（architecture/network/protocol_spec/bootstrap/…） |
| Mission/Tasks | mission/README.md · tasks/README.md（证据不足域） |

## E. Evidence 导航

见 `evidence/README.md` 与 `evidence/manifests/evidence_manifest.json`（32 条 Evidence ID）。
常用：CLIENT_DUMP_CS / CLIENT_IL2CPP_2_4 / CLIENT_FULL_TABLES_2_4 / PROTOCOL_CATALOG /
DROP_GRAPH / SECTION_REWARD_CATALOG / REWARD_REVERSE_JSON / EXTERNAL_WORKBOOK_X2_LOCAL_SERVER。

## F. 当前 Runtime 状态

`docs/knowledge/CURRENT_STATE.md`；根 `SESSION_HANDOFF.md`（人工试玩环境与存档边界）。

## G. Known Unknowns

`docs/knowledge/coverage/known_unknowns.md`（10 项，含 DropValueID 运行时语义、
商店商品内容、装备官方星级分布等）。

## H. Compatibility Decisions

`docs/decisions/compatibility/` —— Revival 明确自定的行为（非官方）都登记在这里。

## I. History

`docs/history/PROJECT_TIMELINE.md`（认知里程碑）· `docs/history/SUPERSEDED_KNOWLEDGE.md`
（已推翻结论）· 33 篇 dated 报告。

## J. Tooling

`tools/analysis/`：build_table_dictionary / build_reference_graph / build_protocol_catalog /
audit_hardcodes / audit_persistence / build_section_catalog / build_coverage_reaudit /
build_reward_reverse / build_evidence_manifest / validate_knowledge_base / calculate_drop_probability。
仓库外：`D:/demo/x2/analysis/drop_archaeology/*.py`（表全量解码与交叉扫描）。

## K. Tests

`python -m pytest tests/` = 226 passed。隔离 SQLite；禁用活跃库。

## L. 按任务的阅读路径

- **研究掉落**：READ docs/knowledge/rewards/drop_system.md + rewards/drop_algorithm.md +
  rewards/fightitembag_persistence_boundary.md；EVIDENCE DROP_GRAPH、DROP_ALGORITHM_EVIDENCE、
  CLIENT_FULL_TABLES_2_4。
- **研究装备**：READ docs/knowledge/equipment/equipment_system.md + equipment_instance_generation.md；
  EVIDENCE REWARD_REVERSE_JSON、CLIENT_FULL_TABLES_2_4。
- **研究协议**：READ docs/knowledge/protocol/*；EVIDENCE PROTOCOL_CATALOG、CLIENT_DUMP_CS。
- **实现奖励/商店**：READ rewards/reward_system.md + economy/economy_system.md + shop/shop_system.md +
  rewards/server_fix_plan.md；EVIDENCE SECTION_REWARD_CATALOG。
- **继续开发**：READ docs/knowledge/coverage/runtime_backlog.md + CURRENT_STATE.md；
  根 SESSION_HANDOFF.md（环境边界）。
- **查历史**：docs/history/PROJECT_TIMELINE.md 起步。
""", encoding="utf-8")

# ---------------- docs/README.md (governance) ----------------
(REPO / "docs" / "README.md").write_text(f"""# docs/ 目录治理（{TODAY} 起生效）

新文档必须放对层级，**禁止继续扔 docs 根目录**：

| 内容 | 位置 | 命名 |
|---|---|---|
| 研究过程报告（某轮做了什么） | `docs/history/` | `YYYY-MM-DD_NN_topic.md`（文件头加 Historical Report 元数据块） |
| 当前权威知识（游戏/系统现在怎么工作） | `docs/knowledge/<domain>/` | `snake_case.md`（文件头加 Current Knowledge 元数据块） |
| Revival 自定行为决策 | `docs/decisions/compatibility/` | `snake_case.md`（Decision/Reason/Scope/Official/User-authorized） |
| 架构决策记录 | `docs/decisions/adr/` | 沿用 NNNN-title |
| 原始证据 | `evidence/raw/`（大文件原地+manifest 登记） | 稳定机器名 |
| 派生机器数据 | `analysis/`（canonical 登记在 evidence manifest） | 稳定机器名，禁 final/new/latest 后缀 |
| 第三方资料 | `evidence/external/` | 原名 |
| 临时草稿 | `analysis/scratch/` | 任意 |
| 完全被替代且无历史价值 | `docs/archive/superseded/` | 原名 |

同一产出只有一个 canonical；改结论不改历史（历史报告加 Status/Corrections 头）。
迁移一律 `git mv`；每轮整理产出 migration_map 与 PATH_MIGRATION.md。
校验：`python tools/analysis/validate_knowledge_base.py`。
""", encoding="utf-8")

# ---------------- history README / TIMELINE / SUPERSEDED ----------------
(REPO / "docs" / "history" / "README.md").write_text("""# 开发与研究历史

- [PROJECT_TIMELINE.md](PROJECT_TIMELINE.md) — 按认知变化整理的里程碑（先读这个）
- [SUPERSEDED_KNOWLEDGE.md](SUPERSEDED_KNOWLEDGE.md) — 曾被相信、后来推翻的结论
- 文件命名 `YYYY-MM-DD_NN_topic.md`；文件头的 Metadata 块标注 Status / Superseded-By /
  Known-Corrections。历史内容保持原样，不回写新结论。
""", encoding="utf-8")

(REPO / "docs" / "history" / "PROJECT_TIMELINE.md").write_text(f"""# 项目认知时间线（按里程碑，非流水账）

## Phase 0 客户端恢复启动（2026-09-22 前）
Problem: 停服游戏能否本地跑起来。Breakthrough: 官方 2.4 APK 内核心资源完整（评级 B），
IL2CPP 可逆向，热更 DLL 未随包。Evidence: phase2/phase3 报告（history/2026-09-22_*）。
遗留: 热更程序集失传；Web 配置失效。

## Phase 1 协议基础与登录大厅（2026-09-22）
Breakthrough: PackInt/CRC/protobuf 子集/分帧全部还原；54→79 登录链路打通。
Evidence: phase6–phase10 报告。Code consequence: src/x2server/network+protocol。

## Phase 2 MainMission / 稳定启动（2026-09-22~23）
Breakthrough: Revival v0.2 客户端改造方案；首关实机进入。Evidence: phase11–13。

## Phase 3 持久化 / Hero / 大厅状态（2026-09-23）
Breakthrough: SQLite 快照+乐观并发；60 级账号；26 对大厅消息。
Evidence: phase14–16, phase18–20。Code consequence: player/store+login+hero。

## Phase 4 经济与成长静态审计（2026-09-23）
Breakthrough: 固定奖励 Section→Gift→Item 静态闭环；成长曲线全解；
随机掉落断链被首次确认（DropValueID 零命中）。
Evidence: history/2026-09-23_01_client_economy_data_audit.md 等。

## Phase 5 运行覆盖审计 / 假完成清理（2026-09-25 前）
Breakthrough: 76 feature×运行态口径矩阵；DailyDungeon 奖励审计；hardcode 门控消除。
Evidence: history/2026-09-24_*、docs/knowledge/coverage/false_complete_*。

## Phase 6 完整 265 表提取（2026-09-24~25）
Breakthrough: ResourceManager 全量注册表 dump；209 张从未提取的表全部解码（零记录错误）。
Evidence: D:/demo/x2/analysis/drop_archaeology/。

## Phase 7 掉落考古（2026-09-24）
Breakthrough: DropValueID 无静态映射（A 级负面）；DropProp 递归闭包 COMPLETE；
Unit.DC→DropClass 100%；ExtraDroop/CurrencyType/ItemSource 新表；
outsideItems/eNum/887 结构、323 无发送点。
Evidence: history/2026-09-24_07/08/09_*。

## Phase 8 第三方数据交叉验证（2026-09-25）
Breakthrough: 第三方工作簿掉落/商店静态层 99–100% 互证；识别其 3 处未申报修复+
4 处噪声行；"随机商店实测"22 条为唯一外部价格样本。
Evidence: history/2026-09-25_02_external_dataset_crosscheck.md。

## Phase 9 DropProp 算法逆向（2026-09-25）
Breakthrough: GetDropItemByGroup 完整 ARM64 还原——正/负 Picks 两种模式、
NoDrop+ΣProb 权重池、嵌套栈展开、IsADC 动态候选；"Prob=百分比"被精化为权重。
Evidence: docs/knowledge/rewards/drop_algorithm.md + analysis/drop_algorithm/。

## Phase 10 统一 Section Reward（2026-09-25）
Breakthrough: 3203/3203 关的奖励来源分类；扫荡 SecSweep 落地；
DYNAMIC_ALLOWED 真实性保护策略。Evidence: knowledge/rewards/section_reward_*.md。

## Phase 11 奖励语义总还原（2026-09-25）
Breakthrough: SetCheckout_BattleItem/GetPersistentItemsList 逐指令还原（eNum=迷宫获取计数）；
Gift 发放=服务器执行+客户端解析器孤立；装备实例=服务器整装下发（RewardData.rewardEquip）；
ChallengeReward1=文案 key、Chest=E_Chest 物品；Tower/Battlepass/WorldBoss=CLAIM_BUTTON。
Evidence: knowledge/rewards/reward_semantics.md + analysis/reward_reverse/。

## Phase 12 知识库重构（2026-09-25）
本层建立：evidence/knowledge/history/decisions 四层分离；PROJECT_INDEX 成为唯一入口。
""", encoding="utf-8")

(REPO / "docs" / "history" / "SUPERSEDED_KNOWLEDGE.md").write_text(f"""# SUPERSEDED KNOWLEDGE — 曾被相信、后来被推翻/精化的结论

目的：防止未来 AI 从旧报告把旧错误带回来。当前权威结论一律以 docs/knowledge/ 为准。

| 曾相信 | 状态 | 推翻证据 |
|---|---|---|
| 323 C2L_FightDropInfo = 逐次拾取上报 | REJECTED | 全 dump.cs 无发送实例化点；实机两场金币本未出现 |
| 150 C2L_CheckoutMainMission 是结算通道 | REJECTED（精化） | 客户端 2.4 只发 887 wrapper（checkout 内嵌） |
| DropProp.Prob 数值=百分比 | REFINED | 正 Picks=相对权重（NoDrop+ΣProb 归一），负 Picks=确定重复次数（ARM64 还原） |
| NoDrop+ΣProb 必须=100 | REJECTED | 原始 332 行中 208 行违反（合计 1~209）；第三方工作簿据此做的 3 处"修复"不采纳 |
| DROP_WEIGHT_PARAM=10000 参与普通抽取 | REFINED | 仅 IsADC 动态候选权重（10000/Item.ItemValue） |
| DropValueID 可静态映射掉落 | REJECTED | 341 值全静态域零命中；第三方独立同结论 |
| ChallengeReward1 = 挑战奖励字段 | REJECTED | 值为 Language 文案 key（"111%月钻掉落奖励…"） |
| ChestReward/ExpertChestReward = Gift 组 | REJECTED | 是 E_Chest 物品 ID（1203501/1203701 系） |
| Gift.E_Random 需 ΣProbability=100 才可执行 | REJECTED | GetProbability 按权重和归一化，任意正权重合法 |
| 兽主 quality/eNum = 星级/词条参数 | REJECTED | quality=战斗包品质透传；eNum=迷宫物品场内获取计数 |
| HeroEquip 可由客户端生成 | REJECTED | 实例整只由服务器 RewardData.rewardEquip 下发，客户端零构造 |
| 兽主掉落=最终 HeroEquip 直接入包 | REFINED | 战斗内只掉 1240xxx ItemDataP，实例化在服务器 |
| MatchEnter(1082)/BattleEnter(1085) 无发送点 | REJECTED | 修正后的协议目录确认有发送点（早期扫描脚本 bug） |
| RandomShop 成交价=客户端默认价 | REJECTED | 第三方实测价（金币）与静态默认（光辉）完全不同→服务器定价 |
| AddGold(903) = 加账号金币 | REJECTED | 903 是场内迷宫银币（E_MazeCurrency→Item 1237903） |
| 1501/1526 bundle 之外还需 CDN 补资源 | REJECTED | assets_info 索引闭合、缺失 0（phase2） |
""", encoding="utf-8")

# ---------------- decisions/compatibility ----------------
comp = REPO / "docs" / "decisions" / "compatibility"
comp.mkdir(parents=True, exist_ok=True)
(comp / "gold_dungeon_manual_reward.md").write_text("""---
Document-Type: Compatibility Decision
Domain: Rewards
Status: ACTIVE
Updated: 2026-09-25
---
# Decision
金币资源本（2130101–2130105）手打胜利结算的金币数量 = 各关 MopReward 中扣除普通
VReward 后的独立金币组数量（2078/4678/9356/14552/20788）。

# Reason
官方动态金币公式依赖 IsADC 候选与服务器数据（失传）；影响面仅 5 关；用户明确授权。

# Scope
仅 2130101–2130105；不复制到其他资源本；不执行整个扫荡奖励。

# Official
NO（官方按罐子/金币怪动态计算，公式未恢复）

# User-authorized
YES（2026-09-24）

# Notes
若 outsideItems 已含 1237901，由兼容金币量替代避免重复；1237903 永不入账号。
""", encoding="utf-8")
(comp / "shop_closed_guard.md").write_text("""---
Document-Type: Compatibility Decision
Domain: Shop
Status: ACTIVE
Updated: 2026-09-25
---
# Decision
商店查询/购买/刷新一律明确返回 code 13，不返回成功空列表。

# Reason
官方客户端 ShopModule.OnRefreshShoppingMall 在成功空商品时解引用空集合并崩溃；
错误码分支是安全路径（OnReceiveShopGoodsMsg 0x17A5660 实机依据）。

# Scope
全部 25 店。

# Official
UNKNOWN（官方服务器在停服前的行为不可考）

# User-authorized
YES（NEED.md 记录）
""", encoding="utf-8")
(comp / "sweep_rules.md").write_text("""---
Document-Type: Compatibility Decision
Domain: Rewards
Status: ACTIVE
Updated: 2026-09-25
---
# Decision
扫荡（SecSweep 1027/1028）：要求已通关+充足体力，每次消耗该关 ManualValue，
次数上限 10，只发 MopReward 静态奖，不模拟 DropProp、不读 outsideItems。

# Reason
官方扫荡次数/消耗规则未恢复；MopReward 静态奖是可证实的部分。

# Scope
41 个有 MopReward 的 E_Daily 关。

# Official
PARTIAL（MopReward→RewardData 为官方结构；次数/体力为 Revival 规则）

# User-authorized
YES
""", encoding="utf-8")
(comp / "daily_calendar_beijing.md").write_text("""---
Document-Type: Compatibility Decision
Domain: Tasks
Status: ACTIVE
Updated: 2026-09-25
---
# Decision
日任务北京时间每日 00:00 换期；周任务周一 05:00 换期；首次登录按等级生成；
旧期归档不补发；每小节扣 ManualValue 体力、失败原额退还。

# Reason
TaskControl 的 DailyRefresh/WeeklyRefresh=5 单位未证实；用户明确指定本地规则。

# Official
NO（官方时区/边界不可考）

# User-authorized
YES（2026-09-23）
""", encoding="utf-8")

# ---------------- PATH_MIGRATION.md ----------------
(REPO / "docs" / "PATH_MIGRATION.md").write_text("""# PATH_MIGRATION（2026-09-25 知识库重构）

常用旧路径 → 新路径（完整 69 条见 `analysis/knowledge_reorg/migration_map.csv`）：

| 旧 | 新 |
|---|---|
| docs/runtime_coverage_matrix.md | docs/knowledge/coverage/runtime_coverage.md |
| docs/runtime_backlog.md | docs/knowledge/coverage/runtime_backlog.md |
| docs/battle_variant_coverage.md | docs/knowledge/battle/battle_variant_coverage.md |
| docs/section_reward_system.md / _coverage.md | docs/knowledge/rewards/section_reward_system.md / section_reward_coverage.md |
| docs/drop_algorithm_reverse_engineering.md | docs/knowledge/rewards/drop_algorithm.md |
| docs/reward_semantics_reverse_engineering.md | docs/knowledge/rewards/reward_semantics.md |
| docs/fightitembag_persistence_boundary.md | docs/knowledge/rewards/fightitembag_persistence_boundary.md |
| docs/gift_runtime_semantics.md | docs/knowledge/rewards/gift_runtime_semantics.md |
| docs/special_reward_state_machines.md | docs/knowledge/rewards/special_reward_state_machines.md |
| docs/reward_system_server_fix_plan.md | docs/knowledge/rewards/server_fix_plan.md |
| docs/equipment_instance_generation.md | docs/knowledge/equipment/equipment_instance_generation.md |
| docs/client_economy_data_audit.md | docs/knowledge/economy/client_economy_data_audit.md |
| docs/economy_missing_evidence_followup.md | docs/knowledge/economy/missing_evidence_followup.md |
| docs/client_progression_data_audit.md | docs/knowledge/progression/progression_system.md |
| docs/client_static_table_dictionary.md | docs/knowledge/client/static_table_dictionary.md |
| docs/persistence_relog_audit.md | docs/knowledge/persistence/persistence_relog_audit.md |
| docs/false_complete_audit.md / _elimination.md | docs/knowledge/coverage/ |
| docs/architecture.md | docs/knowledge/architecture/server_architecture.md |
| docs/development.md / network.md / protocol_spec.md / bootstrap*.md / startup_routing.md / gameconfig_resolution.md / reverse_engineering_sources.md / android_toolchain_manifest.md / all_section_battle_recovery.md | docs/knowledge/dev/ |
| docs/adr/ | docs/decisions/adr/ |
| docs/phase*_*.md（各阶段报告） | docs/history/YYYY-MM-DD_NN_* |
| docs/milestones.md / android_lab*.md / first_contact_*.md / mumu_migration.md / daily_dungeon_reward_audit.md / gold_dungeon_drop_clues.md / shop_recovery_from_workbook.md | docs/history/ |
| docs/project_knowledge_index.md | /PROJECT_INDEX.md（本文件同级的仓库根） |
| docs/*_evidence.json | evidence/raw/runtime_traces/ |
| D:/demo/x2/docs/deep_drop_archaeology.md | docs/history/2026-09-24_07_deep_drop_archaeology.md |
| D:/demo/x2/docs/drop_graph_audit.md | docs/history/2026-09-24_08_drop_graph_audit.md |
| D:/demo/x2/docs/dropvalue_code_path.md | docs/history/2026-09-24_09_dropvalue_code_path.md |
| D:/demo/x2/docs/external_dataset_crosscheck.md | docs/history/2026-09-25_02_external_dataset_crosscheck.md |

保持不动（脚本/运行时依赖）：`analysis/**`（canonical 已登记 evidence manifest）、
`src/x2server/data/**`、`analysis/progression/*.json`（EquipmentService 运行时读取）、
仓库外 `D:/demo/x2/{phase2_output,phase3_output,analysis,tools}`。
""", encoding="utf-8")

print("index/governance/history-overlay docs written")
