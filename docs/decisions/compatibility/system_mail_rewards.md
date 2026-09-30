---
Document-Type: Compatibility Decision
Status: USER_DECISION / REVIVAL_COMPATIBILITY
Approved: 2026-09-28
Official-Behavior: NO
---

# 系统邮件奖励

当前邮箱为 PARTIAL：MailData、ReadMail、ReceiveAttachment、ReceiveAllAttachment、DelMail、DelAllMail 已接入；`player_mail` 持久化附件、阅读/领取状态和删除状态。登录时同步 MailData，新邮件可推送。客户端邮件对象需要 id、发件人、标题、正文、状态、时间、附件的 ItemID/数量。附件只在点击领取后通过统一 RewardGrant 入账，与领取标记同一 SQLite 事务；未领取附件不可删除。没有过期机制。

2026-09-28 实机补证：官方 2.4 客户端登录时实际还会 POST `/MailService.GetMailPage`（请求字段 `appid/page/page_num/state/userid`）。最初仅有 TCP `L2C_MailData` 推送，HTTP 路由返回 404；接入 HTTP 后，实机日志又显示客户端 `Authorization` **仅为字面量 `Bearer`（长度 6）**，不附游戏令牌，导致每次列表读取返回 401，玩家 3 的两封数据库邮件无法显示。现保留带令牌的严格验证；仅当 HTTP 监听在 loopback、且恰好一个已认证的游戏 TCP 玩家在线并与 `userid` 相同，才兼容该客户端的无令牌 `Bearer`。公网监听不启用此兼容，不能把 `userid` 单独当作身份凭据。HTTP `GetMailPage` / `GetMail` 复用 `player_mail`，附件按 `MailModule.GetAttachInfo` 所需的 `attachment/equip/gift` JSON 字符串下发。修复后的实机显示、已读及领取待复测。断线重连路径同时补上当天邮件创建和新信推送。

用户决定的欢迎邮件对所有账号最多一封：新账号创建事务内立即 ensure；旧账号在下一次成功游戏登录/重连时 ensure。source_key=`welcome_mail:<account_id>`，标题和正文均为空，附件为光辉 `1237902` ×3600、许愿币 `1237914` ×80。ensure 同时识别旧版 `account_welcome:<account_id>` 与相同内容的既有邮件，已发送或已领取都不补发；`(player_id, source_key)` 唯一索引和 SQLite 写事务保证并发、重登、重启幂等。每日邮件在成功的游戏 TCP 登录中创建，source_key=`daily_login:<account_id>:<daily_period_start>`；每日边界复用 `task_period(1, now)`，北京时间零点。标题为空，正文严格为“祝您玩的开心”，附件为光辉 ×200、许愿币 ×10。当天新号会收到两封。

`Item` 静态证据：`1237902` 的 `ItemType=16 E_Currency`、`FunctionEff=2 E_Currency`、`EffData=[902]`、图标 `Ico_Currency_GuangHui`；`1237914` 的对应字段为 `16/2/[914]`、图标 `Ico_Currency_XuYuanBi`。两者均用原有发奖通道，登录本身不直接增加资产。

用户后来明确确认每日附 100 因果卡 `1202014` ×10。客户端 `Item` 与 `Gift` 静态表有 `1202010..1202014` 五档因果卡，对应 10/20/30/60/100 因果。五档卡的 `C2L_ItemOpt` 使用操作均按客户端 `Item.Used -> Gift.Num` 事务扣卡并增加因果。
