---
Document-Type: Current Knowledge
Domain: Account Registration
Status: REVIVAL_COMPATIBILITY (2026-09-28)
Evidence: analysis/account_registration/current_auth_flow.md
---

# 账号注册与首登

## Original client behavior

Account 模式的注册按钮向 `{Login_Url}/register` 发送 HTTP form `account,password`，
只读取 JSON `success` 布尔值。成功后保存输入的账号密码；玩家还需点击登录。
登录依次使用 `/loginwithpw`、`/apply/httpLogin`，最后以 TCP 54 请求进入游戏并
接收 79。注册不是 54 的职责。该版本的游客按钮生成 `user{0..9999}` 并用空密码
调用账号登录。

## Original backend lost pieces

官方账号库、账号分配规则、初始赠送内容和游客身份服务均无可信服务端资料。
不能从客户端证明官方初始 Hero、货币或任务状态。

## Revival compatibility

`AccountStore` 是明确标注的 REVIVAL_COMPATIBILITY 账号层。客户端真实的注册
和登录路径保持不变。未知用户名不能通过登录自动建号。游客按钮由于 10000 个
用户名的碰撞空间和空密码，当前拒绝；公开部署前需独立解决游客身份问题。

## Database model and registration flow

现有 `players` 表保持原形；迁移从 v1 到 v2 只添加 `accounts` 表和唯一
`player_id` 索引，不删除玩家数据。注册先验证输入，再以 `BEGIN IMMEDIATE`
事务插入 `players`（SQLite 自动分配整数主键）和 `accounts`（用户名 UNIQUE，
玩家 ID UNIQUE），成功后同时提交；异常时回滚。密码使用随机盐 PBKDF2-SHA256
哈希，不保存明文。HTTP 线程使用独立 SQLite 连接并串行化对该连接的访问。

## Login flow and security constraints

账号密码验证后发放 `secrets` 生成的一小时内存 token。`/apply/httpLogin` 复核
token、账号名或对应 account_id，然后发放玩家 ID 和新的游戏 token；TCP 54
再次核对游戏 token 与玩家 ID。未知账号、错误密码、控制字符和过长字段均拒绝。
注册重复返回 `success:false`；数据库故障返回非 200 且 `success:false`。
token 在服务重启后失效，需要重新登录。注册限流留待公网加固。

## New player bootstrap

`new_player_snapshot()` 在注册事务中生成独立的 1 级快照：0 货币、0 经验、
无 Hero、满额 60 体力。它是 REVIVAL_COMPATIBILITY 最小初始状态，未从
`runtime/phase14/player.sqlite3` 复制。背包、装备、任务等扩展状态由已有
领域服务在首次登录时读取空态或幂等生成；不能将空态解释为官方开服奖励。
重复登录不再运行注册 bootstrap，也不会重置保存的快照。

## Legacy compatibility

已存在的开发玩家通过配置的种子用户名与密码，只在尚无账号记录时关联原
`players.id`；快照、登录次数和库存不改。普通用户不能认领未绑定的旧玩家名。

## Remaining unknowns and deployment

原服账号规则、初始赠送和游客后端规则仍未知。自动化测试验证了独立数据库的
注册、首登、重登、并发及 HTTP/TCP 报文。
2026-09-28 的 MuMu 实机新号注册、首登和服务重启后重登均通过；详见
`../../analysis/account_registration/real_client_validation.md`。注册闭环的五项门槛
（注册、登录、新玩家、重登、旧玩家）均已通过，
`PUBLIC_DEPLOYMENT_BLOCKER: CLEARED`。这只表示账号注册门槛已解除；
本轮仍按用户要求暂停 APK 端点修改和公网部署。游客路径及限流留待公网加固。
