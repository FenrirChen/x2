# Derived Evidence（canonical 索引）

| Evidence ID | canonical 路径（相对仓库根） | 生成器 |
|---|---|---|
| STATIC_DICTIONARY_TABLES / _DOMAINS | `analysis/static_dictionary/` | tools/analysis/build_table_dictionary.py |
| ID_NAMESPACES / REFERENCE_GRAPH / REVERSE_REFERENCE_INDEX | `analysis/static_dictionary/` | tools/analysis/build_reference_graph.py |
| PROTOCOL_CATALOG / UNHANDLED_HIGH_VALUE | `analysis/protocol/` | tools/analysis/build_protocol_catalog.py |
| SQLITE_SCHEMA_CATALOG / STATE_LIFECYCLE | `analysis/persistence/` | tools/analysis/audit_persistence.py |
| SECTION_TYPE_CATALOG | `analysis/battle/` | tools/analysis/build_section_catalog.py |
| HARDCODED_BUSINESS_RULES / RUNTIME_COVERAGE_JSON | `analysis/coverage/` | tools/analysis/audit_hardcodes.py、analysis/coverage/build_runtime_coverage.py、tools/analysis/build_coverage_reaudit.py |
| SECTION_REWARD_CATALOG | `analysis/reward/` | tools/analysis/build_section_reward_catalog.py |
| REWARD_REVERSE_JSON | `analysis/reward_reverse/` | tools/analysis/build_reward_reverse.py |
| DROP_ALGORITHM_EVIDENCE | `analysis/drop_algorithm/` | drop-algorithm 逆向会话（CFG/callers/rng） |
| DROP_GRAPH / DROPVALUE_CROSS_SCAN / CLIENT_FULL_TABLES_2_4 / EXTERNAL_CROSSCHECK | `D:/demo/x2/analysis/drop_archaeology/`、`D:/demo/x2/analysis/external_crosscheck/` | 同目录脚本 |

同一产物只有一个 canonical；历史版本进 `docs/history/` 或 `docs/archive/superseded/`。
重跑生成器不会改变路径。
