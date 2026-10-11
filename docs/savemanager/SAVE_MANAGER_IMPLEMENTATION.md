# SAVE_MANAGER_IMPLEMENTATION.md — 存档管理实现说明

功能：登录界面"游客登录"→"存档管理"改造；账号密码认证后导出/导入该账号的服务器存档。
正式发行功能。服务端融入现有 18080 bootstrap HTTP 框架，不新增进程/端口。

## 1. 服务端（x2_revive_workspace）

| 文件 | 内容 |
|---|---|
| `src/x2server/player/save_manager.py` | 存档边界常量（60 表，与 SAVE_DATA_AUDIT.md 一致）、`.x2save` 容器导出（单只读事务一致快照）、导入（校验→备份→`BEGIN IMMEDIATE` 单事务→删除→重放→ID remap→foreign_key_check→COMMIT/ROLLBACK）、PRE_IMPORT_BACKUP、canonical_state（round-trip 比较基准） |
| `src/x2server/bootstrap/save_manager_api.py` | HTTP 路由（见下）；独立短时 save token（10 分钟、单用途）；在线检测；不落日志的凭据处理 |
| `src/x2server/bootstrap/local_identity.py` | 仅新增：`save_manager_api` 参数与 `/save-manager/*` 委派（现有 Mail/bootstrap/Game 流程零改动） |
| `src/x2server/bootstrap/http_server.py` | 仅新增：`/save-manager/` 路由的请求体上限（96MB+64KB）；其余路由维持 64KB |
| `src/x2server/player/store.py` | 仅重构：snapshot 校验提取为 `validate_snapshot()` 供写入与导入共用（行为不变） |
| `tools/local_game_server.py` | 装配 `SaveManager`+`SaveManagerAPI`；在线检测经 `asyncio.run_coroutine_threadsafe` 到 TCP 主循环取 `authenticated_player_ids()` 快照（跨线程无竞态） |
| `tools/savemanager/*` | 审计/验证/构建工具（generate_audit、validate_boundary、round-trip 运行器、客户端构建脚本） |

### API（全部复用现有 18080 服务）

| 路由 | 请求 | 响应 |
|---|---|---|
| `POST /save-manager/auth` | form `account,password`（复用 `AccountStore.verify` PBKDF2 校验） | `{"code":"ok","token":…,"expires_in":600}`；`invalid`/`empty` |
| `POST /save-manager/status` | `Authorization: Bearer <save-token>` | `{"code":"ok","account":…,"online":bool}` |
| `POST /save-manager/export` | Bearer | `application/octet-stream`（.x2save 容器） |
| `POST /save-manager/import` | Bearer + 原始 .x2save 字节 | 成功 `{"code":"ok","backup":…}`；在线 `409 {"error":"account_online","message":"账号当前在线，请先退出游戏后再导入存档。"}`；坏档 `400 {"error":"invalid_save","message":…}` |

- save token 与游戏 token 完全隔离（互不可用，测试断言）；认证失败不记录账号名，只记长度。
- 导入成功后自动失效该账号全部 save token（防重放）。

### 导入安全（任务第十七节逐项）

超大文件（96MB 上限+逐条目/总解压上限）✓ zip bomb（解压总量限制）✓ path traversal
（条目白名单+正则，文件名不落盘）✓ 重复 ZIP entry ✓ 非法 JSON/类型错误/整数越界 ✓
非法外键（引用完整性预检+导入后 foreign_key_check）✓ schema 注入/SQL 注入（表名列名
全部来自服务器代码常量与 PRAGMA，存档文件仅提供参数值，语句全部参数化）✓ 恶意路径
（备份文件名来自服务器时间戳+用户名净化）✓ 任意文件覆盖（写入仅限备份目录内新文件，
永不覆盖）✓ 绝不执行存档内 SQL ✓

## 2. 客户端（X2-Revival-SaveManager APK）

| 修改 | 内容 |
|---|---|
| 文字 | 4 个条目原位等长替换 游客登录→存档管理 / 遊客登入→存檔管理（8 处） |
| libil2cpp.so | 1 指令 hook（0x15166F0）+ code cave trampoline（0x42B02C0，~330B），见 LOGIN_UI_REVERSE_REPORT.md 第 4 节 |
| lib/arm64-v8a/libx2save.so | 19,520 字节 C 桥（zig cc 交叉编译，无 NDK）：读两个 InputField 文本 + `GameConst.Login_Url`，经 `AndroidJavaClass.CallStatic("open", account, password, baseUrl)` 交 Java；DT_NEEDED libc.so/libdl.so；返回 0 时回落原行为 |
| classes5.dex | `SaveManagerBridge`（UI 线程调度+空值提示）+ `SaveManagerDialogFragment`（程序化 LinearLayout 对话框：当前账号/导出/导入/返回；SAF `ACTION_CREATE_DOCUMENT`/`ACTION_OPEN_DOCUMENT`；HttpURLConnection；org.json） |

- **无需新增 AndroidManifest 条目**：UI 为 DialogFragment（宿主 UnityPlayerActivity 原生
  分发 onActivityResult 到 Fragment），避免二进制 Manifest 重编码。
- 凭据仅在内存（Bundle 参数），无任何持久化、无日志输出；不请求任何存储权限（SAF）。
- 导入前弹确认："导入存档将覆盖当前账号的全部游戏进度。/服务器会在导入前自动创建备份。/是否继续？"（取消/继续导入）。
- 成功后提示"存档导入成功，请重新登录。"并关闭存档管理，由玩家手动重新登录（不自动进游戏）。
- 服务器地址取自客户端运行时 `GameConst.Login_Url`（与登录同一 endpoint 配置），不破坏 18080 bootstrap / 29000 game / 29001 chat。

## 3. 构建管线（可重跑）

```
python tools/savemanager/client/build_bridge.py      # zig cc → libx2save.so（无 NDK）
python tools/savemanager/client/build_dex.py         # javac+d8 → classes5.dex
python tools/savemanager/client/patch_il2cpp.py <libil2cpp.so> <out>   # hook+cave，内建 capstone 验证
python tools/savemanager/client/build_apk_savemanager.py <patched.so> <unsigned.apk>
python tools/savemanager/client/validate_unsigned_apk.py <unsigned.apk>
powershell 逆向/脚本/sign_release.ps1 -InputApk <unsigned.apk> -OutputApk X2-Revival-SaveManager-signed.apk
```

签名使用既有 `D:\demo\x2\.runtime\signing\`（alias `x2-revival-release`），未生成新 key、未输出密码。
