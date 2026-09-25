---
Document-Type: Current Knowledge
Domain: Rewards
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - (none; still authoritative)
---

# Section 奖励与结算系统（开发版）

更新：2026-09-25。本轮只修改开发工作区；没有改 APK、分发目录或活跃 SQLite。基线 `216 passed`。数据根是官方 2.4 `SectionTable` 3203 行、`Gift`、`Item`、`DailyDungeon`、`ExtraDroop`；生成脚本为 `tools/analysis/build_section_reward_catalog.py`。

## 来源与顺序

| 来源 | 输入 | 当前处理 |
|---|---|---|
| `FIRST_CLEAR_FIXED` | `Section.FirVReward → Gift → Item` | 成功首通且事务内未见通关记录时入账；重复 887 使用原收据 |
| `NORMAL_CLEAR_FIXED` | `Section.VReward → Gift → Item` | 每次有效手打成功结算 |
| `RUNTIME_BATTLE_DROP` | 客户端 `FightItemBag → checkout.outsideItems` | 887 内嵌 ItemDataP 的 id/num/quality/eNum；逐项验证后入账或记待发；服务端不再重抽 DropProp |
| `SWEEP_REWARD` | `Section.MopReward → Gift → Item` | 1027/1028 `SecSweep` 独立请求，要求已通关、足够体力；只使用 MopReward |
| `EXTRA_DROP` | `ExtraDroop` | 仅分类/保留，触发与数量规则尚未证实，暂不自动给付 |
| `COMPAT_GOLD_DUNGEON` | 该金币资源关自己的扫荡 Gift | 用户授权的唯一手打兼容：五个金币关分别取各自扫荡金币数量 |
| `UNRESOLVED_SERVER_DATA` | `DropValueID` 等 | 记录在未解账本；不编造服务端映射、概率或奖励 |

`DroopDisplay` 只保留作界面与审计资料。旧的“单个预览物品 ×1”代码已从结算路径删除，其他资源本不会套用金币策略。金币关手打若 `outsideItems` 已含账号金币 `1237901`，该项由兼容金币量替代，避免重复；其他客户端实际物品继续处理。`1237903` 属场内银币，不可当作账号金币入账。

`C2L_CheckoutMainMissionSign` 的内嵌 schema 现解析字段 3 `outsideItems`，`ItemDataP` 解析字段 1–4；同时解析字段 22 `killMonster`、30 `npcEventOnNumber`。原始 checkout 字节和未知顶层字段号存于 `battle_checkout_wire`，便于之后追真实请求。结算先验证有效未结 run、Section 与成功标志；拒绝未知 Item、非正/超界数量、场内物品及失败战斗带出物品。静态 Section→实际刷怪/事件闭包尚不完整，目录标 `DYNAMIC_ALLOWED` 并留审计记录，避免拒绝真实客户端的 ADC/动态结果；提供 DropClass 嵌套闭包函数，只有未来证明某 Section 根组完整时才可升级为 `STRICT_STATIC`。

统一来源记录为 `RewardGrant`，可交付物品汇总后走现有事务型 `_grant`：账号货币进入快照、可堆叠道具进入 `inventory`，结算与收据同一 SQLite 事务；`PlayerData`、`ItemUpdate`、任务更新在回包后推送。装备/其他非堆叠结果不写普通背包：原始品质与 `eNum` 存 `pending_reward_instances`，回执不宣称已交付，也不发送虚假 `EquipUpdate`。固定 Gift 中目标未解的物品沿用 `pending_rewards`。每次手打或扫荡写 `reward_settlement_audit`，按来源留清单与阻塞原因；`economy_grants`、`battle_receipts` 和 `sweep_receipts` 防止相同请求重复给付。

失败战斗不发首通、普通或 runtime 奖励，并沿用已有体力退款。放弃旧 run 由下一次入场的既有替换逻辑处理；本轮没有重做断线续战。扫荡需要已通关、有 `MopReward` 和已知 `ManualValue`；每次扫荡消耗该关手打体力值，次数上限 10 是 Revival 本地边界，非声称官方次数规则。扫荡不读取 `outsideItems`，也不模拟 DropProp。

## 已知限制

- `Section.DropValueID → 264/266 dropValues` 无可恢复服务端映射，仍不可生成官方服务器运行时奖励。客户端本局真实 `outsideItems` 则可以结算。
- `IsADC` 和事件源依赖战斗上下文；当前逐 Section 严格白名单为未证实，目录用 `DYNAMIC_ALLOWED`。若将来补齐地图、房间、刷怪与 NpcEvent 闭包，再按组启用严格校验。
- `ExtraDroop`、关卡宝箱/挑战专属奖励仅登记数据源，触发条件未恢复，不能自动发放。
- 装备实例生成所需完整参数/品质规则尚未证实；待发账本不是已交付资产。
- `Gift.E_Random` 仅现有可核实概率和为 100 的组可执行；其余组明确记未解，不强行归一化。
- Battle Entry 的类型覆盖与奖励目录分开：目录覆盖 24 类、3203 关，不表示这些类型都可进入。实机结算刷新仍需用户后续在客户端复核。
