---
Document-Type: Current Knowledge
Domain: Rewards
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - docs/history/2026-09-24_07_deep_drop_archaeology.md
  - docs/history/2026-09-25_02_external_dataset_crosscheck.md
Evidence-IDs: see evidence/manifests/evidence_manifest.json
---

# 奖励体系（五层权威模型）

| 层 | 内容 | 计算 | 随机 | 保存 | 发奖 |
|---|---|---|---|---|---|
| 1 ROGUELITE_LOCAL_STATE | 场内银币(903)/神迹/塔道具/Buff/mazeItems | 客户端 | 客户端(战斗RNG) | 内存 | 无（仅遥测） |
| 2 BATTLE_PERSISTENT_DROP | Unit.DC→DropProp→FightItemBag(source=FIGHT)→887.outsideItems | 客户端 | 客户端 | 战斗包 | 服务器入账 |
| 3 SECTION_SETTLEMENT_REWARD | FirVReward/VReward/MopReward→Gift→**RewardData** | 服务器 | 服务器 | 服务器 | 服务器 |
| 4 SPECIAL_GAME_MODE_REWARD | Chest(物品)/Tower/Battlepass/WorldBoss/Race/Collection/活跃宝箱 | 服务器 | 服务器 | 服务器 | CLAIM_BUTTON/AUTO 混合 |
| 5 ACCOUNT_INSTANCE_REWARD | HeroEquip 整装（Id/Star/Param 全服务器） | 服务器 | 服务器 | 服务器 | RewardData.rewardEquip |

关键判定（全部有原生证据，详见子文档）：
- 层2→层1 的过滤：`source==FIGHT ∧ ItemUseScence==E_Outside`（outsideItems）；
  eNum 仅迷宫物品填写获取计数。
- 层3 的客户端解析器（GetItemByGiftGroup）存在但孤立；发放永远是服务器 RewardData。
- 层5 客户端零生成——HeroEquip 整只从 wire 反序列化。

子文档：[drop_system.md(drop_system.md) · [gift_system.md(gift_system.md) ·
[special_rewards.md(special_rewards.md) · [section_reward_system.md(section_reward_system.md) ·
[server_fix_plan.md(server_fix_plan.md)。
详细逆向过程记录：[reward_semantics.md(reward_semantics.md)（历史级证据链）。
