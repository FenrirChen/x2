# 活动抽取奖池阶段修复（2026-10-11）

## 原因和客户端证据

斟鄩之邑首次查询返回全部六个 RewardPoolInfo，客户端将它们全部视为已解锁。

- ActivityNoticeModule.RefreshRewardPool（0x133A4F0）清空并重建已解锁 ID 列表 this+0x220，逐项添加响应中的 rewardPoolId。
- AncientBoxView.AncientRewardPoolItem.Refresh（0x17BABDC）以该列表 Contains(poolId) 决定锁定标记。
- ActivityNoticeModule.GetDefalutSelectId（0x133B518）倒序寻找最后一个剩余奖励非零的已开放奖池，所以全量返回导致直接选中第六阶段。
- goodsIdCountPair.Value 是已抽次数；RefreshRewardPool 使用 BuyTimes - Value 计算剩余库存，此字段语义保持不变。

## 实现

ActivityService.unlocked_pools 按 NextBox、UnlockGroupID、UnlockGroupTimes 和本期已抽次数计算完整可达链。查询及抽取结果只返回已开放奖池，同时保留此前已开放阶段。抽取服务使用相同判定，不能绕过未解锁的前序阶段。

适用于阏逢敛遗、斟鄩之邑、秘宝之海、珠雀绮馔的抽取奖池。普通兑换商店不使用此规则。

当前本地审核期为斟鄩之邑（period=2），修复前数据库该期没有 pool 状态，未修改玩家存档。

## 回归范围

四个活动初始阶段、关键奖励不足时保持锁定、逐阶段解锁、服务重新实例化后进度保留、40 天后同活动新一期重置；斟鄩之邑抽取应答直接解锁下一阶段并可继续抽取；越过未解锁前序阶段被拒绝；既有扣币、重复请求及失败回滚检查。
