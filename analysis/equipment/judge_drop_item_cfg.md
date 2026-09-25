# JudgeDropItem / SetCurItemValueTotal / IdentifyItem — ARM64 还原（2026-09-25）

证据级：A（`libil2cpp.so` 0x1E49838 / 0x1E4AD70 / 0x1E49578 全量反汇编，字段偏移与 dump.cs 对齐）。
辅助：`LogicX2.DropItemManager$$InitDrop` 0x1E48B0C、`AddItems` 0x1E4AFF8、`DropItem$$Init` 0x1E46470、
`LogicX2.Random$$Range` 0x3EFD408。

## 1. JudgeDropItem（掉落门控 + 价值预算）0x1E49838

```csharp
bool JudgeDropItem(DropItemManager.ItemStruct item, bool isEqt = false) {
    // ItemStruct: id 0x10, num 0x14, quality 0x18, needIdentify 0x1C, itemValue 0x20,
    //             addADCGroup 0x24, enableInDungeon 0x28
    var section = SectionTableManager.Instance
        .GetItem(LogicBattle.Current.BattleInfo.FightData.missionId);   // FightData+0x20
    if (section != null && isEqt) {                       // isEqt = Item.ItemType == E_Equip(10)
        var lim3 = section.DroopLimit3;                   // SectionTable+0xB0
        if (lim3.Count >= 1) {
            if (lim3.Count == 2) {
                if (item.quality > lim3[1]) item.quality = lim3[1];  // 0x1E4997C..0x1E49B0C: clamp DOWN to max
                if (item.quality < lim3[0]) { EmitDebug(...); return false; } // 0x1E49B18..0x1E49B40: below min -> reject
            } else { EmitDebug(...); return false; }      // 0x1E499E0..0x1E49AFC: count!=2 且非空 -> 拒绝
        }
    }
    if (section != null) {
        if (item.enableInDungeon)                         // Item.ItemUseScence == E_Maze(0)
            return section.DroopLimit2.Contains(item.addADCGroup);   // 0x1E49C24..0x1E49C60 tail-call
        if (!section.DroopLimit.Contains(item.id)) { EmitDebug(...); return false; } // 0x1E49C64..0x1E49C90
    }
    var budget = LogicBattle.Current.BattleInfo.dropValues;  // BattleInfo+0xC0
    if (budget.Count <= item.addADCGroup) return false;   // 0x1E49D34
    int delta = item.itemValue;
    if (isEqt) {
        var st = EquibStageManager.Instance.GetItem(item.quality);    // 0x1E49D90: QUALITY 作键
        if (st != null) delta = (int)(st.EquibValue * item.itemValue / 1000.0);  // 常量 1000.0 @0x4189CD0
    }
    delta *= item.num;
    if (this.DropValueList == null) this.DropValueList = InitDropValueList(budget.Count); // 全 0 列表
    if (this.DropValueList[item.addADCGroup] + delta > budget[item.addADCGroup])
        return false;                                     // 0x1E49E4C: 组预算超限 -> 拒绝
    this.DropValueList[item.addADCGroup] += delta;
    return true;
}
```

要点：
- **DroopLimit3.Count 必须 == 2**（否则装备掉落被拒）；`[min, max]` 星级带：超上限**收敛**，低于下限**拒绝**。
- DroopLimit（+0xA0）= E_Outside 物品 id 白名单；DroopLimit2（+0xA8）= E_Maze 物品 AddADCGroup 白名单。
  （"DroopLimit2=星级带"是旧误读，本轮以代码+数据推翻。）
- 价值预算：每次装备掉落扣 `EquibStage[quality].EquibValue × Item.ItemValue / 1000 × num`，
  组 `AddADCGroup` 累计值不得超过 `BattleInfo.dropValues[组]`。BattleInfo 构造器把 dropValues
  初始化为空表（0x19A1C9C），空表时所有装备掉落被拒 → dropValues 必须由战斗入口填充。

## 2. SetCurItemValueTotal（纯价值记账）0x1E4AD70

```csharp
void SetCurItemValueTotal(int itemID, int quality, int num) {
    var item = ItemManager.Instance.GetItem(itemID);
    if (item == null) return;
    var budget = LogicBattle.Current.BattleInfo.dropValues;
    if (budget.Count <= item.AddADCGroup) return;          // Item+0x34
    int value = item.ItemValue;                            // Item+0x30
    if ((int)item.ItemType == 10) {                        // Item+0x24 == E_Equip
        var st = EquibStageManager.Instance.GetItem(quality);   // quality 作键
        if (st != null) value = (int)(st.EquibValue * item.ItemValue / 1000.0);
    }
    value *= num;
    // mDropValueList[Item.AddADCGroup] += value（与 JudgeDropItem 同一累加器）
}
```
分类：**B（掉落价值记账）**，唯一调用方 `LogicBattle$$RecoverBattleData`（战斗恢复时重放累计），
不参与星级选择（它消费 quality，不产生 quality）。

## 3. IdentifyItem（星级掷骰，quality 的产生点）0x1E49578

```csharp
int IdentifyItem(Item item, int level, DropProp info) {
    if (info == null) return (int)item.ItemQuality;        // 无 DropProp -> 静态品质兜底
    int result = 6;                                        // 潜在品质（失败下探）
    for (int i = 0; i >= -2; i--) {                        // 尝试 6(Legendary) 5(Epic) 4(Rare)
        var db = DropBaseManager.Instance.GetItem(i + 6);
        if (db == null) { result--; continue; }
        int cv = (i == 0) ? info.LegendaryCv : (i == -1) ? info.EpicCv : info.RareCv; // DropProp+0x24/0x28/0x2C
        int diff = db.Value - (level - item.NeedLevel) / db.Divisor;  // 有符号整除; Item+0x50=NeedLevel
        int mf   = LogicBattle.Current.magicFind           // LogicBattle+0x134
                 + (int)PlayerGroup.ControllPlayer.GetProperty(AttribTypeENameEnu.E_MF); // 82
        float num = (diff * 128) * (cv * (-1f/1024f) + 1f) * 100f;    // C1=-0.0009765625 @0x418E320, C2=100 @0x40AF0A4
        float den = mf + 100f;
        int cap = (int)(num / den);
        if (cap > db.ThresholdValue) cap = db.ThresholdValue;
        if (cap < 1) cap = 128;
        if (LogicX2.Random.Range(rng, 0xEEFF0072, 1, cap) < 129)      // System.Random.Next(1,cap) ∈ [1,cap)
            return i + 6;                                  // 命中 -> quality = 该档
        result--;                                          // 失败 -> 下探（6→5→4→3）
    }
    return result;                                         // 最低 3
}
```

## 4. DropBase（全 6 行，静态表）

| ID | ItemQua | Value | Divisor | ThresholdValue |
|---:|---|---:|---:|---:|
| 1 | Poor | 4 | 2 | 128 |
| 2 | Common | 6 | 8 | 768 |
| 3 | Uncommon | 12 | 12 | 1536 |
| 4 | Rare | 18 | 20 | 2304 |
| 5 | Epic | 48 | 15 | 6144 |
| 6 | Legendary | 400 | 3 | 51200 |

Cv=0、MF=0、battleLevel≤NeedLevel 时的**单档条件命中率（最低基准）**：此时 computed cap ≥
ThresholdValue 被截顶（cap=ThresholdValue），`Next(1,cap)` 上界**不含** ⇒ p = 128/(cap−1)：

| 档 | cap | 单档条件命中率（基准/最低） |
|---|---:|---:|
| 6★ Legendary | 51200 | 128/51199 ≈ **0.2500%** |
| 5★ Epic | 6144 | 128/6143 ≈ **2.0837%** |
| 4★ Rare | 2304 | 128/2303 ≈ **5.5580%** |

level>NeedLevel、MF>0 或 Cv>0 使 cap 低于截顶值、命中率**上升**（cap≤129 该档必中；
cap<1→128 亦必中）。注意上表是"轮到该档后"的**条件**命中率；**边际分布**（无带）需乘
前档失败概率：

| Star | 边际概率（基准，无带） |
|---|---:|
| 6★ | p6 ≈ **0.2500%** |
| 5★ | (1−p6)·p5 ≈ **2.0785%** |
| 4★ | (1−p6)(1−p5)·p4 ≈ **5.4286%** |
| 3★ | 其余 ≈ **92.243%** |

**再经 DroopLimit3 星级带**（对最终分布影响大，必须分开算）：
- 带 [3,5]：原 6★ 被**收敛为 5★** ⇒ 关卡最终 P(5★) = 边际5★ + 边际6★（6★ 在该关不可见）；
- 带下限以下（如 [4,6] 的原 3★）：**整件掉落被拒**（JudgeDropItem return false → InitDrop
  跳过该件，无 DropItem 产生），**不是升档**；
- 带内原值不变；超上限收敛（[3,4] 的 5★/6★ → 4★）。
DropProp 332 行中仅 13 行非零 Cv（1309xxx 特殊组）；Cv=1024 ⇒ cap=0→128 ⇒ 该档必中。
83 个 IsADC=E_ADC 组（装备掉落组）Cv 全为 0。

## 5. 调用位置

- `InitDrop` 主循环（0x1E48CE0..0x1E48E68）：`needIdentify → IdentifyItem → quality 写入 ItemStruct`
  → `JudgeDropItem(item, isEqt: Item.ItemType==10)` → `DropItem.Init(..., quality, num, itemValue, addADCGroup, ...)`。
- `AddDropItem`（NPCUnit/JinHuaUnit/LieXiUnit TriggerDropItem、FishTrigger）→ `GetDropItemByGroup`/`JudgeDropItem` 同管线。
- 拾取：`DropItem$$PickItem` → `FightItemBag.AddItem(id, mQuality, mNum, GoldCount, …, FIGHT)`。
