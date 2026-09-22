# Phase 12 — 稳定启动（实验入口验收通过）

日期：2026-09-22。范围：固定 Revival v0.1 APK，在现有 API 30 AVD 上
建立可重复的冷启动路径，验证到达本地 Bootstrap。此阶段不实现 Login 业务。

**结果：gles01、gles03、gles04 三次相同最终图形配置的独立冷启动通过。**
均进入 Awake、主进程存活、controlInfo HTTP 200，无已知 memory/shader 错误，
且逐一查看截图，均为正常“正在构建领域”画面。客户端尚停留在加载阶段，
没有进入登录；本结论限于本机现有 AVD/应用数据和 ADB 实验入口。

## Git 基线

- 分支：`feat/stable-client-startup`。
- `c29320e` 保存进入本阶段之前已有的 Phase 11 补丁、Bootstrap 和测试改动。
- `428bc15` 保存可复现冷启动工具、运行说明和回归测试。
- APK、开发签名私钥、ADB 私钥、运行日志和截图不入 Git。
- Reference APK 不修改；Revival v0.1 SHA-256：
  `b6a95c274cd61a91d2c4ab1ea448a300669bbc91861e989c1593da8dd071f98f`。

## 实验原则与边界

- 同一 `X2-ABI-Probe-API30`，同一已安装 APK，同一应用数据；不 wipe、不重装。
- `-no-snapshot` 禁用快照读取和保存；每次真正退出模拟器后再启动。
- 使用 root ADB 直接启动非导出的 `X2UnityActivity`，这是实验入口，
  不代表桌面图标的渠道 Splash 入口已修复。
- 新观察工具 `tools/android/startup_probe.py` 仅启动 HTTP Bootstrap，
  不开 TCP listener，不发送 Login；成功退出要求 controlInfo、Awake、存活进程
  且无已知 memory/shader 错误，画面和重复冷启动仍需独立验收。
- 原 `android_preflight.py` 针对 Reference APK + hosts/QEMU 导流，
  不适用于当前已签名、改 GameConfig 的 Revival 路线。新工具检查指定 AVD、
  启动完成标志、root、已安装 APK 哈希；不声称已验证网络隔离。

## 实验记录

原始证据位于未跟踪的 `runtime/phase12/`，每个正式 probe 子目录包含
`result.json`、`logcat.log`、`screen.png`、`ui.xml`；结果附带文件哈希。
可提交的脱敏摘要与文件哈希见 [证据索引](phase12_startup_evidence.json)。

| Run | 变化 | 已观察结果 |
|---|---|---|
| cold01 | 软件渲染，禁用快照 | Awake、controlInfo HTTP 200；纯紫画面、shader platform 5 错误；无 16GB 报错 |
| host01 | 仅改 `-gpu host` | controlInfo HTTP 200；进程存活；shader 错误仍在；guest GLES=131072 |
| gles01 | host 基础上加 `-feature GLESDynamicVersion` | GLES=196609；Awake、HTTP 200、正常游戏加载画面；无 memory/shader 错误 |
| gles02 | 相同运行参数，脚本化冷启动 | APK 哈希读取超过 30 秒；尚未启动游戏，不计客户端结果 |
| gles03 | 哈希读取超时改为 120 秒，客户端参数不变 | Awake、HTTP 200、正常游戏加载画面、进程存活；无 memory/shader 错误 |
| gles04 | 最终脚本、相同客户端参数 | Awake、HTTP 200、正常游戏加载画面、进程存活；无 memory/shader 错误 |

`cold01` 是手工探索，旧 first_contact_runner 的结果 JSON 因不同执行身份的
目录权限写入失败；HTTP 200 来自当时服务输出，不能冒充结构化结果文件。
后续实验统一用新 probe 和同一执行身份。

## 当前发现

- CONFIRMED：host01 的安装包哈希匹配固定 Revival；实际 ABI 为 arm64-v8a。
- CONFIRMED：host01 宿主渲染日志报告 GLES 3.0，guest 却声明 GLES 2.0。
- CONFIRMED：仅增加动态 GLES 开关后，guest GLES 从 131072 变为 196609，
  shader 错误消失，纯紫画面变为“正在构建领域”的正常加载画面。
- UNKNOWN：早前 16GB 报错根因。未复现不等于证明快照是原因。

模拟器自身 `lib/advancedFeatures.ini` 说明动态版本关闭时最大 GLES 按 <=2
处理。`emulator -help-feature` 确认可通过单次启动参数开关，无需修改 SDK。
图形后端参数参考 [Android 官方文档](https://developer.android.com/studio/run/emulator-acceleration)。

## 验收

已满足三次相同最终图形配置的独立冷启动验收。gles02 的工具校验超时
单独保留，不计客户端启动次数；放宽哈希读取时限没有改变游戏或模拟器配置。
gles01 为手工启动，gles03/04 为脚本启动；三者均禁止快照，使用同一 AVD、
host GPU、GLESDynamicVersion、arm64 APK 和内部 Activity。

复现命令见 [Android 工具说明](../tools/android/README.md)。最终保留的参数为：

```text
-avd X2-ABI-Probe-API30 -port 5554 -no-window -no-boot-anim
-no-snapshot -gpu host -feature GLESDynamicVersion
```

没有编辑 AVD config.ini、SDK、系统镜像或 APK。三次画面正常仅代表初始加载
可渲染；不代表战斗画面、全部资源或后续渲染已验证。

## 检查与下一步

- `pytest`：134 passed；PowerShell 启动脚本语法检查通过。
- 本地虚拟环境没有 ruff/mypy，未执行这两项；没有为此安装依赖。
- 本轮重新核对 Reference APK SHA-256 与原记录一致。
- 下一阶段从正常加载画面继续：定位 controlInfo 之后的初始化/渠道 SDK
  等待点，再验证 connectInfo/address 和第一条真实 TCP 请求。
- 未增加或发送 Login 响应，未改变玩家数据、客户端 ABI 或游戏逻辑。
- 本阶段只证明现有应用数据下的实验启动路径；未证明全新安装、图标启动、
  长时间运行、完整外网隔离或完整游戏可玩。
- 完成后确认 ADB 设备列表为空，18080/29000 均无监听；未留下观察服务。
- 根目录 README/SESSION_HANDOFF 不属于服务器 Git 仓库，已添加最新入口提示；
  正式、受版本管理的验收记录以本报告为准。
