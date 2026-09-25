---
Document-Type: Current Knowledge
Domain: Protocol
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - docs/history/2026-09-25_01_project_knowledge_index.md
Evidence-IDs: see evidence/manifests/evidence_manifest.json
---

# 协议总览

- 枚举 `ERequestTypes`：**395 个 C2L / 444 个 L2C**（921 个 ID）。
- **348 个 C2L 有真实发送实例化点**；**47 个 NO_SEND_POINT_IN_2_4**（含 150/151/323/217 等）
  —— 给枚举写 handler 前必须查 `analysis/protocol/protocol_catalog.json` 的
  `client_status/send_channels`（Evidence: PROTOCOL_CATALOG）。
- 服务器已注册 64 个 C2L；61 个 L2C push。
- 战斗通道（SendBattle）专用消息：FightData/CheckoutSign/FightKillInfo/FightDropData/
  CheckFightProfile 等；商店/任务/活动走普通 Send。
- 887 `C2L_CheckoutMainMissionSign` 内嵌完整 150 `C2L_CheckoutMainMission` 载荷
  （checkout 字段 + battleFile），150 从不裸发。
- 消息字段结构查询：[message_catalog_guide.md(message_catalog_guide.md)。
