---
Document-Type: Current Knowledge
Domain: Rewards
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - (none; still authoritative)
---

# 特殊玩法奖励触发模型

2026-09-25。证据级：A/B/C/D。机器可读：`analysis/reward_reverse/special_reward_consumers.json`、
`special_reward_protocols.json`。发送通道事实来自修正版 protocol_catalog.json。

## 1. 重大纠错（D 级旧判断推翻）

| 字段 | 旧理解 | 本轮定性（A） |
|---|---|---|
| ChallengeReward1 | "挑战独立奖励字段"（127 关） | **Language 文案 key**（21101515="111%月钻掉落奖励\n109%兽主掉落奖励\n掉落1-3★兽主…"），模式=关联 SectionID×10+变体。**不是奖励数据，不可发放** |
| ChestReward/ExpertChestReward | "宝箱 Gift 组" | **E_Chest 宝箱物品 ID**（1203501/1203701 系，101 关各一套，全部存在于 Item 且 ItemType=E_Chest）。奖励=给宝箱物品，开启走物品使用 |

## 2. 按触发模型分类（C3）

### CLAIM_BUTTON（客户端点击领取，C2L→L2C，全部有真实发送点）
| 玩法 | 协议 | 状态机 |
|---|---|---|
| 活跃宝箱 | PickTreasureBox(310) | boxId+type+activityId → 服务器校验阈值 → L2C_PickTreasureBox |
| 塔奖励 | QueryTowerReward(927) → ReceiveTowerReward(929) | 查询榜单/进度 → 领取；Tower 表族为配置 |
| Battlepass | QueryBattlePassInfo(935)/ReceiveBattlePass(941)/SignBattlePass(949)/BuyBattlePassLevel(939)/BattlePassLevelReceiveReward(1059) | 等级/积分状态在服务器；领取幂等由服务器记录 |
| 赛段奖励 | RaceSectionGetReward(1106) | RaceReward 表(100 行)为配置 |
| 收藏 | GetCollectionAward(588){collectionAwardID} | Collection 系统领取 |
| PickChest 翻牌 | FlipPickTreasureBox(1073) | E_PickChest 物品使用 UI |

### AUTO_ON_CLEAR（结算自动，服务器解析）
主线/资源本 FirVReward/VReward → RewardData(152)；扫荡 MopReward → RewardData(1028)。

### ITEM_USE（宝箱物品开启）
ChestReward/ExpertChestReward 给的 1203xxx 物品 → 背包使用 → 服务器解析内容 → 物品/装备下发。
开启协议未在 Send 泛型清单中以独立 C2L 出现（可能走 ItemOpt/UseItem 通道或热更），标 B/C。

### TASK_EVENT（任务条件事件）
E_GetExpertChest(42)（TaskCondition 与 TaskConditionLine 双处定义）——专家宝箱的获取被
任务系统追踪；领取/发放与任务进度联动。

### QUERY_PLUS_CLAIM（WorldBoss 全链，全部 SendBattle）
QueryWorldBossOpenTime(679) → QueryWorldBossInfo(415) → WorldBossSelectHero(701) →
WorldBossAct(417)（伤害参与）→ WorldBossSearch(407)/WorldBossOpenSearchChest(409)（搜索宝箱领取）→
WorldBossLetter(419)/WorldBossQuestSelect(471)。奖励=参与/伤害/搜索宝箱多路，WorldBossInfo 表
含 BossID/MonsterLevel/StageID。伤害排名奖励的精确分配在服务器（表内无分配公式）。

### MoonCamp（月潮）独立通道
SetDropLimit 帧命令唯一创建点 MoonCampModule.SendDropLimit（掉落上限推送进战斗）。

## 3. Activity / Battlepass 与战斗奖励的关系（C9）

**两套系统**：Section.Type=E_ActivityBattle/E_Battlepass 的关卡战斗结算走通用
887→152 链（Fixed Gift/RewardData）；活动进度奖励（ActivityTask/ActivityBoxGoods/
BattlepassLevel 等）走各自的 QUERY+CLAIM 协议族。不得把 Activity 表的 reward 字段
塞进普通 checkout。Battlepass 关卡 (2,400 个 E_Battlepass Section) 的战斗结算本身
与其他 Section 同构，差异在入场凭证与加成（BattlepassEquib 字段等）。

## 4. WeeklyDungeon / DailyDungeon（C10）

普通 Section clear reward（FirVReward/VReward，走 152）与周本里程碑（WeeklyDungeon 表
5 行、EndlessDungeonTask、ChallengeTask）是分开的：后者是**进度型配置**，其触发/领取
协议族在本轮协议目录中未见独立 C2L（WeeklyDungeon 相关请求无枚举项），触发模型
UNKNOWN——不得并入 VReward。

## 5. 协议纪律（C11）

47 个 NO_SEND_POINT_IN_2_4 中奖励相关的只有 150/151/323/217；**MatchEnter(1082)/
BattleEnter(1085) 实际有发送点（修正上轮口径）**。为任何"看起来像奖励"的 enum 写
handler 前，必须先查 protocol_catalog.json 的 send_channels。

## 6. 状态图模板（C12，以塔为例）

```
Trigger: 玩家打开塔奖励页
  ↓ Client state: QueryTowerReward(927) → L2C(928) 榜单/可领列表
  ↓ CLAIM: ReceiveTowerReward(929) → L2C(930)
Server state mutation: 校验条件 → 发奖（RewardData 同构载荷）→ 记录已领
  ↓ L2C/push: 物品/装备入账推送（ItemUpdate/EquipUpdate）
Reward: 最终物品/实例由服务器解析
Persistence: 服务器领取账本；客户端重登由 Query 重建
UNKNOWN: 排名结算周期与服务器算法
```
