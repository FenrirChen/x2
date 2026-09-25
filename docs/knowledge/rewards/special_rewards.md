---
Document-Type: Current Knowledge
Domain: Rewards
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - docs/history/2026-09-25_05_special_reward_state_machines.md
Evidence-IDs: see evidence/manifests/evidence_manifest.json
---

# 特殊玩法奖励（触发模型）

**字段定性纠错（A 级）**：
- `ChallengeReward1` = **Language 文案 key**（如 21101515="111%月钻掉落奖励…"）——不是奖励。
- `ChestReward`/`ExpertChestReward` = **E_Chest 宝箱物品 ID**（1203501/1203701 系，101 关）
  —— 奖励=给宝箱物品，开启走物品使用（服务器解析）。

**触发模型**（发送通道事实来自 PROTOCOL_CATALOG）：
| 模型 | 玩法 | 协议 |
|---|---|---|
| CLAIM_BUTTON | 活跃宝箱 / 塔 / Battlepass / 赛段 / 收藏 / PickChest 翻牌 | 310, 927+929, 935/941/949/939/1059, 1106, 588, 1073 |
| AUTO_ON_CLEAR | 主线/资源本结算、扫荡 | 152 / 1028 RewardData |
| ITEM_USE | Chest 物品开启 | 未在 Send 泛型清单独立出现（B/C） |
| TASK_EVENT | E_GetExpertChest(42) | 任务条件系统 |
| QUERY_PLUS_CLAIM | WorldBoss 全链 | 679/415/701/417/407/409/419/471 |
| UNKNOWN | WeeklyDungeon 里程碑 | 无独立枚举项 |

Activity/Battlepass 与战斗结算是**两套系统**：E_ActivityBattle/E_Battlepass 关卡的战斗结算
仍走 887→152，活动进度奖励走各自协议族。
状态图：[special_reward_state_machines.md(special_reward_state_machines.md)。
