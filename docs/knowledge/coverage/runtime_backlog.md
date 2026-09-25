---
Document-Type: Current Knowledge
Domain: Coverage
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - (none; still authoritative)
---

# X2 Revival Runtime Coverage Backlog

> 2026-09-25 奖励结算进展：887 `outsideItems`、全关卡奖励分类、五关金币扫荡量兼容、1027 扫荡静态 Gift 已接入；单预览 ×1 已移除。下一步优先解决装备实例交付、逐 Section 运行时掉落源闭包与特殊奖触发。历史条目保留原时点事实，现状见 [section_reward_system.md(../rewards/section_reward_system.md)。

来源：[`runtime_coverage_matrix.md`(runtime_coverage.md) 与 [`runtime_coverage.json`(../../../analysis/coverage/runtime_coverage.json)。2026-09-24 只读审计，不包含本轮功能实现。优先级按核心可玩性、依赖与覆盖面排序，不按未处理请求数量排序。每项完成前先核对客户端入口→C2L/L2C→状态→SQLite→重登→push；无法判定的变体保留 `UNKNOWN/NEED_RUNTIME_PROBE`。

## P0 — 主链路与会卡住正常游玩的覆盖

| 顺序 | 开发项 | 依赖/完成证据 | 当前状态 |
|---:|---|---|---|
| 1 | **Battle Entry 扩展已分类类型**：已建立 3,203 Section 的 Type 分流、统一 run 元数据；继续补 Challenge、Endless、活动和 profile/retry/next | 主线与资源本使用统一上下文；每个新增类型须有静态链、准入、run、场景、错误与实机证据 | 整域 PARTIAL；主线/资源本入口 PARTIAL，其他类型已分类未实现 |
| 2 | **DailyDungeon 剩余变体**：25 个本地配置、141 个关联 E_Daily Section 中，当前 4 个 Dungeon/20 个 Section 可交付固定奖与用户授权的逐关临时普通掉落 ×1；其余 121 个关联 Section 因多候选、实例生成或特殊奖励目标未解而阻断；另有 6 个孤立 Section 和 5 个非 Daily 类型 Dungeon | `Gift.E_Random` 已按静态权重执行；2030100 与 2030200 分别产自己的资源。补多候选掉落/实例生成、开放日/次数；见 `daily_dungeon_reward_audit.md` | PARTIAL |
| 3 | **结算按关卡类型分派**：主线/资源/挑战的首通、普通、失败、重复收据与奖品事务 | 依赖入场类型与有效 run；对 `pending_rewards` 实例奖建立可交付方案；保留收据幂等 | PARTIAL |
| 4 | **Mission/Chapter 真实进度**：已通、当前、可开、章节/星/宝箱/剧情与下一节 | 明确 `QueryMission.OtherChapter/story`、解锁条件和独立持久化；主线已通不等于全部解锁 | PARTIAL |
| 5 | **战斗断线/放弃/重试状态**：CheckFightProfile、DelFightProfile、同玩家重连后续战或退款 | 现 `CheckFightProfile` 永远 false；需避免 run 费用/奖励重复 | STUB/PARTIAL |
| 6 | **Guide/Tito 与导航一致性**：NoviceFinish、GuideStep/GuideStep163、功能开放和 UI stack | 不直接抹掉跳教程兼容；从当前预置章/节追最小 flag 集和重登状态 | STUB/MISSING |
| 7 | **登录完整状态恢复**：业务状态回送与重启后的可靠重新登录路径 | 已有英雄/背包/装备/日周/池；补主线、引导、战斗 profile、后续新域，并验证刷新 | PARTIAL |

Battle Entry 的 SectionType 框架与资源本固定奖励/通关进度已接通，但整域仍 `PARTIAL`。下一步优先补 DailyDungeon 多候选掉落、实例型奖励目标与开放/次数，再扩展 Challenge 等已分类入口；详见 [`phase_battle_entry_domain.md`(../../history/2026-09-24_03_phase_battle_entry_domain.md)。单次入场或空奖结算不构成完成。

## P1 — 成长与资源循环

| 顺序 | 开发项 | 当前证据 / 阻塞 | 验收边界 |
|---:|---|---|---|
| 1 | 库存统一交付：堆叠、碎片、装备实例、特殊币种、`pending_rewards` | 固定 Gift 静态引用可读；实例/特殊币种 destination 仍在待发账本 | 奖励入账、ItemUpdate/PlayerData、重登与重复请求均一致 |
| 2 | Skill 全角色与神权分支 | `hero.id == 1003` 硬限制；SkillLevel 有 2,155 行，`StarSkillUp` 无 handler | 至少覆盖 39 个开放原型及不同前置/门槛 |
| 3 | Hero 成长与属性叠加 | 合成/等级/升星部分可用；神器/兽主/技能综合属性未闭环 | 角色变体、消耗、失败、push、登录值一致 |
| 4 | Artifact 完整管线 | 已有基础升级/熔合/镶嵌；JewelCompose/GodSlotLock 无 handler | 孔位、宝石、属性、消耗与重登，多角色实机核对 |
| 5 | Equipment 真实实例与品质/套装 | 测试实例与强化已存在；真实掉落、喂养输入、锁、品质路径缺 | 六部位、多实例、更换、强化节点、套装效果 |
| 6 | 日周任务事件全覆盖及活跃箱 | 40 个候选任务；部分 `_event` 来源未连，`PickTreasureBox` 拒绝 | 每个开放任务的事件来源、换期、领取、push、重登；盒子索引需样本 |
| 7 | 玩家等级/功能开放与等级礼包 | RoleExp 静态曲线；终端溢出、礼包时点、FunctionOpen 条件不全 | 经验、体力上限、Gift、开放状态一致 |
| 8 | 扫荡 `SecSweep` | protobuf/客户端页面明确存在，服务无 handler；41 个 Section 有 MopReward | 前置通关、次数/体力、奖励、幂等、日限制 |

## P2 — 内容系统与次级玩法

| 开发项 | 当前状态 | 下一步证据 |
|---|---|---|
| Shop 商品、购买、刷新 | STUB，`BLOCKED_BY_MISSING_DATA` | 25 店/1,567 分组的 GoodsID→物品/数量多数未知；优先历史非空 `L2C_ShopGoods`，不可自拟为官方 |
| Achievement 列表、进度、领取 | MISSING | 318 静态行可做目录；需事件来源与领奖协议 |
| Draw/Gacha 全 48 池与展示 | PARTIAL | 当前 43 个轮换池、1 个新手池；核对余下静态池、保底 UI 和缺失图片；本审计不实现 |
| Mail 列表、已读、附件、删除 | MISSING | 先定义本地邮件来源与生命周期，不凭空生成官方邮件 |
| Activity catalog/任务/商店/战斗 | STUB/MISSING | 逐活动区分可恢复与已停服；首选有静态内容且不依赖外网的活动 |
| Challenge/Endless/WorldBoss/Tower 等玩法 | MISSING | 在 Battle Entry 分流之后逐型评估；不要假设共用主线结算 |
| 剧情/收集/章节宝箱 | MISSING/PARTIAL | `QueryMission` 的未填字段与 `GetCollectionAward` 等请求 |

## P3 — 社交及低恢复价值范围

| 开发项 | 状态与决策边界 |
|---|---|
| Friend 好友关系、互赠体力/币、任务 | MISSING；当前尚无正式“不恢复”决定，不能冒称 `INTENTIONALLY_UNSUPPORTED` |
| Club/Guild 创建/加入/捐赠/挑战 | MISSING；同上，若决定不恢复，逐功能写原因及兼容空态 |
| 完整 Chat/Comet/Snowflake 内容 | `INTENTIONALLY_UNSUPPORTED`：当前 Revival 明确选择 Null Chat，仅保持节点发现/连接/空响应兼容；若目标变化需重新立项 |
| 停服赛季、联动、充值活动 | UNKNOWN/MISSING；逐活动核对静态内容、有效期和依赖；不一概归为不支持 |

## 按域清零的工作顺序

1. 为目标域列全客户端入口与主要变体，并核对枚举/生成类/Module；把请求 ID 放进矩阵。
2. 补静态数据缺口或明确 `BLOCKED_BY_MISSING_DATA`；与运行逻辑状态分开。
3. 为每个支持变体记录请求、响应、状态事务、SQLite、重登字段、即时 push；未支持变体保留显式状态。
4. 做主要成功/失败/重试/断线/重复请求的隔离存档验证。只有必要的客户端实机探测由用户完成战斗。
5. 按 [`runtime_coverage_matrix.md`(runtime_coverage_matrix.md#新-definition-of-done) 的 DoD 复核整域，再将 `PARTIAL` 改成 `COMPLETE`。单条 happy path 不升级整域状态。

## 最小运行时探测队列

| 探测 | 动作 | 收集 | 不需要做的事 |
|---|---|---|---|
| Resource Dungeon 首次入场 | 打开资源本→选第一关→点击准备 | 首个 C2L ID、request body、Section/scene、回应 | 无需打完 |
| Challenge 首次入场 | 打开任意当前可达挑战→准备 | 前置请求、FightData 的 type/scene/hero | 无需扫全部挑战 |
| Sweep | 已通关且可扫荡的一节点击扫荡 | `1027` 字段、回包、界面变化 | 不反推不存在的奖励概率 |
| Guide/Navigation | 重登后走一个以前跳过的入口 | `374/871/217` 是否发送、UI stack 状态 | 不清当前存档 |
| Battle retry/next | 用户手动完成/失败一个低风险关卡 | 请求序列、run UUID、体力/收据 | 助手不替用户操作战斗 |

## 文档维护

README 与仓库外 `D:\demo\x2\SESSION_HANDOFF.md` 的历史 milestone 继续保留。下一次维护时在“当前状态”增加本矩阵链接并写明各域 `PARTIAL/STUB`；不要把早期里程碑的当时事实抹掉。最新业务状态以矩阵和实际运行证据为准。
