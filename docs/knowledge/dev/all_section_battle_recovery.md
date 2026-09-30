---
Document-Type: Current Knowledge
Domain: Dev
Status: AUTHORITATIVE
Updated: 2026-09-30
Supersedes:
  - (none; still authoritative)
---

# 全类型关卡入场与证据限定结算（2026-09-24）

本轮只改开发服，不改分发目录。源数据是已提取的客户端 `SectionTable`（3,203 行、24 种 SectionType）、`Gift` 与 `Item`，未重新逆向 APK。新增的 `battle_rewards_catalog.json` 只导出 Section 引用的 722 个奖励组及相关 Item。`tools/export_battle_rewards.py` 可重复导出。

## 入场

- 测试账号可通过 snapshot.test_challenge_unlocks 保存已授权开放的挑战 SectionID。QueryMission 仅将 Type=2 的有效记录纳入对应章节的界面开放进度，不写 economy_clears、不触发结算；2026-09-30 用户授权测试账号 1 的第一章全部月相开放。
- 2026-09-30 月相难度继续修复：实机持久化回包确认第一章 `2110851/2110852/2110853` 已收到 expertMode=true、各自地图 ID，但 `L2C_FightData.monsterInitLevel` 仍缺失。ARM64 序列化 `0x34FAED8` 写 tag 0x80 0x01（field 16），`0x34FAF38` 读取应答偏移 0x80；`ChapterModule.Convert_L2CFightData_To_LogicFightData(0x16C1034)` 将该值复制到逻辑数据偏移 0x88；`LogicBattle.OnBattleStart(0x18F70EC)` 将它作为 `BaseLevel.InitMapInfo` 的第二个参数；`InitMapInfo(0x199F25C)` 直接将参数保存为基础等级，并未读取 `MapInfo.MonsterLevel`；后续 `BaseLevel.BuildScene(0x199F448..0x199F4C8)` 将基础等级与地图的 MonsterLevelUp 对应层增量相加。旧回包因此使基础等级恒为 0。现通过 `tools/dev/export_battle_monster_levels.py` 导出原始 MapInfo 3,099 条数据，并按实际入场地图下发 field 16。第一章十档为 15/23/31/40/53/64/78/89/103/290，剧情首关为 2；这些数值来自原表，并非 RecommendedLevel 或自定倍率。测试验证十档编码回包、地图、专家标志及切回剧情；实机战斗效果待用户复测。
- 2026-09-30 难度传递修复：旧服务虽然接受请求的 `expertMode`，却在 `FightData` 与 `FightDataProfile` 回包中遗漏它，客户端收到默认 false。原客户端 ARM64 `FightData.Serialize(0x350E1C0)` 将偏移 0x29 的 bool 写为 field 6（tag 0x30）；`FightDataProfile.Serialize(0x351177C)` 将偏移 0x3C 的 bool 写为 field 8（tag 0x40）。`ChapterModule.ConvertFightData(0x16C24D4)` 把前者复制到逻辑战斗数据偏移 0x31，`LogicBattle.CheckExpert(0x18FE3F0)` 读取它。现在两个回包均保留请求标志。月相仍使用各自 SectionID/Maps，未新增怪物属性倍率；隔离测试覆盖白夜崩解 10 档月相和切回普通剧情，实机战斗难度待用户复测。
- `C2L_FightData(126)` 对所有 24 种已知 SectionType 使用同一经过实测的战斗入场合同。按 SectionID、ChapterID、Map、已拥有且有战斗属性的队伍、已知等级/前置关卡校验；地图和 Chapter 不匹配仍拒绝。
- 实机挑战关 `2110851` 的正常入口发送 `expertMode=true`。旧代码错误地把此标志判作未支持模式并返回 13；现在全类型共用入场、掉落和结算路径均接受它，仍校验 Section/Chapter/Map。`checkGm` 与旧战斗档恢复另列为未实现。
- `ManualValue` 存在时入场扣对应体力，失败或下一次入场替换未结 run 时按现有事务退款；没有 `ManualValue` 的类型不猜体力费用，入场费记 0（`NO_KNOWN_COST`）。`OpenType=3/4` 等尚未恢复的特殊门槛只标识未知，不以未知规则封锁入口。资源本的开放日与次数继续沿用既有已声明的 Revival 兼容策略。
- 奖励数据缺口不再提前拒绝战斗。`FightDropData(264)` 对对应活动 run 和任意 SectionType 返回带 UUID 的空掉落列表；空列表不代表官方掉落已恢复。

## 结算

- `CheckoutMainMissionSign(887) → L2C_CheckoutMainMission(152)` 对全部类型验证当前 run、Section、Chapter 与收据；重复结算读取同一持久化收据，不重复发奖。失败结算返还已扣体力。
- 成功结算逐组解析本节 `VReward`，首通再解析 `FirVReward`。仅通过原始 `Gift` 的物品、数量、概率与已支持入账目标校验的奖励才发放；未支持的实例/货币目标进入已有 `pending_rewards`，无法解析的奖励组记录在新增 `battle_unresolved_rewards`。不使用扫荡奖代替普通奖，不推断活动或挑战掉落。
- 可直接入背包的物品类型限定为已明确作为可堆叠物品处理的消费品、碎片、普通材料、礼盒、炼金材料、剧情/活动材料与宝石碎片；兽主、宝石实例、勋章、收藏等需要独立状态的目标暂记待发，不能假装成普通背包数量。
- 现有四组资源本的用户已授权普通掉落兼容政策继续有效；其余无法解析的普通掉落只记缺口，不能阻止结算，也不会凭预览图发奖。新类型的 `DropValueID` 记未恢复。成功通关写入 `economy_clears`，`QueryMission.OtherChapter` 按 SectionType/Chapter 返回已通关进度；主线 frontier 规则不变。

## 验证与限制

- 隔离内存存档对 **3,203/3,203** 个 Section 分别以普通模式和 `expertMode=true` 执行 `FightData → FightDropData → CheckoutMainMissionSign`，24 种类型两轮均全部结算、0 失败。测试先满足已知等级与前置关卡条件；因此这个结果证明合同与持久化路径覆盖，不证明官方活动日历、挑战规则或所有客户端画面已实机验收。
- 722 个被引用的奖励组中，497 组可产生当前支持的入账物品，210 组仅含待处理目标或空交付，15 组无法安全解析；679 个 Section 没有 `VReward/FirVReward`。这些关卡可以结算，但不能声称奖励完整。实机尚需由用户分别打开挑战与活动的可达关卡，确认是否还有该模式特有的额外 C2L 请求或 UI 分支；战斗本身须由用户操作。
- 单元测试 180 项通过。实机 `2110851` 曾在改动前因 `expertMode=true` 四次入场失败；后来一次不带该标志的入场成功，用户退出后客户端上报 `success=false`，服务器正常返回成功的失败结算并退体力，因此这不是胜利奖励验收。修复后仍需实机挑战/活动入场与胜利结算验收。此阶段状态为 `PARTIAL`，不是全战斗系统 COMPLETE。
