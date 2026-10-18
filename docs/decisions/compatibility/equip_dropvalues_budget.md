---
Document-Type: Compatibility Decision
Domain: Equipment / Drop
Status: ACTIVE（2026-09-26 起改为 LOW/MID/HIGH 分级预算；旧 27×1,000,000 策略已废弃）
Updated: 2026-09-26
---
# Decision
2026-10-10更新（已批准）：兽主第5组的适用关卡改用100%=3000，官方每关倍率优先，无倍率现世复刻/新血月使用兼容曲线，战令保持原值；其他26组仍使用下述分档。当前执行规则见[兽主预算倍率](beastlord_budget_scaling_20261010.md)。264刷新使用本场入场持久化的预算，不随配置修改重新给予额度。

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

## 2026-10-10 剧情组补充（当前规则）

用户批准独立修复 PR12：新开战斗的 dropValues 增至28项，下标27固定3000；
0–26组沿用已批准规则，其中兽主组5以100%=3000按关卡比例计算，战令原有组预算不变。
第27组包含12件剧情道具、1件剧情礼物与12件旧活动道具；剧情/礼物价值均为1。
3000足够剧情拾取，价值9999的旧活动道具仍受限制。

130入场与266刷新共享同一份冻结值；已保存的27组历史战斗仍原样返回，
不会在刷新或重启时追加额度。重新进入战斗取得28组新预算。
实现与证据见 [PR整合记录](../pr13_18_integration_20261010.md)。

## 2026-10-18 元素晶体组补充（当前规则）

用户批准独立修复：新开战斗的 dropValues 增至29项，下标28固定3000；
0–27组完全沿用前两条规则（兽主组5按关卡比例、剧情组27固定3000）。

第28组是四色元素晶体（1103006/1103007/1103008/1103009），也是官方 Item 表里
AddADCGroup 的最大值（全表再无更高组）。四件晶体均为 E_Maze（ItemUseScence 缺省=0），
只存在于战斗内、不会进入账号背包，元素合成在局内由 495 带 missionID+layer 提交；
ItemValue 为12，3000 约等于一局250枚的宽松上限。

官方 SectionTable 中 DroopLimit2 含 28 的关卡恰好只有元素之章那8关
（2110191-94 起源 / 2110291-94 白夜，Type 7），其 DroopLimit2 为
[0,2,3..19,22,28]。`JudgeDropItem` 在 `dropValues.Count <= AddADCGroup` 时拒绝
整组掉落，因此原先只覆盖到组27的预算会让这四件晶体在部分路径上被迫拒绝。

130入场与266刷新共享同一份冻结值；此前保存的27组与28组历史战斗仍原样返回，
不会在刷新或重启时补额度（266 的长度白名单同时接受 27/28/29）。重新进入战斗
取得29组新预算。版本后缀更新为 `:story-28-element-crystal-v1`。
行证据：`analysis/equipment/element_crystal_group_20261018.json`，记录源导出
SHA256、四件晶体的 ItemID/ItemValue/AddADCGroup/类型/使用场景，以及含组28的8个关卡。
