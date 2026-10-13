# 活动任务宝箱与商铺修复检查

## 宝箱

原客户端 `NewYear2TaskView.BoxNode.RefreshData` (0x19CC2E8) 用下发
`TreasureBoxData.boxId` 查询静态 ActivityTaskBox，必须保留全局 BoxID。
`OnBoxReadyStateClick` (0x19CC630) 将配置 ActivityID 传给视图；视图
`OnClickBoxItem` (0x1A4661C) 调用 `NetGainActivityPresent(9,mCurIdx,activityId)`。
后者 (0x169319C) 实际发包是 `boxId=页面零基序号, type=9, activityId=活动ID`。
领取时用当前活动的列表序号查表，应答保持该序号。

`RefreshData` 使用状态 0未就绪、1可领取、2已领取；原服务器0/1错误，
使领取后的宝箱重新显示可领。`NewYear2TaskView.Refresh` (0x1A458C4)
统计 TaskStatus=4 的任务，因此进度宝箱按已领取任务奖励数判断。
奖励去重仍使用原来的 `ActivityID:静态BoxID`，保留历史记录。
增加相同请求重放应答，重放不重新发奖；活动再次轮换时独立重置。

## 商铺：服务端路径已验证，用户现场原因尚未确认

`FoodShop.OnClick` (0x1A29404) 仅在客户端检查食谱持有量通过时发
`C2L_CafeStoreUnLock{storeType}`。`CheckStoreCanUnlock` (0x1755CD8)
固定读取一级配置，E_GetItem要求对应食谱数量>0；不消耗食谱。
服务端改为同样读取一级修复条件，并在拒绝日志中加入商铺类型、活动期及
缺失食谱ID。六家当前轮换活动商铺逐一经实际协议测试：无食谱拒绝、
持有一本成功、重复请求不重复收费、重新查询保持解锁、食谱保留。

阏逢敛遗：类型7/8/9需要1290301/1290306/1290328，分别由
2161111第一幕、2161114第四幕、2161117第七幕首通奖励提供。
珠雀绮馔：类型1/2/3需要1290134/1290138/1290141，分别来自
2160411第一幕、2160431第三幕、2160451第五幕首通。

本轮没有捕获用户现场失败请求；本地模拟器7555未启动，服务日志没有本轮
游戏操作。不能据服务端测试声称用户商铺问题已经解决，需要活动、商铺名称
和点击提示/新日志继续定位。没有改APK，也没有放宽食谱要求。
