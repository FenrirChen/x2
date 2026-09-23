# MuMu 人工试玩环境迁移

日期：2026-09-23。本报告只验收日常客户端验证环境；业务进度仍以 Phase 19 报告和根目录交接为准。用户另行手动确认这条启动路径没有问题。

## 结论

MuMu 12 可作为主要人工试玩环境，现有签名 Revival v0.2 直接可用。MuMu 的 `10.0.2.2` 能访问 Windows 上仅监听 `127.0.0.1` 的本地服务，因此没有修改 APK、服务绑定或网络设置，也没有制作 v0.3。登录沿用当前 SQLite 存档，正常登录计数会照常更新；没有清库或重置玩家。Google `X2-ABI-Probe-API30` 仍作为参考和底层复现环境保留。

## 实际发现

| 项目 | 验证结果 |
|---|---|
| MuMu 安装根目录 | `D:\MuMuPlayer-12.0\MuMuPlayer`，由运行中进程路径反查 |
| 主要进程 | `MuMuNxMain.exe` PID 10604；`MuMuNxDevice.exe` PID 43584；`MuMuVMMHeadless.exe` PID 37712（仅为本次观察，不可当作固定 PID） |
| 系统 ADB | `C:\Users\18207\AppData\Local\X2RecoveryLab\android-sdk\platform-tools\adb.exe` |
| ADB endpoint / serial | MuMu VM 进程监听 `127.0.0.1:7555`；现有 ADB `connect 127.0.0.1:7555` 后显示 `device` |
| MuMu 自带工具 | `nx_main\adb.exe`、`nx_device\12.0\shell\adb.exe`、`nx_main\MuMuManager.exe`；本次无需切换 |
| Android / API / 型号 | Android 12 / API 32 / V2366GA |
| ABI / 分辨率 | `x86_64,arm64-v8a,x86,armeabi-v7a,armeabi`；设备 `720x1280`，游戏横屏截图 `1280x720` |
| 已装客户端 | `com.siva.project.x2` 的 `base.apk` SHA-256 为 `460dc657a8fb1b5410a4c0eaa5fac9433b45ecc54b7f3845afc626420946276d`，与现有签名 Revival v0.2 完全一致；没有重装 |
| MuMu 网络 | guest `wlan0=10.0.2.15/24`；到 `10.0.2.2` 经 `wlan0` 路由 |
| 宿主机地址 | **`10.0.2.2`**，由 guest 实测可达，不是根据模拟器类型推断 |
| 本地服务 | 已有 Python 进程使用 `runtime/phase14/player.sqlite3`；HTTP `127.0.0.1:18080`、游戏 TCP `127.0.0.1:29000`、空聊天 TCP `127.0.0.1:29001`；未重复启动 |

MuMu 内执行 `POST http://10.0.2.2:18080/apply/controlInfo` 得到 HTTP 200；`nc` 到 `10.0.2.2:29000` 连接成功。正常游戏登录后，既有服务日志记录本地身份认证、玩家 1 的登录响应、服务配置和大厅查询；客户端画面显示 `Revival` 60 级、体力 `149/149`、金币 `800`。这同时证明 Bootstrap、TCP、登录与当前 SQLite 存档链路可用。首次登录大厅的截图保存在忽略的 `runtime/mumu/afterstart.png`。

## 可重复启动顺序

1. 保持现有服务运行；先检查 `18080/29000/29001` 是否已有监听，避免重复启动。如果没有服务，在仓库目录使用现有入口和 `runtime/phase14/player.sqlite3`，不得恢复旧备份或初始化存档：

   ```powershell
   cd D:\demo\x2\x2_revive_workspace
   Get-NetTCPConnection -LocalPort 18080,29000,29001 -ErrorAction SilentlyContinue
   # 仅在没有现有服务时，在单独 PowerShell 窗口运行并保持窗口开启：
   $env:PYTHONPATH='src'
   $env:X2_LOCAL_ACCOUNT='revival'
   $env:X2_LOCAL_PASSWORD='revival-local'
   .venv\Scripts\python.exe tools\local_game_server.py --database runtime\phase14\player.sqlite3 --seconds 3600
   ```
2. 用户打开已经安装的 MuMu；不要重新安装或修改 Google AVD。
3. 在 PowerShell 中复用现有 SDK ADB：

   ```powershell
   $adb = 'C:\Users\18207\AppData\Local\X2RecoveryLab\android-sdk\platform-tools\adb.exe'
   & $adb connect 127.0.0.1:7555
   & $adb -s 127.0.0.1:7555 devices -l
   & $adb -s 127.0.0.1:7555 shell am start -W -a android.intent.action.MAIN -c android.intent.category.LAUNCHER -n com.siva.project.x2/com.dh.platform.widget.SplashActivity
   ```

4. 客户端正常入口 `SplashActivity` 会进入 `X2UnityActivity`；首次在 MuMu 输入现有本地账号并点击“开始跃迁”。本次重新启动后账号和密码已保留，正常入口再次到达登录页。用户随后手动确认完整路径无异常。

若日后 MuMu 实例或网络配置改变，重新检查 ADB endpoint、guest 路由及 `10.0.2.2` 实测结果；本次观察的 PID 和地址不得无条件套用到新实例。当前无需 v0.3。

## ADB 日常操作

| 能力 | 结果 |
|---|---|
| launch / input tap / input swipe | 已通过，含登录页输入与正常入口启动 |
| logcat / screencap | 已通过 |
| push / pull | 已通过临时文件往返，SHA-256 一致；临时 guest 文件已删除 |
| dumpsys / pm path | 已通过 |
| package install | 已装包 SHA-256 已核对，遵照“不重复安装”要求，本次未执行安装；标准 ADB 仍可用于以后缺包时安装签名包 |

本轮未运行 pytest：仅整理环境验证文档，没有修改业务代码。此前 Phase 19 的测试记录为 `154 passed`，不能当作本轮重新运行结果。Reference APK、Revival v0.2、玩家等级与已有备份均未改动；测试登录会正常更新现有存档的登录记录。
