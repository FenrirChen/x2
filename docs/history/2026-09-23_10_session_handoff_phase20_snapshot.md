---
Document-Type: Historical Report
Date: 2026-09-23
Status: SUPERSEDED
Superseded-By:
  - D:/demo/x2/SESSION_HANDOFF.md (trimmed current version)
---

# X2 Revival — Session Handoff

## Phase 20 当前交接（2026-09-23，优先于以下历史记录）

- Git：审计资料 `1d6d5da`，实现与报告 `6387e38`；分支 `feat/lobby-account-state`，提交后工作区干净。根目录 README/本文件位于仓库外，已同步更新。
- 战斗基础属性修复另提交 `b80f707`，等待用户实战复测。
- **最新结果覆盖上面的待测状态**：server03 中 19:58:48 第二小节成功，自动进入第三小节；20:00:36 第三小节也成功，main_section=2110803。用户同时实机升星到 stage=2 并领取任务；20:01 存档：账号60/角色2级2阶，金币12340、晶石90、经验36、神格经验1240、日活跃15、体力137。两件兽主各1待发。第四节未验收，摇杆/伤害体验的明确用户答复仍待收到；不要回写这些动态余额。

- 依据 [Phase 20 报告(2026-09-23_08_phase20_progression.md)。MuMu 12 为当前试玩环境，serial `127.0.0.1:7555`，1280×720；正常 SplashActivity 启动，客户端仍 Revival v0.2。Reference 未修改，不重装、不清数据、不启动 Google AVD。
- 用户明确规则：北京时间每日 00:00、周一 05:00 换期；首登录按等级生成任务，保留未恢复在线功能任务。每小节扣表中体力（首段每节 6），失败全额退还本节。重试不重复扣费/退款。放弃旧场并重新入场会退还旧场费用。
- 163 项测试通过。已实现周期归档/迁移、养成成本事务、四小节主线推进及退款。旧日任务领取保留，不能补发。战斗不开发录像反作弊；基本幂等保留，支持同玩家跨连接结算当前场。
- 贝黑莫斯升级在 MuMu 成功：1→2，神格经验 620→500，属性 75/46/752，日任务 630016=1、周任务 630105=1；重新登录仍保持。升星/技能正常存档缺材料，没有注入假材料；成功路径只在隔离测试库验证。
- 旧存档已有第一小节 2110801 的经济通关记录，本轮迁移 main_section=2110801、main_chapter=2010100，不重复发奖、不追扣。19:43 服务已收到客户端进入 **2110802** 的请求；用户正在手动试玩，请先看最新画面/日志再操作，不强制打断。
- 活跃 DB `runtime/phase14/player.sqlite3`，部署前备份 `runtime/phase20/before-phase20.sqlite3` 不覆盖。当前日志 `runtime/phase20/server02.err.log`；服务 14400 秒限时，PID 仅临时事实，操作前重新检查。
- 部署前存档：账号 60、英雄 1、金币 980、晶石 30、账号经验 12、神格经验 620、体力 149；升级后神格经验 500。**试玩会继续改变余额/主线，不能按文档数值覆盖存档。**
- 未恢复固定装备/特殊货币入 `pending_rewards`，账号升级礼包时点未知也记待发；随机掉落仍空。商店、活跃宝箱、武器/兽主实例继续按 [NEED(../../NEED.md) 定点补证据。商店错误码查询仍可能在开店页轮询，不返回成功空列表。
- 下一步核对用户实战后的连续小节、失败退款、结算奖励；随后恢复武器/兽主与待发奖励。不要重做 Bootstrap、签名、全量资源扫描，不降回备份，不把测试库成功写成实机验收。
- 最新实战：19:44:15 第二小节 2110802 失败，6 点体力已全退，存档恢复 149；金币/晶石/主线不变，退款标记持久化。失败退款已验收，成功后的连续推进仍待用户战斗。
- 随后用户报告第二小节只有移动/攻击动画，坐标不变且无伤害。已定位 `FightHero.attrAdd` 缺失：客户端转成非 null 空列表后跳过本地基础属性初始化；修复下发 IndexInfo 映射的 19 项原始属性，包含移速 550、Damage 60 与 COR 12；客户端自行计算等级/阶段成长。证据与导出在 Phase20 报告，163 测试通过。最新部署 **server03.err.log**，MuMu 已重启；等待用户复测移动/伤害，不能把旧失败结算当正常战斗验收。

以下 Phase 19/18/16 段落均为历史记录，“免费战斗、不重置任务、不发奖、不推进”等旧限制已经由 Phase 20 对应实现替代。

## MuMu 人工试玩环境迁移（2026-09-23，优先于下方旧模拟器操作说明）

- MuMu 12 已作为主要人工试玩环境验收；完整证据与启动命令见 [MuMu 迁移报告(2026-09-23_09_mumu_migration.md)。运行进程反查安装根目录为 `D:\MuMuPlayer-12.0\MuMuPlayer`；现有 SDK ADB 连接 `127.0.0.1:7555`。Android 12 / API 32，设备 V2366GA。
- MuMu 已装包 SHA-256 与签名 Revival v0.2 一致，不重装。guest `10.0.2.15` 实测可经 `10.0.2.2` 访问原有 localhost Bootstrap/TCP；无需 v0.3、服务改绑或网络设置修改。正常桌面 `SplashActivity` 启动后进入 Unity，既有账号已登录 60 级大厅，体力 149/149、金币 800；用户手动确认路径正常。
- 接手先检查现有服务和 MuMu 进程，不重复启动。活跃存档仍为 `x2_revive_workspace/runtime/phase14/player.sqlite3`，Phase 19 备份不覆盖；本轮未修改业务代码、Reference APK 或 Google `X2-ABI-Probe-API30`，未清库或重置玩家。测试登录会正常更新登录计数。
- Google 模拟器及旧 `tools/android/open_lab_window.ps1` / 内部 Activity 指令仍保留作参考实验，**日常 MuMu 启动不要机械沿用它们**。MuMu 的正常入口及 ADB 路径见迁移报告。下方 Phase 19 的业务进度仍有效；旧段落的“当前模拟器”只反映当时环境。

## Phase 19 当前工作（优先于下方历史记录）

- 用户要求恢复商店、任务和战斗掉落；选择**严格按已确认数据**实现，缺失部分写入 [NEED.md(../../NEED.md)。不采用自拟商店数量、掉落概率或任务日历。
- 代码已提交：审计证据 `9145c8e`；经济实现 `66bacc1`。报告 [phase19_economy.md(2026-09-23_07_phase19_economy.md)。154 项测试通过。
- 已实现固定奖励事务、流水、首通去重、背包同步、日/周任务进度和领取。旧练习 run 不补奖；新 run 限当前会话/一小时，完整旧结算不能换 run 重放。仍不扣体力、不自动升级；玩家保持 60 级。
- 任务实机领奖已成功，当前金币 800、神格经验池 500、日活跃度 10、体力 149。**登录任务已领取，不得重置/补发**。初始日/周实例暂不自动刷新。
- 商店成功空列表会使客户端 ShopModule 空引用重连；已改为查询/购买/刷新都明确返回 13。商品数量、随机掉落、日历与宝箱等缺口见 NEED；不能宣称完整恢复。
- 当前集中验证进行中，战斗发奖尚待用户实战。可跳剧情，需要战斗提醒用户。用户补充允许必要重启，不要为避免重启而停滞。
- 本轮开始时模拟器已关闭。重新打开后 wlan0 缺 IPv4 路由，重启游戏不解决；模拟器 Wi-Fi disable/enable 后路由恢复，点击重试即可登录。没有修改宿主机防火墙/代理。
- 活动库仍为 `runtime/phase14/player.sqlite3`，备份 `runtime/phase19/before-economy.sqlite3` 不得覆盖。当前日志 `runtime/phase19/server02.err.log`；启动器 PID 5480 仅供核对，先检查实际进程再操作。客户端仍 v0.2 / 2.4（202），Reference 未改。
- 下方 Phase 18/16 的“无奖励、147 项测试、snapshot 未变化”等是历史结果，不再描述当前经济存档。不要重做 Bootstrap/签名/全 APK 扫描，不清数据、不降回旧备份、不重复创建初始账号。

更新日期：2026-09-23。当前依据为 [Phase 18 报告(2026-09-23_06_phase18_chat_first_battle.md)。此前报告保留为历史证据。

## Phase 18 当前交接

- 客户端仍为 Revival v0.2，未修改 APK。首关 **2110801 / 2010100 / 2210801** 已成功加载，移动与技能已验证，用户已手动完成实战。
- chatNode 和独立空聊天服务（29001）已成功握手；大厅观察未见持续重试。战斗中聊天闲置超时关闭不等于持续重连。
- 界面重叠未复现，用户允许暂缓。不要宣布已修复，也不要通过强行销毁全部页面掩盖问题。
- 新增有界入场与 SQLite battle_entries。战后实际发送 887 CheckoutMainMissionSign 和 316 FightKillInfo；887 用 152 回包，没有独立 Sign 响应。
- 本地试跑结算已实机验证：用户再次完成战斗后，887 -> 152 回包被接受，客户端经过星图过渡并请求下一小节 2110802。该小节尚未开放，明确拒绝后回到关卡页，再点击大厅正常返回。**这不是完整第一幕的奖励结算页验收。** 试跑记录结果但不验证录像、不扣体力、不发奖励、不推进持久化主线；重复提交返回相同结果，冲突提交拒绝。空服务端掉落配置和击杀报告收讫已验证，不推进任务。
- 147 项测试通过。证据见 runtime/phase18；备份 before-battle.sqlite3 不得覆盖。活跃库和 60 级存档不变。
- Unity 偶发超过 16GB 地址跨度错误仍可能卡加载；冷启动模拟器曾绕过，并非永久修复。CollegeModule.RefreshTrainRedDot 空数据异常仍存在。
- 最新用户授权可跳过剧情、继续开发；需要实战时提醒用户接手。当前服务/游戏进程必须重新检查，不把记录中的 PID 当作持久事实。
- 最终已回到大厅；整个玩家 snapshot 与 before-battle.sqlite3 一致，60 级 / 149 体力未变，新增一条试跑结算记录。服务日志 server06；可见窗口保持打开。
- 下一步补齐第一幕连续小节（2110802 起），再做权威掉落/奖励/主线推进；Hero/Mobility 普通战斗数值和体力业务仍待实现。下方 Phase 16 状态用于保留原始存档边界，已被本节更新的限制以本节为准。

## 接手时的确认状态

- 正式仓库：`x2_revive_workspace/`；分支 `feat/lobby-account-state`。
- Phase 16 实现与报告提交：`c565d3d`。
- Phase 15 实现提交：`c949714`；文档与证据提交：`28df044`。根目录 README 和本文件位于该仓库之外。
- 当前客户端：**Revival v0.2**，基于官方 2.4 / versionCode 202，包名 `com.siva.project.x2`。
- 已签名产物：`x2_revive_workspace/revival_client/build/X2_Eclipse_v2_4_Revival_v0.2-signed.apk`。已沿用现有开发签名覆盖安装并保留数据，并非官方 publisher signature；Phase 14–16 没有再改 APK。
- Reference `X2_Eclipse_v2_4.apk` 永久原样保存。v0.2 仅保留本地 Login_Url 与 packageType=testpackage 兼容修改，client_Type=product；版本细节见 [Phase 13(2026-09-23_01_phase13_first_contact.md)。
- 可见模拟器沿用 `X2-ABI-Probe-API30`、host GPU、GLESDynamicVersion、禁用快照；入口是内部 X2UnityActivity。窗口供用户观察和手动干预，不自动关闭。
- 已进入大厅；Phase 16 重登后显示 60 级、149/149 体力、已拥有的贝黑莫斯、第一章及首关。145 项测试通过。Phase 15 的 161 秒无断线观察仅属于当时操作窗口，不能扩大为当前入口的长期稳定性结论。

进程状态不是持久事实。接手时先检查模拟器与服务是否仍在运行；已有服务不重复启动，已有模拟器不重复启动。Phase 16 验证结束时两者保持运行，服务为 3600 秒限时进程。

已验证的游戏启动顺序：先保持本地服务运行，再用 `tools/android/open_lab_window.ps1` 打开可见模拟器并等待 Android 启动；通过 root ADB 启动内部 `com.siva.project.x2.X2UnityActivity`，等登录页出现后用已保存账号点击“开始跃迁”。Activity 返回成功只表示启动命令被接受，还要检查游戏继续运行并到达界面。

## 已实现模块

1. PackInt、CRC32、protobuf 子集、分帧、消息注册、TCP/session/dispatcher、零长度心跳兼容。
2. 本地 Bootstrap 与单账号临时身份；真实链路 `/loginwithpw` → `/apply/httpLogin` → TCP。`/apply/address` 尚未在当前账号链路实机验收。
3. 最小 L2C_Login 79、基础玩家推送 1000、配置 945/946、认证重连 337/338。
4. SQLite 基础玩家持久化、登录计数、修订号/冲突保护，以及 MainChapter/MainSection 同步。
5. 26 对大厅初始化/查询/点击消息；空账号状态、任务查询关联、明确拒绝未实现领奖。ButtonClick 不等于业务操作完成。
6. Hero 1003 和 Mobility 最小快照从 SQLite 提供给登录响应、玩家推送与 HeroAll 查询；主线章/节改用客户端表中的有效 ID。
7. `tools/prepare_lobby_account.py` 和 `tools/prepare_hero_mobility_account.py` 均显式备份后修改存档；已在当前账号执行，不能重复运行。`tools/android/open_lab_window.ps1` 启动可见窗口。

## 当前存档与保护边界

- 活跃实验库：`x2_revive_workspace/runtime/phase14/player.sqlite3`。
- 跳过教程前的备份：`x2_revive_workspace/runtime/phase15/before-lobby.sqlite3`，已存在，不能重复覆盖。
- 主线章/节准备已完成，客户端据此跳过开场视频/新手战斗；不代表全部 Tito 引导组完成。
- 玩家 1 / `revival` 保持 **60 级**。Phase 16 将占位章/节 `1/1` 修正为有效 `2010000/2110001`，补入本地 Hero 1003 和体力 149；修改前 60 级备份为 `runtime/phase16/before-hero-mobility.sqlite3`。不恢复为 1 级或覆盖任何备份。
- 原始日志、截图、数据库和备份位于忽略的 runtime 目录；不提交 token、设备标识或签名材料。

## 当前限制

- Hero、Mobility 最小持久化快照已实现，角色 1003 和体力 149/149 已在界面核对；发放、恢复、购买和消耗规则仍未实现。
- 正式物品、任务玩法、完整引导、Fight Session、Checkout 和 Reward 尚未完成。
- 空状态不代表官方发放/经济规则。ReceiveGiftRew 返回 E_ERROR_OPT=13；未开放活动返回 208，不伪造成功。
- Comet/Snowflake/Mail/Friend/Club/chatNode HTTP 服务未实现，聊天提示可能出现；未注册接口仍明确未实现。
- 本地单测试账号、限时服务、token 默认一小时；重启服务需重新登录，重连没有完整业务增量重放。
- 桌面启动图标、新安装设备、长时间运行与全部大厅入口没有验收。

## 下一次开发目标

Hero/Mobility 快照与主线第一章显示已完成。下一步按用户操作反馈补齐角色详情、体力业务、具体主线交互、Tito 引导和首战；不要把关卡显示等同于战斗与结算可用。在线服务继续保持明确未实现。

## 不要重复或误执行

- 不执行旧文档的“制作第一版 APK”“First Contact 未完成”“只收 54，不发 L2C_Login”。这些阶段已完成。
- 不使用 Phase 12 固定校验 v0.1 的 startup_probe 验收当前 v0.2；不使用超时遗留的无效 `v0.2.apk`。
- 不重做全 APK/1501 bundles 扫描、批量导出、已恢复协议/schema/GameConfig selection；已有证据优先复用。
- 不重建现有 TCP/Bootstrap/SQLite/大厅接口，不统一返回成功掩盖缺失业务。
- 不下载新 SDK/镜像，不回到 API 27、ARM bridge、WHPX 或 hosts/proxy/remount/guestfwd 实验。
- 不修改 Reference，不卸载或清应用数据，不重置 60 级存档，不覆盖备份，不擅自关闭窗口或重复启动模拟器。

当前工作入口为根目录 [README(../../README.md)、本文件和 [Phase 16 报告(2026-09-23_04_phase16_hero_mobility_mission.md)；实现细节再按需读取仓库。历史阶段报告用于查证，不替代当前任务范围。
