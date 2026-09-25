# 知识库重构盘点（2026-09-25）

机器可读全量清单：`analysis/knowledge_reorg/current_file_inventory.json`（932 文件，
分类 A-J）；迁移明细：`analysis/knowledge_reorg/migration_map.csv`（69 条）。

| 分类 | 数量 | 去向 |
|---|---:|---|
| CURRENT_KNOWLEDGE（docs） | 32 | docs/knowledge/<domain>/（git mv+元数据头）；adr→docs/decisions/adr |
| HISTORICAL_REPORT | 33+4 | docs/history/YYYY-MM-DD_NN_topic.md（含根目录 4 篇迁入） |
| RAW_EVIDENCE（docs json） | 4 | evidence/raw/runtime_traces/ |
| DERIVED_EVIDENCE（analysis/） | 58 | **原地保留**，canonical 登记 evidence manifest |
| TOOLING / TOOLING_CODE | 44/58 | 原地（生成器输出路径已更新） |
| RUNTIME_DATA | 628 | runtime/（活跃库禁动） |
| TEST_ARTIFACT | 48 | 原地 |
| EXTERNAL | 1 | evidence/external/third_party/（隔离副本+哈希） |

大文件策略：APK/libil2cpp.so/global-metadata.dat/解包目录保留原位（仓库外 D:/demo/x2/...），
由 `evidence/manifests/evidence_manifest.json` 以 Evidence ID 登记（32 条，含 SHA256）。
