# 电玩城大金币 DP 计数修复（2026-10-15）

- 官方任务 650727 属于章节 2010700：E_GetItemID，物品 1107003，累计 233 次，奖励 2 DP。
- 客户端 dump.cs 的 TaskConditionECompleteType.E_GetItemID=35。原生 ClientX2.Achievement.ChapterAchievement.GetDPDatas 地址 0x1AD6804；道具分支在 0x1AD6C5C 调用 FightItemBag.GetItemNumByID，0x1AD6B8C 起将条件类型、物品、参数和数量交给 SetTaskData，随 316.chapterTaskEvent 上报。
- 原服务端仅处理 316 中的类型 39（单局货币），忽略类型 35。264.dropItem 为候选掉落池，且实际计数只接受 relicList 中的神迹，大金币无法走此路径。
- 现接入当前章节已配置的类型 35 道具事件，仍要求当前有效战斗已有成功结算。与其他观察共用 run UUID/item 信号及 MAX 高水位，同局重试不累加，跨局累计。仅更新进度，不发放道具。类型 39 保持单局最大值逻辑。
- 无服务端历史拾取记录的旧战斗无法凭空补记；修复后成功结算的战斗会正确累计。
- 回归：test_chapter_dp_official.py 共 14 项通过，覆盖失败结算拒绝、异常事件拒绝、两局 120+113 完成、重复报告去重、重建服务后保留进度、棱镜不跨局累加。

社团祈愿以 social.day(now)=(Unix秒+8小时)//86400 划分游戏日，每天北京时间 00:00 清除当日 wish_counts，即每日一次资格刷新。
