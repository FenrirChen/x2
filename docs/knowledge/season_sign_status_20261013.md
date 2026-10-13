# 赛季每日签到宝箱状态修复

日志 2026-10-13 19:21:30 的 C2L_SignBattlePass (949) 被拒绝：season sign already collected。并非请求未收到。

客户端 BattlePassTaskTab.Refresh (0x14c928c) 读取 LastBattlePassSign，调用 GameAPI.CheckTimePassDay (0x154e450)。后者比较日期及 05:00 阈值。服务端原先直接发送北京时间零点 sign_day，已领取状态会被误判可领取。

base_info 现在投影权威领取状态：当天已领取发送当前服务端时钟；当天可领取发送 0。查询、签到响应和后续赛季同步共用此处。两个原生日期转换方法使用相同静态基准，不能仅凭 GetTempDateTimeFrom2018 名称对其中一个字段减去 2018 偏移。保留服务器午夜重置政策、原始领取日和去重凭证，重复签到仍拒绝且不再次发奖。无需客户端补丁。

回归覆盖不同小时、旧零点标记恢复、午夜重置、重复请求不增经验及赛季协议/任务链。
