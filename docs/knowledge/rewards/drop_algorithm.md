---
Document-Type: Current Knowledge
Domain: Rewards
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - docs/history/2026-09-24_03_deep_drop_archaeology.md
---

# X2 2.4 客户端 DropProp 抽取算法

## 结论与证据范围

`dump.cs` 中目标实际是 `LogicX2.DropItemManager.GetDropItemByGroup(DropProp,int)`，RVA `0x1E4845C`，终点 `0x1E48B0C`。`DropPropManager.GetItem`（`0x1CAE54C`）只负责按 `DropClass` 查表。分析依据是同版本 `libil2cpp.so` 的完整 ARM64 函数（428 条指令、113 个基本块）、字段偏移、直接调用及静态表。完整逐指令与控制流边见 [CFG(../../../analysis/drop_algorithm/get_drop_item_by_group_cfg.md)，调用者、字段和随机数调用分别见同目录的 `callers.json`、`field_accesses.json`、`rng_calls.json`。

证据指纹：`libil2cpp.so` SHA256 `37F092F117C11D7E0CDAE1E9AC9F7123487C97B6D91C4E7AB699D380646A1DCA`；`global-metadata.dat` SHA256 `CB249BA8841F042AAB1C22828CC390AC7B7E4B0306D450AABB025A9EF7B8A427`；`dump.cs` SHA256 `B5C7AD3D9A551565BF399258401A30FE26881773DDE886FDD2E535F9A42A09A1`。`A` 表示原生指令/直接调用证实，`B` 表示由指令组合和均匀 RNG 强重建，`C` 表示待运行时证实，`D` 表示被代码否定。

| 问题 | 结论 | 证据 |
|---|---|---|
| `Prob` | 普通正 `Picks` 组是**相对权重**；负 `Picks` 组是每个候选的**确定重复次数**；`IsADC` 由动态候选流程解释 | A：`0x1E48704–0x1E48768`、`0x1E4886C–0x1E488AC`、`0x1E48940–0x1E48964` |
| `NoDrop` | 普通组每个 pick 的空奖权重，与所有 `Prob` 求和后构成第一随机范围；不是每个物品的独立失败率。负 `Picks` 不读取它 | A：`0x1E4893C–0x1E489C4` |
| `Picks` | 正数是抽取循环次数，零次则没有普通抽取；负号切换到确定次数模式，负数绝对值不作循环次数 | A：`0x1E484FC`、`0x1E486FC`、`0x1E4896C–0x1E48AB8` |
| `ItemList` | 与 `Prob` 同索引；正组每次选一个索引。直接 Item ID 与嵌套 DropClass 分流 | A：`0x1E48878`、`0x1E48A14–0x1E48A98` |
| 独立伯努利模型 | 同一 pick 内候选互斥；`Prob=[50,50,50,50]` **不是**四个各 50% 的独立判断 | D：只调用一次 `GetProbability` 选择单个索引 |
| `DROP_WEIGHT_PARAM=10000` | 普通组不以 100/10000 归一化。`10000 / Item.ItemValue` 是 `IsADC` 动态候选权重 | A：`CheckItem` `0x1E4C308–0x1E4C314` |

### 控制流及伪代码

下面只将 ARM64 控制流翻成 C# 风格。`AddItems`、`AddMetaLoot`、`CheckItemLimit` 等维持原函数边界；注释指出哪些结果仍受下游状态影响。

```csharp
List<ItemStruct> GetDropItemByGroup(DropProp root, int level)
{
    mLootGroup.Clear();
    mItems.Clear();

    if (root.Picks < 0) // 0x1E484FC；预先把嵌套组重复压栈
        for (int i = 0; i < root.ItemList.Count; ++i)
            if (IsDropClass(root.ItemList[i]))
                for (int n = 0; n < root.Prob[i]; ++n)
                    mLootGroup.Push(root.ItemList[i]);
    mLootGroup.Push(root.DropClass); // 0x1E48624

    while (mLootGroup.Count > 0) { // 0x1E486xx–0x1E48ACx
        DropProp group = DropPropManager.GetItem(mLootGroup.Pop());
        if (group.Picks < 0) { // 0x1E486FC
            for (int i = 0; i < group.ItemList.Count; ++i)
                for (int n = 0; n < group.Prob[i]; ++n) {
                    int id = group.ItemList[i];
                    if (IsDirectItem(id)) AddItems(i, group); // index; num=1 per call
                    // Nested groups are processed through mLootGroup, not a
                    // direct recursive call to this method.
                }
            continue;
        }

        int total = group.NoDrop + Sum(group.Prob);
        if (group.IsADC == 1) { // 0x1E48940–0x1E48964
            AddMetaLoot(group.DropClass, level, total);
            continue;
        }
        for (int pick = 0; pick < group.Picks; ++pick) {
            int gate = mRandom.Range(mark, 0, total); // max exclusive
            if (gate < group.NoDrop) continue;
            int index = GlobalFun.GetProbability(mRandom, group.Prob);
            int id = group.ItemList[index];
            if (IsDirectItem(id)) AddItems(index, group);
            else mLootGroup.Push(id); // nested DropClass, own rules later
        }
    }
    CheckItemLimit(); // may alter pre-limit results
    return mItems;
}
```

上述负 `Picks` 伪代码把入栈和直接物品循环简化显示；实际代码在入口及逐层处理处有栈操作，迭代顺序见 CFG。`IsDirectItem` 的直接分流区间是 `1000001..1299999`（含端点）；其余候选按组 ID 处理。组嵌套由显式 LIFO 栈完成，没有对本方法的直接递归调用；每个子组重新执行自己的 `Picks/NoDrop/IsADC` 规则。代码没有发现显式深度上限；静态图无循环，运行时出现环的行为仍需验证。

`GlobalFun.GetProbability` RVA `0x18D2880` 先求权重和，然后调用 `Range(0,sum)` 并依次减去各权重选中一个索引（`0x18D28D4–0x18D2984`）。普通组一次非空 pick 先经历 `Range(0,NoDrop+ΣProb)`，再做候选权重抽签。于是对理想均匀随机，令 `T=NoDrop+ΣProb`，单次 `P(empty)=NoDrop/T`、`P(candidate i)=Prob[i]/T`（B）。相同组 `Picks=N` 时按替换抽取 N 次；可出现多个不同物品，也可重复相同物品，但单个 pick 内候选互斥。`Picks<0` 则无这两次随机抽取，`Prob[i]` 次处理候选。`ItemList`/`Prob` 长度不等时函数没有显式容错；静态 332 行均对齐，不能据此推定异常输入的正式行为。

`AddItems` `0x1E4B0B8–0x1E4B0BC` 为一次成功的直接物品添加设置 `ItemStruct.num=1`；这并不证明最终背包给付数始终为 1，后续限额、拾取及服务端结算仍另有逻辑。`IsADC` 在 `AddMetaLoot` 中查 `Group/Level` 与 `TableMgr.mDCTable`，经 `CheckItem`/`SectionTable.DroopLimit` 等过滤动态物品候选，做空奖门控及候选加权选择。其 `ItemList=[0]` 是哨兵，不能当普通物品零或由表直接算最终 Item 率。`10000 / Item.ItemValue` 只出现在这条动态候选权重路径。

### RNG 与调用链

`LogicX2.Random.Range(uint mark,int min,int max)` RVA `0x3EFD408` 最终调用 `System.Random.Next(min,max)`，**上界不包含**。`LogicBattle.InitBattle` `0x18F3A18` 接收战斗种子，初始化 `mRandom4FightSeed`（`0x18F41F8`），派生 `mRandom` 种子（`0x18F4220–0x18F4244`）；`Random.InitSeed` `0x3EFD3E4` 构造 `System.Random(seed)`。同种子、同调用顺序/回放状态下可重现；并无 DropClass 固定结果。具体随机标记和调用顺序属于战斗重放的一部分。

完整 `.text` 直接 BL 交叉引用显示目标方法被 `DropItemByUnit` 两处（自定义组和 `UnitBase.DC` 列表）及 `AddDropItem` 一处调用。上游包括 `Monster.EnterDead`、`TriggerActions.ItemDrop`、`FishTrigger.EndFishEvent`、`JinHuaUnit.TriggerDropItem`、`LieXiUnit.TriggerDropItem`、`NPCUnit.TriggerDropItem`。这覆盖怪物死亡、脚本及特殊单位/事件投放路径；仅凭直接 xref 不能把每个场景都定性为箱子、活动或装备掉落。间接虚调用也不在该 BL 清单内。

### 真实表样本

| DropClass | 原始配置简写 | 恢复的静态结果（下游限制之前） |
|---:|---|---|
| 1301102 | `IsADC=1,Picks=1,NoDrop=88,Prob=[12],ItemList=[0]` | 12/100 通过空奖门控；最终 Item 身份/率由动态候选决定 |
| 1309118 | `Picks=1,NoDrop=70,Prob=[30],ItemList=[1109011]` | Item `1109011` 概率 `3/10` |
| 1309102 | `Picks=1,NoDrop=60,Prob=[50,49,1]` | 总权重 160，三项依次 `5/16`、`49/160`、`1/160`；空奖 `3/8` |
| 1309116 | `Picks=5,NoDrop=30,Prob=[70],ItemList=[1101021]` | 期望 `7/2` 个条目，至少一个的概率 `99757/100000` |
| 1309010 | `Picks=-1,Prob=[5,1],ItemList=[1101021,1100001]` | 确定处理第一项 5 次、第二项 1 次；负值绝对值不是次数 |
| 1309024 | `Picks=1,NoDrop=70,Prob=[30],ItemList=[1302601]` | 30% 压入子 ADC 组；子组 `Picks=5,NoDrop=40,Prob=[60]`，动态候选期望尝试数 `0.9`，最终 Item 率未知 |
| 1309250 | `Picks=1,NoDrop=0,Prob=[1],ItemList=[1104048]` | `Prob=1` 仍是 100% 选中，而非 1% |

机器可读样本见 [`sample_evaluations.json`(../../../analysis/drop_algorithm/sample_evaluations.json)。尤其 `1309102` 的 `NoDrop+ΣProb=160` 直接否定固定百分比；`1309250` 更明确否定“原始 Prob 数字就是百分比”。负 `Picks` 行则连概率语义都不适用。

### 计算器与未解范围

分析工具 [`calculate_drop_probability.py`(../../../tools/analysis/calculate_drop_probability.py) 只接受普通/负 `Picks` 且全部子组可由静态配置解出的路径，输出每个 Item 的 `expected_quantity`、`expected_count`、`P(at least one)` 及名字（若语言表可解析）。负路径按确定次数、正路径按重复权重抽取做精确有理数运算。遇 `IsADC`、未知组、循环或无效权重会返回/抛出不可计算原因；**不会编造最终掉率**。例如：

```powershell
python tools/analysis/calculate_drop_probability.py 1309102
```

输出的范围标为 `STATIC_CONDITIONAL_PROBABILITY_PRE_LIMIT`。真实结果还可能受到 `CheckItemLimit`、品质/拾取规则、怪物及关卡条件、战斗状态、服务端结算影响。`Section.DropValueID`、`FightDataProfile.dropValues`、264/266 消息属于另一层，本研究未恢复其映射或服务端规则。当前不能仅凭 DropProp 给出全部游戏终态的精确掉率；普通静态组可以给出上述条件化、限额前概率，ADC 组不能脱离运行时上下文给最终物品概率。

### 第三方工作簿重新判定

第三方“掉落概率%”列只忠实复制了原始 `DropProp.Prob` 数字，标题的百分号**不是算法证据**。它应标为 `RAW_PROB_PARAMETER`：普通正 `Picks` 行为 `WEIGHT`，负 `Picks` 行为 `DETERMINISTIC_REPEAT_COUNT`，ADC 行参与动态流程。只有在特定行恰好 `NoDrop+ΣProb=100` 且无其他条件时，单次普通组候选概率数值才碰巧等于所写百分数。原表三处未申报的凑 100 修改仍不采纳。此结论替代此前“算法尚未复原、10000 参与普通抽取”的临时判断。
