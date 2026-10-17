---
Document-Type: Compatibility Decision
Domain: Shop / Gift Package
Status: ACTIVE
Updated: 2026-10-17
---
# Decision
修 `E_FreeDaily` 礼包的每日领取口径。客户端 GiftPackage 2700000（商店"礼包"页
的"日常补给·第 7 次领纯晶石"）为 `GiftPackageType=E_FreeDaily`、`Param1=[7]`、
`Param2=[781005]`、`Times=1`、`GiftID=[781004]`。

服务端不再拿**终身累计领取次数**去比这张表的 `Times`，改为：

- 每日一次的上限由 `_period()` 生成的按天 key（`YYYY-MM-DD`）保证；
- `L2C_QueryGiftPackage` 的 `PurchaseTime` 下发**跨天累计领取次数**（就是
  `gift_package_claims` 里该包的行数），供客户端的进度条使用；
- 跨天累计次数到达 `Param1[0]` 的整数倍的那一次领取，发 `Param2`（gift 781005
  = 纯晶石 1237925）而不是日常的 `GiftID`（781004）。

# Reason
客户端 GiftBoxTab_GiftBoxNode_SetData 对 `GiftPackageType=2` 的格子按
`领取进度：{PurchaseTime % Param1[0]}/{Param1[0]}`（语言键 13100855）渲染。
上游 `listing()` 与 `_claim()` 都用 `_bought_count()`（终身累计行数）去比
`Times=1`：第一天领完后 `bought=1 >= limit=1`，该包被永久判为售罄——客户端
显示"已领取"，`PurchaseTime` 恒为 1，进度条永远停在 `1/7`，且第 7 档奖励
`Param2` 从不发放。

只有 2700000 受影响：`Times=1` 的其余礼包（2700002–2700033，`GiftPackageType=3`
等级礼包链）是**正确的终身限购**，2700001 月卡 `Times` 缺省为 0，均保持原路径。

# Scope
- `src/x2server/player/gift_packages.py`：`_free_daily()` / `_free_daily_cycle()`
  / `_reward_groups()` 三个小助手；`listing()` 的 free-daily 分支；`_claim()`
  的限购守卫加 `not free-daily`；`_rewards()` 接受可选 gift 组。
- `src/x2server/data/selected_gift_packages.json`：补 781005 这一行
  （`AwardType=E_material`、`GiftValue=[1237925]`、`Num=[1]`），上游此前缺失，
  不补则第 7 档奖励解析失败。781004 行不动。
- 奖励概率（gift 781004 的 `AwardType=2`、权重和 1000）与客户端 Gift 表一致，
  不在本次改动范围内。

# Official
YES（修复目标是让服务端与官方客户端 GiftPackage/Gift 表语义一致：`Times=1` 对
free-daily 包表示"每天一次"，进度条读累计天数）

# User-authorized
YES（USER_DECISION，2026-10-17）

# Notes
- 单测 `tests/unit/test_gift_package_free_daily.py` 覆盖 7 天循环（每天可领、
  当天再领拒绝、跨天恢复、第 7 天发纯晶石）与 14 天两轮循环。
- 该包每日领取记录写在 `gift_package_claims`，key 为日期字符串，跨天自动放开，
  不需要定时任务。
