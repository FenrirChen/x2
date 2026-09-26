---
Document-Type: Compatibility Decision
Domain: Equipment / Drop
Status: ACTIVE（2026-09-26 起改为 LOW/MID/HIGH 分级预算；旧 27×1,000,000 策略已废弃）
Updated: 2026-09-26
---
# Decision
战斗掉落预算（两个载体：L2C_FightData 130 的 FightData.dropData、
L2C_FightDropData 266 应答）按官方 SectionTable.DifficultyLevel 分三档：

- DifficultyLevel 1-3 → **LOW：每组 1000**
- DifficultyLevel 4-6 → **MID：每组 3000**
- DifficultyLevel 7+ → **HIGH：每组 5000**
- 无难度/未知关卡 → **MID（默认）** + 遥测记录
- 覆盖全部 27 组（AddADCGroup 0..26）；实现：src/x2server/player/drop_budget.py
  （DropBudgetCompatibilityPolicy，集中配置，无按 Section 散布）

旧策略（2026-09-25：27 组全部 1,000,000，等效不限量）已废弃——它使金币本等
资源本的官方"货币代理物"产出失去经济节流。

# Reason
官方证据链（ARM64 A 级）：**主通道** = 客户端 264 C2L_FightDropData 上报 →
服务器 266 L2C_FightDropData{result,data=FightDropData{dropValues,missionId}} →
`FightModule.OnFightDropData(0x1447E1C)` 反序列化 data 并以
`LogicX2Command.UpdateDropValue` 经 `LogicBattle.OnInput(0x1448224)` 更新预算。
**次通道** = 130 入场响应 `FightData.dropData` → `BattleInfo.SetSceneInfo(0x19A25B4)`
AddRange 进 `BattleInfo.dropValues(+0xC0)`。`JudgeDropItem(0x1E49838)` 以
`dropValues[AddADCGroup]` 为组预算，`Count <= addADCGroup` 时拒绝全部 ItemStruct
掉落（装备 AddADCGroup=5）。Revival 此前 264 应答 dropValues 恒空（注释明示
'no server drops'）→ 预算恒空 → 客户端本地掉落全灭 → 887.outsideItems 恒空
（2026-09-25 实机 2133101 兽主本两次复现）。
每组官方预算值不可考（known unknowns #2 残留），须取一个值才能启用官方管线。

# Scope
仅 dropData.dropValues 预算数值；管线本身（SetSceneInfo/JudgeDropItem/
IdentifyItem/DroopLimit3）均为官方行为。

# Official
NO（官方每组预算值未知；27 组与 1,000,000 为 Revival 自定）

# User-authorized
YES（USER_DECISION，2026-09-25）

# Notes
- 预算放宽不会凭空生成掉落：掉什么仍由客户端 DropProp/ADC 权重与
  Section.DroopLimit/DroopLimit3 决定；
- 若未来获得官方预算样本，按新 USER_DECISION 替换常数
  （src/x2server/player/battle.py REVIVAL_DROP_BUDGET_PER_GROUP）。
- 官方预算的配置键结构已破解：DropValueID = 10600000 + SectionID%100000
  （310/341 命中，85 组共享），但配置数值随官方服务器数据失传（2026-09-26）。
