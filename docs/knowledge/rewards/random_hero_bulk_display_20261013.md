# 随机三星礼包批量显示修复（2026-10-13）

## 实际故障
测试玩家 revival（1）于 23:20:45 一次使用 10 个 1203000，收据 7181007005ccd418a32f7b50f4e5dc7173a2a6d7ef4831e5b4ef6b1933be2890。
服务端 ledger 证明全部是已拥有角色：碎片总计 640，补偿票 1237915 数量 100，已到账。客户端日志显示 ArgumentException: An element with the same key already exists in the dictionary，堆栈 BagModule.EnqueueGetItemsInfo → UIAPI.ShowGetAwardItem → BagModule.OnL2CItemOptReceiveMsg。
此前修复了真实发奖和回调前更新，但漏掉了重复角色 RewardItem 的显示约束；单个礼包和服务端到账测试不能发现此问题。

## 原生证据
原版 libil2cpp.so 的 BagModule.EnqueueGetItemsInfo（0x19c1010）在 0x19c13a0 调用 Dictionary<int,object>.Add，非堆叠物品条目必须以 itemId 唯一。同目录 asm 保留地址与字节 SHA256。

## 修复
bag_reward_view 将奖励 rewardItem 按 itemId 合并并累加数量，相同角色的新获得/重复转换混合条目以新获得显示；转换的碎片和补偿票仍独立显示。
transformHero 保留每次抽取的结果与转换标记，不重抽、不改变候选或权重。历史奖励恢复优先使用逐次记录，避免按合并显示行把首次解锁也算成重复补偿。
旧 ItemOpt 回执重传仅规范化响应显示，不重复扣除礼包、不重发奖励、不覆写原始收据。
本次服务端修改不要求 APK 补丁。玩家界面由用户手动验收。
