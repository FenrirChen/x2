# FINAL_SAVE_MANAGER_VALIDATION.md — 存档管理最终验收报告

> 2026-10-11 补充：本报告仅代表旧静态/服务端测试，旧 APK 的入口桥接存在缺陷，已修复并生成 AuthFix 包。线上认证接口实测返回 404，Android 实机全流程仍待验收。当前结论以 [SAVE_AUTH_FIX_20261011.md](SAVE_AUTH_FIX_20261011.md) 为准。

日期：2026-10-01　|　交付：X2-Revival-SaveManager-signed.apk + 服务端存档管理 API

# 1 Result

**PASS**（服务端全链路自动化验证通过；真机人工回归未执行，见第 14 节）
**BLOCKED 项：无**——存档边界审计完整（第 3 节），无 UNKNOWN 状态，Import 未被阻断。

# 2 Database Discovery

| 项 | 值 |
|---|---|
| DB 类型 | SQLite 3 单文件（`PRAGMA user_version=2`，journal=delete） |
| 位置 | `runtime/phase14/player.sqlite3`（由 `tools/local_game_server.py --database`/`X2_DB_PATH` 指定） |
| schema 来源 | 代码内建 DDL（PlayerStore + 各 player 模块幂等建表）；无 ORM；参数化 SQL |
| 表总数 | 63（60 张玩家状态表 + accounts/players 身份表 + repair_history 运维表） |
| 全库检索结论 | 除该 SQLite 外无任何文件型玩家持久化（`src/` 无玩家数据落盘代码） |
| 认证 | `accounts` 表 PBKDF2-SHA256(100k, 16B salt)；复用 `AccountStore.verify`，未重新实现密码算法 |
| 审计产物 | `SAVE_DATA_AUDIT.md` + `tools/savemanager/save_boundary.json`（代码边界 ↔ 活体 schema 由 `validate_boundary.py` 交叉校验通过） |

# 3 Complete Save Boundary

**包含（INCLUDED，60 张）**：
- 主存档：`players.snapshot`（JSON：货币/等级/主线/体力/星图/terminal/guide/heros[]（含技能/好感/装备槽/神器）等）
- 经济/背包 18：inventory、economy_*、pending_rewards、pending_reward_instances、reward_settlement_audit、shop_*、item_opt_receipts、wish_*
- 养成/外观 13：equipment_*（实例/强化/成长）、appearance_*、collection_awards、favor_touch_log、bag_*、college_state、wish_receipts
- 战斗/关卡/任务 20：battle_*（entries/receipts/wire/costs/unresolved/shop_*）、chapter_*、challenge_task_state、task_*、sweep_receipts、fight_drop_*
- 成就/邮件/礼包/星图 9：achievements、achievement_events/receipts、progression_receipts、player_mail、gift_package_*、star_chart_receipts
- join 归属 4：battle_receipts、battle_checkout_wire（uuid→battle_entries）、fight_drop_items/claims（report_id→observations）

**排除（EXCLUDED_FROM_SAVE，逐项理由见 SAVE_DATA_AUDIT.md 第 5 节）**：
accounts 整表（登录身份）；players.id/account/created_at/login_count/revision（身份+活动+技术）；
repair_history（运维）；session token/nonce（纯内存）；导入审计日志；自增序列；TCP 连接。
**无 UNKNOWN**；不影响游戏表现/资源/进度/解锁/奖励/养成/任务的字段才允许排除——已满足。

客户端本地状态：原客户端既有 SaveAccount/PlayerPrefs 缓存为原版行为（本功能不读写）；
服务器重登录全量快照覆盖，不破坏恢复一致性（SAVE_DATA_AUDIT.md 第 7 节）。

# 4 Export

- 实现：`SaveManager.export_save`（save_manager.py），单只读事务（`BEGIN DEFERRED`）内一次取得全部 60 表+snapshot，逻辑快照一致。
- 格式：`.x2save` ZIP 容器 = manifest.json（format X2_REVIVAL_SAVE / format_version 1 / server_save_schema x2-revival/2 / exported_at / source_player 元数据（无 secret）/ 全条目 SHA256）+ save.json（确定性序列化：sort_keys、UTF-8、整数无损、BLOB→blobs/NNN.bin + SHA256）。
- 细节见 `SAVE_FORMAT_SPEC.md`；同一账号重复导出 save.json 逐字节一致。

# 5 Import

| 步骤 | 实现 |
|---|---|
| 验证账号密码 | `/save-manager/auth` → `AccountStore.verify`（PBKDF2），签发 10 分钟单用途 token |
| 验证文件 | 大小上限（96MB/条目 128MB/总解压 256MB）、条目白名单、重复/加密条目拒绝、逐条 SHA256 |
| 验证 format/version | manifest 字段集精确匹配；未知 schema 拒绝并提示迁移（迁移框架挂载点已留） |
| 验证 schema | 逐行逐列对照活体 PRAGMA：未知列/缺失 NOT NULL/类型错/整数越界拒绝；snapshot 走 `store.validate_snapshot` |
| 验证引用 | battle uuid 族、economy run_id、fight_drop report_id、equipment equip_id（含 snapshot 内引用）全部预检 |
| 大小与安全 | 全部通过后才开写；表名/列名来自服务器常量与 PRAGMA，语句参数化，**不执行存档内 SQL** |
| 确认目标账号 | token 绑定 account_id/player_id；`LookupError` 拒绝未知账号 |
| 锁定目标 | `BEGIN IMMEDIATE`；且要求目标账号无活动 game TCP session（在线→409） |
| 在线 session | HTTP 线程经 `run_coroutine_threadsafe` 到主循环取 `authenticated_player_ids()`；在线拒绝：**"账号当前在线，请先退出游戏后再导入存档。"** |
| 自动备份 | PRE_IMPORT_BACKUP：`server_backups/save_import/player_<id>/latest.x2save`，完整写入后原子替换、每账号保留一份，可用同一 importer 人工恢复 |
| 事务 | 删除目标全部边界行→插入+remap（player_id 一律改写；equipment/observation 自增 id 冲突才重映射并同步重写 snapshot/引用；player_mail id 一律重分配；uuid/request_key 族冲突整族一致重映射）→ sqlite_sequence 前推 → `PRAGMA foreign_key_check` → COMMIT；任何异常 ROLLBACK，导入前状态原样保留（测试强制中途失败验证） |

# 6 Round-trip Verification

`SAVE_ROUNDTRIP_VALIDATION.md`：**Export 快照 == Import 恢复快照**（60/60 表逐表
canonical SHA256 相等，变更阶段证明真实落地后完整回滚）。跨账号：B 导入 A 存档后
canonical(B)==canonical(A)，B 的用户名/密码/PBKDF2 哈希不变，owner ID 全部 remap
（equipment 实例 id 与 A 零交集，enhancements/growth/snapshot 引用全部指向 B 自己的实例）。

# 7 Login UI

- 文字来源：语言表 protobuf 条目（语言 ID 246 等）×3 条目 + LoginPage prefab 序列化字符串 + DHUI SDK 布局（详见 `LOGIN_UI_REVERSE_REPORT.md` 第 2 节）。
- 修改方式：**原位等长 UTF-8 替换**（游客登录→存档管理 / 遊客登入→存檔管理，8 处），保留按钮背景/位置/动画/尺寸/美术。
- click handler：原 `OnMBtnVisitorLoginClick`（RVA 0x15166F0，尾调 `OnVisitorLogin` 0x1AEB794）→ 1 指令 hook 接 code cave trampoline（0x42B02C0）→ dlopen/dlsym 调 `x2_open_save_manager(this, il2cpp)`；桥成功返回 1 终止原流程，桥缺失回落原游客登录。
- 账号密码：桥经 il2cpp C API 读 `mTxtAccount/mTxtPassword.get_text` 复用现有输入框（无需重填）；为空 → Java 提示"请输入账号和密码"；认证失败 → "账号或密码错误"。

# 8 Android UI

- `SaveManagerDialogFragment`（android.app.DialogFragment，程序化 LinearLayout/TextView/Button/AlertDialog，无图片/字体资源；宿主为 UnityPlayerActivity，**无需修改 AndroidManifest**）。
- SAF：导出 `ACTION_CREATE_DOCUMENT`（建议名 `X2_<account>_<yyyyMMdd_HHmmss>.x2save`），导入 `ACTION_OPEN_DOCUMENT`（.x2save）；**零存储权限**（无 READ/WRITE/MANAGE_EXTERNAL_STORAGE），Android 11–16 免权限。
- 导入前确认对话框（取消/继续导入）；成功后提示"存档导入成功，请重新登录。"并关闭，不自动进游戏。

# 9 Security

| 项 | 结果 |
|---|---|
| password/hash | 导出内容不含任何凭据字段（accounts 整表排除）；不落 URL/GET/日志/存档 |
| token | save token 短时（600s）、单用途、与游戏 token 互斥（测试断言）；导入成功即失效 |
| untrusted save | 第 5 节全链路校验；SQL/表/列名全部来自服务器，参数化执行 |
| zip safety | 重复条目/加密/路径穿越/解压炸弹全部拒绝 |
| transaction | 单事务，强制中途失败测试证明 ROLLBACK 无半写 |
| 日志 | 服务端仅记录路由/大小/账号 id/行数，凭据不落日志 |
| 在线覆盖 | 导入强制离线；无内存 Player 缓存可回写（逐请求直读 DB 的服务器架构） |

# 10 APK Diff

`APK_DIFF_SAVE_MANAGER.md`：新增 `classes5.dex`（8,885 B 压缩）+ `lib/arm64-v8a/libx2save.so`（6,759 B 压缩）；
内容变更 5 条目（4 个等长文字替换 + libil2cpp hook）；删除 3 个旧 v1 签名条目；
其余 12,636 条目逐字节一致（含 AndroidManifest、加密 GameConfig、全部 classes*.dex、libunity.so）。

# 11 APK Size

| | bytes |
|---|---|
| 基线 AllocatorFix-signed | 2,145,044,177 |
| **最终 SaveManager-signed** | **2,144,999,251** |
| 距 2,147,483,647 裕量 | 2,484,396 |
| 硬约束 < 2,147,483,647 | ✅ |
| 新增净体积（新增条目压缩计） | 15,644 B（建议 <1MB ✅） |

# 12 Allocator Regression Check

最终 APK 内 `lib/arm64-v8a/libunity.so` SHA256：
`7c5a3c1f457572727020d498bc894a0832cc1dcd415d1a35a3c59e0ee10c8aa5` —— 与要求**完全一致**（零回归）。

# 13 Signing

- apksigner verify --verbose：v1 ✅ / v2 ✅ / v3 ✅，`Verifies`，1 signer。
- 证书 SHA256：`C3:0B:81:37:CE:4C:CD:81:03:D2:C9:40:EA:76:90:DB:9D:F9:B6:BB:99:11:7D:DF:A9:A9:F1:12:23:64:2C:28` —— 与发布身份一致 ✅（sign_release.ps1 内建比对通过）。
- 使用既有 `D:\demo\x2\.runtime\signing\`（alias `x2-revival-release`）；未生成新 key、未输出/提交任何密码。
- packageName `com.siva.project.x2` 不变；versionCode 202 不变（检查确认其不参与 bootstrap/协议检查，按保守原则不递增）。

# 14 Runtime Test Status

**READY FOR DEVELOPER RUNTIME TEST**

自动化覆盖：单元 12 项 + HTTP 集成 5 项 + round-trip 验证运行器（60 表 + 跨账号 4 项断言）
+ 无签名 APK 校验器（CRC/patch/hook/对齐/SHA）全部通过；服务端全量回归 511 passed
（7 failed + 6 errors 为**预先存在**的环境问题——仓库外 `analysis/drop_archaeology` 数据
文件缺失与 mail 计数旧行为，经 git stash 基线对照确认与本功能无关）。

未执行（开发者侧人工回归清单，通过后才可评估发布）：
1. MuMu 12 覆盖安装 → 登录页按钮显示"存档管理"；
2. 空/错密码提示与认证成功进入存档管理界面；
3. 导出 SAF 落盘 → 继续游玩（打关卡/抽卡/改装备）→ 导入 → 重登后逐项核对；
4. 在线时导入被拒提示；坏档导入错误提示；备份目录人工恢复演练；
5. 服务器重启后账号登录/游戏/聊天三链路不回归。

**不写 READY FOR PUBLIC RELEASE。**
