# 2026-09-27 卡池、好感度与邮件修复

- 普通、限定和绮石池的 `CardPool.securityNum` 与 `LuckDraw.securityNum` 使用共享的 40 抽未命中次数；新人池仍使用 10 抽神格未命中次数。普通池的 `failCount` 保留 10 抽计数，绮石池沿用 40 抽计数。抽到低星神格时普通池的 40 抽计数继续增加。
- 重复神格的兑换票据来自客户端 `PlayerAttrib.Compensate`，不是神笺。背包余额已验证增加；抽卡回包现同时填充 `RewardData.transformHero`，让客户端显示转化。每个神格的补偿数量来自客户端静态表。
- 偏好礼物由 `SendGiftControl.FavoriteGoodID` 决定，按普通礼物基础好感值的两倍结算。档案达到 `FavorabilityFiles.TypeNumber` 后直接显示已开放，并通过角色更新刷新。好感突破需要 `FavorabilityLevel.BreakItem` 指定材料，扣费与状态变更在同一事务中。
- 邮件协议为 `196/200` 查询、`204/205` 阅读、`197/206` 单封领取、`208/211` 批量领取、`207/210` 删除、`212/213` 批量删除。服务器调用 `MailService.send(player_id, title, body, attachments)` 持久化邮件；本地服务在登录时推送列表，并监听新增邮件以向在线玩家推送。附件只从服务器数据库结算，领取收据由经济系统去重。没有给现有玩家自动创建奖励邮件。
