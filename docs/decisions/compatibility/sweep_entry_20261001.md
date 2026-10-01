# 扫荡入口恢复

## 原因与客户端证据

服务端 C2L_QueryActivity 仅返回 code=10、空 activityData。
客户端扫荡是 ActivityCenterPage 的 SaoDang/ChapterSweepPage，依赖活动
目录中的 ActivityReal 类型 E_ActivityMop=71，所以空目录无法创建扫荡入口。

官方客户端表唯一匹配：ActivityReal[73010]，parent=2 (E_DailyEvent)，
group=24，ActivityName=730101，ActivityShow=1，OpenLever=10，param1=[3]，
ActivityTaps=UIAltas/Activity/SaiJiSaoDang。原表完整行保存在
data/sweep_activity.json，读取源为 analysis.progression.probe 的客户端表。

ActivityData.Serialize 0x1dc97c8 确认字段 1..20；actType 字段4、param1字段11。
ChapterSweepPage.SetData 0x177aff0 根据 AdventureList.AdventureType 选择章节，
param1=3 表示 E_DailyDungeon2，不是扫荡三次的次数限制。
AdventureList[3] 包含 2032200/2031300/2030500/2030600/2030700/2031200。
ChapterModule.CheckCanSweep 0x16ce860 调用 CheckSectionIdFinished，要求通关。
SectionSweepView.RefreshView 0x176dfb8 根据体力除以单次消耗计算可选次数，
并在 0x176e02c..0x176e038 限制最大99。单次消耗取 SectionTable.ManualValue。

## 实现

QueryActivity 下发上述单一扫荡活动，保留官方等级10、分类、章节选择参数
与图标，状态OPEN。为恢复已过期活动的功能，服务端开放时间兼容为
Unix 1..2147483647；这是 Revival 兼容决定，不声称为官方当期活动日程。
其他活动仍未启用。入口在活动中心，不在所有主线关卡上追加按钮。

已有 1027/1028 SecSweep 接口继续使用 MopReward 与 Gift 权重和数量，
不改变 outsideItems/887、首次通关奖励或卡池等规则。
批次数从旧硬编码上限10对齐客户端99。非法次数、未通关或未知奖励拒绝；
基本校验在体力恢复前进行，防止非法请求产生无关存档写入。
实际扣体力和发奖复用既有事务/回执。重复请求读取回执，不重复发奖扣款。
不为 MopReward 为空的章节编造奖励。

## 验证

9项定向测试通过：活动目录协议与字段、五类原表材料本奖励和持久化回执、
99次批量体力、非法次数、余额不足、未通关拒绝，以及现有金币本扫荡幂等。
客户端入口是否显示仍需部署后实机验收。
