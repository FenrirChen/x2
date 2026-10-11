# 2026-10-11 活动入口、经营队列与活动代币

## 修改

- 客户端 MainPage.ActivityEnterNode.StartEffect 在入口出现时立即激活 openDes / lockDes，避免等待 ElectronicEffect 的装饰动画回调。修改指令地址为 0x1415008、0x141501c；最终点击效果由用户手动验收。
- CafeStoreInfo 的三个流读取入口初始化缺失的 employeeList、queueList。服务器只发送真实制作队列，不再将空闲位置伪装成订单。原生客户端用队列 Count 判断制作容量和能否换店员，旧零填充会同时阻止这两项操作。
- 店铺流程包括配方持有检查、解锁、厨师选择、材料扣除、真实槽位容量、完成制作、营业收入领取和升级。制作中不能撤换或跨店调走店员；升级与店员加成继续参与成本和收入计算。轮换后保留的配方仍可使用，店铺当期进度重置。
- 活动道具 ItemKind=16 的持有量由客户端通过 EffData 的货币枚举读取 BaseInfoProto，并非读取背包数量。补齐精确协议字段和对应道具余额聚合；领取、消费及清零时按现有玩家快照链同步。

## 货币协议

| 字段 | protobuf tag | 货币枚举 |
| --- | --- | --- |
| ActivityCoin | 46 | 989 |
| ShuangHanCoin1 / 2 / 3 / 4 | 49 / 50 / 51 / 52 | 985 / 986 / 987 / 988 |
| NewYearCoin | 58 | 984 |
| AoxilisiCoin | 62 | 982 |
| MainActivityCoin | 63 | 981 |
| BattlepassShopCoin | 65 | 998 |
| MemoryPoint | 73 | 977 |

战令兑换价格和奖励未变。本次没有继续修改活动图片资源；保留此前的活动战斗场景补丁和存档管理补丁。

## 产物与验证范围

原生补丁工具：tools/savemanager/client/patch_activity_ui.py。
原生补丁与逐条审计：tools/savemanager/client/build/libil2cpp.activity-ui.so 及同名 .audit.json。
签名客户端：D:/demo/x2/逆向/打包/X2-Revival-ActivityUI-Local-signed.apk（10.0.2.2:18080）、X2-Revival-ActivityUI-Remote-signed.apk（8.163.2.72:18080）。

完成服务代码回归、原生指令检查、两份 APK 的完整 ZIP CRC、对齐、存档管理钩子、libunity 保留检查及正式签名验证。未操作客户端进行游戏内验收；由用户手动验证。客户端必须更新，旧客户端不能安全接收没有零填充的空制作队列。远程服务器需同步本次服务端代码；本次只重启本地服务端，保留 runtime/phase14/player.sqlite3。
