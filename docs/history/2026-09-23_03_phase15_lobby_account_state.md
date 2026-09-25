---
Document-Type: Historical Report
Date: 2026-09-23
Status: CURRENT_AT_TIME
Superseded-By:
  - (read alongside current knowledge)
---

# Phase 15 — 可见模拟器与大厅开发账号

日期：2026-09-23。分支 `feat/lobby-account-state`，基线 `f58ded8`。
用户授权以账号状态跳过教程，并要求开启模拟器窗口供观察和手动操作。
本阶段不修改 APK，不清空应用数据，不关闭用户的模拟器窗口。
实现与测试提交：`c949714`。回归测试：**143 passed**。

## 当前成果与边界

- 新增可见窗口启动工具 `tools/android/open_lab_window.ps1`，沿用 API 30 AVD、host GPU、
  GLESDynamicVersion 和禁用快照设置，不传 `-no-window`，不自动关闭窗口。
- 玩家基础快照支持 MainChapter / MainSection。新增显式运行的账号准备工具，修改前通过
  SQLite backup API 保留完整旧库；只把小于 1 的主线章/节提高到 1，不重置后续进度、货币或登录次数。
- 实际客户端跳过开场视频/新手战斗，显示主大厅，并能打开空背包。
- 恢复 26 对大厅初始化/查询/点击消息的编号和字段。新加入的业务状态仅代表本地空账号：
  没有在线活动、装备、时限物品、特权或增益。任务查询保留请求中的类型和章节。
- ReceiveGiftRew 返回 E_ERROR_OPT=13，不发奖励；未开放活动查询返回
  E_ACTIVITY_REAL_NOT_OPEN=208。ButtonClick 只确认遥测，不发奖励或推进引导。
- 未注册接口继续保持明确未实现；HTTP Comet/Snowflake/Mail/Friend/Club/chatNode 仍未实现，
  聊天提示可能出现。没有用一个通用成功响应伪装所有服务。

**这不是完整可玩版本。** Hero 登录快照仍为空，展示角色 1003 不等于已拥有角色；
体力快照仍待补齐（当前界面显示 -1/60），任务、正式背包物品和战斗均未实现。
账号准备工具绕过的是 MainHallFSM 开场战斗门槛，不声明所有 Tito 引导组已完成。

## 证据

所有来源均为已有 2.4 dump.cs / libil2cpp.so，未联网取得新资产。

| 事实 | 依据 |
|---|---|
| 开场战斗门槛 | MainHallFSM.NetSyncUpdate 0x13BBC00 读取运行时 BaseInfo+0xC0（MainSection）；0 进入 newbeeBattle，非 0 进入 MainAni |
| 主线字段编号 | BaseInfoProto.Serialize 0x30A2184/0x30A21D0 写入 varint tag 0x108/0x110，即字段 33/34，读取 +0xC4/+0xC8 |
| 大厅消息编号 | ERequestTypes；SeasonIcon 的响应是 1001，不是 1000（1000 为玩家快照） |
| 任务关联 | GameTask Serialize 0x3AB13B0，code/type/taskList/boxList/chapterId 等按字段 1..8；请求 0x3982258 |
| 活动与奖励拒绝 | GameLogicErrCode.E_ERROR_OPT=13、E_ACTIVITY_REAL_NOT_OPEN=208；ReceiveGiftRew Serialize 0x37320C4 |
| 按钮点击 | C2L_ButtonClick 376 / L2C_ButtonClick 377；Serialize 0x3CA59C4 / 0x3AFF3E8 |
| 英雄后续线索 | HeroModule.CheckHeroUnlock 0x190E8A8 比较 state==2；HeroData.Serialize 0x3525840，HeroAll 546/547。尚未把此分析作为已实现英雄发放 |

每个恢复消息的定向反汇编保留在忽略目录 `runtime/phase15/C2L_*.txt`、`L2C_*.txt`。
原始日志、截图、数据库及备份均在 runtime 下，不提交账号 token 或设备标识。

## 复现

先停止本地游戏服务，再准备已有测试账号（首次使用需先完成一次登录以创建玩家）：

```powershell
$env:PYTHONPATH='src'
.venv/Scripts/python.exe tools/prepare_lobby_account.py `
  --database runtime/phase14/player.sqlite3 --backup runtime/phase15/before-lobby.sqlite3
```

备份路径必须不存在；工具拒绝覆盖旧备份。回滚时停止服务，另存当前数据库后，
以该备份替换数据库路径。此工具是开发夹具，不在每次登录时自动覆盖玩家进度。
本次实验已运行，备份为 `runtime/phase15/before-lobby.sqlite3`，不要重复覆盖。

```powershell
./tools/android/open_lab_window.ps1
$env:PYTHONPATH='src'
$env:X2_LOCAL_ACCOUNT='revival'
$env:X2_LOCAL_PASSWORD='revival-local' # 专用实验值
.venv/Scripts/python.exe tools/local_game_server.py --database runtime/phase14/player.sqlite3 --seconds 3600
```

模拟器已存在时不要重复启动。游戏仍通过已验证的内部 X2UnityActivity 启动；
桌面图标和新安装设备未验收。服务本次为限时实验进程，默认 token 一小时有效；
服务重启后重新登录。窗口保持开启供手动操作。

## 实验过程

- probe01：设置账号前已备份；本次启动时发现模拟器未运行，随后按用户要求用可见窗口启动。
- probe02：第一批 8 个查询后进入大厅；新暴露 15 个初始化请求导致重连。
- probe03：第二批回复生效，无空引用；进一步出现 QuerySharedMessage / AccountBuffData。
- probe04：大厅连接遮罩消失，空背包可打开；点击背包产生 ButtonClick 376，未回复导致约 8 秒后重连。
  此次原因是按钮遥测请求，不是心跳协议，不能仅凭单张大厅截图宣称长期稳定。
- probe05：补上 ButtonClick 后复验，大厅与空背包可往返，点击回复正常；观察期内未出现
  未注册 TCP 消息、协议错误或认证重连。连续观察 161 秒，1 条 TCP 连接、0 次断线、
  0 次空引用异常。详见 [脱敏证据(../../evidence/raw/runtime_traces/phase15_lobby_evidence.json)。此为有限观察窗口，非长期稳定性承诺。

测试覆盖：未认证大厅请求拒绝、所有 26 对消息通过真实本地 TCP 回复且保持 requestId、
任务类型/章节和增益 ID 关联、领奖拒绝且数据库无变化、账号准备备份/持久化/后续进度保留。

下一步先补齐持久化 Hero 与 Mobility 快照，再逐步恢复已进入界面的业务操作、Tito 引导状态和首战。
聊天等在线服务可以继续明确隔离，但不能靠返回成功掩盖未实现的数据合同。
