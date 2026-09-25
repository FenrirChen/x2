---
Document-Type: Current Knowledge
Domain: Rewards
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - (none; still authoritative)
---

# FightItemBag 持久化边界（局内 vs 带出）

2026-09-25。证据级：A=原生指令/直接调用证实；B=强重建；C=推断；D=被代码否定。
机器可读：`analysis/reward_reverse/fightitembag_methods.json`、`item_use_scene_consumers.json`。

## 1. FightItemBag 完整结构（A）

| 字段 | 类型 | 归属 |
|---|---|---|
| mItemList (0x10) | FightItemData[]{id,num,quality,source,isFirstGet} | 战斗物品槽（唯一进入 checkout 的主体） |
| mMoney (0x18) | Dictionary<int,SmartInt> | **场内货币桶**（901/903/907…），不是账号资产 |
| mTrueMoney (0x20) | Dictionary<int,SmartInt> | "真实货币"镜像（GetTrueCurrency 默认 901） |
| RelicItem/TowerItem/TowerLib | List<int> | Roguelite 神迹/塔玩法状态，**纯局内** |
| ConsumeSilver/PickupSilver | int | 903 银币消耗/拾取计数 |
| GainRate/CostRate | float | 掉落增益/消耗倍率 buff |
| profileDropItems (0x60) | List<ProfileDropItem> | 264 C2L_FightDropData 遥测快照 |
| mItemDayNumCache | Dictionary<int,int>（DropItemManager 上） | Item.DropLimit 每日掉落计数 |

`AddItem(id, quality, num, silverCount, show, recover, source=1)`：source 默认 **ItemSource.FIGHT(1)**
（枚举 1=FIGHT/2=SHOP/3=COMPOSE）；901/903/907 形态的 id 被分流进货币桶（立即数 0x385/0x387/0x38B），
其余进 mItemList。`AddGold(num, itemID=903)` 只写 mMoney，无账号转换（A，10 个调用点全为塔/技能/触发器）。

## 2. outsideItems 真实筛选规则（A：SetCheckout_BattleItem 0x1442894 全量反汇编）

```csharp
static void SetCheckout_BattleItem(bool battleWin, SectionTableEType mode,
                                   List<ItemDataP> outMaze, List<ItemDataP> outOutside) {
    outMaze.Clear(); outOutside.Clear();
    if (!battleWin && (mode > 20 || ((1 << mode) & 0x80840000) == 0)) return;   // 失败放行位掩码
    var items = LogicBattle.Current.FightItemBag.ItemList;
    foreach (var it in items) {
        if (it == null) continue;
        var p = new ItemDataP { id = it.ID, num = it.Num, quality = it.Quality };   // quality=包内品质透传
        var info = ItemManager.GetItem(it.ID);
        if (info == null) continue;
        if (it.source != ItemSource.FIGHT) continue;            // 只有战斗来源可上报
        switch ((int)info.ItemUseScence) {
            case 1:  // E_Outside → 账号带出；eNum 保持 0
                outOutside.Add(p); break;
            case 0:  // E_Maze → 迷宫遥测列表
                int tracked = LogicBattle.Current.StatsManager.getItemData.TryGetValue(it.ID);
                if (p.num > tracked) { LogError(...); p.eNum = tracked; }   // eNum=场内获取计数, 超量钳制
                else p.eNum = tracked;
                outMaze.Add(p); break;
            default: /* E_Alchemy(2)/未设置 */ break;            // 丢弃
        }
    }
}
```

- **eNum 语义（A）**：只对迷宫物品填写，值 = `StatsManager.getItemData`（0xA8 字典）中该物品的
  场内获取计数；背包数 > 计数时钳制并打 LogError。**不是序列号、不是随机种子、不是词条数**。
- **887 同时携带 outsideItems（0x18）与 mazeItems（0x50）**；mazeItems 是 Roguelite 局内
  遥测/校验载体，不是账号交付清单。
- **失败战斗放行位掩码 0x80840000**：只有 E_ShuangHanBattle(11) 与 E_ActivityBattle(15) 两类
  失败战斗仍上报物品列表（部分进度奖励语义）。
- `GetPersistentItemsList`（0x1E51A54）：同 E_Outside 过滤但**无 source 检查、无 eNum、只出
  outside 列表**；尾部 `get_Gold` 为死调用（返回值被 `mov x0,x20` 丢弃）。无直接 BL 调用者，
  实际结算走 SetCheckout_BattleItem。

## 3. 两类边界清单

**PERSISTENT_OUTSIDE_ITEM（可带出，全部条件）**：
`source==FIGHT` ∧ `ItemUseScence==E_Outside` ∧ Item 表存在。例：1237901（金币）、
1240xxx（兽主 E_Equip）、1209162–65（随机兽主）、各材料/碎片。

**CLIENT_LOCAL_ONLY（不带出）**：
- 场内货币 901/903/907 —— 在 mMoney 桶，不在 mItemList；结算映射靠 CurrencyType 表（服务器侧）。
- RelicItem/TowerItem/TowerLib —— 独立列表，无 checkout 出口。
- E_Maze 物品（1101021、1237903 等）—— 进 mazeItems 遥测，不进 outsideItems。
- E_Alchemy(2)/未设置 ItemUseScence 的物品 —— 直接丢弃。
- source==SHOP/COMPOSE 的战斗包物品（局内购买/合成）—— 被 source 过滤拒绝。

## 4. 对 Revival Server 的含义

官方服务器在 887 里同时收到两份列表：outsideItems=待入账交付，mazeItems=局内一致性
校验数据（可作反作弊输入，不发放）。当前 Revival 只解析 outsideItems 的做法方向正确；
未来若要增强真实性校验，可用 mazeItems + eNum 与自身战斗遥测对账。
