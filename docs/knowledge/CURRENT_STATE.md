---
Document-Type: Current Knowledge
Domain: Coverage
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - (none)
Evidence-IDs: see evidence/manifests/evidence_manifest.json
---

# 当前状态快照（2026-09-25）

- **可运行**：登录/大厅/物品/英雄(1003)/装备测试实例/**装备实例真交付(887→Factory→落库→152.rewardEquip)/**
  魂器基础/技能/抽卡/固定奖励结算/主线 78 关 + 资源本 20 关/扫荡(41 关静态)/日周任务/聊天空频道。
- **测试**：266 passed（隔离 SQLite；含装备掉落交付、ReportCurrency 折算、分级预算）。
- **已恢复领域**：见 knowledge/ 各域文档；运行态口径：coverage/runtime_coverage.md。
- **主要 PARTIAL**：Battle Entry 扩展类型、DailyDungeon 剩余变体、Mission 真进度。
- **掉落经济**：E_ReportCurrency 代理物结算折算已实施（金币本实机空白贴图已修）；dropValues 预算改为 DifficultyLevel 分级 LOW/MID/HIGH=1000/3000/5000（REVIVAL_COMPAT）。
- **兽主本结算 blocker 修复待实机复测（2026-09-26）**：2133101 的 887 含 1101060×90 时，resolver 已折算为 1237912×900，但 `_grant` 缺少非 BaseInfo 货币落账路径，导致 result=13；现按官方 E_Currency Item 把这类账户货币记入 item ledger，并保持代理物不入包。隔离库回归覆盖 68 个代理物和 8 个货币桶；实机 152/客户端表现仍待复测。
- **主要 known unknowns**：coverage/known_unknowns.md（10 项）。
- **兼容决策**：docs/decisions/compatibility/。
- **下一步推荐**：reward_system_server_fix_plan.md 的 FIX-1/2/3。
- **禁改**：Reference APK、活跃 SQLite（runtime/phase14/player.sqlite3）、已有备份。
