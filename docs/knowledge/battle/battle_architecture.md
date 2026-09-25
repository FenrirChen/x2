---
Document-Type: Current Knowledge
Domain: Battle
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - docs/history/2026-09-24_03_phase_battle_entry_domain.md
Evidence-IDs: see evidence/manifests/evidence_manifest.json
---

# 战斗架构

- **入场**：`BattleEntryCatalog.resolve`（src/x2server/player/battle_entry.py）按 Section.Type
  分流；当前运行态入口仅 E_Normal(78 线性主线) 与 E_Daily(20/141) 子集。
- **战斗模拟**：客户端权威模拟（帧同步命令 UpdateDropValue/FightItemBag_AddGold/SetDropLimit），
  服务器存 run/收据并在 887 结算校验。
- **结算**：887(内嵌 150) → 152 `L2C_CheckoutMainMission{rewardData…}`；316 FightKillInfo
  在结算后到达（遥测）；264/266 dropValues 语义仍未解（见 known_unknowns）。
- **掉落**：客户端运行时抽 DropProp（服务器不重抽），见 rewards/drop_system.md。
- 类型全集/样本：[section_types.md(section_types.md)（Evidence: SECTION_TYPE_CATALOG）。
