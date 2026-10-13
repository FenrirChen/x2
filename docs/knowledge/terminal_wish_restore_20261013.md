# 终端心愿恢复：服务端实现与客户端边界

2026-10-13。本轮未修改APK，活跃存档保持原库。

## 用户批准的规则

- 每次分析生成3个不重复候选，在符合条件的官方任务之间等权抽样。
- 每个服务器日总共接取3个心愿任务。客户端要求一次确认选满3个，故一批确认消耗3个名额，不解释为3轮、共9个任务。
- 采用现有ServerClock/服务器日历：北京时间00:00刷新。独立于手机日期和远程主机操作系统默认时区。
- 候选生成、查询和重登不消耗接取名额。重新查询不重抽；确认后的任务当天保持，不能刷出另一批。
- 官方FunctionOpen 21942：20级开放。候选不足3个回原生E_NOT_GEN_MIND_TASK(173)，不填入重复或虚构任务。

## 已恢复的服务端链路

351条FavorabilityDailyTask、对应TaskCondition、3个完整Gift奖励组从2.4原APK重新解码。所有任务、条件和奖励校验通过。数据源与资源地址保留在terminal_wish_catalog.json.source。

351条任务共5类：

| 条件 | 数量 | 权威计数来源 |
| --- | --- | --- |
| 11 携带指定角色通关指定关卡 | 229 | 成功结算与battle_entries.team_json，按关卡ID匹配 |
| 25 携带角色通关指定复刻难度 | 10 | Type=2现世复刻成功结算、DifficultyLevel与实际队伍 |
| 67 指定角色探险 | 44 | 时空之门探险成功领取，真实heroList与ruinId |
| 68 给指定角色送指定礼物 | 52 | AddFavor成功扣除的itemId和实际num |
| 69 指定角色训练 | 16 | 光之密室训练成功领取，实际heroId |

分析候选只考虑已拥有的官方角色；战斗检查现有关卡开放条件，训练排除已达账号等级的角色，探险考虑已开放遗迹，礼物任务考虑实际持有的所需数量。等权是对符合条件的TaskID，未人为给角色或任务类型加权。

查询351/354 type=6，extraType=1为分析、0为查询；接取459/460；领奖350/353、814/815 type=6。原生459序列化在0x37d09a0写重复tag08、0x37d0a2c写tag10，对应taskIds字段1和type字段2；460字段1是code。没有按方法命名猜消息类型。

候选TaskStatus=0，已接取=2，达标=3，已领取=4；taskRefreshTime为下一次服务器零点。真实空列表在FavorWishModule中有null判断，不制造TaskID=0占位任务。

领奖同时发GiftGroup原版奖励并增加FavorabilityGift；沿用现有好感累计经验、突破与等级上限规则。保留现有角色培养和好感。成功领奖派发条件72事件，赛季/周任务可据此计数，不制造完成事件。

原版GiftGroup 780002/780003/780004分别为1237908账号经验110/135/170。每条心愿的好感值由其任务表单独决定，未统一改为固定值。

## 持久化、防重与日切

favor_wish_state保存当天候选、任务、进度、领取状态、接取数量；favor_wish_events保存真实行为的防重复键；favor_wish_receipts保存分析/接取请求与所属日期。奖励唯一键为terminal-wish:day:taskId，物品和好感在同一事务内发放。

重复报战斗/领取训练探险不重复计数，接取前已记录的行为不能通过重报来完成新任务；取消训练或探险不计数。重复领取仅返回已有奖励回执，不再发奖励、不再增加好感。旧日期的接取请求不能在新日接取。无法完成、无权拥有、错误类型或写库失败均应答真实错误，不伪成功。

新表纳入完整存档边界，进度、候选、每日名额和防重历史跟随存档迁移。以前的/3、/4、/5且缺少新表的存档继续可导入；缺少的心愿数据重置为未分析，不保留目标旧任务，不重置一次性福利保护。洗练兼容和ID映射保持原规则。

在现有daily_welfare_watch零点回调中清理过期心愿，对在线玩家推354 type=6真实空态；查询、行为、领取亦按同一日历校验，避免定时回调与操作竞争。

## 客户端跨日边界：本轮尚未修改

原客户端FavorWishModule.OnReceiveAcceptFavorWishMsg(0x18ba1cc)成功接取后将isAnalyse设为true；OnFinishFavorWishMsg(0x18b9f7c)仅在真实领奖回调时清为false。OnReceiveFavorWishMsg(0x18b9b6c)替换任务列表但不重置此标志。

CalPageState(0x18bb6b4)在isAnalyse=true时，即便新列表全为WAITING，也可能选择TaskPage；isAnalyse=false且全WAITING才进入ChoosePage。因此连续在线跨零点、当天从未领取任何奖励时存在客户端残留风险。服务器日切和名额已重置，重登重建模块可清理该标志；不能声称所有在线跨日UI边界已经实测或仅靠服务端彻底修复。

最小客户端方案见[terminal_wish_client_patch_proposal.md](terminal_wish_client_patch_proposal.md)。实施需用户允许修改本地/远程两份APK，本轮未实施。
