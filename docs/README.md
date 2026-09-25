# docs/ 目录治理（2026-09-25 起生效）

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
