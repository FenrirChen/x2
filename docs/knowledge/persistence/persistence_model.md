---
Document-Type: Current Knowledge
Domain: Persistence
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - docs/history/2026-09-25_00_persistence_relog_audit.md
Evidence-IDs: see evidence/manifests/evidence_manifest.json
---

# 持久化模型

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
  审计：[persistence_relog_audit.md(persistence_relog_audit.md)。
活跃库=runtime/phase14/player.sqlite3，禁覆盖。
