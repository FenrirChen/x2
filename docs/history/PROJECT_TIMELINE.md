# 项目认知时间线（按里程碑，非流水账）

## Phase 0 客户端恢复启动（2026-09-22 前）
Problem: 停服游戏能否本地跑起来。Breakthrough: 官方 2.4 APK 内核心资源完整（评级 B），
IL2CPP 可逆向，热更 DLL 未随包。Evidence: phase2/phase3 报告（history/2026-09-22_*）。
遗留: 热更程序集失传；Web 配置失效。

## Phase 1 协议基础与登录大厅（2026-09-22）
Breakthrough: PackInt/CRC/protobuf 子集/分帧全部还原；54→79 登录链路打通。
Evidence: phase6–phase10 报告。Code consequence: src/x2server/network+protocol。

## Phase 2 MainMission / 稳定启动（2026-09-22~23）
Breakthrough: Revival v0.2 客户端改造方案；首关实机进入。Evidence: phase11–13。

## Phase 3 持久化 / Hero / 大厅状态（2026-09-23）
Breakthrough: SQLite 快照+乐观并发；60 级账号；26 对大厅消息。
Evidence: phase14–16, phase18–20。Code consequence: player/store+login+hero。

## Phase 4 经济与成长静态审计（2026-09-23）
Breakthrough: 固定奖励 Section→Gift→Item 静态闭环；成长曲线全解；
随机掉落断链被首次确认（DropValueID 零命中）。
Evidence: history/2026-09-23_01_client_economy_data_audit.md 等。

## Phase 5 运行覆盖审计 / 假完成清理（2026-09-25 前）
Breakthrough: 76 feature×运行态口径矩阵；DailyDungeon 奖励审计；hardcode 门控消除。
Evidence: history/2026-09-24_*、docs/knowledge/coverage/false_complete_*。

## Phase 6 完整 265 表提取（2026-09-24~25）
Breakthrough: ResourceManager 全量注册表 dump；209 张从未提取的表全部解码（零记录错误）。
Evidence: D:/demo/x2/analysis/drop_archaeology/。

## Phase 7 掉落考古（2026-09-24）
Breakthrough: DropValueID 无静态映射（A 级负面）；DropProp 递归闭包 COMPLETE；
Unit.DC→DropClass 100%；ExtraDroop/CurrencyType/ItemSource 新表；
outsideItems/eNum/887 结构、323 无发送点。
Evidence: history/2026-09-24_07/08/09_*。

## Phase 8 第三方数据交叉验证（2026-09-25）
Breakthrough: 第三方工作簿掉落/商店静态层 99–100% 互证；识别其 3 处未申报修复+
4 处噪声行；"随机商店实测"22 条为唯一外部价格样本。
Evidence: history/2026-09-25_02_external_dataset_crosscheck.md。

## Phase 9 DropProp 算法逆向（2026-09-25）
Breakthrough: GetDropItemByGroup 完整 ARM64 还原——正/负 Picks 两种模式、
NoDrop+ΣProb 权重池、嵌套栈展开、IsADC 动态候选；"Prob=百分比"被精化为权重。
Evidence: docs/knowledge/rewards/drop_algorithm.md + analysis/drop_algorithm/。

## Phase 10 统一 Section Reward（2026-09-25）
Breakthrough: 3203/3203 关的奖励来源分类；扫荡 SecSweep 落地；
DYNAMIC_ALLOWED 真实性保护策略。Evidence: knowledge/rewards/section_reward_*.md。

## Phase 11 奖励语义总还原（2026-09-25）
Breakthrough: SetCheckout_BattleItem/GetPersistentItemsList 逐指令还原（eNum=迷宫获取计数）；
Gift 发放=服务器执行+客户端解析器孤立；装备实例=服务器整装下发（RewardData.rewardEquip）；
ChallengeReward1=文案 key、Chest=E_Chest 物品；Tower/Battlepass/WorldBoss=CLAIM_BUTTON。
Evidence: knowledge/rewards/reward_semantics.md + analysis/reward_reverse/。

## Phase 12 知识库重构（2026-09-25）
本层建立：evidence/knowledge/history/decisions 四层分离；PROJECT_INDEX 成为唯一入口。
