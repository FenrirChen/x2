---
Document-Type: Historical Report
Date: 2026-09-24
Status: CURRENT_AT_TIME
Superseded-By:
  - (read alongside current knowledge)
---

# 金币资源本掉落线索（定点静态复核）

日期：2026-09-24。针对 `2030100`（咻咻的宝藏秘境）的 `2130101`–`2130105`，使用已有客户端 `dump.cs` 与已提取的 canonical 表；未重新做 APK 全量逆向，未修改战斗发奖规则或分发目录。

## 已确认的客户端链路

1. `SectionTable` 的这五关使用 `DropValueID=10630101` 等逐关值、`DroopDisplay=[1237901]` 显示金币。`Item.ItemID=1237901` 是外部金币，`EffData=[901]`；`CurrencyType.TpyeId=901` 对应 `E_Gold`。预览字段不含实际战斗数量。
2. `SceneBase` 的 `2230101`–`2230105` 各有独立 `AutoQuestID=560104/560107/560110/560113/560116`，且共用同一组房间候选。`Quest` 链从进入终点房间转为 `E_KillMonster`：例如 `560105` 要求击杀 **1 个单位 4020**，然后 `560106` 触发 NPC `2062` 的事件 `60038`；其余四关相同模式。`UnitBase[4020]` 是 `Elite_Goblin` 精英单位，`DC=[1309026]`，`MonsterEventTable[30101]` 和 `MonsterEventGroup[2330101]` 均引用它。
3. `UnitBase[7025,7026,7027]` 的 prefab 分别为 `Smash_GuanZi01/02/03`，类型 `E_DestructibleObj`，均引用掉落组 `1309024`；`7030/7031/7032` 是另三种罐子，引用 `1309029`。`MonsterEventTable[10241]` 在同一客户端配置中生成 5 个前三种罐子，事件 `10294` 生成 8 个后三种罐子。这些事件表与金币关的房间组之间尚无已验证的直接映射，不能断言每个金币关一定刷出这些固定数量。
4. `NpcEvent[60038]` 类型为 `E_DropItem`，指向掉落组 `1309030`；单位 `2062` 是宝箱 NPC。静态链证实终点宝箱也是独立掉落来源。
5. `DropProp` 包含各来源不同的字段：罐子组 `1309024` 为 `Picks=1, NoDrop=70, ItemList=[1302601], Prob=[30]`；哥布林组 `1309026` 为 `Picks=20, ItemList=[1301201], Prob=[100]`；另三种罐子组 `1309029` 为 `Picks=11, NoDrop=30, ItemList=[1301201], Prob=[70]`；宝箱组 `1309030` 为 `Picks=120, ItemList=[1301201], Prob=[100]`。这些是客户端抽取参数，**不能直接把 Picks 当成最终金币数**：`1301201/1302601` 是嵌套的 `DropProp.DropClass`，而非 `Item.ItemID=1237901`。
6. 已恢复的方法调用关系：`DropItemManager.DropItemByUnit` 按 Section/Unit 与 `DropPropManager.GetItem` 取得掉落组；`GetDropItemByGroup` 会读取嵌套组并调用客户端随机函数；`FightItemBag.AddItem` 可调用 `FightItemBag.AddGold`。这支持“击杀、破坏、拾取影响本次结果”的客户端路径，但上述方法名及调用关系仍不足以推出确切概率、数量和最终入账转换。

## 协议与当前服务缺口

- `C2L_FightDropInfo(323)` 含 `sectionId,layer,itemId,quality,itemNum`，`L2C_FightDropInfo(324)` 仅有状态码；当前服务未注册 323，现有日志没有这条请求的真实样本。它可能是逐次拾取上报，需实机抓到后确认发送时点和数据含义。
- `C2L_CheckoutMainMission` 含 `outsideItems: List<ItemDataP>`（字段 3，条目有 `id,num,quality,eNum`）、`killMonster: FightKillMonster`（字段 22，含 `killDetail`）及 `npcEventOnNumber`（字段 30）。当前服务的 Checkout schema 未解析这些字段，只按关卡给临时金币 ×1。`C2L_FightKillInfo(316)` 另含逐英雄 `unitId[]/num[]`，但现有实机日志显示它在 checkout **之后**才到达，因此不能直接让它决定本次已完成结算；checkout 自身的 `killMonster` 更值得优先核对。
- 当前实测金币 +1 只证明 Revival 临时规则生效，不证明原版每关固定 +1。用户观察到金币随打碎罐子和击杀金币怪变化，与以上客户端静态线索相符。
- `DropProp` 的 `ItemList=[0]` 嵌套终点、场内货币 `901/903` 与 `ItemID=1237901` 的转换及结算信任边界尚未确定。`FightItemBag.AddGold` 默认 `itemID=903`，而 `CurrencyType[903]` 是 `E_Silver`，因此不能只凭方法名把它记为账号金币。

## 原拟验证步骤（两场对照已完成）

在开发服务的独立存档上做一次金币关实战，抓 **323、887、316** 的原始请求体及相同 run ID，按原 protobuf 结构解码；记录打碎罐子数、击杀 `4020` 数、场内拾取显示与结算前后账号金币。对照第二次只改变罐子数的通关，可区分拾取、击杀与固定宝箱部分。战斗由用户操作。实现前需对重复 323、伪造 itemNum、失败结算、重连以及 checkout 幂等建立边界。当前不更换临时规则，也不把 `Picks` 当官方金币公式。

## 2026-09-24 两场 2130102 实战报文

用户在同一关连续完成两场，服务端按时间配对 `C2L_FightData(126) → C2L_CheckoutMainMissionSign(887) → C2L_FightKillInfo(316)`。结算均成功，SQLite 金币由 7,194,941 增至 7,194,943；这两个 +1 来自 Revival 临时规则。

| 场次 | 316 中被击碎的罐子 `7030/7031/7032` | 其他击杀 `4018/4020` | 887 的 `killMonster.eliteMonsterNum` | 887 的 `outsideItems` | 887 的宝箱事件 `60038` | 服务端到账金币 |
| --- | --- | --- | ---: | --- | ---: | ---: |
| 第一场 | 2 / 5 / 5，合计 12 | 3 / 1 | 4 | 空 | 1 | 1 |
| 第二场 | 4 / 5 / 7，合计 16 | 2 / 1 | 3 | 空 | 1 | 1 |

这两场没有 `C2L_FightDropInfo(323)`。罐子数量明确出现在 **结算响应之后**的 316，887 的 `killMonster` 只给出精英怪总数 4/3，不包含罐子明细；`outsideItems` 也为空。887 的其他变化主要是战斗反作弊/状态字段、`fightDataA` 28/27 与精英怪数，尚不能从中还原金币数量。当前 `L2C_FightDropData` 明确返回空 `dropValues`，会影响客户端场内掉落；因此两场不能证明原版罐子金币公式，也不能直接把 316 当作当前结算前可用的奖励依据。后续应先恢复 `DropValueID → dropValues → 场内拾取` 的证据链，再设计可信的结算与迟到 316 的关系。原数量仍标 **UNRESOLVED**。

## 用户指定的后续 Revival 金币规则

用户决定当前先让金币资源本普通胜利结算的金币数量等于**本关扫荡专属金币组**的数量。开发版据各 Section 的 `MopReward` 中扣除普通 `VReward` 后的独立金币组取数：`2130101`→2078、`2130102`→4678、`2130103`→9356、`2130104`→14552、`2130105`→20788。这里只借用每关金币**数量**，不执行整个扫荡奖励，也不复制到其他资源本；原版按罐子/金币怪动态计算的规则仍未恢复。五关逐关结算测试已通过。
