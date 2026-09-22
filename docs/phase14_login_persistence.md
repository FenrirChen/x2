# Phase 14 — 最小登录回复与玩家持久化

日期：2026-09-22。阶段三；分支 `feat/minimal-login-persistence`，基线 `23cb15f`。
本阶段沿用已安装的 Revival v0.2，不再修改或重签 APK。Reference 保持不变。
实现与测试提交：`e1fb06e`；阶段报告和脱敏证据随后独立提交。

## 已实现范围

- 本地 HTTP 身份 token 验证后发送 `L2C_Login`（79），成功码 **10**。
- 随后以 requestId=0、dataVersion=1 推送 `PlayerDataProto`（1000），包含基础玩家数据。
- SQLite schema v1 保存账号映射、玩家 ID、创建时间、登录次数、基础快照、存档修订号。
  创建与计数在事务中完成；再次登录不覆盖快照。快照更新要求匹配修订号，冲突回滚。
- `C2L_ReConnect`（337）验证同进程有效 token 后回复 338，不增加登录次数。
- 配置请求 945 回复 946，code=10；回显客户端内置 `PowerBuyNum=120`，其余保持内置配置。
  不能发送空列表：该客户端 protobuf 解码会留下 null，回调直接读取 Count 导致异常。
- 消费单字节零长度心跳；普通包仍执行原有长度及 CRC 检查。
- 登录身份绑定到当前 TCP 连接；允许客户端预先排队的空 session 字段，拒绝不匹配的非空 session。

这是**最小身份与基础玩家快照**，不是完整玩家服务或已可玩的大厅。英雄、装备、背包、
任务等登录嵌套快照目前为空；不会把空集合描述成恢复了官方初始发放。
昵称 Revival、等级 1、货币/经验 0、展示角色 1003 是明确的 TEMPORARY_COMPAT 默认值。
展示角色不等于已拥有角色；后续英雄快照必须单独实现。

## 协议证据

| 内容 | 静态来源及结论 |
|---|---|
| Login 成功码 | LoginManager.OnReceiveLoginMsg 0x1AE8774 比较 0xA；GameLogicErrCode.E_Ok=10 |
| 登录后状态 | LoginFinish 0x1AE9CB8 → AppMainImpl.FinishLogin → MainHallFSM |
| 玩家快照 ID | MessageReflector..cctor 0x1428640 将 PlayerDataProto 映射到 **1000**；生成类 get_PID=0 不能直接作网络 ID |
| BaseInfo 字段 | BaseInfoProto.Serialize 0x30A1348：1 Id、2 NickName、3 Level、4 Crystal、5 Gold、6 Exp、8 Show |
| 快照容器 | PlayerDataProto.Serialize 0x2DBA468：field 1 BaseInfo；NetSyncData.Merge 0x174916C 合并玩家对象 |
| 同步门槛 | MainHallFSM.NetSyncUpdate 0x13BBA98 检查 BaseInfo.Id>0，之后开始模块/开场流程 |
| 心跳 | MarsNet..cctor 0x3E4E024 创建长度 1 的零初始化 tick；HeartBeat 0x3E4D874 RawSend；decoder 0x3E4E584 跳过零长度包 |
| 重连 | ERequestTypes 337/338；L2C_ReConnect.Serialize 0x34A15DC 字段 1 code、2 id、3 fightDataProfile、4 serverTime |
| 服务端配置 | ERequestTypes 945/946；Serialize 0x36A2578；MainModule.OnReceiveServerTableConfig 0x13C9AA4 接受 code=10，遍历 keyVal 后发就绪事件 |
| 非空列表兼容 | KeyValuePair_String_String.Serialize 0x37A6244：1 key、2 val；ServerData..ctor 0x13CD05C 将 120 写入 PowerBuyNum。只回显此默认值，不声称恢复了原服务器经济参数 |

临时反汇编输出和完整客户端日志位于忽略目录 runtime；只提交摘要，不提交设备标识、token 或签名材料。

## 运行

现有 API 30 AVD 仍使用 Phase 12 图形配置与内部 X2UnityActivity 入口。
该入口与当前应用数据已验证；桌面启动图标、新安装设备尚未验收。

```powershell
$env:PYTHONPATH='src'
$env:X2_LOCAL_ACCOUNT='revival'
$env:X2_LOCAL_PASSWORD='revival-local' # 专用实验值，勿使用真实账号
.venv/Scripts/python.exe tools/local_game_server.py --database runtime/player.sqlite3 --seconds 3600
```

只监听本机 127.0.0.1；返回模拟器可访问的 10.0.2.2。退出可按 Ctrl+C。
每次服务器启动签发新的临时 token，已有数据库继续使用；服务重启后需重新进行账号登录。
重连只恢复同进程的已认证连接，不实现业务增量重放。数据库存档 revision 与网络 dataVersion
含义不同：当前每次完整登录重新发送版本 1 基础快照；后续业务增量需要单独设计。

## 实验记录与后续

- probe01：code=10 最小登录回复已被客户端接受，随后请求 945；心跳被旧解析器误判，已修正。
- probe02：同一 SQLite 文件重启服务，login_count=2；推送基础快照后客户端离开账号页面，
  进入开场画面并请求多个模块。没有再出现心跳解析错误；未实现请求导致超时重连。
- probe03：login_count=3；严格 session 检查误伤客户端排队的空 session 请求；观察到真实 337
  并成功认证回复，后续修正空 session 时序兼容。
- probe04：login_count=4；不再出现心跳或 session 协议断线，真实重连认证通过；
  配置空列表触发 MainModule.InitServerTableData 空引用，定位并改为回显一条内置默认值。
- probe05：定时服务在点击登录前结束，出现网络提示；没有产生新的数据库登录记录。
- probe06：重启服务并重试，login_count=5；登录、基础快照、配置及真实重连均被接受，
  客户端进入开场动画。采集窗口中没有再出现 InitServerTableData 空引用或服务端协议错误。
  仍有视频渲染 GL_INVALID_ENUM 日志，以及未实现大厅请求导致的超时重连，不能视为大厅验收通过。

脱敏证据见 [phase14_login_persistence_evidence.json](phase14_login_persistence_evidence.json)。

回归测试：141 passed。新增测试覆盖首次创建、保存后重启/再次登录不重置、修订号冲突回滚、
未来 schema 拒绝、错误认证无数据库写入、登录/推送的消息号和请求关联、配置嵌套字段、
心跳与分片普通包混合、重连不增加登录次数、伪造非空 session 拒绝。
数据库/协议版本及启动工具仍是本地实验范围，尚不提供账号注册或多用户服务。

后续大厅依赖清单（真实请求，尚未实现）：782 QueryTelInfo、999 SeasonIcon、
715 QueryItemLimitTime、576 QueryDivination、669 QueryNotic、805 NoticPushInfo、
776 QueryReturnInfo、432 SystemInfo，以及 Comet/Snowflake/Mail/Friend/Club HTTP 服务。
不能用统一成功包代替这些接口；需要逐项恢复合同、确认是否阻塞大厅、补足最小状态。

下一阶段优先完成英雄与大厅必需初始化，维持连接并验证可操作大厅；随后再做引导和首战。
