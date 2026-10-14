# 世界 BOSS 等待大厅超时与退出补修（2026-10-14）

用户反馈进入等待大厅后提示人数不足并无法退出。当前本地服务器最新日志没有该次操作；MuMu端口7555未运行，无法抓取现场Unity栈。以下是代码与2.4原生客户端中确认的协议缺陷及对应修复，需用户复测实际反馈场景。

## 时间单位

WorldBossModule.Tick RVA 0x1377424：0x13774C8读取WorldBossInfo.stateFinishTime，0x13774CC–0x1377514为有符号整数除1000；随后0x1377514调用GetCurTimeSecFrom1970，0x137753C比较是否到期。故该wire字段为Unix毫秒。此前查询、独立Boss socket通知以及PlayerDataProto雷达内的StateFinishTime均直接发送数据库秒值；修复为wire乘1000，数据库和服务端有效期判断仍以秒存储。

## 状态与退出

WorldBossState JOINABLE=1,FIGHT=2,OVER=3,DISMISS=4。原生HandleAfterEnterMassScene RVA0x1375900在FIGHT调用StartEnterTimer（0x1376090），由本地配置MassCompleteTime启动约10秒开战流程。保留已有单人加入即state=FIGHT的规则，不伪造人数，不要求30/50人集结。

LEAVE现在先校验玩家对该实例的所有权或成员关系，清理active；不再以“今天的Boss”、有效期或当前等级作为退出前置。旧的玩家专属不透明ticket只可用于认证退出，过期ticket仍不得JOIN或DAMAGE。退出不创建当天新Boss、不重置日状态、不扣挑战次数，重复请求幂等。

原生OnHandleW2CDoBossAct 0x13755A0在0x1375664先UpdateChallengeWorldBossInfoChange，再按act调用LeaveWorldBoss；若LEAVE回包包含state=DISMISS的bossInfo，将先重入解散弹窗。退出回包省略bossInfo，UpdateChallenge...在0x1374064对null直接返回，随后0x1375828正常LeaveWorldBoss，避免解散循环。旧缓存退出回包同样去除bossInfo。

回归用例覆盖单人入战、数据库秒与wire毫秒、雷达一致性、终止状态/午夜轮换退出、请求重放、不扣次数、不创建新Boss以及跨账号/过期ticket安全边界；同时运行全部原有test_world_boss.py。

本轮只改服务端，无APK改动。未从现场日志确认“人数不足”的唯一触发原因，不能把上述修复当作远程实机验收结果。
