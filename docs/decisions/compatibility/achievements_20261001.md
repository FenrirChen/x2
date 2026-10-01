# 恢复原生成就系统（2026-10-01）

## 客户端证据

- 2.4 APK ResourceManager 的 Achievement 有 318 行，IsUse=1 的 311 行恢复到 `data/achievements.json`。
- AchievementCondition / AchievementConditionLine 保存单次目标及阶段目标，Achievement.GiftGroup 保存对应阶段奖励。**不是 TaskCondition**：两套表的 62xxxx ID 存在重叠，不可混用。
- 四个分类：培养 1、战斗 2、玩法 3、社交 4；AchvStatus 为 Ing=0、Reward=1、Finish=2。
- FunctionOpen 21907 / E_Achievement：6 级显示，原生客户端入口无需修改 APK。
- 原生协议：总览 345/348、详情 344/347、成就领奖 346/349、点数奖励 358/359、更新 565、重算提示 811/812。
- 静态 Serialize：AchvData `0x1dc2a10`、总览 `0x37adefc`、详情 `0x37acce0`、成就领奖 `0x37b0690`、点数领奖 `0x37af544`、重算 `0x3a0e37c`。
- RequestAchvDetialData `0x1318c5c`：startIndex 从 0 起，endIndex=start+30；GetDetailData `0x1319f70` 满 30 条继续请求。服务端返回半开区间，最后空页结束。
- InitAchievement `0x131d58c` 按 stage 直接索引目标/Gift；完成所有阶段后仍返回最后有效索引，不能返回数组长度。
- GetOverView `0x1319c3c`、RefreshOverView `0x131c608`：achvPointRewardList 是**每档状态**，不是已领取索引集合。返回 15 个 0/1/2，阈值与 Gift 来自 TaskControl.CompleteAchievementNumber / CompleteAchievementNumberGiftGroup。

## 服务端规则

- `tools/analysis/export_achievements.py` 按客户端中文条件和实际表映射建立规则。这些规则绑定是 Revival 解释，未宣称恢复了原服实现。
- 288 条启用成就已有可信进度来源：账号等级、神格数量/等级/星级、魂器星级、好感等级/点击/赠礼、兽主数量/强化/星级/指定种类与整套、普通和特殊宝石、剧情终关、新月限时/血月通关、学院建筑/奇迹等级、登录天数。
- 个体默契度绑定只选 FavorabilityHero 中的账号神格，排除 UnitBase 的同名战斗/助战变体，避免后者覆盖账号 ID。缺省默契度与神格数据使用相同 InitialLevel；保留显式已有等级。用户确认朱雀与陵光为同一角色，绑定 1034。
- 指定整套兽主要求 6 星、6 个不同部位；同一部位的 6 件不能算整套。
- 宝石数量包含背包正数量与魂器镶嵌的宝石；零数量墓碑不计数。普通宝石星级按条件的准确星级统计，神格和兽主“及以上”按下限统计。
- ChapterInfo.StageID 绑定剧情终关；不把序章当第一章。ChallengeName 的中文值绑定新月、血月，不靠 ID 或月相索引猜测。
- 限时成就只读取 player 对应已 settled 的 economy_runs、battle_checkout_wire 与 battle_receipts；成功、关卡一致、result=10 且已记录时间在 (0,360] 才计入。未接受的客户端战报不会推进，也不增加 outsideItems 奖励。
- 登录沿用项目任务日边界；复用 economy_events 中已有 challenge:loginday 证据，合并同日记录而不累计两次。
- 达成进度取历史最大值；后续消费、合成、分解物品不会撤销已达成成就。
- LastAchievement 作为前置领奖条件；达到后继条件不允许跳过前置领奖。
- 成就点数为已达成的阶段数，每个阶段 1 点；点数宝箱的真实奖励使用现有 EconomyService / RewardGrant。
- 阶段领取、经济奖励、请求回执在同一事务。相同会话/请求编号/内容重发返回原回执，不会领取下一阶段。每档点数奖励永久只领一次。
- L2C_AchvUpdate 随经济状态同步发送；ReCountAchv 只是刷新提示，不接受客户端提交的进度或奖励。

## 明确的剩余限制

23 条仍未绑定可信来源，显示但不会自动完成：世界聊天/友情点/好友友情等级、终端心愿任务、部分学院累计生产派遣交易任务、祈神、白夜补给累计购买、击杀怪物分类计数。配置中这些行保留 `unsupported`，后续找到证据再接入。

旧存档的等级、装备、宝石、好感、学院等级和通关可按持久状态恢复；缺少历史日志的累计事件不虚构补发。赠礼次数从本次恢复后的成功赠礼开始记录；已有点击日志和登录日记录可复用。

## 验证与部署

定向测试使用临时 DB，覆盖总览/分页、状态数组、阶段重发、重复点数领奖、重连持久化、失败回滚、镶嵌宝石/墓碑、剧情终关/血月、六部位套装、已结算限时回执、全部等级阶段、旧登录证据和不信任重算输入，并回归经济、好感、战斗及兽主主属性强化。

备份 active DB 后按项目 `tools/local_game_server.py` 启动方式重启。没有重置存档、修改余额或直接补发成就。客户端实机验收待用户进行。
