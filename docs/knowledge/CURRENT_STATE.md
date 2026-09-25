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

- **可运行**：登录/大厅/物品/英雄(1003)/装备测试实例/魂器基础/技能/抽卡/固定奖励结算/
  主线 78 关 + 资源本 20 关/扫荡(41 关静态)/日周任务/聊天空频道。
- **测试**：226 passed（隔离 SQLite）。
- **已恢复领域**：见 knowledge/ 各域文档；运行态口径：coverage/runtime_coverage.md。
- **主要 PARTIAL**：Battle Entry 扩展类型、DailyDungeon 剩余变体、装备实例交付、Mission 真进度。
- **主要 known unknowns**：coverage/known_unknowns.md（10 项）。
- **兼容决策**：docs/decisions/compatibility/。
- **下一步推荐**：reward_system_server_fix_plan.md 的 FIX-1/2/3。
- **禁改**：Reference APK、活跃 SQLite（runtime/phase14/player.sqlite3）、已有备份。
