---
Document-Type: Runtime Validation
Domain: Account Registration
Date: 2026-09-28
Status: PASS
---

# 注册接管验收

## 接管与自动化

- 接管 HEAD `a273784`，未暂存账号半成品；基线全量 `320 passed`。
- 完成账号/玩家同事务注册、独立 HTTP SQLite 连接、旧玩家关联。
- 隔离库测试覆盖重复/非法注册、注入失败回滚、两连接并发、HTTP 真请求、
  TCP 54/79、快照更改后重登。最终全量 `323 passed`。
- 复制活跃 v1 SQLite 到临时库试迁移：玩家行逐字段相同；原活跃库字节未变。

## MuMu 实机（隔离 SQLite）

使用现有 Revival APK 的 Account UI，注册一个全新专用测试账号。客户端
实际发出 `POST /register`，服务端返回成功；隔离库恰好有一条 account 和
一条 player，`accounts.player_id=players.id=1`。点击开始游戏后客户端进入
开场流程，服务器收到 TCP 登录并回复 79，`login_count=1`。

强制退出客户端、停止测试服务，把隔离玩家金币设为 37，再重启相同数据库
的服务和客户端。客户端保留账号输入，点击开始游戏后再次进入开场流程；
同一玩家 ID=1，`login_count=2`，金币仍为 37。没有再次初始化账号或玩家。

## 活跃存档恢复

切换服务前，使用 SQLite online backup 保存活跃库为
`runtime/phase14/player.pre_auth_20260928.sqlite3`，`integrity_check=ok`，
包含一条原有玩家。隔离测试结束后，原路径
`runtime/phase14/player.sqlite3` 已由新版服务打开，非破坏性迁移到 v2。
其原玩家的 id、account、created_at、login_count、snapshot、revision 与备份
逐字段一致；账号层关联到原玩家 ID=1，历史开发账号的密码登录通过。
随后在 MuMu 客户端切回历史测试账号，实际 TCP 登录到同一玩家 ID=1，
`login_count` 从 101 正常增至 102；模拟器不再停留在隔离测试账号。
新服务监听 127.0.0.1:18080 / 29000 / 29001。

## 边界

游客按钮使用空密码和 10000 个候选名，本轮未开放。未修改 APK 端点、
未进行公网部署。账号注册闭环五项门槛均通过；
`PUBLIC_DEPLOYMENT_BLOCKER: CLEARED` 仅指本账号注册门槛。
