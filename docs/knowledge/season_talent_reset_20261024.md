# 赛季天赋重置排查（2026-10-24）

反馈：远程玩家提示“操作失败”，无对应日志；本地日志未记录该次请求，因此不能确认玩家的具体触发条件。

## 客户端证据

原始 2.4 libil2cpp.so：
- BattlePassModule.GetResetTalentCost 0x1860D38：读当前 ActivityReal.ActivityParam3[0]。
- BattlePassTalentView.OnResetTalent 0x14C4444：0x14C45FC、0x14C4708 将单点费用乘已保存等级；确认回调 0x14C68A4 的 0x14C6924 再次验证光辉。因此保留每点500光辉，不能改成整项仅500。
- 确认回调 0x14C69F0 调 SendBattlePassTalentReset，使用 TalentItemData.talentID（+0x6C），协议956字段1。
- OnReceiveBattlePassTalentResetMsg 0x185E940：成功时更新 leftPoint、将 update 写入天赋字典并刷新UI；协议957需要完整 update 消息。

## 已复现并修复

- 相同重置换新请求编号时，旧实现因已为零级而报13。合法天赋的重复清零改为幂等，无扣费、无返还、无新增成就次数；未知天赋仍拒绝。
- 原 L2C_BattlePassTalentUpdate 只有剩余点数，无法修复客户端缓存的旧等级。重置与加点应答前下发完整天赋及货币快照；失败也同步真实状态，以便重新操作。
- 费用不足原来统一显示13，现改为原生 E_LIMIT_CRYSTAL(36)。费用按当前主赛季活动ID定位，避免依赖活动表行顺序。
- 拒绝日志加入请求参数，方便后续直接定位具体天赋与错误。

测试覆盖清零重试、同包重放、重新加点、重登、费用恰好充足/差1、未知天赋，以及原赛季功能与战斗加成。此修复不声称已复现该远程玩家原始请求；若仍失败应收集新版本拒绝日志。
