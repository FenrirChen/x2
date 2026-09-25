---
Document-Type: Current Knowledge
Domain: Coverage
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - (none; still authoritative)
---

# False-Complete Elimination — 第一批

日期：2026-09-25。仅修改开发工作区；未修改分发目录、Reference Client、APK 或活跃 SQLite。测试基线 `204 passed`，本批 `210 passed`。本批消除的是已确认的单样本门控和默认值，**没有**把 DailyDungeon、Hero、Skill、Battle 等整域提升为 COMPLETE。

## 清理清单

| ID | Domain | File | Old behavior | Problem | Evidence | Fix | Static source | Protocol source | Persistence | Refresh | Tests | Before status | After status | Remaining blocker |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| FC-001 | DailyDungeon | `src/x2server/player/daily_rewards.py` | `dungeon_id == 2030100` 才读取扫荡数量 | 按开发样本 ID 分派金币规则 | `DailyDungeon.SectionID`、每节 `MopReward`/`VReward`/`DroopDisplay`；用户明确指定金币按本关扫荡数量 | 对单一金币预览按该 Section 的 sweep-only Gift 数量计算；其他单预览资源按已授权临时数量 1；多候选明确阻断 | DailyDungeon、SectionTable、Gift、Item | `C2L_FightData`→`C2L_CheckoutMainMissionSign` | 既有结算事务与收据；余额、库存入 SQLite | 既有 PlayerData/ItemUpdate | 25 个 Dungeon 目录核对；2130101/2130102/2130201 跨样本 | PARTIAL | PARTIAL | 普通掉落数量/概率未恢复；25 个 Dungeon 中只有 4 个、20 个关联节可执行现行兼容规则 |
| FC-002 | Hero/Skill | `src/x2server/player/progression.py` | 缺技能状态时只给 Hero1003 默认技能；升级先按 Hero ID 硬拒绝 | 其他合法角色技能列表为空；规则由角色 ID 而非静态原型决定 | 39 个 `hero_unlock.initial_skills`；`skill_progression` 仅覆盖 1003 的 53 行 | 所有原型从自己的 `initial_skills` 生成读模型；技能请求校验属于本 Hero；费用行缺失则明确失败且零扣费 | Hero/SkillLevel 导出目录 | HeroAll、HeroUpdate、`C2L_UpHeroSkill` | 成功仍走现有事务/收据；缺数据零变更 | HeroUpdate 和重登 HeroAll 使用同一读模型 | 1003/1004/未知 Hero；1004 缺费用零变更 | PARTIAL | PARTIAL | 1004 等角色技能升级的费用/解锁行未在当前运行目录；不能复制 1003 |
| FC-003 | Mission | `src/x2server/player/economy.py` | `main_section` 缺失时默认 2110001 | 结算可能从开发样本判断前沿 | 实际结算包含 Section，`SectionTable.ChapterID` 可查 | 不使用默认节；由本次已验证结算 Section 推进 | SectionTable | CheckoutMainMissionSign、QueryMission | 既有 `economy_clears` 与玩家快照事务 | 既有 PlayerData/QueryMission | 缺前沿的 2110801 清算 | PARTIAL | PARTIAL | 章节星级/宝箱/剧情等仍缺 |
| FC-004 | Login/Hero display | `src/x2server/player/login.py`, `store.py` | Show 缺失或新账号时固定 1003 | 其他角色账号可展示未拥有角色 | 快照 `heroes` 与 `show`；PlayerData BaseInfo.Show | 选已拥有且 state=2 的展示角色；没有则 0；新账号种子不再强行 1003 | Hero 原型/玩家快照 | PlayerDataProto | 新账号持久种子改为 0；既有存档不批量迁移 | 每次登录/状态 push 重算有效展示 | 仅拥有 1004、存档无 Show/陈旧 Show | PARTIAL | PARTIAL | 展示角色主动选择协议尚未恢复 |
| FC-005 | Runtime drop | `src/x2server/player/daily_rewards.py`, `economy.py` | 单预览掉落可按数量 1 执行 | 数量 1 是用户授权的临时体验规则，不是官方概率 | `DropValueID` 无可恢复数量/概率；已做定点考古 | 保留为显式 `compat_normal_drop`，与 fixed Gift 独立；多候选阻断并记 `battle_unresolved_rewards` | SectionTable DroopDisplay / Gift | FightDropData/结算 | 收据幂等、待解账本持久化 | ItemUpdate / PlayerData | 已有 Daily 重复结算测试 | TEMP_COMPAT | INTENTIONAL_COMPAT | 官方 runtime drop 概率/数量与 264/266 语义仍未知；不继续猜测 |
| FC-006 | Login collection | `src/x2server/player/login.py` | 部分登录字段为空 | 可能形成空成功假象 | 当前 `noticeAll` 等仍无完整业务态 | 本批未改；保留在审计中 | 按各模块静态表另审 | L2C_Login | 不适用或缺失 | 登录空态 | 既有登录测试 | STUB/PARTIAL | STILL_PRESENT | 必须逐字段证明合法空态，不能全局删除 |
| FC-007 | Economy ledger | `src/x2server/player/economy.py` | `pending_rewards` 等未登录回送 | 待发资产容易被误认为已发放 | `state_lifecycle.json` 记录账本；`pending_rewards` 为未解决目标 | 本批不机械恢复账本为物品；保留待发记录 | Gift/Item | 结算奖励 | SQLite `pending_rewards` | 无可展示 ItemUpdate 目标 | 既有待发/重登测试 | PARTIAL | BLOCKED | 装备实例与特殊货币目标/交付仍需证据 |
| FC-008 | Shop | `src/x2server/player/shop.py` | 可见商店部分商品内容缺失 | 假目录会伪装官方商品 | 原表只确认 GoodsID/价格，缺货品映射 | 本批未造商品；保持明确拒绝 | ShopConfig/ShopGoodsGroup | ShopGoods/BuyGoods | 不扣费 | 无 | 既有 Shop 拒绝测试 | STUB | BLOCKED | 官方 GoodsID→物品及数量缺失 |

## 复扫与覆盖变化

| 分类 | Before | After | 差值 | 解释 |
|---|---:|---:|---:|---|
| SINGLE_SAMPLE_IMPLEMENTATION | 14 | 8 | -6 | 移除 DailyDungeon ID、Hero1003 技能门控/默认、Section2110001 默认、Show1003 默认；其余多为样本工具/报告或待审路径 |
| TEMP_COMPAT | 38 | 38 | 0 | 兼容仍明确保留，未靠删除标记降低计数 |
| DATA_DRIVEN_DEFAULT | 14 | 13 | -1 | 新账号 `show=1003` 种子移除 |
| FALSE_COMPLETE_RISK | 0 | 0 | 0 | 扫描器正则只找少数固定返回，0 不表示不存在假成功 |
| REAL_BUG_RISK | 0 | 0 | 0 | 当前扫描器无独立该分类；需继续静态/实机审查 |
| 合计 | 66 | 59 | -7 | 由 `tools/analysis/audit_hardcodes.py` 重建 |

机器可读复扫：`analysis/coverage/hardcoded_business_rules.json`。Coverage 静态重审生成器已重跑：69 个 feature 注记刷新；**业务状态升级 0、降级 0**。原因是该生成器只更新静态证据字段，本批四项仍未满足整项 DoD。`docs/runtime_coverage_matrix.md` 追加当前状态说明，不改写 2026-09-24 历史表格。

## 仍需优先清理

1. `SkillLevel` 当前运行目录只覆盖 1003，需从已有静态表核对其他角色是否真的没有等级行。未补齐前其他角色可显示各自技能，但升级只能明确失败。
2. DailyDungeon 25 个目录中 5 个关联非 E_Daily 类型，141 个关联 E_Daily 节仅 20 个可执行当前兼容普通掉落；其余固定奖励与 runtime drop 应继续分开判定。
3. 战斗 `battle_base_1003.attributes` 是 19 项属性字段布局，值由所选 Hero 的 `battle_hero_base` 提供；命名仍像单 Hero，后续可改名，但本批不做无行为收益的目录重写。
4. `pending_rewards` 对实例型物品/特殊币种仍是待发账本；不要把已入账当成已交付。
5. 登录、活动等空集合与大厅 `ButtonClick` 的 `code=10` 需要逐客户端消费链审查；不可因扫描器没有命中就算修复。

本批未修复额外持久化或推送缺口；四项改动使用既有事务、重登快照和推送路径，并由回归测试复核。下一批应优先清理**奖励目标交付与结算假完成**：它直接影响普通战斗的资产一致性，且是成长、装备、任务的共同依赖。
