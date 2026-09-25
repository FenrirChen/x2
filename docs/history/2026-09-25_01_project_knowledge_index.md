---
Document-Type: Historical Report
Date: 2026-09-25
Status: SUPERSEDED
Superseded-By:
  - /PROJECT_INDEX.md
Known-Corrections:
  - navigation migrated into PROJECT_INDEX.md; per-domain links now live under docs/knowledge/
---

# X2 Revival 项目知识总索引

更新：2026-09-25。供新会话直接定位权威资料。历史阶段报告不在此重复；以本索引指向的当前文档为准。

## 0. 每轮必读

1. 仓库外 `D:\demo\x2\README.md` 与 `D:\demo\x2\SESSION_HANDOFF.md`（当前客户端/存档/服务状态）
2. [runtime_coverage_matrix.md(../knowledge/coverage/runtime_coverage.md)（76 个 feature 的运行态口径）
3. [NEED.md(../../NEED.md)（未恢复证据清单，禁自造数据边界）
4. [runtime_backlog.md(../knowledge/coverage/runtime_backlog.md)（P0–P3 开发顺序）

## 1. 静态表知识库（265 张注册表）

| 资料 | 路径 |
|---|---|
| 表数据字典（字段统计/主键/引用候选/业务域） | `analysis/static_dictionary/tables.json` |
| 业务域分类 | `analysis/static_dictionary/table_domains.json` |
| 人类可读字典摘要 | [client_static_table_dictionary.md(../knowledge/client/static_table_dictionary.md) |
| APK 解码原始记录（249 张全量记录） | `D:\demo\x2\analysis\drop_archaeology\full_tables\` |
| 注册表解析状态（265 张逐张） | `D:\demo\x2\analysis\drop_archaeology\table_registry_extract.json` |
| 重建脚本（可重跑） | `tools/analysis/build_table_dictionary.py` |

无 schema 的 12 张表定性：device/globalparamstring/gmadvanceaccount 有 Manager（非掉落）；
mailinfo 关联 L2C_MailInfo；battlefavorability/battlepassachievementcondition/chatcontrol/
favorabilityidcontrol/herodamagefactor/holidaytask/itemgetandconsume/statisticalinformation
无任何代码引用（NO_CODE_REF）；eventtable 43 条为场景事件显示（field7 引用 NpcEvent/Quest 域）。

## 2. ID / 外键关系图

| 资料 | 路径 |
|---|---|
| Namespace 定义（30 个域） | `analysis/static_dictionary/id_namespaces.json` |
| 表间引用关系（367 CONFIRMED / 267 STRONG / 161 WEAK） | `analysis/static_dictionary/reference_graph.json` |
| 反向引用索引（值 → 引用方） | `analysis/static_dictionary/reverse_reference_index.json` |
| 已证伪关系（REJECTED，勿再猜） | `reference_graph.json` 的 `rejected_relations` |
| 重建脚本 | `tools/analysis/build_reference_graph.py` |

关键命名空间事实：DropClass 1301101–1309250 与 Item 上限 1300105 无交集；
DropValueID 10600000–10660999 与一切表无交集；CurrencyType 900–999 不是 Item。

## 3. 协议目录

| 资料 | 路径 |
|---|---|
| 全量协议目录（395 C2L / 444 L2C / 发送通道 / 服务器注册交叉） | `analysis/protocol/protocol_catalog.json` |
| 高价值未实现请求（按业务域分组，仅含客户端真实会发的） | `analysis/protocol/unhandled_high_value.json` |
| 重建脚本 | `tools/analysis/build_protocol_catalog.py` |

口径：348 个 C2L 有发送实例化点；**47 个 NO_SEND_POINT_IN_2_4**（含 150/151/323/217/
1082/1085 等——实现前先查该清单，不要给客户端不发的消息写 handler）。
服务器已注册 64 个 C2L；61 个 L2C push。

## 4. 假完成 / 硬编码审计

| 资料 | 路径 |
|---|---|
| 审计报告（66 处命中，按分类） | [false_complete_audit.md(../knowledge/coverage/false_complete_audit.md) |
| 机器可读（file:line 全量） | `analysis/coverage/hardcoded_business_rules.json` |
| 重跑脚本 | `tools/analysis/audit_hardcodes.py` |

最高风险：`src/x2server/player/daily_rewards.py:64` 的 `dungeon_id != 2030100` 硬门控；
`progression.py:32/203` 的 `hero["id"] == 1003` 限制；`economy.py:415` 的 main_section 默认值。

## 5. 持久化 / 重登

| 资料 | 路径 |
|---|---|
| 24 张表 schema 目录 | `analysis/persistence/sqlite_schema_catalog.json` |
| 状态生命周期（写入链/事务/幂等/重登/推送） | `analysis/persistence/state_lifecycle.json` |
| 审计报告 | [persistence_relog_audit.md(../knowledge/persistence/persistence_relog_audit.md) |
| 重跑脚本 | `tools/analysis/audit_persistence.py` |

players.snapshot 是账号状态主体，登录全量回送（login.py snapshot_push）；
5 张表 PERSISTED_NOT_RESTORED（多为账本类：economy_checkouts/pending_rewards 等）。

## 6. 战斗变体

| 资料 | 路径 |
|---|---|
| 24 种 SectionType 全量目录（代表样本/支撑表/服务器支持） | `analysis/battle/section_type_catalog.json` |
| 覆盖报告 | [battle_variant_coverage.md(../knowledge/battle/battle_variant_coverage.md) |
| 重跑脚本 | `tools/analysis/build_section_catalog.py` |

E_Battlepass 2,400 个 Section 为最大未实现类型；运行态入口仅 E_Normal/E_Daily 受限子集。

## 7. Coverage 与静态数据重审

| 资料 | 路径 |
|---|---|
| Coverage 矩阵（含 2026-09-25 重审增补节） | [runtime_coverage_matrix.md(../knowledge/coverage/runtime_coverage.md) |
| 静态重审明细（69 个 feature 注记） | [runtime_coverage_static_reaudit.md(../knowledge/coverage/runtime_coverage_static_reaudit.md) |
| 机器可读（`static_data_status_v2`/`static_data_reaudit` 节） | `analysis/coverage/runtime_coverage.json` |
| 重跑脚本 | `tools/analysis/build_coverage_reaudit.py` |

## 8. 掉落数据考古（前轮结论，A 级）

| 资料 | 路径 |
|---|---|
| 最终报告（13 问） | `D:\demo\x2\docs\deep_drop_archaeology.md` |
| DropProp 闭包 / DropValue 代码路径 | `D:\demo\x2\docs\drop_graph_audit.md`、`D:\demo\x2\docs\dropvalue_code_path.md` |
| drop_graph / dropvalue_hits / namespace | `D:\demo\x2\analysis\drop_archaeology\` |

## 9. 奖励语义逆向（2026-09-25 轮）

| 资料 | 路径 |
|---|---|
| 五层奖励体系总图 + Server 审查 + 20 问 | [reward_semantics_reverse_engineering.md(../knowledge/rewards/reward_semantics.md) |
| FightItemBag 持久化边界（outsideItems/eNum 规则） | [fightitembag_persistence_boundary.md(../knowledge/rewards/fightitembag_persistence_boundary.md) |
| Gift 运行时语义（发放=服务器；客户端解析器孤立） | [gift_runtime_semantics.md(../knowledge/rewards/gift_runtime_semantics.md) |
| 兽主实例生成链（服务器 roll/交付差距） | [equipment_instance_generation.md(../knowledge/equipment/equipment_instance_generation.md) |
| 特殊玩法触发模型（Chest=物品/ChallengeReward1=文案） | [special_reward_state_machines.md(../knowledge/rewards/special_reward_state_machines.md) |
| Server 修复方案（FIX-1..7，只方案不实施） | [reward_system_server_fix_plan.md(../knowledge/rewards/server_fix_plan.md) |
| 证据 JSON ×8 | `analysis/reward_reverse/`（脚本 tools/analysis/build_reward_reverse.py） |
| 掉落算法（前轮） | [drop_algorithm_reverse_engineering.md(../knowledge/rewards/drop_algorithm.md) + section_reward_system/coverage |

## 10. 测试

- 全量 `python -m pytest tests/` = **204 passed**（本轮新增 `tests/unit/test_audit_hardening.py` 5 项：
  全库级"拒绝操作零变更"、强化精确扣费与 15 级终止、DoEquip 重放幂等、重启恢复、未知装备零建行）。
- 幂等重点已有覆盖：重复结算（test_battle/task/daily）、抽卡重放（test_wish）、
  商店无效购买不扣费（test_shop）、收据失败回滚（test_economy/test_phase20）。
- 规则：隔离 SQLite（tmp_path/`env` fixture）；不为过测改业务；未实现行为记
  KNOWN_FAILING_BEHAVIOR 而非造假成功。

## 10. 常用工具速查

| 用途 | 命令 |
|---|---|
| 解析一张表（canonical 解析器） | `python phase3_output/phase3_parsers/x2_table_parser.py <bin>`（X2 根） |
| 反汇编一个方法 | `python x2_revive_workspace/analysis/economy/static_xrefs.py Class.method`（X2 根） |
| 方法调用者反查 | `python D:\demo\x2\analysis\drop_archaeology\find_callers.py 0xRVA` |
| 重建静态字典/引用图/协议目录 | `python tools/analysis/build_table_dictionary.py` 等（本仓库） |
| 服务器 | `tools/local_game_server.py`（勿动活跃库 runtime/phase14/player.sqlite3） |
