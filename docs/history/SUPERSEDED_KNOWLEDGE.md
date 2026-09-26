# SUPERSEDED KNOWLEDGE — 曾被相信、后来被推翻/精化的结论

目的：防止未来 AI 从旧报告把旧错误带回来。当前权威结论一律以 docs/knowledge/ 为准。

| 曾相信 | 状态 | 推翻证据 |
|---|---|---|
| 323 C2L_FightDropInfo = 逐次拾取上报 | REJECTED | 全 dump.cs 无发送实例化点；实机两场金币本未出现 |
| 150 C2L_CheckoutMainMission 是结算通道 | REJECTED（精化） | 客户端 2.4 只发 887 wrapper（checkout 内嵌） |
| DropProp.Prob 数值=百分比 | REFINED | 正 Picks=相对权重（NoDrop+ΣProb 归一），负 Picks=确定重复次数（ARM64 还原） |
| NoDrop+ΣProb 必须=100 | REJECTED | 原始 332 行中 208 行违反（合计 1~209）；第三方工作簿据此做的 3 处"修复"不采纳 |
| DROP_WEIGHT_PARAM=10000 参与普通抽取 | REFINED | 仅 IsADC 动态候选权重（10000/Item.ItemValue） |
| DropValueID 可静态映射掉落 | REJECTED | 341 值全静态域零命中；第三方独立同结论 |
| ChallengeReward1 = 挑战奖励字段 | REJECTED | 值为 Language 文案 key（"111%月钻掉落奖励…"） |
| ChestReward/ExpertChestReward = Gift 组 | REJECTED | 是 E_Chest 物品 ID（1203501/1203701 系） |
| Gift.E_Random 需 ΣProbability=100 才可执行 | REJECTED | GetProbability 按权重和归一化，任意正权重合法 |
| 兽主 quality/eNum = 星级/词条参数 | REJECTED | quality=战斗包品质透传；eNum=迷宫物品场内获取计数 |
| HeroEquip 可由客户端生成 | REJECTED | 实例整只由服务器 RewardData.rewardEquip 下发，客户端零构造 |
| 兽主掉落=最终 HeroEquip 直接入包 | REFINED | 战斗内只掉 1240xxx ItemDataP，实例化在服务器 |
| MatchEnter(1082)/BattleEnter(1085) 无发送点 | REJECTED | 修正后的协议目录确认有发送点（早期扫描脚本 bug） |
| RandomShop 成交价=客户端默认价 | REJECTED | 第三方实测价（金币）与静态默认（光辉）完全不同→服务器定价 |
| AddGold(903) = 加账号金币 | REJECTED | 903 是场内迷宫银币（E_MazeCurrency→Item 1237903） |
| 1501/1526 bundle 之外还需 CDN 补资源 | REJECTED | assets_info 索引闭合、缺失 0（phase2） |
| 兽主星级编码在实例 TypeId 中（一星级一 TypeId） | REFINED | 部位级 TypeId(1240\|SS\|P) 末位=部位、无星级字段；1245\|SS\|S 族末位=星级但无部位/无 EquibBase 行，仅用于掉落展示/图鉴——Star 是掉落时刻的独立属性 |
| 初始副词条数量规则不可恢复 | REJECTED | EquibStage.MinorListMin 与 EquibAttribBD.MinorAttrNum 双表一致（1/2/3/3/4/4），CheckSubAttruib+GetAttrNum 反汇编闭环（A 级） |
| HeroEquip.Star 可由 TypeId 派生 | REJECTED | GM GetEquip 将 equipId 与星级/属性档作为独立输入；客户端信任 wire Star |
| outsideItems.quality 与星级无关 | REFINED | 掉落管线用 quality 作 EquibStage 键——对兽主掉落 quality 是星级载体（B 级，待实机样本固化） |
| quality 是星级载体（B 级，待固化） | REFINED | IdentifyItem（0x1E49578）以 DropBase 6/5/4 档公式掷出 quality∈{3..6}、JudgeDropItem 以 DroopLimit3=[min,max] 带收敛、outsideItems.quality 直接携带——**Star=quality（A 级闭环，无需实机固化）** |
| DroopLimit2/3=星级带 | REFINED | JudgeDropItem 代码+3203 关数据：仅 **DroopLimit3** 是 [min,max] 星级带（Count 必须=2，超上收敛/低于下拒绝）；**DroopLimit**=E_Outside 物品 id 白名单、**DroopLimit2**=E_Maze 物品 AddADCGroup 白名单 |
| 初始副词条数量 = MinorListMin（A 级） | REFINED | MinorListMin 客户端**全二进制 0 读者**（184,213 方法扫描）；初始条数 = 所选 EquibAttribBD 行 MinorAttrNum（A，GM opt=15 values=[equipId, attrbdId] 证据），base 行(QQ000000)的 MinorAttrNum 与 MinorListMin 六星一致；掉落路径官方选行规则（Min/Max 档）=SERVER_ONLY_UNKNOWN。合法范围 [Min,Max] 仍为 A 级（CheckSubAttruib 强制 Max 上限） |
| 掉落星级在带内的分布 UNKNOWN | REFINED | IdentifyItem 公式已恢复：cap=min(trunc((DropBase.Value−(level−NeedLevel)/Div)·128·(1−Cv/1024)·100/(magicFind+玩家MF+100)), ThresholdValue)，Next(1,cap)<129 命中（上界不含）。基准（Cv=0/MF=0/level≤NeedLevel）单档条件命中率为最低值 6★≈0.2500%、5★≈2.0837%、4★≈5.5580%（边际分布 0.2500/2.0785/5.4286/92.243%，再经带收敛/拒绝）；83 个 ADC 组 Cv 全 0。运行时输入（level/MF）可观测，无结构性未知 |
| 词条数值按 EquibAttribBD[Star] 行池 roll / AvK 取 AttribBD 行数值域 | REFINED | EquibAttribBD base 行（QQ000000/000100）**全部数值=0**，仅决定条数；随机件数值宇宙 = **EquibAttrib[star, src, type] 3 档阶梯**（src0 主基础/src1 主成长/src2 副基础/src3 副强化增量，384 行重解析含 AttribSRC，consumer 仅 College 图鉴显示 A）；AttribBD filled/seasonal 行 = 固定发放盘（1★/2★ 盘值超出全部阶梯 → 盘可自由授权）。取档算法在服务器 |
| EquibAttrib 与生成无关（前轮未研究） | REFINED | EquibAttrib 384 行 = 6星×4src×16类型数值阶梯；GetEquipBaseProperty/GetEquipMaxProperty 反汇编给出 src 配对（主 0+1 / 副 2+3）与公式（主 max=src0top+src1top×level）；ChanceSec=[60,40]/[80,20] 恒定——官方数值为多档离散+权重，非连续 min-max |
| 练习服时代 'no server drops' 空应答规则无害 | REJECTED | drop_data(264) 应答 dropValues 恒空 ⇒ BattleInfo.dropValues 预算恒空 ⇒ JudgeDropItem 拒绝全部 ItemStruct 掉落 ⇒ outsideItems 恒空——整个客户端本地掉落管线被静默杀死（2026-09-25/26 实机 2133101/2130104 复现并修复验证） |
| dropValues 预算由客户端本地生成 | REJECTED | 预算是服务器权威配额：264 客户端上报 → 266 应答 → FightModule.OnFightDropData(0x1447E1C) 以 UpdateDropValue 命令经 LogicBattle.OnInput 触发 OnUpdateDropValue(0x18FA700) **整表替换** BattleInfo.dropValues（str x19,[x20,#0xC0]）；客户端只执行 |
| 27 组 × 1,000,000 无限预算（2026-09-25 恢复期策略） | SUPERSEDED | 2026-09-26 起改为官方 DifficultyLevel 分级预算 LOW/MID/HIGH = 1000/3000/5000（REVIVAL_COMPAT/USER_DECISION，decisions/compatibility/equip_dropvalues_budget.md）——无限预算使资源本货币代理物产出失去经济节流 |
| 金币本手打金 = 该关 MopReward 数量（兼容金） | SUPERSEDED | E_ReportCurrency 代理物（金币袋 1101076-80 等，EffData=[901,单件值]）实机确认即官方手打金币本源；结算折算入账后手打 MopReward 兼容金删除，MopReward 回归扫荡专用 （gold_dungeon_manual_reward 决策 SUPERSEDED） |
| 1-2★ 不经战斗 ADC 掉落产生（IdentifyItem 兜底 3★） | REFINED | 实机 [1,3] 带兽主本掉出 1★×73/2★×9/3★×21——IdentifyItem 只覆盖 3-6★，低带存在另一条未追明的 1-2★ 质量路径（疑似低带改用 DropBase 1/2/3） |
| DropValueID 是语义未知的独立 ID 族 | REFINED | 结构已破解：DropValueID = 10600000 + SectionID%100000（310/341 全量命中，85 组有意共享）——服务器侧按关卡派生的掉落配置键（现知用途=264/266 预算配置来源，B 级）；配置数值随官方服务器数据失传 |
| E_ReportCurrency 代理物可按普通可堆叠物品发放 | REJECTED | 官方表 Icon=""×36/NameID 无条目=设计为永不展示；官方语义为结算折算为账户货币（EffData=[桶,单件值]×num，桶+1237000=账户 Item，68/68 表派生映射）——Revival 已实施；原物发放导致金币本结算页大量空白贴图（实机 2130104） |
| SetCurItemValueTotal 参与星级/品质选择（存疑） | REJECTED | 纯价值记账（0x1E4AD70）：仅重算 EquibValue×ItemValue/1000×num 并累加，唯一调用方 RecoverBattleData；不产生也不筛选星级 |
