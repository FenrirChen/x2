# 赛季成就进度奖励与周任务宝箱（2026-10-13）

用户最新指令：不修改成就完成误判；只修复进度奖励及赛季周任务。此次未更改 achievement_values、成就规则或既有完成记录。

## 客户端证据
BattlePassAchievement.RefreshOverView 0x1805f08 与 GetPointsReward 0x180b8ac 使用 TaskControlManager.GetItem(5)，字段偏移 0x88/0x90 对应 CompleteBpAchievementNumber 和 CompleteBpAchievementNumberGiftGroup。
阈值 5/10/20/40/60，Gift 797134–797138。列表 achvPointRewardList 为五个状态（0未完成/1可领取/2已领取），不是已领取ID集合。
**订正（2026-10-14）**：领取请求的 achvPointId 是里程碑的**阈值数值**（5/10/20/40/60），不是零起始索引。BattlePassAchievementModule.RequestPointsReward 0x1809500 先取 TaskControlManager.GetItem(5)[+0x88] 做 get_Item(index)，把阈值数值写进 C2L_SeasonAchvPointReward（ctor 0x3A1E25C）后才 Send（0x1809638 `mov w19,w0` → 0x180969C `str w19,[x21,#0x10]`）；回包处理 GetPointsReward 0x180C05C 也在 0x180C24C 读回包的 achvPointId（[+0x18]）后与同一张阈值表逐项比较。对照原生 AchievementModule.RequestPointsReward 0x1319DE4 是直接 `str w19`（发下标）—— 两个模块语义不同，服务端须按阈值数值取值。
DailyTaskModule.GetActivity(15) 从 BaseInfo.BattlePassWeeklyActive 读取赛季周活跃度。其 protobuf get_IsSet getter使用 BitArray.Get(67)，Gold getter使用 Get(5)（对应已有字段5），证明周活跃度字段号67。
BattlePassTaskTab.OnBoxReadyStateClick 使用 DailyTaskModule.mCurTab（GameTaskType15）发出 C2L_PickTreasureBox，沿用现有协议；任务查询和 TreasureBoxUpdate 都用 type15。

## 实现
周任务奖励中的1237999按本周存入season_state.weekly_active；不再把新的周活跃度当作永久背包货币。来源仍为原版任务Gift中的数量。
登录及背包/任务同步的PlayerDataProto下发BaseInfo字段67。Task查询包含五个宝箱，状态改变追加TreasureBoxUpdate。
五个周宝箱阈值30/60/90/120/150，Gift797124–797128。领取要求已达到对应阈值、活动有效、尚未领取；记录和发奖同事务，重传使用收据。
本周旧领奖账本source season:<instance>:task:<week>:...中的1237999可恢复进度，避免过去已领取的任务活跃度丢失；不使用跨周库存总数。周一北京时间00:00重置周任务、活跃度和周宝箱领取状态，成就进度奖励仍以赛季实例为单位。
全部状态使用已有season_state/season_receipts/economy_grants，仍在完整存档导入导出边界内。

验证：赛季/任务/签到/邮件/登录44项通过；追加首次登录账本恢复与真实HTTP登录4项通过。
