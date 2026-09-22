# Phase 13 — 真实客户端 First Contact 通过

日期：2026-09-22。分支：`feat/first-login-contact`，基线 `c0cf6b3`。
阶段二范围：让 Revival Client 进入原有账号界面，连接本地游戏服并解析真实
`C2L_Login`，不发送 `L2C_Login`。已两次达成，第二次核实身份与本地签发 token 一致。
玩家数据库、登录快照和大厅仍未实现，不能据此宣称游戏已可玩。

## 实际链路与证据

首轮 23:06:37 controlInfo → connectInfo → 原有账号界面；23:09:21
`/loginwithpw` → `/apply/httpLogin` → TCP；23:09:22 解出消息 54、request ID 1。
23:11:14 在同一客户端上重新点击登录，再次解出消息 54、request ID 2，
`local_identity_valid=true`。第二轮没有重启客户端，因此未重复请求启动配置。

两轮均通过真实 frame CRC 检查及 protobuf 解码，字段为 `id`、`token`、
`connectType`、`deviceid`、`submitInfo`；仅保存字段类型/长度及第二轮 body 哈希。
脱敏结果见 [证据摘要](phase13_first_contact_evidence.json)。账号、token 和设备标识
不写入提交的证据。原始运行文件在忽略目录 `runtime/phase13/`。

本分支实际使用 httpLogin 返回的 entryIP/entryPort，**未调用 `/apply/address`**；
address 既有合同保留，但不能标记为实机验证。`/apply/loginStep`、`/apply/noticeUrl`
返回 404，未阻止此链路；没有为了消除日志而添加伪成功响应。

## 阻塞原因及最小兼容修改

1. `AppMainImpl.ControlInfoCallback`（RVA 0x17E072C）只在 update 为 LEBIAN/TAPTAP
   时继续；空字符串会返回而不推进状态。Phase 12 的 controlInfo 200 不等于继续加载。
2. product 模式 + LEBIAN 实机触发辅助进程缺失 BGService 的异常。
3. `LoginManager.OnInit`（0x1AE5C30）在 packageType=testpackage 时选 Account=1。
   `StartLeBianUpdate`（0x17E0970）对此模式直接使用已有 OnLeBianFinish 分支。
   `DHSDKMangager.InitSDK`（0x1ADA5C8）也已有该模式的完成路径。
4. v0.2 仅在原 URL 补丁之外将 GameConfig 第 0 行 packageType 改为 testpackage；
   client_Type 保持 product。不修改 native/DEX/协议/玩法资源。补丁工具做语义差异检查。

Reference SHA-256 仍为 `26a47aa684576549142cf0e4d096a78b90446314506626d2f9e57e6f76450bbe`。
unsigned v0.2：`2296c06c30b3614876d841625571f0e2e2cb9b3eb34d0cd3920617f7d4a9137b`。
signed v0.2：`460dc657a8fb1b5410a4c0eaa5fac9433b45ecc54b7f3845afc626420946276d`。
沿用开发密钥，覆盖安装成功、保留数据；签名口令经用户明确授权从本项目原记录复用，
不输出、不提交。首次 180 秒签名超时留下的 `v0.2.apk` 无效；最终文件带 `-signed` 后缀。

## 身份合同（TEMPORARY_COMPAT）

静态来源：`_AccountLogin.MoveNext` 0x1AEBE28，`_httpLogin.MoveNext` 0x1AEC9A8，
以及 dump.cs 的 TokenCtx / LoginCtx；上述字段与返回值随后通过实机链路确认。

| 请求 | 必要输入 | 成功返回 |
|---|---|---|
| POST /loginwithpw（兼容 /login） | account,password 表单 | code="ok",token,id,start,expire |
| POST /apply/httpLogin | accountid,token,logintype="GAME" | code=1,logicCode=0,token,playerID,entryIP,entryPort 字符串,serverID |

桥接只处理单个配置的本地测试账号，使用不同的随机账号/游戏 token，有效期一小时；
错误密码、错误 token、错误账号/模式和过期请求拒绝。玩家 ID 1 是实验身份，
不代表持久玩家。仅首次连接工具显式启用此服务，绑定 127.0.0.1，不修改默认服务入口。
HTTP 传输最多读取 64 KiB 请求体并传入服务，不记录正文或查询参数。

## 复现

使用现有 API 30 AVD、Phase 12 的 `-gpu host -feature GLESDynamicVersion`，
安装 `revival_client/build/X2_Eclipse_v2_4_Revival_v0.2-signed.apk`。
仍通过 root ADB 的 `X2UnityActivity` 实验入口启动；桌面 Splash 入口、新装/其他设备不在验收范围。
Phase 12 startup_probe 固定校验 v0.1，不应用它来验收 v0.2。

在仓库根目录启动：

```powershell
$env:PYTHONPATH='src'
$env:X2_LOCAL_ACCOUNT='revival'
$env:X2_LOCAL_PASSWORD='revival-local' # 仅此实验的公开测试值，勿使用真实账号
.venv/Scripts/python.exe tools/first_contact_runner.py --local-account --timeout 300 --result runtime/phase13/recheck.json
```

启动客户端，输入上述测试值，Unity 弹出的输入框需点 OK 确认（返回键会取消输入），
点击开始跃迁。工具收到真实 54 后退出，不回复登录；客户端留在登录页是预期边界。
运行时原始日志可能包含客户端自己的标识信息，保持忽略，不整份提交。

## 验证与下一阶段

新增测试覆盖配置补丁限制、身份交换/拒绝/过期、HTTP 表单正文传递；保留协议回归。
最终回归：`python -m pytest -q` **137 passed**；`git diff --check` 通过。
下一阶段：从客户端接收路径恢复最小 L2C_Login 合同，同时建立 SQLite 玩家持久化，
验证最小快照、重连及重启一致性，再逐步进入大厅。不要提前扩大到完整任务/战斗服务。
