# 2026-10-01 镶嵌宝石合成、周常无尽与时序之门入口

## 宝石

实机反复重发 215（request 38326），因协议未注册而无回包。按客户端 C2L_GodEqupJewelCompose 的 HeroID/HoleIsID/RecipeID 实现 215/216。产物 ID 用于 ArtifactModule.OnL2CEqpJewelCompose 查询 JewelBase；不能返回英雄 ID。

使用既有 Recipe 配方，将已佩戴宝石作为一颗原料，扣除余下背包原料与金币后将产物留在同一槽。角色、材料变更在响应前同步。事务内持久化回执，重连重试同一请求不会再次扣费。不影响 144/147 背包合成。

## 周常无尽（之前误识别为主界面时序之门）

用户实机确认主界面时序之门提示每日 17–23 点开放。核对客户端后确认该入口属于 WorldBossModule；下述 Type 7 / EndlessWeekly 修复属于另一玩法，不能作为主界面时序之门已修复的证据。

- 447/448 存档查询之前仅返回空状态，缺 weeklyId，使 ChapterModule.OnConfirmSave 无法取得 WeeklyDungeon。恢复最后客户端章节 2060101 的元数据，支持八个 Type 7 难度关卡的既有战斗准入和结算。
- REVIVAL_COMPATIBILITY：原客户端活动日历已失效，目前固定开放 2060101，currentWeek 使用该行 OpenCycle 的起始周 272；保留等级 22/33/39/44 门槛。不会修改全局服务器时钟。原轮换日历、周重置尚未恢复，任务当前为持久化一次性奖励。
- 264 保存层数、地图、随机种子、队伍、拾取、货币、神迹、NPC 和杀敌数据；从 isFromProfile 恢复同一 UUID，不再扣体力。存档仅对未结算 run 可恢复，删除存档不会发奖。所有结算仍走原 RewardGrant/outsideItems/887 和 battle receipt。
- 补齐 FightDataProfile 序列化字段，纠正 264.killMonster 为单个消息（客户端是 FightKillMonster，非列表）。观察计数按 run+条件+对象取高水位，重发或较早报告不重复累计或回退。
- 导出 17 个 EndlessDungeonTask 及分阶段条件/GiftGroup/VomLimit；恢复类型 12 查询和领取事务。当前已接入杀敌、层数、拾取货币的进度。E_ThreeHero、E_Element、E_ElementExp 的额外条件仍缺可验证事件/文案，未擅自完成这些任务；需要后续实机包取证。这些任务不是已完成的功能。

临时数据库验证：镶嵌材料/金币、原槽替换、失败回滚与重试；时序入口、存档、恢复不重复扣体力、结算重试、任务高水位和领取回执。18 个背包相关测试通过，24 个相关战斗和主线回归通过（含 3 个重叠的新测试）。实机效果仍需审查。

## 主界面时序之门全天开放

日志 restart_20261001_190032.err.log 中 679/C2L_QueryWorldBossOpenTime 返回 code=208，导致客户端显示时间限制。WorldBossModule.OnHandleQueryOpenState（RVA 0x137257c）只在 code=10 时设 OpenState=Open 并调用入口成功回调；其他返回码显示原客户端提示。CheckActivityOpen（RVA 0x1372084）检查等级和这个服务端状态，没有独立的小时检查。

按用户决策，679/680 现在全天返回 code=10，保留客户端原有等级门槛，记录 policy=always-open 日志。不修改全局时间和 active DB。WorldBoss 的探索、Boss 列表、匹配及多人战斗仍需继续恢复，入口开放不等同于这些玩法均已实现。
