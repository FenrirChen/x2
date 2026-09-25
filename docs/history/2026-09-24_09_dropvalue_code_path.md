---
Document-Type: Historical Report
Date: 2026-09-24
Status: CURRENT_AT_TIME
Superseded-By:
  - docs/knowledge/rewards/ (domain docs)
Note: moved from D:/demo/x2/docs/ into the repository during knowledge reorg
---

# DropValueID 代码路径考古（Section.DropValueID 的消费链）

2026-09-24。方法：dump.cs 类/方法枚举 + libil2cpp.so ARM64 定点反汇编（capstone）+
全 .text BL/B 字节级 xref 扫描。所有结论附 RVA/调用点。

## 1. 静态数据侧（否定性结论，A级）

- Section.DropValueID（Example.SectionTable 字段 0x130）3,043 行携带、341 个不同值。
- **249 张已解码注册表（约 25 万条记录全字段数值索引）中，341 个值零出现**。
  见 `analysis/drop_archaeology/dropvalue_cross_scan.json`。
- 二进制扫描（global-metadata.dat / libil2cpp.so / globalgamemanagers，u32 LE + varint）
  有数百个候选命中，全部是 4 字节/变长编码巧合级噪声（81MB 文件中的随机重合），
  无聚类，不构成表。见 `binary_id_hits.json`。
- **不存在名为 DropValue 的表**：265 个注册表名中无 dropvalue；ExtraDroop/DropProp/DropBase
  均不携带这些值。

结论：客户端没有任何静态结构把 DropValueID 映射到掉落内容。这一步如果发生，只能发生在服务器。

## 2. 运行时数据结构（谁持有 dropValues）

| 结构 | 位置 | 说明 |
|---|---|---|
| `LogicX2.DropItemManager.DropValueList` | 字段 0x48 | 战斗运行时掉落值列表 |
| `LogicX2Command.UpdateDropValue { List<int> dropValues }` | 帧同步命令 | 战斗中更新 |
| `CommandX2.FightDataProfile.dropValues` | 字段 0x20 | 网络 DTO（含 randomSeed/missionId/sceneId） |
| `CommandX2.FightDropData.dropValues` | 字段 0x10 | 264/266 请求与响应载荷 |
| `PlayerDbData.FightDataProfile/InsideBattle.DropValues` | 存档结构 | 续战档案 |
| `FightDataProfileProto/InsideBattleProto.DropValues` | protobuf | CheckFightProfile(447) 存档传输 |

## 3. 写入链（dropValues 从哪来）

1. **服务器响应 266**：`FightModule.OnFightDropData`（RVA 0x1447E1C）反序列化
   `L2C_FightDropData.data → CommandX2.FightDropData`，取其 dropValues 构造
   `UpdateDropValue` 帧命令，经 `LogicBattle.OnInput` 注入战斗模拟。
   即：**服务器可以把展开后的 dropValues 下发给客户端**。
2. **客户端自生成**：`DropItemManager.InitDropValueList(int Count)`（0x1E4ACC4）按数量生成列表，
   由 `JudgeDropItem`（0x1E49838，调用点 0x1E49DF8）与 `SetCurItemValueTotal`（0x1E4AD70，
   调用点 0x1E4AF70）惰性调用。
3. **续战恢复**：`BattleInfo.SetSceneInfoFromSave` / `GameSaveModule.SetGameSaveData`
   （0x567233）从档案恢复。
4. 未找到任何把 `SectionTable+0x130`（DropValueID）装入 DropValueList 的指令路径：
   SectionTableManager.GetItem（0x1BDF664）被编译器内联，全量字节扫描无法直接 xref；
   但 JudgeDropItem 的反汇编显示它读取的是 **BattleInfo.FightData 的 dropValues 列表做
   Contains 门控**，而非 Section 表字段。

## 4. 消费链（dropValues 决定什么）

- `JudgeDropItem`：逐掉落物判定，调用 `get_FightData→GetItem→Contains`×2 +
  `InitDropValueList` + get_Item/set_Item。语义：dropValues 列表参与"这次掉落是否生效/值多少"的判定。
- `SetCurItemValueTotal(itemID, quality, num)`（0x1E4AD70）：统计场内物品总值，
  与 DropBase（品质阈值表：ID/ItemQua/Value/Divisor/ThresholdValue）配合。
- `CheckItemLimit`（读 Item.DropLimit/DropLimitParam，0x1E4BD48/0x1E4BE30）：
  每-物品掉落上限检查，配合 `mItemDayNumCache`（每日计数缓存）。

## 5. 相关但独立的两条线

- **ExtraDroop 表（26 行）**：DroopType 枚举 E_DroopValue/E_DroopUP/E_GoldDroopUP，
  按 SectionGroup 绑定资源本（例：ID 100002 → 2130101–2130105，ExtraParam1=[1237901]，
  NumLimit=10，RefreshCycle=1，ResourceNum=10）。这是"额外掉落/掉落加成"的官方静态配置，
  含物品 ID 与数量上限，但不是 DropValueID 的映射表。
- **MoonCampModule.SendDropLimit**（0x172DC08）：`SetDropLimit{id[],count[]}` 帧命令
  唯一创建点，属月潮玩法，与 ExtraDroop 是两套限制机制。

## 6. 状态分级

- "DropValueID 无客户端静态映射" — **A（CONFIRMED，负面证据完整）**
- "dropValues 运行时语义 = 门控+值 roll" — **B（STRONG_CANDIDATE：反汇编链完整，未逐指令复原公式）**
- "服务器在 FightDataProfile/FightDropData 中下发展开值" — **B（结构+处理链完整，需历史报文样本证实实际取值）**
