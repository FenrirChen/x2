---
Document-Type: Current Knowledge
Domain: Progression
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - (none; still authoritative)
---

# 客户端成长系统静态配置审计

2026-09-23；官方简中 Android 2.4。复用 `phase3_output`、既有资源索引、`dump.cs`、protobuf 结构及定点 `libil2cpp.so` 反汇编。只从资源索引指定的少数配置路径读取缺失表，未重新全量解包 APK、遍历 1,501 个 Bundle、运行模拟器或改服务器/存档。`CONFIRMED` 表示指定静态字段与消费路径已核对；`PARTIAL` 表示仍不能闭合官方业务操作。

## 1. 总结

| 成长系统 | 结果 | 核心表/缺口 |
|---|---|---|
| 玩家等级 | **partial** | `RoleExp` 120 行的经验、体力上限、奖励和 `FunctionOpen` 已导出；满级溢出与实际发奖时点未知 |
| 角色等级 | **partial** | `PlayerLevelBonus` 120 行、神格经验资源和基础属性公式可用；服务器升级校验仍缺 |
| 角色升星 | **partial** | `PlayerStage` 46 行，专属/万能碎片路径及属性已找到；选择和最终迁移校验未知 |
| 角色独立突破 | **not found** | 没有发现区别于 `PlayerStage` 升星的角色等级上限突破表/协议操作 |
| 武器等级 | **partial** | 实际是角色绑定 `Artifact`；`ArtifactFuse` 有升级材料与金币，非传统武器经验条 |
| 武器升星/突破 | **partial** | `ArtifactFuse` 有熔合材料、金币及角色阶段条件；状态转换仍需确认 |
| 兽主强化 | **partial** | `EquibExp` 0–15 成本和 `EquibStage` 品质/喂养值；经验来源、实例执行仍缺 |
| 兽主升星/品质 | **partial** | 1–6 阶及品质预置属性可见；操作成本和真实实例生成未闭环 |
| 技能升级 | **partial** | `SkillLevel` 2,155 行含材料、角色等级门槛、前置技能；全部 `GoldConsume` 为零 |
| 属性成长 | **partial** | 角色基础 HP/攻击/防御公式已在代码确认；武器/兽主等完整叠加未知 |
| Material → Item | **resolved（本轮引用范围）** | 112 个引用的 ItemID 均命中 `Item` 并可用 `Language` 命名；不表示材料使用业务全恢复 |

每套系统的 `STATIC_RULE / RUNTIME_STATE / SERVER_ONLY / REVIVAL_READY` 分类保存在 `analysis/progression/progression_summary.json`。目前没有一套**完整官方业务系统**可仅凭这些表直接宣告 `REVIVAL_READY=true`；成本曲线与材料目录可以先用于离线校验。

## 2. 玩家账号等级

`RoleExp`：120 行，字段 `RoleLevel, ExpLevel, ExpSum, PowerNum, GiftID`；来源 `phase3_output/raw_tables/RoleExp__e5e6471e3e1ce034785246440f2beb02.bin`。`ExpLevel` 在当前等级行表示升往下一等级的需求；`ExpSum` 与相邻行累计关系一致，是**到达当前等级**的累计值：Lv1 0，Lv2 12，Lv3 24。Lv120 无 `ExpLevel`，最高配置等级为 120。完整曲线、每级 `PowerNum`、`GiftID → Gift → Item` 和 `FunctionOpen.OpenLevel` 引用在 `analysis/progression/player_level.json`，不是人工抄表。

| 当前等级 → 下一级 | 本次经验 | 当前等级累计 | 体力上限 | 达到当前等级的 Gift/解锁示例 |
|---|---:|---:|---:|---|
| 1 → 2 | 12 | 0 | 60 | Lv1 无 Gift |
| 2 → 3 | 12 | 12 | 62 | `721000 → 1237900 因果 ×10` |
| 3 → 4 | 12 | 24 | 64 | `721000 → 因果 ×10` |
| 10 → 11 | 12 | 108 | 78 | `FunctionOpen` 有许愿、票据兑换的 Lv10 条件 |
| 60 → 61 | 6,400 | 121,007 | 149 | `721002 → 因果 ×120` |
| 119 → 120 | 64,000 | 1,435,366 | 150 | `721003 → 因果 ×150` |
| 120 终端 | 无 | 1,499,366 | 150 | 仍有 GiftID，但领取时点不能仅凭行推断 |

`FunctionOpen` 共 84 行，含 `OpenLevel/OpenStory`；`OpenLevel=999` 等可能代表未开放，不能直接发放功能。当前证据没有证明满级后的经验舍弃、储存或转化，也没有确认每级 Gift 的服务器实际发放时点。玩家 `L2C_UpdatePlayerLevel` 协议存在；等级/经验是运行态，不等于客户端自动按表发奖。

**STATIC_RULE:** 等级曲线、配置最高级、体力上限、Gift/功能条件。**RUNTIME_STATE:** 账号等级、经验、已领奖与功能解锁。**SERVER_ONLY:** 满级溢出、升级事务和实际发奖时点。**REVIVAL_READY:** no，曲线可用，业务尚未闭环。

## 3. 神格等级、升星与突破：贝黑莫斯 1003

`PlayerAttrib`：1,182 行；1003 的静态原型 `Level=1, DefaultStage=1, ChipPropID=1201003, WeapenId=1503, Profession=303, HPMax=600, Damage=60, Defense=40`。这是角色初始配置，**不是当前玩家实例**；实例 `HeroData` 有 `level/star/exp/heroSkills/godEquip/equips`。本轮没有读取或修改玩家 SQLite。

`PlayerLevelBonus`：120 行，`HeroLevel/HeroExp/ExpSum/DamageLevelBonus/DefenseLevelBonus/HPMaxLevelBonus/SPMaxLevelBonus`。`HeroLevelUP.RefreshLevel` (RVA `0x1400084`) 用当前角色等级取表，`RefreshConsume` (`0x14003FC`) 调用 `GetCurrencyNum(7)`，并将 UI 消耗物设为 **Item 1237907 神格经验**。因此 `HeroExp` 是当前等级到下一等级的经验消耗；`ExpSum` 是包含本行转移的累计消耗。界面这条路径未读金币，不能凭常见 RPG 规则另加金币。

| 贝黑莫斯当前等级 → 下一级 | 神格经验 | 累计到下一等级 | 等级属性加成（攻击/防御/HP） |
|---|---:|---:|---|
| 1 → 2 | 120 | 120 | 0 / 0 / 0 |
| 2 → 3 | 140 | 260 | 58 / 67 / 54 |
| 3 → 4 | 160 | 420 | 117 / 134 / 109 |
| 119 → 120 | 237,184 | 4,868,075 | 6,941 / 7,932 / 6,445 |
| 120 终端 | 无 | 4,868,075 | 7,000 / 8,000 / 6,500 |

`HeroModule.IsMaxLevel` (`0x19100E0`) 查询 `PlayerLevelBonusManager.GetItem`；表终止于 120。没有找到当前星级降低等级上限的独立字段或该界面的阶段门槛。满级后的神格经验如何处理仍需服务器规则。完整 1–120 曲线见 `hero_level.json`。

`PlayerStage`：46 行，`HeroStage/ChipNum/UniversalChip/BigStarNum/SmallStarNum` 和阶段属性加成。`HeroStarUP.OnClickUpLevel` (`0x1927868`) 查询 `PlayerStageManager.GetItem` 后调用 `HeroModule.UpStar`。`C2L_HeroOpt` 的 `OPT_UPSTAR=2` 带 `upstarConsumeItemId`，表明实际消耗的碎片物品可在请求中选择。贝黑莫斯的专属碎片是 `PlayerAttrib.ChipPropID=1201003 贝黑莫斯碎片`，通用备选 `PlayerStage.UniversalChip=[1201000 万能神格碎片, 数量]`。表中的 `ChipNum` 是阶段行数量，不将两种碎片相加。

| 当前 Stage → 下一 Stage | 显示大星/小星 | `ChipNum` | 万能碎片备选 | 阶段攻击/防御/HP 加成 |
|---|---|---:|---:|---|
| 1 → 2 | 1 / 0 | 10 | 1201000 ×10 | 0 / 0 / 0 |
| 2 → 3 | 1 / 1 | 10 | 1201000 ×10 | 76 / 96 / 57 |
| 3 → 4 | 2 / 0 | 10 | 1201000 ×10 | 161 / 201 / 120 |
| 4 → 5 | 2 / 1 | 25 | 1201000 ×25 | 334 / 417 / 250 |
| 46 终端 | 6 / 0 | 18（原始字段） | 1201000 ×18（原始字段） | 4,000 / 5,000 / 3,000 |

46 终端行仍有 `ChipNum`，不能解释为可升到 47。实际专属/万能选择、是否存在额外服务端限制，以及 `RelicID` 如何解锁被动，保留 `PARTIAL`。`PlayerStage` 没有金币字段。没有发现单独的角色等级上限突破表/操作；**角色突破 = NOT_FOUND**，不能把升星自动称作突破。`hero_star.json` 含全部阶段记录。

**STATIC_RULE:** 通用角色经验、阶段星图、碎片 ID 与数量、属性加成。**RUNTIME_STATE:** `HeroData.level/star/exp`、神格经验和碎片余额。**SERVER_ONLY:** 转移合法性、选择与消费事务、满级处理。**REVIVAL_READY:** no。

## 4. 武器：角色绑定 Artifact 1503

`PlayerAttrib.WeapenId=1503 → ArtifactBase.ArtifactID=1503`，名称**绯红之刃**，所以本客户端武器走 `Artifact`，不是 `Equib`。`ArtifactBase` 40 行，1503 的 `FuseLevel=[0,1,2,3,4,5,6]`；基础属性类型/值为 `(100,24),(102,22),(104,182)`，高级属性数组与等级对应。`ArtifactFuse` 28 行，按职业 `ProfEnum` 与 `FuseID` 查；贝黑莫斯 `Profession=303`。`ArtifactModule.ArtifactLevelUP` (`0x17F52C0`) 检查 `AdvancedItem/AdvancedConsume`，`ArtifactFuse` (`0x17F5578`) 检查 `FuseItem/FuseConsume`；二者调用 `GetCurrencyNum(1)`，枚举 `E_Gold=1`。协议 `ArtifactOpt.JO_LevelUP=0`、`JO_Fuse=1`，实例 `HeroGodEquip` 有 `level/star/jewel/godEquipAttr`。

| 职业 303，FuseID | 角色 Stage 条件 | 升级材料 / 金币 | 熔合材料 / 金币 |
|---:|---:|---|---|
| 0 | 1 | 无材料字段 / 0 | 无材料字段 / 20,000 |
| 1 | 3 | `1238100 1★灵魂石 ×6` / 1,000 | `1238047 空粒子 ×12` / 50,000 |
| 2 | 5 | `1238101 2★灵魂石 ×6` / 3,000 | `1238048`、`1238052` 各 ×12 / 100,000 |
| 3 | 8 | `1238102 3★灵魂石 ×6` / 12,000 | `1238049`、`1238056` 各 ×18 / 200,000 |

武器没有找到独立 `WeaponExp` 曲线；此版本主要是 Artifact 等级/熔合材料与金币。`FuseID` 到具体实例 `level/star` 的迁移、属性比率 `AttrRate/MaxAttrRate` 的最终算法仍未完整追通，不把表列误当成已经可执行的事务。全 28 行在 `weapon_progression.json`。

**STATIC_RULE:** 角色→武器、职业→阶段材料/金币、基础属性与熔合节点。**RUNTIME_STATE:** `HeroGodEquip.level/star/jewel`、金币/材料。**SERVER_ONLY:** 具体迁移与最终属性、失败处理。**REVIVAL_READY:** no。

## 5. 兽主 Equib

`EquibBase` 126 行，`EquibExp` 16 行（Level 0–15），`EquibStage` 6 行，`EquibAttrib` 384 行，`EquibAttribBD` 66 行，`EquibSuit` 20 行。`Item` 的 `E_Equip` 与 `EquibBase.EquibId` 精确交叉；例 `1240001 奇美拉·一`，部位 1、套装 400，主属性候选类型 `[100]`，副属性候选和权重由 `EquibBase` 提供。`HeroEquip` 协议实例有 `id/typeId/level/exp/star/param`，同名兽主可以有不同实例 ID 与属性参数，不能只凭 ItemID 合并。

| 当前强化等级 → 下一级 | `NeedExp` | `NeedGlod` | `SumExp` / `SumGold`（当前级） |
|---|---:|---:|---:|
| 0 → 1 | 30 | 500 | 0 / 0 |
| 1 → 2 | 50 | 800 | 30 / 500 |
| 2 → 3 | 70 | 1,000 | 80 / 1,300 |
| 14 → 15 | 1,030 | 30,000 | 4,460 / 89,500 |
| 15 终端 | 无 | 无 | 5,490 / 119,500 |

`EquibExp.IsEvent` 在 3/6/9/12/15 行为 1，提示强化节点事件；不能直接断言新增副词条的具体算法。10–15 行还有未命名 protobuf `unknown_field_8=[400]`，不解释其语义。`EquibStage` 1–6 行有 `MinorListMin/Max`、装备喂养经验值、经验/金币倍率和高阶芯片字段；未确认 `EquibStage` 是可主动“升星”操作还是掉落品质/喂养等级。`EquibAttribBD` 中 6 品质有 0–15 等级预置，其他品质多只有 0 级；不能据此宣称所有品质都能强化到 15。随机主副属性的权重/范围配置存在，实际实例抽取及升级副词条结果为 **LIKELY_SERVER_ONLY**，不拟合或编造。

**STATIC_RULE:** 强化需求表、阶段与品质属性候选、套装关联。**RUNTIME_STATE:** 每个 `HeroEquip` 独立 ID、等级、经验、星/品质和 `param`。**SERVER_ONLY:** 喂养输入到经验的计算、随机词条生成、事件节点执行。**REVIVAL_READY:** no。完整样本和各表摘要见 `equipment_progression.json`。

## 6. 技能与神权

`SkillBase` 1,333 行；`SkillLevel` 2,155 行，主键 `SkillID + Level`，字段 `SKillGrowCond/GrowCond/Item/ItemNum/GoldConsume/PreSkillID/PreSkillLevel`。客户端 `HeroSkillDetail.CanLevelUp` (`0x1916204`) 按当前技能等级取 `SkillLevelManager.GetItem` 并检查金币、物品、前置技能；`IsLevelMax` (`0x1916060`) 也据表判断。全部 2,155 行的 `GoldConsume` 均未编码非零值，按该版本配置为 **0**；UI 仍有通用金币检查代码，不能凭代码存在造出金币价格。`C2L_UpHeroSkill` 带 heroId/skillID/uplevel，实例等级在 `HeroData.heroSkills`。

贝黑莫斯 1003 的普通技能 `10030 夺魂之镰` 有 Lv1–12；Lv12 行无升级消耗。示例：

| 技能当前级 → 下一级 | 角色等级门槛 | 材料 | 金币 | 前置 |
|---|---:|---|---:|---|
| 10030 Lv1 → 2 | 15 | `1202080 神权拓本·空白 ×1` | 0 | 无 |
| Lv2 → 3 | 20 | 同上 ×1 | 0 | 无 |
| Lv6 → 7 | 40 | `1202081 神权拓本·剑柄 ×1` | 0 | 无 |
| Lv10 → 11 | 64 | `1202086 高级神权拓本·剑柄 ×1` | 0 | 10030/10031/10032/10033 均达到 10 |

同角色 `10031/10032/10033` 也有 Lv1–12，`10035 山之巨兽` 有 Lv1–5，`10039 神降：红月之舞` 只找到 Lv1。`SkillBase(10039).SkillUnlock=[46,1206003,5]`；`GodHole` 的 `HeroID=1003,HoleNum=5,SkillID=10039,ItemID=1206003,Cost=5` 交叉印证此特殊技能由第 5 孔和指定材料关联，不能仅凭数组断言“角色 46 级”——46 也可能是 HeroStage。`SkillBase` 技能种类和原始解锁数组保存在 `skill_progression.json`，避免把被动、普通、奥义强行视为同一规则。技能倍率/CD 在 `SkillBase`、其他战斗表中有字段，本轮不做全面战斗数值审计。

**STATIC_RULE:** 各技能每级材料、英雄条件、前置技能、配置最高行。**RUNTIME_STATE:** `HeroData.heroSkills` 与材料余额。**SERVER_ONLY:** 实际解锁、连续升级次数与业务事务。**REVIVAL_READY:** no。

## 7. 属性成长与材料闭环

`HeroModule.GetBaseAttr` (RVA `0x1906600`) 连取 `PlayerAttrib`、`PlayerStage`、`PlayerLevelBonus`。定点反汇编在 `0x19067A4` 读取常量 **0.001**，攻击、 防御、HP 分别执行：

`trunc(基础值 × (1 + 阶段加成/1000) × (1 + 等级加成/1000) + 对应 COR)`。

结果以向零截断转为整数。对 1003 的静态初始 Stage1/Lv1，攻击 `trunc(60+12)=72`、防御 `trunc(40+4)=44`、HP `trunc(600+120)=720`；这是 `GetBaseAttr` 的**基础属性计算**，不是把武器、兽主、技能、战斗 Buff 全部叠加后的最终面板。其余属性和叠加顺序仍 `PARTIAL`。不从少数点拟合额外曲线。

本轮引用的 112 个材料/货币 ID 全部落到 `Item`，名称来自 `Language.Chinese`，类型也已保存。关键例子：`1201003 贝黑莫斯碎片` (`E_Chip`)、`1201000 万能神格碎片` (`E_Chip`)、`1237907 神格经验` (`E_Currency`)、`1237901 金币` (`E_Currency`)、`1202080 神权拓本·空白`、`1202081 神权拓本·剑柄`、`1238100 1★灵魂石`、`1238047 空粒子`。全表见 `material_links.json`；**名称本身没有被用作成本证据**，引用必须来自上游配置字段及调用路径。

## 8. 缺口性质与 Revival 结论

| 缺口 | 性质 | 处理结论 |
|---|---|---|
| 角色独立等级上限突破 | 未找到独立静态配置 | `NOT_FOUND`；升星不可代替突破 |
| 玩家满级溢出、每级 Gift 实际发放 | 需服务端权威行为/历史响应 | 不把静态 `GiftID` 自动当作已发奖 |
| 武器等级/星级迁移与完整属性 | 有表，调用/状态变化未闭环 | `PARTIAL`；不得把两种消耗混为一笔 |
| 兽主经验喂养、品质/星级操作 | 有成本及候选表，缺输入算法 | `PARTIAL`，需要定点 handler 或响应样本 |
| 兽主随机属性、副词条强化 | 静态候选与权重存在，实例结果动态 | `LIKELY_SERVER_ONLY`；不生成伪官方词条 |
| 神权特殊技能解锁 | `SkillBase` 与 `GodHole` 相交，但数组 46 的单位未证实 | `PARTIAL`；保留原始条件 |

这些表足以做官方配置的**离线索引与成本核对**，还不足以实现完整官方成长业务。机器可读输出：`analysis/progression/{player_level,hero_level,hero_star,hero_breakthrough,weapon_progression,equipment_progression,skill_progression,material_links,progression_summary}.json`。重建脚本只定位已有索引的 22 张命名表并写解析后摘要，未复制原始资产。
