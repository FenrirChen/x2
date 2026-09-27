# 白夜行星名称映射（官方 2.4 客户端）

| 名称 | 位置 / 证据 | 判定 |
|---|---|---|
| 白夜行星 | `language.json` Key 1499039：基地设施说明；Key 2820171：进入基地权限 | 显示/剧情名称，A |
| 基地 | `functionopen.json` ID 21902，`FunctionType=E_Base`，19 级开放 | 功能入口名，A |
| 以太的奇迹位面 | `functionopen.json` ID 21912，`FunctionType=E_Wonder`，25 级开放 | 奇迹建筑入口名，A |
| 白夜大厅 | `collegebuilding.json` ID 701 | 基地主建筑名，A |
| College / GrowthBase | `dump.cs` 的 `CollegeModule`、`L2C_QueryGrowthBase`、`CollegeBuildingManager` | 内部系统名，A |
| CollegeAlchemy / CollegeWonder / CollegeUpgrade | `dump.cs` 的同名模块 | 基地子系统，A |

**结论：**玩家所说的“白夜行星”对应客户端的 **College/GrowthBase 基地系统**，不是一个名为 WhiteNightPlanet 的独立 Activity 或战斗玩法。两类入口分别通向基地与奇迹建筑；`CollegeEntry.OnOpen` 发 `C2L_QueryGrowthBase(579)`，`CollegeMainEntry.OnOpen` 发炼金数据及遗迹解锁查询。`activity.json` 的唯一 `ActivityID=28001` 没有与 College 表键相连，不能当作白夜行星玩法 ID。

**避免混淆：**`sectiontable.json` 中“白夜大厅”“白夜崩解”是主线关卡文案；`brinkconversation`、普通剧情文本及包含“白夜”的商店名也不是基地协议证据。`collegeexplore.json` 的 34001–34015 是限时英雄派遣点，不是 `SectionID`，其客户端链路是 `StartExplore/FinishExplore`，不是战斗入场/结算。
