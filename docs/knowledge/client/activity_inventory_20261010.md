# 客户端活动遗留调查（2026-10-10）

## 结论与范围

2.4客户端保留大量活动模块、协议、配置和资源，不只是空按钮。本次为静态调查，没有开启活动、修改运行代码或改动存档；没有进行客户端逐页实测。原生方法存在及配置可解码，不代表服务端业务闭环或全部资源可加载。

证据导出：`analysis/activity/client_activity_inventory_20261010.json`。使用既有 `analysis.progression.probe.read_tables` 从规范资源索引读取APK原始表，meta记录每张表来源和数量；类与协议来自 `tools/Il2CppDumper-bin/dump.cs`。Activity表仅有世界BOSS一行；一般活动应读取ActivityReal，不能混用。

## 静态存量

| 配置 | 数量 | 意义 |
|---|---:|---|
| ActivityReal | 141 | 活动条目，包含预告、主玩法、商店等子项，不等于141个独立活动 |
| ActivityDungeon | 105 | 活动副本及挑战关联 |
| ActivityTask / ActivityTaskBox | 314 / 55 | 任务和进度奖励 |
| ActivityBox / ActivityBoxGoods | 27 / 693 | 活动奖池及商品行 |
| TradeActivity | 87 | 限时兑换规则 |
| ActivityBuilding | 16 | 建筑配置 |
| NewYearCafe / NewYearFood / NewYearCook | 90 / 35 / 11 | 春节餐厅、菜谱和厨师玩法 |
| NewYearFoodTask / NewYearCookTask | 78 / 50 | 春节专用任务 |
| MonopolyGrid | 51 | 大富翁格子及奖励关联 |
| Tower / TowerBase / TowerController / TowerGrid / TowerRank | 24 / 50 / 23 / 16 / 24 | 塔防单位、升级、波次、格子、排名关联配置 |
| MoonWorldMap / MoonCamp / MoonEquip / MoonNPC | 12 / 4 / 24 / 20 | 月主题地图、阵营、装备、NPC |
| MemoryBuff | 26 | 记忆玩法增益 |
| Card / CardPassive | 60 / 59 | 卡牌与被动规则 |
| SimpleActivity / SimpleActivityAction | 1 / 4 | 七天积分活动，配置奖励档位及额外奖励 |

还确认存在activity01–activity11共11个剧情资源包。APK音频目录保留周年、春节、共工、月羲初九、影之岛、奥西里斯等资源名称。音频名字仅证明对应资源遗留，不能单独用来认定活动组映射。

## 有直接证据的玩法

- 周年、春节：AnniversaryActivityModule、NewYearActivityModule、NewYear2ActivityModule。后者有餐厅解锁、布置、烹饪、升级、收益领取，以及灯会问题、回答、剪纸与奖励处理方法。
- 主题剧情与挑战：FrostActivityModule、OsirisActivityModule、AncientActivityModule、SakuraActivityModule、SakuraEndActivityModule、BaseActivityModule；共有副本、任务、商店、预告奖励、回顾奖励及奖励池查询路径。
- 塔防：TowerDefenseModule、TowerDefenseModuleNeo和专用表；ActivityReal中72015、72024、72033明确标记E_ActivityTowerDefense。
- 大富翁：73017标记E_MonopolyActivity；DiceGameActivityModule、MonopolyGrid存在。
- 翻牌：73018“花语缦心”、73021“星语携愿”，类型E_Flip。
- 卡牌：73100类型E_Card，CardGameFightModule、CardGameUIModule及卡牌表存在。
- 记忆：80026类型E_MemoryActivity，MemoryBuff和Section类型Memory存在。
- 兑换：炼金限时兑换、万圣道具兑换、炎夏期风限时兑换、秋夕限时兑换；73009“零钱大作战”。
- 签到、累计抽奖、限时任务、七日活动、额外掉落，以及问卷、邀请、累充等运营条目。

许多大型活动ActivityName键在当前Language/LanguageUI中未解析成中文，证据中保持空值。不能仅凭模块英文名猜官方中文标题。早期试探用MoonChapter/MonopolyMap/Memory/TowerDefense作为表名找不到；它们不是已确认缺失的整套玩法，后续已按实际表名找到对应配置。

## 协议与入口

dump中存在QueryActivity、UpdateActivity、UpdateActivityConfig、QueryActivityConfig、ActivityMissionData、ActivityMissionSelBranch、ActivityShop、ActivityRewardPoolInfo/Draw、预告/回顾领奖及累计抽奖/累充协议。ActivityNoticeModule具备活动列表、配置更新、等级变化、任务、副本、商店及领奖处理方法。

入口由服务端活动列表及功能开放状态共同控制，不能只改一个按钮。部分活动有运行期服务器配置更新路径；静态历史时间和部分缺失展示文本不能直接作为今天的完整运营配置。

## 当前服务端状态和恢复次序

`LobbyService(..., sweep_enabled=False)`为默认，生产启动未传True，因此QueryActivity返回空列表，EntryidStatus关闭功能19。扫荡73010虽有保留实现和配置，也没有默认启用。不能以旧覆盖文档或代码分支存在判断当前已开放。

多数活动专用业务处理尚未实现。世界BOSS、战令等独立玩法应按自己的已实现模块评估，不等于活动中心已完成。

建议第一批选择静态规则较少的兑换、签到/累计抽奖、积分任务，分别完成查询、条件、扣费、领取、推送、持久化和防重复，再恢复主题活动副本+商店+任务。春节经营、塔防、大富翁和卡牌需专门研究交互及战斗结算，不能通过批量下发141条活动直接恢复。
