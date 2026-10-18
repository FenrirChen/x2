# 月之荒庭恢复记录（2026-10-18）

## 原因与接入

原服务端只有 964/965 `MoonEquip` 空态应答，958/960 等入口必需请求没有处理器。客户端 `MoonCampPage.OnOpen`（0x17305C8）会同时请求阵营解锁和声望；缺响应时一直显示正在连接。

新增 `messages/moon.py` / `player/moon.py`，接入 958–981 共12对原生消息，移除 Lobby 的装备空态占位。任务类型16/17/18/19分别是全部、阵营、委托、引导，使用原生 `GameTask` / `FinishGameTask` 链路；TaskData保留第10字段childrenMission。先推任务缓存，再应答入口，避免只修消息号后出现空引用。

数据恢复到 `data/moon_catalog.json`：4阵营、20NPC、24月之装备、193任务组及其子任务/前置/奖励。入口为2111001（月之荒庭）和2111051（月之暗面·新月），沿用已有战斗授权、掉落校验、结算收据，不改变普通战斗的团队技能载荷。装备选中后，在FightData字段10下发原生FightGroupSkillData，技能、等级和附加被动来自月之装备表。

## 原版数据证据

数据源为提取APK的 `assets/bin/Data`，ResourceManager索引指向table/mooncamp、moonequip、moonnpc、missiontable、missionpredecessor、quest、gift、item、globalparamstring。客户端符号来自Il2CppDumper dump.cs，ARM64指令来自libil2cpp.so。摘要见旁边 `moon_evidence/source_manifest.json`，关键指令保存在该目录。

重要更正：GlobalParamString不是只有键名。解密后前4字节是条目数，后面protobuf容器字段1为键名索引，字段2为完整键值行。之前按普通定长表解析失败，误以为数值缺失。本轮按容器字段2恢复了512行，月之参数以下采用原值，无需临时数值。

| 配置 | 原值 |
| --- | --- |
| MoonChapterID / MoonDefaultCamp | 2011000 / 700001 |
| MoonEquipExpItem / MoonFavorItem | 1120001 / 1120002 |
| MoonEquipExpGetLimit | 每日300蚀化芯片 |
| MoonFlowerGetLimit | 每日6朵月见花 |
| MoonFlowerGiveLimit | 每日9999朵赠花额度 |
| MoonNormalEquipLimit / MoonSpecialEquipLimit | 普通槽最多4 / 特殊槽1 |
| MoonTaskReceiveLimit | 每日接取4次 |
| MoonTaskRefreshLimit / MoonTaskRefreshNum | 共6批（初始批+5次手动刷新）/ 每批3个候选 |
| MoonPrestigeReward1 / MoonPrestigeReward2 | 1120013 / 1120014，分别提升采花、赠花额度 |

原生 `MoonTaskPage.OnOpen`（0x174612C）查询时opt=1，`MoonAcceptTaskPage.OnRefresh_BtnClick`（0x172BF40）刷新时opt=2；刷新面板上限按参数值减1展示，按钮也限制5次。

`MoonCampModule.OnMoonCampUnLock`（0x172CBD8）把959的keyVal同名参数视为今日已用数量，与ServerTableConfig的最大值含义不同。下发今日采花、赠花、芯片、委托接取和刷新计数。

`MoonEquipModule.GetLevelUpConsumeNum`（0x17385E0）读取EquipExp[currentLevel]，升级消耗600、1200、1800，不取相邻差值。普通槽由四个阵营各一个1120007声望奖励逐个打开。`MoonEquipPage.OperationEquip`（0x1739BF8）穿戴operate=1，卸下operate=2；卸下回包moonEquipId=0，保留槽类型和索引。

月见花1120002的EffData=[5]，每朵增加5点目标NPC好感，达到100停止；五档阈值20/40/60/80/100。NPC任务中的1120008按其EffData增加发布任务NPC的好感。阵营解锁依据对应CampTask引导完成，地图Level=1/4/7/10是营地所在层，不是账号等级。

## 兼容规则与持久化

用户2026-10-18批准：委托随机兽主原Gift只提供部位权重，ItemQuality为E_Unsure，缺鉴定规则；按任务难度1–2/3–4/5–7/8–9分别发3/4/5/6星。部位仍按原Gift权重。真正生成装备实例，并在领奖应答前发送EquipUpdate；不把装备部位ID当普通堆叠道具。

每日额度按服务器既有北京时间00:00边界重置；保留阵营、好感、装备、一次性任务和未完成委托。在线午夜推刷新，离线首次请求惰性刷新。重复领取、未知ID、未达前置、未接取子任务、错误槽位、材料不足均返回13，不伪成功。升级扣料、奖励与领取状态在同一事务提交，传输重试收据每日/256条有界保存。

状态存在既有activity_state的账号行：period=0、namespace=moon、state_key=state。不新增账号历史大表、不保存战斗日志副本；该表已经在存档导出/导入边界内，测试验证真实ZIP导出再导入后月之进度及背包一致。

## 验证及验收范围

自动测试覆盖全部入口查询编码、原生操作码、任务前置和子任务校验、引导解锁及重复同步、赠花实际扣料、声望奖励阈值、升级与卸装、委托领奖及兽主实例、每日重置、普通战斗回归、月之战斗结算额度，以及存档ZIP往返。客户端场景、剧情触发和UI最终表现由用户手动验收；自动测试通过不代表已经完成设备验收。

本轮结果：月之荒庭25项通过；扩展回归共103项，首次99通过、1项本轮宝石奖励失败（已修复并重跑通过）、3项旧失败。三个旧失败已在干净51d6f1b归档上以同样断言复现（赛季关闭两项、现世复刻新增箱子与旧预期不符一项）。本地服务已于2026-10-18 14:33:24启动，三端口监听正常；重启前测试库备份位于runtime/before_moon_garden_20261018_143322/player.sqlite3。未修改APK，未部署远程。
