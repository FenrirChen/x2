---
Document-Type: Compatibility Decision
Domain: Equipment / Reward
Status: ACTIVE
Updated: 2026-09-26
---
# Decision
E_ReportCurrency（FunctionEff=14）代理道具在结算时折算为账户货币：

- `RuntimeDropResolver` 识别 outsideItems 中 FunctionEff=14 的 Item；
- 折算：账户货币 Item = `EffData[0]` 对应的 E_Currency 账户物品（表派生映射，见
  `src/x2server/data/report_currency_map.json`，68/68 全覆盖）；
  数量 = `EffData[1] × outsideItem.num`；
- 同一账户货币的多个代理合并为一条 grant（source=REPORT_CURRENCY）；
- 原代理 Item 不进入 inventory / rewardItem（结算页不再出现无名空白贴图）；
- 无法解析 EffData / 账户货币的代理：parked（UNRESOLVED_REPORT_CURRENCY）+ 遥测，禁止猜测。

# Reason
官方 Item 表证据（A）：该族 68 个道具全部 E_Gift、36 个 Icon=""、NameID 无 Language 条目、
FunctionEff=E_ReportCurrency、EffData=[货币桶, 单件价值]（如 1101076=[901,28]、
1101060=[912,10]）——设计上就是"结算上报折算"的战斗内货币代理。
桶→账户物品映射为官方表派生（901→1237901 金币、912→1237912 月钻、913→1237913 光能等，
全部 8 桶验证）。

# Scope
仅战斗掉落（887.outsideItems）路径；Gift/邮件/商店发放同族道具的场景接入时复用
同一 resolver（本轮未接）。

# Official
结算折算的**存在**为强 B（官方表语义 + 官方服从未下发原物品的设计意图）；
**折算公式（EffData[1] × num）** 为 Revival 解释——官方样本失传。

# User-authorized
YES（USER_DECISION，2026-09-26）

# Notes
- 与金币本手打 MopReward 兼容金互斥：旧兼容金已删除（SUPERSEDED），
  金币本手打收入 = 折算金；扫荡仍走 MopReward；
- 若未来获得官方折算样本（如折算金 = ItemValue×28×num 的官方确认），替换常数需新决策。
