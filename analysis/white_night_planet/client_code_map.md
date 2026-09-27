# College/GrowthBase 客户端代码图

来源：官方 2.4 `D:/demo/x2/tools/Il2CppDumper-bin/dump.cs`、`script.json`、`libil2cpp.so`；调用边由 `analysis/equipment/callgraph_bl.json` 的 ARM64 `bl` 图交叉核对。RVA 为 `libil2cpp.so` 虚拟地址。级别 A 指直接类型/方法/静态表证据，B 指跨方法语义推断。完整 32 条发送链见 `protocol_matrix.csv`。

## 入口与解锁

| 类/方法 | RVA | 直接调用关系 | 关键状态 | 证据 |
|---|---:|---|---|---|
| `CollegeEntry.OnOpen` | `0x1BAFF2C` | → `CollegeModule.SendQueryGrowthBase` | 进入基地时重新查询 | A |
| `CollegeEntry.OnShow` | `0x1BAFFA0` | → `CollegeModule.SendQueryGrowthBase` | 重新显示也查询 | A |
| `CollegeMainEntry.OnOpen` | `0x1AF3EFC` | → `CollegeAlchemyModule.SendAlchemyMainData`、`CollegeModule.SendUnlockExploreRuin`；另查公会协助 | 基地主页的两个依赖 | A |
| `MainHallFSM.UpdateLoadModule` | `0x13BC1FC` | → 炼金主页和遗迹查询；检查 `GameAPI.IsClientFunctionClose/IsServerFunctionClose` | 大厅加载模块开关 | A |
| `CollegeModule.IsCollegeEnable` | `0x1AF9FF8` | → `NetSyncData.get_PlayerData`、双端 FunctionClose | 入口使能门；`FunctionOpen` 21902/21912 分别给 19/25 级 | A/B |

## 数据根与初始化

| 类/方法 | RVA | 调用 / 字段 | 证据 |
|---|---:|---|---|
| `CollegeModule.InitData` | `0x1AF78D4` | 注册网络/事件监听，读取 `CollegeBuilding`、`CollegeStarLevel`、`FunctionOpen` 和全局参数；调用遗迹查询 | A |
| `CollegeModule.SendQueryGrowthBase` | `0x1AFB594` | 构造并发出 `C2L_QueryGrowthBase(579)` | A |
| `CollegeModule.OnGetQueryGrowthBaseData` | `0x1AF8850` | → `CollegeInit`；模块字段 `growthData: L2C_QueryGrowthBase` 在 `0x68` | A |
| `CollegeModule.CollegeInit` | `0x1AF6174` | 消费建筑、奇迹、派遣、训练、祈祷、队列/计时等基地快照 | B（字段由 wire 类型及模块状态交叉定位） |
| `CollegeModule.SendUnlockExploreRuin` | `0x1AF40E4` | 在主入口及模块初始化被调用 | A |
| `CollegeAlchemyModule.SendAlchemyMainData` | `0x189CBF4` | 在 `CollegeMainEntry.OnOpen`、`MainHallFSM.UpdateLoadModule`、制作回包后调用 | A |

`L2C_Login.growthBase` 与 `L2C_QueryGrowthBase(584)` 共享 `L2C_QueryGrowthBase` 类型。它含 `starEnergy/buildingList/warehouseGold/goldGainTime/starGainTime/extraPower/exploreList/trainingList/civilization/buildQueue/wonderQueue/prayQueue/washingCountDay` 13 个字段（`dump.cs` TypeDefIndex 13812）。客户端还把当前奇迹选择 `CurWonderIndex` 和最近配方存在本地；这些 UI 偏好不能替代服务器进度。

## 子模块与真实发送点

| 模块 | 代表性 RVA | UI/模块调用与协议 | 状态含义 | 证据 |
|---|---:|---|---|---|
| `CollegeUpgradeModule.UpgradeClick` | `0x1974464` | `BuildingUpgrade(233)` / `BuildStarUP(235)` | 升级与进阶；`CompleteClick` 经回调发 `BuildCrystalFinish(271)` | A |
| `CollegeUpgradeModule.C2L_BuildSpeedUP` | `0x1976C1C` | 回调构造 `BuildSpeedUP(234)` | 扣加速资源、改完成时间 | A |
| `CollegeModule.SendExchangePower` | `0x1AFBF88` | `ExchangePower(238)` | 星能转体力 | A |
| `CollegeModule.SendStartExplore` | `0x1AFD204` | `StartExplore(242)`，传地点/难度/遗迹/英雄 | 开始定时派遣；无 `FightData` | A |
| `CollegeModule.SendFinishExplore` | `0x1AFD5A4` | `FinishExplore(239)` | 领 `rewardData`，更新遗迹经验 | A |
| `CollegeModule.SendCancelExplore` | `0x1AFDC54` | `CancelExplore(236)` | 清队列、可能退星能 | A/B |
| `CollegeModule.SendExploreSpeed` | `0x1AFDE7C` | `ExploreSpeed(624)` | 派遣加速 | A |
| `CollegeModule.SendStartTrain` | `0x1AFC8C4` | `StartTrain(259)` | 英雄训练计时 | A |
| `CollegeModule.SendFinishTrain` | `0x1AFCB3C` | `FinishTrain(258)` | 英雄经验/等级 | A |
| `CollegeModule.SendCancelTrain` | `0x1AFCEE4` | `CancelTrain(257)` | 清训练队列 | A |
| `CollegeWonderModule.NetStartPray` | `0x1DB69C0` | `BuildStartPrayGod(369)` | 祈祷队列、英雄/材料 | A |
| `CollegeWonderModule.NetGetAward` | `0x1DB6B8C` | `BuildRewardPrayGod(368)` | 一次性奖励领取 | A |
| `CollegeAlchemyModule.SendMakeItem` | `0x189E174` | `MakeItem(594)` | 材料消耗与生产槽 | A |
| `CollegeAlchemyModule.SendAlchemyCollect` | `0x189F40C` | `AlchemyCollect(602)` | 产物/配方经验 | A |
| `CollegeAlchemyModule.SendAlchemyFinish` | `0x189EABC` | `AlchemyFinish(598)` | 顾客交易奖励 | A |
| `CollegeModule.SendWashingRoomOpt` | `0x1B006FC` | `WashingRoomOpt(1057)` | 装备属性与日次数 | A |

其余真实发送点、C2L/L2C ID、声明字段及对应回调逐项列于 `protocol_matrix.csv`。`HelpPowerSpeed(879)` / `HelpPowerSpeedValid(881)` 在构造器预先保存请求对象，发送点需继续逐指令核实，因此标 `INDIRECT`；不能把 `C2L` 类存在本身算成发送证据。

## 主动消息和 UI 更新

| L2C | ID | 客户端消费线索 | 证据 |
|---|---:|---|---|
| `TrainingUpdate` | 562 | `CollegeModule.OnReceiveTrainingUpdateMsg` `0x1AFB648` | A |
| `UpLevelBuildingId` | 507 | `CollegeModule.OnReceiveUpLevelBuildingIdMsg` `0x1AFB874` | A |
| `ExtraPower` | 695 | `CollegeModule.OnReceiveExtraPowerMsg` `0x1AFC404` | A |
| `PrayEnd` | 514 | `CollegeWonderModule.OnReceivePrayEndMsg` `0x1DB75DC` | A |
| `BuildingUpdate` | 559 | 声明 `type/buildingList`；具体消费注册点待逐指令确认 | B |
| `ExploreUpdate` | 561 | 声明 `exploreList`；具体消费注册点待逐指令确认 | B |
| `QueryGrowthBaseAlchemy` | 617 | 声明炼金元素/星能/增益字段；是否主动推送待确认 | UNKNOWN |

`L2C_FinishExplore(250)`、`L2C_AlchemyCollect(603)`、`L2C_AlchemyFinish(599)`、`L2C_BuildRewardPrayGod(372)` 自带 `rewardData`；基地事务随后还可能引起通用 `PlayerDataProto`/`ItemUpdate`。**实际推送顺序及是否每条都发没有原服线包，仍属 UNKNOWN**，实现时须通过实机回归验证。

## 反证

`collegeexplore` 的 34001–34015 与 `sectiontable.SectionID` 无交集；`CollegeModule.SendStartExplore` 构造 `C2L_StartExplore`，没有调用 `C2L_FightData(126)`/`C2L_CheckoutMainMissionSign(887)` 的直接边。故基地探险是定时派遣；主线“白夜崩解”是另一个系统。`activity.json` ID 28001 也没有作为 College 模块键使用。
