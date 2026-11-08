# 赛季成就列表堆叠与卡顿（2026-11-08）

## 证据与根因

本地11:35的990、992、994请求均正常应答；Unity日志中捕获49次 `ArgumentOutOfRangeException`，栈为 `BattlePassAchievement.InitAchievement → LoopListView2.GetNewItemByIndex → Update`。日志保存在runtime，不提交。

原生 `BattlePassAchievement.InitAchievement`：0x1807bc4先创建列表节点，随后0x1808554读取SeasonAchvData.stage，0x1808574访问该成就的GiftGroup[stage]。这一步异常会留下未完成初始化的列表节点，并在后续刷新中重复报错。

当前赛季75条原版成就的GiftGroup均只有一个元素。服务端错误地将已领奖转为stage=1，使已领取成就访问GiftGroup[1]越界；领奖状态应由status=2单独表达。原生 `BattlePassAchievementModule.GetReward` 在0x180b560也只更新status，不递增stage。

## 修复

单档成就始终下发stage=0，保留现有进度、status和领奖账簿。查询不复用旧回执，现有已领取存档在重新查询后自然得到正确字段，无需数据库迁移或重发奖励，无需更新APK。

回归测试首先复现“净化道具领取后stage=1而GiftGroup长度=1”的失败，修复后通过。覆盖真实领奖、服务重建、重复领奖拒绝，以及全部75条成就三个分类的完整分页和原生奖励索引边界。既有赛季进度奖励、赛季商店和赛季基础测试31项通过，新回归4项通过。

本地服务端重启后，客户端需重新登录并重新进入成就页面，丢弃旧页面的错误缓存。活动保持秘宝之海，未推送远程。
