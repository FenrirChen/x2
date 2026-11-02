# 赛季天赋重置排查（2026-10-24）

反馈：远程玩家提示“操作失败”，无对应日志；本地日志未记录该次请求，因此不能确认玩家的具体触发条件。

## 客户端证据

原始 2.4 libil2cpp.so：
- BattlePassModule.GetResetTalentCost 0x1860D38：读当前 ActivityReal.ActivityParam3[0]。
- BattlePassTalentView.OnResetTalent 0x14C4444：0x14C45FC、0x14C4708 将单点费用乘已保存等级；确认回调 0x14C68A4 的 0x14C6924 校验的是金币（详见下节 2026-11-02 更正）。因此保留每点500金币，不能改成整项仅500。
- 确认回调 0x14C69F0 调 SendBattlePassTalentReset，使用 TalentItemData.talentID（+0x6C），协议956字段1。
- OnReceiveBattlePassTalentResetMsg 0x185E940：成功时更新 leftPoint、将 update 写入天赋字典并刷新UI；协议957需要完整 update 消息。

## 已复现并修复

- 相同重置换新请求编号时，旧实现因已为零级而报13。合法天赋的重复清零改为幂等，无扣费、无返还、无新增成就次数；未知天赋仍拒绝。
- 原 L2C_BattlePassTalentUpdate 只有剩余点数，无法修复客户端缓存的旧等级。重置与加点应答前下发完整天赋及货币快照；失败也同步真实状态，以便重新操作。
- 费用不足原来统一显示13，现改为原生资源不足码36（客户端枚举名 `E_LIMIT_CRYSTAL`，但天赋重置实际校验的货币是金币，见下节更正）。费用按当前主赛季活动ID定位，避免依赖活动表行顺序。
- 拒绝日志加入请求参数，方便后续直接定位具体天赋与错误。

测试覆盖清零重试、同包重放、重新加点、重登、费用恰好充足/差1、未知天赋，以及原赛季功能与战斗加成。此修复不声称已复现该远程玩家原始请求；若仍失败应收集新版本拒绝日志。

## 2026-11-02 更正：扣费货币是金币，不是光辉

远程玩家反馈「重置不了」的后续定位：服务端一直按光辉 (1237902) 校验和扣费，客户端却按金币
校验，因此客户端拦不住、服务端必然回 36，按钮看起来点了没反应。

重新用 `.runtime/il2cpp-meta.json` 的地址表核对 2.4 `libil2cpp.so`（此前用 `work/cpp` 另一版本
头文件里的地址，反汇编到的是 `RefreshTalentGroupList`，才得出「校验光辉」的错误结论）：

- `BattlePassTalentView.OnResetTalent` 0x014C4444：单点费用取
  `BattlePassModule.GetResetTalentCost`（0x01860D38 → ActivityReal.ActivityParam3[0]=500），
  弹窗文案走 Language 60050165「每重置1点已分配的天赋点，需要{0}金币…」。
- 确认回调 `BattlePassTalentView_c_DisplayClass21_0__OnResetTalent_b__0` 0x014C68A4 内
  0x014C6924 调用的是 `GameAPI_GetCurrencyNum(1)`，enum 1 = E_Gold → 金币 1237901。

修复：`BattlePassTalentReset` 的余额校验与 `self.spend(player, …)` 均改为金币 1237901，
不足时仍回 36。`tests/unit/test_season_talent_reallocation.py` 的余额断言与「差1」用例
同步改为 `snapshot['gold']`，`test_origin_season` 的 fixture 补足金币余额。

回归：`tests/unit/test_season_talent_reallocation.py` + `tests/unit/test_origin_season.py`
共 21 项通过。服务端重置现与客户端同口径：按金币 1237901 扣费，单点价格与失败码不变。
