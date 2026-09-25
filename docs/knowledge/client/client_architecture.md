---
Document-Type: Current Knowledge
Domain: Client
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - docs/history/2026-09-22_05_milestones.md
Evidence-IDs: see evidence/manifests/evidence_manifest.json
---

# 客户端架构要点（2.4）

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
