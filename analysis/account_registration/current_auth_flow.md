---
Document-Type: Analysis
Domain: Account/Login
Status: CURRENT_SNAPSHOT (2026-09-27)
Baseline: git a273784 (integrate/external-repairs-0925-0926), pytest 308 passed
Evidence: CLIENT_DUMP_CS, CLIENT_IL2CPP_2_4, CLIENT_FULL_TABLES_2_4, PROTOCOL_CATALOG,
  phase13_first_contact_evidence.json, 2026-09-23_01_phase13_first_contact.md
---

# 当前认证/注册实现审计（current_auth_flow）

## 1. 结论速览

| 问题 | 当前状态 |
|---|---|
| 登录账号如何识别 | **单个环境变量配置账号**（`X2_LOCAL_ACCOUNT`/`X2_LOCAL_PASSWORD`），仅存于 `LocalIdentityService` 内存，不落库 |
| player_id 如何产生 | **硬编码 1**：`/apply/httpLogin` 恒返回 `playerID=1`；`validates_game_identity` 只接受 `player_id==1` |
| account 与 player 是否分表 | **否**。`players` 表有一列 `account TEXT UNIQUE`，但全部生命周期只有一行 (id=1) |
| 是否已有 guest/default account | 无游客入口；仅有配置的开发账号 |
| 是否已有自动建档 | 有，但仅限 id=1：`PlayerStore.login` 用 `INSERT OR IGNORE` 首登建默认快照 (`nickname="Revival", level=1`) |
| password 是否存在 | 仅内存明文比较（`secrets.compare_digest`）；无 hash、无数据库持久化 |
| token/session 是否存在 | 有：HTTP 账号 token + TCP game token（内存随机、1 小时过期、全登录共享）；连接级 `session_id`/`player_id` 在 `SessionState` |
| Login 54/79 实际行为 | 54=C2L_Login：验 (id==1, token==game_token) → 建档/`login_count+1` → L2C_Login(79) 全量快照 + PlayerDataProto 推送。79 不是独立请求，是 L2C_Login 的消息 ID |
| 新账号第一次登录会发生什么 | **无法发生**：非配置账号在 `/loginwithpw` 被拒；`player_id!=1` 在 TCP 侧被 `ProtocolError` 拒绝 |

## 2. 现有调用链（实机验证过，Phase 13/14）

```text
客户端 LoginPage（Account 模式, packageType=testpackage）
  → POST {Login_Url}/loginwithpw   form: account,password
     ← TokenCtx {code:"ok", token, id, start, expire}
  → POST {Login_Url}/apply/httpLogin   form: accountid, token, logintype="GAME"
     ← LoginCtx {code:1, logicCode:0, token, playerID, entryIP, entryPort, serverID}
  → TCP entryIP:entryPort
  → C2L_Login(54) {id=playerID, token=game_token, connectType, deviceid, submitInfo}
  ← L2C_Login(79) {code:10, id, loginCount, serverTime, isCreateRole, ...全量快照}
  ← PlayerDataProto 推送
```

服务端组成：

- `src/x2server/bootstrap/local_identity.py` — `LocalIdentityService(RecoveredBootstrapService)`：
  路由 `/login`、`/loginwithpw`、`/apply/httpLogin`、`/apply/chatNode`；其余回落到
  bootstrap 合同（`/apply/connectInfo` 等）。**单账号、双 token、1 小时过期、重启即失效。**
- `src/x2server/player/store.py` — `PlayerStore`：SQLite `players`
  (`id INTEGER PRIMARY KEY, account TEXT UNIQUE, created_at, login_count, snapshot JSON, revision`)；
  `PRAGMA user_version=1`；乐观并发 `save_snapshot`。
- `src/x2server/player/login.py` — `LoginService.login/reconnect/server_config`；
  `validates_game_identity(id, token)` → `store.login(identity.account, id, now)`。
- `tools/local_game_server.py` — 组装：HTTP 127.0.0.1:18080 + TCP 29000（游戏）+ 29001（聊天）。

## 3. 客户端真实注册协议（本轮反汇编新证据，A 级）

以下 RVA 均来自 `libil2cpp.so` (arm64-v8a)，用 `D:/demo/x2/phase3_disasm.py`
（capstone + Il2CppDumper script.json 符号）反汇编。

### 3.1 UI 层：LoginPage (TypeDefIndex 11859)

字段：`mTxtAccount`/`mTxtPassword`（InputField）、`mBtnAccountLogin`、
`mBtnCreateAccount`、`mBtnVisitorLogin`、`mBtnStartGame`。

| 按钮 | Handler RVA | 行为 |
|---|---|---|
| 登录 | `OnMBtnAccountLoginClick` 0x1516448 | `CheckInput`（非空校验，0x151652C）→ `LoginManager.OnAccountLogin(account, password)` |
| 创建账号 | `OnMBtnCreateAccountClick` 0x151660C | `CheckInput` → `LoginManager.CreateAccount(account, password)`（0x1AEB94C） |
| 游客登录 | `OnMBtnVisitorLoginClick` 0x15166F0 | 尾调 `LoginManager.OnVisitorLogin()`（0x1AEB794） |

`CheckInput` 仅校验 `String.IsNullOrEmpty(InputField.text)` → 气泡提示；无长度/字符约束。

### 3.2 注册协程：LoginManager.StartCreate (0x1758B24)

1. `WaitRequestManager.OpenWaitRequestPage`（转圈）
2. 构造 form `Dictionary<string,string>`：`Add("account", account)`, `Add("password", password)`
   （coroutine 字段 0x20/0x28；键来自字符串字面量 `account`/`password`）
3. URL = `<Login_Url 静态配置>` + `"/register"` 字面量（与 `_AccountLogin`
   同一静态基址槽 [0x523f000+0xa38]→static_fields+0x58；`_AccountLogin` 的对应
   字面量路径已被 Phase 13 实机确认即 `/loginwithpw`，同一构造模式）
4. `UnityWebRequest.Post(url, form)`
5. HTTP 200 → `LitJson.JsonMapper.ToObject<IsCreate>`（响应 `{"success": bool}`）
   - `success==true` → `UIAPI.ShowSingleBubbleMsg(语言ID)` → `SaveAccount(account, password)`；
     **不自动登录**，玩家需再用账号登录
   - `success==false` → `ShowSingleBubbleMsg(语言ID+2)`（失败/已存在提示）
6. 非 200 / 网络错误 → `OpenMessageBoxLable` 双语言串错误框

`LoginManager.IsCreate`（dump.cs 779612）：唯一字段 `public bool success`。

### 3.3 游客登录：OnVisitorLogin (0x1AEB794)

`new Random().Next() % 10000` → `String.Format("user{0}", n)` 生成访客账号名
→ `OnAccountLogin(访客账号, "")` → 走普通 `/loginwithpw`。格式字面量
`user{0}` 与空密码均已由该方法的 IL2CPP 引用位置复核。此通道只有 10000
个候选名且无密码，不能直接作为公开服务的持久账号认证。

### 3.4 账号登录：_AccountLogin (0x1AEBE28) 与 httpLogin (0x1AEC9A8)

已由 Phase 13 实机链路 + dump.cs TokenCtx/LoginCtx 双重确认（见第 2 节）。
`_AccountLogin` 有 `Application.platform==7` 分支（双平台不同 URL 字面量），
Android 实机走非 7 分支（Phase 13 实测 `/loginwithpw` 命中）。

### 3.5 登录模式枚举（dump.cs 14432）

`LoginMode { SDK=0, Account=1, Token=2, NESDK=3 }`；Revival v0.2 的
`packageType=testpackage` 使 `LoginManager.OnInit` 选 `Account=1`。
另有 `NESDKManager`（网易 SDK，2.4 包内未启用路径）、`mUnisdkLoginJson` 字段（未启用）。

### 3.6 相关端点字面量全集（stringliteral.json）

`/register`、`/login`、`/loginwithpw`、`/apply/httpLogin`、`/apply/httpLogin163`、
`/apply/gmToken163`、`/apply/loginStep`、`/apply/queryPlayer`、`/apply/queryIdByName`、
`/apply/noticeUrl`、`/apply/connectInfo`、`/apply/address`、`/apply/controlInfo`、
`/apply/chatNode`；表单键 `account`/`password`/`accountid`/`logintype`/`token`；
UI 字段名 `mBtnCreateAccount`/`mBtnVisitorLogin`/`visitorAccount`。

`/apply/httpLogin163`+`/apply/gmToken163` 属 163（网易）渠道变体，Account 模式不使用；
`_reportLoginStep`（0x1AEA9D8 → `/apply/loginStep`）是埋点上报，Phase 13 实测 404 不阻断。

## 4. 最终认定（Registration transport）

- **Transport**: HTTP form POST（UnityWebRequest.Post, urlencoded），非 protobuf、非 marsnet
- **Endpoint**: `{Login_Url}/register`（Revival：`http://10.0.2.2:18080/register`）
- **Request fields**: `account`, `password`（表单键名字面量级证据 + 反汇编 Add 调用）
- **Response**: JSON `{"success": <bool>}`（`LoginManager.IsCreate`）
- **Success code**: `success==true`（HTTP 200）
- **Client consumer**: `StartCreate.MoveNext` → 成功后 `SaveAccount` 本地保存凭据，
  不自动登录；玩家回登录表单手动登录
- **账号认证与角色登录是两级**：`/register`+`/loginwithpw`（账号层）与
  `/apply/httpLogin`（发 playerID/entry）+ TCP 54（角色层）分离
- **游客通道**：客户端有独立游客按钮，等价"随机 `user{n}` + 空密码走
  `/loginwithpw`"；原服是否对未知账号自动建号不可考（服务端已失传）。
  Revival 公开账号兼容层拒绝该路径，避免账号碰撞与冒用。

## 5. 缺口（本轮要补）

1. 无 `accounts` 表：账号不落库、无 hash、单账号硬编码
2. `/register` 端点完全缺失
3. `/loginwithpw` 不支持多账号，未知账号直接拒绝（游客登录会失败）
4. `/apply/httpLogin` 恒回 `playerID=1`，无 account→player 分配
5. `validates_game_identity` 只认 (1, game_token)，无法承载多玩家
6. `players.id` 无自增多号机制（`INTEGER PRIMARY KEY` 可自增，但代码恒传 1）
