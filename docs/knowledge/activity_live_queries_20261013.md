# 活动查询重放返回旧状态

## 可复现原因与修复

ActivityRuntime.handle先查询activity_receipts，曾只为QueryActivity、EntryidStatus、
SceneGlobalParam绕过缓存，其他多数查询返回第一次请求的永久应答。
复现三项：同一CafeStoreInfo请求重试在商铺修复后仍返回lockState=0；
同一ActivityMissionData请求重试在通关美食幻境后仍返回lastPastMissionId=0；
同一CafeStoreInfo请求在下一轮同活动重试被旧领奖期检查拒绝，code=13。
修改前这三项回归测试均失败。

现在显式LIVE_QUERIES每次在事务内读取当前状态并校验协议后应答，
不查询、写入或重放历史查询回执。变更操作仍保存回执、验证活动期、
保护相同请求不重复发奖或扣料。问答的出题（会扣材料）等不算只读查询。
不删除历史回执，不修改玩家库存、通关记录或日切规则。

## 客户端证据

NewYear2SectionDifficultySelectView.OnOpen (0x1A3DE1C) 读取活动章节的
lastPastMissionId并在SectionID列表查索引，只允许索引<=上次通关索引+1的
难度点击。因此旧进度应答确实会使后续美食幻境难度无法点击。
同活动再次开放时，查询读取新一期进度，保持该期逐档解锁。

NewYear2ActivityModule.OnReceiveCafeStoreInfoMsg (0x1751C50)更新商铺字典；
FoodShop.Refresh (0x1A26988)读取该字典，旧查询应答会覆盖已经修复的商铺状态。
两份发布APK中的修复点击、修复条件、修复应答、难度选择关键方法与原APK一致，
本轮没有修改APK。

## 链路验证与限制

六间料理商铺的实际首通礼包确实把对应食谱发入inventory，之后原版
C2L_CafeStoreUnLock成功。阏逢三档2161191/2161192/2161193分别完成实际
入场、结算、重复结算应答，第一档按原表使用试用1327，其余使用拥有的神格。
在更新的状态查询中观察实际修复状态/通关状态，并验证跨期查询重试。

没有捕获用户此次现场请求，不能断言所有现场失败均由该缓存引起。
本地账号1当前没有三本食谱，也未通过对应剧情，客户端不发修复请求是正常
原版前置限制：需要先首通第一/第四/第七幕。账号5有前两本，未获得第三本。
三档美食幻境在客户端依次解锁，已通关第一档后原版隐藏第一档入口。
