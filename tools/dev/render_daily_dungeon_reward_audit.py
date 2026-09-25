"""Render the machine-audited per-Dungeon rewards as a compact Markdown table."""
import json
from pathlib import Path

root = Path(__file__).resolve().parents[2]
audit = json.loads((root / "analysis/battle/daily_dungeon_reward_audit.json").read_text(encoding="utf-8"))
lines = [
    "# DailyDungeon 奖励审计", "",
    "2026-09-24。统一机制按 DungeonID/SectionID 读取各自奖励。机器明细见 `analysis/battle/daily_dungeon_reward_audit.json`。", "",
    "`DailySectionCell.Refresh` (RVA `0x168AF9C`) 读取 `SectionTable.DroopDisplay` 和 `DroopDisplayProbability`，并调用 `CommonItem.SetItem` (RVA `0x168B95C`, `0x168BC74`) 显示物品。此证据只确认预览 ItemID，不确认实际掉落数量或概率。", "",
    "| DungeonID | 名称 | Sections | Type | 展示资源 ItemID | 首通固定 Gift | 普通固定 Gift | NORMAL_DROP | 扫荡 Gift | 状态 |",
    "|---:|---|---:|---|---|---|---|---|---|---|",
]
for d in audit["dungeons"]:
    sections = [s for s in d["sections"] if s.get("section_type") == 3]
    first = sections[0] if sections else None
    def gift(key):
        return ",".join(map(str, first[key]["gift_groups"])) or "无" if first else "未提取"
    drop = str(first["normal_drop"]["drop_value_id"]) if first else "未提取"
    types = ",".join(map(str, sorted(set(d["section_types"].values()))))
    lines.append(f"| {d['dungeon_id']} | {(d['name'] or '未提取').replace('|', '/')} | {len(d['section_ids'])} | {types} | {','.join(map(str, d['preview_resource_item_ids'])) or '无'} | {gift('first_clear_fixed')} | {gift('normal_fixed')} | DropValueID {drop}；数量/概率未解 | {gift('sweep_reward')} | {d['status']} |")
lines.extend([
    "", "## 2130101 四种奖励", "",
    "- FIRST_CLEAR_FIXED：`730001` → 光辉 30。",
    "- NORMAL_FIXED：`730071` → 解神者经验 6、神格经验 60；无金币。",
    "- NORMAL_DROP：`DroopDisplay=[1237901]` 预览金币；`DropValueID=10630101`。官方金币数量与概率未解；Revival 临时规则在普通胜利结算追加金币 1。",
    "- SWEEP_REWARD：`730071,795201`，其中 `795201` → 金币 2078。扫荡尚未实现，不得挪到普通结算。",
    "", "## 边界", "",
    "25 个 Dungeon 中，20 个有关联 E_Daily 的资源预览（1 个单一资源，19 个多资源），5 个只关联其他 SectionType。SectionTable 邻近的 `DroopDisplayProbability` 在资源本中仍是 ItemID 列表；`DroopLimit`/`DroopLimit2` 是限制字段，`DifficultyLevel` 是难度枚举，均没有 2130101 的金币数量。", "",
    "定点消费链：`FightModule.OnFightDropData` (RVA `0x1447E1C`) 解码服务端 `FightDropData.dropValues` 并输入 `UpdateDropValue`；`DropItemManager.GetDropItemByGroup` (RVA `0x1E4845C`) 使用本地 `DropProp` 与客户端随机函数。`DropItemManager.AddDropItem` (RVA `0x1E4C8C0`) 调用 `DropPropManager.GetItem` 时传入方法参数 `dropGroup`，不是 Section 的 `DropValueID`。因此不能说所有怪物掉落概率完全由服务端下发。但 332 行 `DropProp.ItemList` 与本报告 20 个 E_Daily 资源预览 ItemID 零交集，`DropValueID→DropProp.DropClass` 亦无直连；当前客户端资料不能恢复这些资源本的 NORMAL_DROP 数量和概率。", "",
    "用户明确授权临时将普通胜利资源掉落数量设为 **1**，后续再替换为实际数据。实现只在每节 `DroopDisplay` 恰有一个可入账 ItemID 时使用该 ItemID ×1；不从名称、相邻 ID 或扫荡数值推算。4 个 Dungeon/20 个 Section 可完整执行此兼容规则，其余 16 个有预览但多候选/实例生成或固定奖励目标未解，5 个仅有其他 SectionType，保持 PARTIAL/BLOCKED，不伪造空奖成功。", "",
    "固定奖励继续按各节 FirVReward/VReward 解析，`Gift.E_Random` 按客户端静态 `Probability` 抽取并与收据共同持久化；正常掉落单独由 `DailyDungeonRewardCatalog.compat_normal_drop` 决定。结算事务同时交付固定奖与临时掉落，重试读取原收据。扫荡仍未实现。`FightDropData` 的战斗内可视掉落仍缺真实展开规则，当前兼容只保证胜利结算到账，不宣称战斗内掉落动画完整。", "",
    "更新服务后的实机请求实际为金币本第二关 `2130102`（非提问中指定的 2130101）。用户反馈正常；该 run 的 SQLite `economy_grants` 为金币 1、光辉 30、神格经验 120、解神者经验 12，结算与金币持久化得到双重核对。第二个不同 Dungeon 的奖励隔离、入账、推送及重登读取已在隔离测试库验证，尚无其实机战斗验收。", "",
])
target = root / "docs/daily_dungeon_reward_audit.md"
target.write_text("\n".join(lines), encoding="utf-8")
print(target)
