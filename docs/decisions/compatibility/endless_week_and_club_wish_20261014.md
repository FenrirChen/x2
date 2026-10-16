# 乌洛波罗斯与社团祈愿补修（2026-10-14）

乌洛波罗斯按北京时间周一 00:00 重置本周光能获取计数及续战存档；持有的货币、局外上限成就进度和已领取的上限加成保留。客户端 EndlessDungeonTask 没有 ResetType，区别于旧 TaskEndlessWeek，因此不把永久上限成就改成可反复领奖的周任务。默认周上限取 WeeklyDungeon.EndlessWeekVowLimit=880，加成取每条成就已领取阶段的 VomLimit 之和。结算发奖时执行剩余周额度限制，以实际发放量推进光能进度；重复结算不重复计入。

新增 PlayerDataProto.Weekly（字段12）。WeeklyProto 原生 Serialize 0x2bbf42c：字段1为本周获取，字段2周刷新时间，字段3已领取上限加成，字段4经验，字段5配方列表，字段6元素经验，字段7通关列表，字段8上限刷新时间。EndlessTask.SetLightData 0x1c28aec 从 PlayerData.Weekly +0x18 读取加成，再加 WeeklyDungeon +0x44 的880；EndlessInfo.RefreshPage 使用 Weekly 显示获取进度。重复消息、重登和存档导入都复用持久状态，在线周界推送部分 Weekly。

历史补修仅依据 economy_grants 中 battle:<uuid> 的光能奖励恢复获取进度，保留原战斗记录的击杀、层数和合成回补。奖励不会重新发放。新状态复用 activity_state（period=-38、namespace=endless-week），已覆盖在完整存档边界中；未新增未导出的表。历史发奖超过原上限的余额不追扣。

社团每天只能成功发起一次祈愿，与材料种类无关；领取后仍保持 wishingCount=1，午夜恢复0。原有 wish_counts 迁移保留当日已使用状态。回应、重放和午夜同步均下发 L2C_ClubWishingCount，避免界面重新出现可祈愿入口。

降临试炼：当前服务端 DAILY_COMPAT.schedule 已为 always_open。客户端 ChapterModule.CheckDailyChapterTime 0x16bad64 在0x16bae84取DayOfWeek，在0x16bae88读取本地DailyDungeon.OpenTime，再在0x16baed4检查当日值>0。2030500/2030600/2030700/2031200的轮日限制不能靠服务端开放字段取消。用户此前要求暂不改客户端，本轮已请示是否允许更新客户端配置表；该请示已于 2026-10-17 获准并落地，见 daily_dungeon_weekday_gate_20261017.md。

测试覆盖光能发奖/重放、上限领取与真实wire、周一00点刷新、上限与货币保留、历史补回、同日换材料拒绝、祈愿领取后次数和次日恢复，并回归登录、奖励与完整存档。
