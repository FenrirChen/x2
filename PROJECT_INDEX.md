# READ THIS FIRST — X2 Revival 项目知识索引

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
