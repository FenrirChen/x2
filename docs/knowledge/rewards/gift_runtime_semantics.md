---
Document-Type: Current Knowledge
Domain: Rewards
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - (none; still authoritative)
---

# Gift 运行时语义（发放者到底是谁）

2026-09-25。证据级：A/B/C/D。机器可读：`analysis/reward_reverse/gift_consumers.json`、
`gift_random_algorithm.json`。

## 1. 结构

`Example.Gift { GiftGroup, AwardType, Probability[], GiftValue[], Num[], GiftShow[], ItemNum, EquibNum }`；
`GiftEAwardType = {E_None=0, E_material=1, E_Random=2, E_RandomInterval=3, E_Pick=4, E_BlindBox=5}`。

## 2. 客户端确实存在原生随机 Gift 解析器（A）

`LogicX2.GlobalFun.GetItemByGiftGroup(Random mRandom, int group)`（0x18D26FC）全量反汇编：

```csharp
Gift g = GiftManager.Instance.GetItem(group);
if (g.AwardType == E_material) return g.GiftValue;              // 固定：整表直出
var result = new List<int>();
int idx = GlobalFun.GetProbability(mRandom, g.Probability);     // 单次加权抽取
result.Add(g.GiftValue[idx]);
return result;
```

- 使用的 `GetProbability`（0x18D2880）与掉落算法同一原语：**先求权重和再 Range(0,sum) 逐项扣除**，
  因此**不要求 ΣProbability=100**——任意正权重即可。
- `GetItemNumByGiftGroup(Random, group)` 返回 `List<int[]>`（item,num 对），Num 维度本轮未逐指令展开（B）。
- **该解析器在 2.4 原生代码中 0 个直接 BL 调用者**。结合 Phase2 结论（ILRuntime 热更 DLL 未随包），
  最合理解释：业务层调用位于缺失的热更程序集；或经委托间接调用。不能证明 2.4 运行时实际执行它。

## 3. 发放路径：服务器执行（A，协议层闭环）

| 路径 | 证据 |
|---|---|
| 战斗结算 | `L2C_CheckoutMainMission(152).rewardData`：`RewardData{rewardItem[itemId,itemNum,transform], rewardEquip[List<HeroEquip>], transformHero[heroId,transform]}` —— **服务器解析后的最终结果** |
| 扫荡 | `C2L_SecSweep{sectionId,sweepCount}` → `L2C_SecSweep{code,sectionId,sweepCount,rewardData}` —— 服务器返回最终物品 |
| 邮件/礼包领取 | MailModule.ReceiveAttachment 等同为服务器下发 |

客户端结算 UI 从不本地 roll Gift：checkout/扫荡路径对 GiftManager 的调用数为 **0**。

## 4. GiftManager 的 33 个调用点全是展示（A）

任务奖励节点（AcceptTaskNode/MoonTaskNode/RespondersItemNode.InitRewardNode）、成就 UI、
邮件附件预览、礼包详情预览、GameAPI.GetItemNumByGiftID/GetShowItemNumByGiftID 等。
账户 buff 的 Gift 链（GodSoonModule.GetAllSectionDropItemByAllBuff → BuffInfo.DropItemByBuff）
终点是 `ChapterInfoView/AnniversaryTowerSectionView/BattlePassTab.ShowDropItem` ——
**关卡详情页"buff 加成后掉落预览"**，非发放。

## 5. FirVReward / VReward / MopReward 分别定性

| 字段 | 定性 | 证据 |
|---|---|---|
| FirVReward / VReward | 服务器结算输入 + 客户端 UI 预览数据；发放走 RewardData | 协议层 A；字段偏移级 xref 因 GetItem 内联未逐一定位（B） |
| MopReward | 服务器扫荡解析输入；客户端只显示过程与结果 | L2C_SecSweep.rewardData（A） |
| ChestReward/ExpertChestReward | **E_Chest 宝箱物品 ID**（1203501/1203701 系），不是 Gift 组 | 全部值存在于 Item 且 ItemType=E_Chest（A） |
| ChallengeReward1 | **Language 文案 key**（如 21101515="111%月钻掉落奖励…"），**不是奖励** | 值域出现在 Language 表；模式=关联 SectionID×10+变体（A） |

## 6. 最终定性（A10）

| Gift 用途 | 分类 |
|---|---|
| 结算/扫荡/邮件发放 | **SERVER_EXECUTED** |
| UI 奖励预览（任务/成就/礼包/关卡详情） | **UI_PREVIEW_ONLY** |
| 原生随机解析器 GetItemByGiftGroup | 存在但孤立（疑似热更调用对象）；算法=单次加权抽取，**无 Σ=100 约束** |

**对当前 Revival 的判定**：根据 Gift 表发奖属于 **B——"利用客户端静态配置构造的兼容实现"，
且该实现是在重建官方服务器的行为**（官方服务器同样读这些表），不是"客户端本来会执行的逻辑"。
但当前实现附加的"仅 ΣProbability=100 的组可执行"约束与客户端算法证据**冲突**：
GetProbability 按权重和归一化，任意正权重都合法。该约束把 34 个 Section 误标为不可执行，
属于 **POTENTIALLY_WRONG**，应改为"按权重和归一化、单次抽取"（与 GetDropItemByGroup 同构），
并保留对 AwardType=E_Pick/E_BlindBox 的特殊语义审慎（其交互语义未恢复）。
