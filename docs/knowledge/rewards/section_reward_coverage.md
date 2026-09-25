---
Document-Type: Current Knowledge
Domain: Rewards
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - (none; still authoritative)
---

# Section 奖励覆盖

生成依据：`analysis/reward/section_reward_catalog.json`，2026-09-25。配置分类覆盖 **3203/3203** 个 Section、**24/24** 个 SectionType（含 Type 未设置的 `E_UNSET`）。分类是识别奖励来源；可入场、特殊奖触发与实例交付分别计。

| 指标 | 数量 | 口径 |
|---|---:|---|
| 全部 Section / 已分类 | 3203 / 3203 | 官方 SectionTable 原始行，ID 唯一 |
| SectionType / 已分类 | 24 / 24 | 包含 Type 未设置的 E_UNSET |
| 配有首通 Gift | 619 | `FirVReward` 非空；实际发放须成功首通且 Gift 可执行 |
| 配有普通 Gift | 2439 | `VReward` 非空 |
| 配有扫荡 Gift | 41 | `MopReward` 非空，全部为 E_Daily；扫荡需已通关与体力 |
| 可接收手打 outsideItems 的 Section profile | 3203 | 真实客户端请求须有有效 BattleRun；当前不是全部可入场 |
| 有 DropValueID | 3043 | 服务端数值映射仍未知 |
| 有 ExtraDroop 静态关联 | 146 | 触发业务未恢复，不自动发放 |
| 有宝箱/挑战独立奖字段 | 127 | `ChestReward`/`ExpertChestReward`/`ChallengeReward1`；未验证触发条件 |
| 官方 Gift 组缺行 | 0 | 引用可定位；可定位不等于都可执行 |
| 引用随机 Gift 的 Section | 94 | 其中 34 个至少含一组当前不可执行的非 100 权重配置 |
| 已证实完整 Section→DropProp 刷怪闭包 | 0 | 逐关地图、房间和事件生成尚未闭合；`contains_adc` 为 UNKNOWN |
| 金币手打兼容 | 5 | 2130101–2130105；每关读取自己的 MopReward 金币量 |

24 类均有统一 `FIRST_CLEAR_FIXED`、`NORMAL_CLEAR_FIXED`、`RUNTIME_BATTLE_DROP` 来源槽位。只有 41 个有 `MopReward` 的关卡具备扫荡静态奖；其余没有数据时明确拒绝扫荡。额外奖励表如 `RaceReward`、`WeeklyDungeon`、`ActivityDungeon`、`WorldBoss*`、`Tower*`、`Endless*`、`Challenge*`、`Battlepass*` 已在静态字典中识别，尚未证实各表的触发/到账链，均列为 `SPECIAL_REWARD_SOURCE / RUNTIME_SERVER_DATA_UNKNOWN`，不得并入 `VReward`。入口现状仍见 `battle_variant_coverage.md`；目录分类不提升 Battle Entry 覆盖级别。

**仍阻塞：** 34 个含当前不可执行 Gift 权重配置的 Section 可能产生部分未解奖励；所有涉及装备实例的真实掉落进入待发，尚未交付；3043 个 DropValueID 的服务器数据及 ExtraDroop/特殊玩法触发仍未知。`DYNAMIC_ALLOWED` 为真实性保护策略，并非全部运行时掉落规则已恢复。
