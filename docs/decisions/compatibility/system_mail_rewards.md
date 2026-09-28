---
Document-Type: Compatibility Decision
Status: USER_DECISION / REVIVAL_COMPATIBILITY
Approved: 2026-09-28
Official-Behavior: NO
---

# 系统邮件奖励

当前邮箱为 PARTIAL：MailData、ReadMail、ReceiveAttachment、ReceiveAllAttachment、DelMail、DelAllMail 已接入；`player_mail` 持久化附件、阅读/领取状态和删除状态。登录时同步 MailData，新邮件可推送。客户端邮件对象需要 id、发件人、标题、正文、状态、时间、附件的 ItemID/数量。附件只在点击领取后通过统一 RewardGrant 入账，与领取标记同一 SQLite 事务；未领取附件不可删除。没有过期机制。

用户决定的欢迎邮件在新账号注册时与账号和玩家快照同一事务写入。source_key=`account_welcome:<account_id>`，标题和正文均为空，附件为光辉 `1237902` ×3600、许愿币 `1237914` ×80。旧账号不追发。每日邮件在成功的游戏 TCP 登录中创建，source_key=`daily_login:<account_id>:<daily_period_start>`；每日边界复用 `task_period(1, now)`，北京时间零点。标题为空，正文严格为“祝您玩的开心”，附件为光辉 ×200、许愿币 ×10。当天新号会收到两封。`(player_id, source_key)` 唯一索引保证重复登录与多连接只生成一封。

`Item` 静态证据：`1237902` 的 `ItemType=16 E_Currency`、`FunctionEff=2 E_Currency`、`EffData=[902]`、图标 `Ico_Currency_GuangHui`；`1237914` 的对应字段为 `16/2/[914]`、图标 `Ico_Currency_XuYuanBi`。两者均用原有发奖通道，登录本身不直接增加资产。

用户后续要求每日附 10 张“120 因果”卡。当前客户端 `Item` 与 `Gift` 静态表只有 `1202010..1202014` 五档因果卡，对应 10/20/30/60/100 因果；没有 120 因果卡。暂按最接近的 100 因果卡 `1202014` ×10 提供，等待用户改选时可调整。五档卡的 `C2L_ItemOpt` 使用操作均按客户端 `Item.Used -> Gift.Num` 事务扣卡并增加因果。
