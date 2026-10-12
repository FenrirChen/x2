# 阏逢敛遗结算卡住：活动专用消息错误分发

2026-10-12 10:24:27，测试玩家 5 通关 2161114。服务端成功保存
run=663295b4-0ae3-40d1-94e9-270f0ce8d987 的结算和奖励：
经验 18、神格经验 54、光辉 30、活动币 160、道具 1290306 ×1。
结算前推送 L2C_QueryActivityMissionRecord，随后 152 应答 code=10。

Unity 栈为 ArgumentOutOfRangeException / List.get_Item →
YueXiModule.RefreshRePrintPovUnlock → OnHandleQueryActivityRecord →
MarsNetManager.OnPushMsgProcessor。专用消息处理器无视当前活动主题，
用阏逢敛遗的通关数据索引日月盈仄 POV 配置，导致消息派发中断。
客户端每八秒重连重发结算；服务端返回成功，客户端每次重现同一异常。
最后一次旧代码返回 code=13；入口从 09:58:36 到结算 10:24:27，尚未超过一小时，
最终拒绝来自重放请求指纹不一致，不能把它归因于入口超时。

来源：上一轮日月盈仄进度修复把其专用推送扩展到了所有活动，是本项目回归。
修复将 QueryActivityMissionRecord 的主动推送限定为 group=99；其他主题
仍保留 SceneGlobalParam、ActivityPassRecord 和各自 MissionData。
非日月盈仄主题误请求该专用查询时，返回 code=13，避免派发错误成功数据。

旧指纹包含外层 battleFileBytes/battleFileString/sendTag，这些附属字段不参与
结算，重连重传不应因此被视为新的奖励请求。新指纹只覆盖实际 checkout；
旧凭据可通过已保存 checkout 字节的精确匹配回放。未捕获旧代码最后一次拒绝
的原始请求，不能确认那次具体变化的字段。
结算重试先检查已保存凭据；匹配实际结算载荷的重试返回原结果，不再受入口
一小时时限影响。新结算仍有时限，修改实际结算载荷的重放仍拒绝，奖励不重复发放。
角色数据与本次已获得奖励无需回滚；完整重启客户端后手动复测。
不修改 APK。回归检查所有七活动的首次通关消息、重放及普通战斗结算，
并验证过时未结算请求和冲突重放仍被拒绝。
