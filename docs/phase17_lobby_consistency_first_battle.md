# Phase 17 — Lobby consistency and first battle entry

日期：2026-09-23。Source of Truth：根目录 `README.md`、`SESSION_HANDOFF.md`、
`docs/phase16_hero_mobility_mission.md` 与真实客户端行为。沿用 Revival v0.2、
玩家 1 / `revival` 的 60 级 SQLite 存档。没有修改 Reference APK、清除应用数据、
重置存档或覆盖已有备份；本阶段未处理任务系统。

## Chat

- 已有客户端静态证据：`ChatModule.GetChatServers` 使用 HTTP POST 获取聊天节点列表；
  解析非空列表后才选择节点。`ChatNetManager` 有 GetChatServer、ConnectSocket、
  ConnectServer、Connected 状态，连接使用独立的 `MarsNet`。现有本地 HTTP 服务
  没有 `/apply/chatNode` 合同。此前阶段已记录该请求未实现。
- 本次客户端在登录前崩溃，未能捕获真实聊天请求或首次 socket 数据。因此聊天节点
  的有效响应格式、endpoint、握手、心跳和停止重连的最小条件尚未确认。
- 未加入猜测性的 Chat Null Server；重连是否停止：**未验证**。主游戏 TCP 服务
  未修改。

## UI

- 用户报告的界面重叠尚未复现到可取证状态；旧界面没有退出的原因仍未知。
- 未修改 Canvas、GameObject、MainHallFSM、UI stack、Guide/Tito 或账号引导标记。
- 大厅→角色→大厅、大厅→主线→大厅、大厅→战斗选人→大厅：**本次未验证**。

## Battle

- 本次没有在真实客户端点击“开始挑战”，故不能声明请求顺序。
- 没有新增 PrepareMainMission、FightData 或其他战斗合同，没有扣体力。
- Section 2110001 / Map 2210001：**未加载**；未进入战斗场景，也未触及结算。

## Tests

- `PYTHONPATH=src .venv/Scripts/python.exe -m pytest -q`：**145 passed**。
- 未改动代码和现有玩家数据库。

## Current blocker

按已验收流程，先确认现有本地服务仍运行（PID 41316），随后用
`tools/android/open_lab_window.ps1` 启动可见模拟器，并通过内部
`com.siva.project.x2.X2UnityActivity` 启动游戏。首次启动于 14:10:29、
仅对游戏进程执行 force-stop 后的第二次启动于 14:12:58，均在登录页前报
`Using memoryadresses from more that 16GB of memory`，随后 Unity 原生
`SIGSEGV`。Activity 启动命令返回成功，但客户端没有正常进入登录页。
模拟器与服务仍运行，未清数据。依照本阶段“两次尝试未定位就停止”的约束，
没有扩大 Android/GLES 逆向范围。**唯一主要 blocker：客户端启动崩溃，
无法做 Chat、UI 与首战的真实客户端验证。**
