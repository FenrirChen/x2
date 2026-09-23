# 经济缺口定点补证据（2026-09-23）

范围：`NEED.md` 的十二项缺口；仅复核已有配置表、`dump.cs`、protobuf 类和 `libil2cpp.so` 定点方法。未重新扫描 APK、运行客户端或修改服务器。状态表示**官方证据的恢复程度**；`REVIVAL_CAN_DEFINE` 单独表示项目可否制定兼容规则。`LIKELY_SERVER_ONLY` 是依据现有客户端作出的判断，并非声称已取得服务端源码。

## A. 商店商品内容 — PARTIAL

**OFFICIAL_EVIDENCE:** 25 个 `ShopConfig`、1,567 行 `ShopGoodsGroup` 可连接 `ShopID → GroupID → GoodsID`，并提供价格、货币、周期类别和条件。`ShopGoodsGroup` 没有 `ItemID`、`Num`、限购次数。`L2C_Goods` protobuf 类有 `goodsId/itemId/num/price/currencyType/canBuyTimes/hasBuyTimes/limited`；`L2C_ShopGoods` 和 `L2C_RefreshShop` 均带 `List<L2C_Goods>`。`ShopModule.OnReceiveShopGoodsMsg` (RVA `0x17A5660`) 把服务响应商品列表写入商店运行态；`OnReceiveRefreshShopMsg` (`0x17A5C28`) 同样处理刷新列表；`OnRefreshShoppingMall` (`0x17A6050`) 从运行态商品构造快购数据。购买请求 `C2L_BuyGoods` 发 `shopId/goodsId/buyNum`，回执 `L2C_BuyGoods` 给 `itemId/itemNum/hasBuyTimes`。这些字段证实客户端有能力消费服务端下发的真实商品，而静态商品表不是完整商品目录。

协议入口先由 `dump.cs` 的 `L2C_Goods.Serialize(Stream, instance)` (`0x3AB6958`) / `Deserialize(Stream, instance)` (`0x3AB6D00`)，以及 `L2C_ShopGoods.Serialize(Stream, instance)` (`0x36A6E4C`) / `Deserialize(Stream, instance)` (`0x36A7250`) 定位，再追接收 handler 与 UI 消费路径；不能把配置表缺字段误判为客户端不使用这些字段。

六个定点 GoodsID 的精确数值搜索结果如下；检索范围为现有 34 份已提取规范表及相关命名配置，而非重新扫描 APK。`QuickBuyID` 是反向购买入口线索，不保证该商品在所有上架条件下的服务端内容。

| GoodsID | 静态路径 | Item 快购反向命中 | Num |
|---:|---|---|---|
| 2001501 | 店 801 → 季节组 957 → GoodsID | 1237913（光能） | 无证据 |
| 2006901 | 店 801 → 季节组 971 → GoodsID | 1237925（纯晶石） | 无证据 |
| 1933001 | 店 809 → 组 326 → GoodsID | 1281001（石雕面具） | 无证据 |
| 1933002 | 店 809 → 组 327 → GoodsID | 1281002（星象盘） | 无证据 |
| 1933003 | 店 809 → 组 328 → GoodsID | 1281003（石刻飞船） | 无证据 |
| 1900101 | 店 801 → 组 1 → GoodsID | 无 | 无证据 |

全表仅 17 条 `Item.QuickBuyID` 能反向命中 GoodsID。故 **GoodsID → ItemID 为 PARTIAL（17 条反向线索；其余很可能仅在服务响应中）**；**GoodsID → Num 为 LIKELY_SERVER_ONLY**。随机店抽取、普通/季节组启用与动态上架结果亦无完整客户端静态算法。当前资料中没有成功且带商品内容的历史 `L2C_ShopGoods` 样本；现有“成功空列表”会使官方客户端在 `OnRefreshShoppingMall` 触发异常，不能作为商品证据。

**REVIVAL_CAN_DEFINE:** yes，仅可明确标作兼容商品目录与抽取策略；不能称官方复原。

**RECOMMENDED_ACTION:** 优先征集可信的历史成功商店响应（含不同店、刷新、购买回执），按 `shopId/goodsId/itemId/num/canBuyTimes` 保存原始样本。没有样本时维持商店不可购买，不从相近 ID、图标或价格猜物品及数量。

## C. 商店限购与刷新 — PARTIAL

**OFFICIAL_EVIDENCE:** `Limited=E_Day/E_Week` 只是周期枚举；静态 `ShopGoodsGroup` 没有次数。响应 `L2C_Goods.canBuyTimes/hasBuyTimes` 提供动态次数。`L2C_ShopGoods` / `L2C_RefreshShop` 提供 `NextRefreshTime`（long）、`RefreshTimes`、`RefreshPrice`，并进入 `ShopModule.ShopInfo`。`ShopConfig` 的 `ShopRefreshTime=[5,18]` 是原始列表；未见证据足以确定时区、是时刻还是配置索引。`ShopModule.GetInterval` (`0x17A7450`) 按已购次数选整数阈值区间，超出后停在末档；`CalNumPrice` (`0x1797A08`) 对价格递增商品使用 `ShopGoodsGroup.RefreshInterval/RefreshPrice` 阶梯。因此这里的 **`ShopGoodsGroup.RefreshInterval` 是购买数量的分档阈值，不是刷新时间单位**。`ShopConfig` 自己的刷新相关字段仍需分开解释。客户端本地倒计时不能证明服务端重置时刻；手动刷新次数和下次刷新时间由响应给出。没有确认的官方 `serverTime` 时区规则。

**REVIVAL_CAN_DEFINE:** yes。可制定自己的配额和时区/刷新时刻，但应作为 Revival 兼容规则登记；不把 `[5,18]` 直接解释为官方 05:00/18:00。

**RECOMMENDED_ACTION:** 若要复原官方规则，先要含 `NextRefreshTime/RefreshTimes/RefreshPrice` 的跨期历史响应。否则保持已知价格阶梯、把周期与日历解释留待兼容规则决策。

## B. 随机/怪物掉落 — LIKELY_SERVER_ONLY

**OFFICIAL_EVIDENCE:** `Section.DropValueID` 的 `10610001`、`10610801`、`10630101` 在现有已提取表中只作为 Section 字段出现，分别见关卡 2110001/2139751、2110801、2130101/2139703。341 个不同 `DropValueID` 与 `DropProp.DropClass`、`DropBase.ID`、`Gift.GiftGroup` 均无直接数值交集；现有 TextAsset/配置索引只有 `DropBase`、`DropProp`，无已提取 `DropValue` 配置。`L2C_FightData.FightDataProfile.DropValues`、`FightDataProfileProto.DropValues` 承载展开的运行态键值。`FightModule.OnFightDropData` (`0x1447E1C`) 处理 `FightDropData`；`LogicBattle.OnUpdateDropValue` (`0x18FA700`) 写入运行态 `DropValues`。`DropItemManager.AddDropItem` (`0x1E4C8C0`) 虽查 `SectionTable`，随后给 `DropPropManager.GetItem` 的却是方法参数 `dropGroup`（ARM64 `mov w20,w2` 后 `mov w1,w20`），并非 Section 的 `DropValueID`。因此找不到可实际跑通的 `DropValueID → DropClass → Item` 静态链；不能按数字前缀硬连。

**REVIVAL_CAN_DEFINE:** yes，仅在项目决定自行设计掉落时；概率和映射绝不能标为官方。

**RECOMMENDED_ACTION:** 若追求官方掉落，需历史 `FightDataProfile/DropValues`、结算 `FightDropData/RewardData` 样本，且要能绑定关卡与战斗上下文。无样本时继续空随机掉落。

## D. 日/周重置 — USER_CAN_DEFINE

**OFFICIAL_EVIDENCE:** `TaskControl` 唯一记录 `ID=5`，`DailyRefresh=5`、`WeeklyRefresh=5`。客户端 `NormalTaskTab.Init` (`0x193E588`) 读取 `TaskControlManager.GetItem(5)`；这个 5 是记录 ID，不能据此推断两个 Refresh 字段的单位。任务显示从服务端任务/宝箱快照取得状态。现有定点证据未证明 `DailyRefresh/WeeklyRefresh` 是小时、星期、枚举或配置索引，也未证明官方时区、周起始日、跨期补发规则。

**REVIVAL_CAN_DEFINE:** yes。

**RECOMMENDED_ACTION:** Revival 可自行确定时区、每日与每周边界、跨期领取规则，并写为兼容规则；在确定前保留当前不自动重置行为。不要把原始值 5 断言为 05:00 或星期五。

## D. 活跃宝箱 — PARTIAL

**OFFICIAL_EVIDENCE:** `TaskControl` 按索引给日门槛 `[20,40,60,80,100]`、普通礼物组 `760001–760005`、季节礼物组 `760016–760020`，周门槛 `[30,60,90,120,150]`、礼物组 `760010–760014`。`L2C_GameTask.boxList` 中 `TreasureBoxData` 有 `boxId/pickStatus/activityId`；日/周共用结构并带类型。`NormalTaskTab.Refresh` (`0x193F664`) 以返回列表顺序显示，`pickStatus=1` 用 ready UI、`=2` 用 opened UI，其余用 closed UI。`OnBoxReadyStateClick` (`0x19401FC`) 把 UI 索引交给 `DailyTaskModule.NetGainActivityPresent` (`0x169319C`)，后者作为 `C2L_PickTreasureBox.boxId` 发送，并携带 type/activityId；`PickBox` (`0x1693BF4`) 按响应 `boxId` 定位快照。因此 **boxId 与阈值按客户端列表索引相关**，但缺少真实非空 `boxList` 来确认索引从 0 还是 1、顺序异常处理。`NormalTaskTab.OnBoxBoxCloseState` (`0x193FF58`) 按日/周类型选对应礼物组；活动服务开放检查 `CheckActivityServerOpen(55)` 为真时改用季节日礼物组。这证实季节预览受活动 55 条件控制，实际发奖仍以服务端回执为准。

**REVIVAL_CAN_DEFINE:** yes，可规定 boxId 编号与状态迁移；须与上述 UI 索引/状态兼容，并明确为项目规则。

**RECOMMENDED_ACTION:** 找到带五个宝箱状态的真实日/周 `L2C_GameTask` 和领取回执，再确认索引基数、领取后状态及奖励；在此之前不开放领取。

## E. 其余 NEED 项

### 任务业务事件 — PARTIAL

**OFFICIAL_EVIDENCE:** 40 个日/周任务的条件、目标、门槛和 Gift 已静态恢复；强化、训练、探险、好友、炼金等成功事件来源尚未逐一绑定服务端操作。指定时段在线的时区未证实。

**REVIVAL_CAN_DEFINE:** yes，可在真实操作成功时触发本地进度，标为兼容行为。

**RECOMMENDED_ACTION:** 只对实际成功的业务事件计数；若要进一步逆向，优先追有协议 handler 的高价值事件，不重复解析任务表。

### 击杀任务 — PARTIAL

**OFFICIAL_EVIDENCE:** `FightKillInfo` 有单位/数量遥测结构；单位分类、重复统计和战斗运行实例的核验关系未恢复。

**REVIVAL_CAN_DEFINE:** yes，可制定与可信战斗结算绑定的计数规则。

**RECOMMENDED_ACTION:** 继续不把未核验的客户端上报直接记入任务。值得定点追 `FightKillInfo` 到可信结算的调用链。

### 战斗体力 — PARTIAL

**OFFICIAL_EVIDENCE:** `Section.ManualValue=6` 存在，但没有充分证据证明每一幕扣 6，或确认首通、串联、失败与退出的收费/退款时机。

**REVIVAL_CAN_DEFINE:** yes，可制定兼容扣费与退款策略。

**RECOMMENDED_ACTION:** 若追官方行为，需对应的进入/结算/退出响应样本；当前保持免费进入，不能从单字段推出全流程。

### 经验升级 — PARTIAL

**OFFICIAL_EVIDENCE:** 固定 Gift 的玩家经验和神格经验数量已恢复，客户端另有经验/等级相关静态配置；目前只落实资源记账，升级阈值、满级、英雄升级操作与所需资源尚未贯通到协议操作。

**REVIVAL_CAN_DEFINE:** yes，可制定兼容等级曲线，但不应把已知奖励量当作升级算法。

**RECOMMENDED_ACTION:** 这是可继续定点逆向的项目：先对齐玩家/角色经验表字段与升级 handler，再考虑启用升级。

### 装备实例与特殊货币奖励 — PARTIAL

**OFFICIAL_EVIDENCE:** 部分 Gift 已能落到装备或额外货币 ItemID；装备实例随机属性、生成参数和货币同步字段仍缺失。

**REVIVAL_CAN_DEFINE:** yes，可定义本地装备词条/同步模型，但只能称兼容规则。

**RECOMMENDED_ACTION:** 优先找可信领取响应的装备实例与货币变化样本；仍须原子地拒绝含未知奖励目标的领取，不猜词条。

### 战斗校验 — PARTIAL

**OFFICIAL_EVIDENCE:** Revival 已有 run UUID、会话、结算摘要和持久回执；官方 `battleFile/sign` 完整校验及跨会话续战语义未恢复。

**REVIVAL_CAN_DEFINE:** yes，可维护独立兼容校验与幂等规则；不能称官方反作弊复现。

**RECOMMENDED_ACTION:** 仅在需要跨会话续战或更强校验时定点追对应 protobuf/handler；维持现有可信边界。

### 后续关卡准入 — PARTIAL

**OFFICIAL_EVIDENCE:** 2110802–2110804 的固定表已导出；串联准入、剧情触发、装备奖励及全流程验证未完成。静态关卡存在本身不能证明可进入。

**REVIVAL_CAN_DEFINE:** yes，可定义保守准入白名单与独立任务进度。

**RECOMMENDED_ACTION:** 保持当前两关范围；只有在剧情/奖励链有证据或项目明确采用兼容流程后再开放。

## 证据边界与后续顺序

最值得继续考古的是成功商店响应、可绑定关卡的战斗掉落响应、日/周非空宝箱响应，以及经验升级 handler。对概率、商品数量、装备词条、官方时区和周期边界，现有静态证据不足；即使 Revival 自定，也须与“官方复原”分栏记录。机器可读分类见 `analysis/economy/missing_evidence_followup.json`。
