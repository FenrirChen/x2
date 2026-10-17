# 新账号好友初始化与剧情首次起名（2026-10-17）

## 首次起名

客户端 `PlotHelper.HasPlayerName`（RVA 0x15BC9CC）在 0x15BCA50 读取 `NetSyncData.PlayerData.BaseInfo+0xC8`，随后判断其大于 0。dump.cs 中这个字段是 `BaseInfo.NickCount`，不是昵称字符串。

`PlotHelper.ShowNamePlayerWindow`（0x15BC874）在 0x15BC8A8 调用上述判断；已经起名则直接调用剧情回调，不再弹窗。原服务端只保存 nickname，没有声明、下发 NickCount，所以退出战斗重开或回看剧情时客户端仍按未起名处理。

修复：

- 声明原生 `BaseInfoProto.NickCount`（字段 36），在登录、重连和玩家快照更新中明确下发。
- 新号初值 0；首次 opt=7 起名成功时，昵称和 nick_count=1 在同一事务保存，先推送 BaseInfo 再回应成功。
- 重复同名请求幂等，不重复增加次数；已经起名后，剧情 opt=7 不能换成另一个名字。普通付费改名 opt=0 的既有行为没有在本轮扩展。
- 老账号和旧存档已有非空昵称但没有计数时，兼容判断为至少起名一次；不要求批量重写玩家数据。显式大于 1 的计数保留。
- 完整存档包含 players.snapshot 中的计数；旧存档跨账号导入也根据原昵称恢复标记。新增字段验证为非负 int32。

## 好友列表

V1 `/FriendService.GetFriendList` 原本存在，原生 `FriendModule.InitData` 调用的 `GetFriendServerList`（0x1522F78）在 0x1523070 发起 `GetFriendListAsync`，即 V1。V1 返回 `Friends: FriendList`，其中包含 Friends、Applys、Blacks、SendApplys。

确认的问题是 `/FriendService.GetFriendListV2` 原来直接复用了 V1 的嵌套对象。但 dump.cs 的 `GetFriendListV2Reply` 明确为 `Total:int` 和 `Friends:FriendItem[]`。已恢复 V2 的扁平数组与总数，支持按 page/pageNum 分页；页号从 0 起，默认一次返回全部角色（上限 200）。V1 的既有原生结构保持不变。

没有降低接口鉴权要求。新账号等级 1、未起名时，仍可按既有单机方案查询全部 39 个角色好友。测试走真实账号注册与 HTTP 身份生成，再经过 LocalIdentityService→SocialAPI→SocialService→名片查询→449/450 好友同步，验证新号初始化，而非只调用 friend_list 辅助函数。

本轮无法连接 MuMu 127.0.0.1:7555，未获取用户现场日志，不能把 V2 的结构问题断言为原版 V1 初始化异常的现场原因。V1 新账号链路测试可正常完成，若用户仍遇到初始化故障，需要对应服务端请求日志继续定位。

## 远程状态

本轮开始时已完成上一次授权推送：远程 main 从 f773b77 更新到 40a49e7，包含四份 PR 本地整合、补修和 #56 累计历史拓展，已用 ls-remote 核对。下面这次新账号修复单独提交，尚未推送。


## 验证与本地部署

- 新账号好友与起名链路、原序章引导、社交与外观测试：44 passed，5 deselected（34.59s）。
- 账户存储、玩家存储、完整存档、注册开关：35 passed（34.67s）。
- 5 项旧注册测试仍使用旧邮件总数（5/4），当前业务实际为 6/5；其中代表性用例用 40a49e7 的原登录、新账号代码复现同样失败，属于既有断言过期，未改动邮件业务。
- 2026-10-17 12:17:10 已备份并重启本地服务；connectInfo 返回 local，HTTP 18080 / game 29000 / chat 29001 就绪。
- 测试玩家快照、家园状态、赛季状态与重启前完全一致；数据库 quick_check=ok。
- 备份：runtime/before_onboarding_20261017_121710/player.sqlite3。
- 新修复未修改 APK，客户端手动验收尚未进行。
