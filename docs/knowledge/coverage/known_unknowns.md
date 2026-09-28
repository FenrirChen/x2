---
Document-Type: Current Knowledge
Domain: Coverage
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - (none)
Evidence-IDs: see evidence/manifests/evidence_manifest.json
---

# Known Unknowns（截至 2026-09-27 仍未解）

账号领域另见 `../account_registration.md`：官方初始赠送和游客后端失传；
Revival 注册兼容层已通过隔离库与 MuMu 实机注册/重登；官方游客身份规则
仍未知，Revival 暂不支持其空密码短随机账号路径。注册门槛已解除，公网部署仍暂停。

| # | Domain | Unknown | Why unknown | Evidence searched | 当前处理 | 阻塞 | 下一步 |
|---|---|---|---|---|---|---|---|
| 1 | Drop | ~~DropValueID 语义~~ **结构已破解（2026-09-26）**：`DropValueID = 10600000 + SectionID%100000`（310/341 全量命中；85 组为有意的跨关卡共享，如活动变体复用本体；少量错位为手工授权痕迹）——它是**服务器侧按关卡派生的掉落配置键**（现知用途：264/266 dropValues 战斗预算的配置来源，B 级），不是'掉什么'的内容表（静态零命中因此合理）。**残留**：配置的具体数值（每组预算等）在官方服务器数据中已失传 | 全量公式验证 341 组 + SetSceneInfo/OnUpdateDropValue/JudgeDropItem 反汇编 + 实机 264/266 闭环 | Revival 用 27×1,000,000 兼容预算（REVIVAL_COMPAT）；不生成 DropValueID 账本 | 低（从'完全未知'降级为'键已破解、值失传'） | 若需官方量级：只有官方报文样本可解 |
| 2 | Drop | ~~264/266 dropValues 准确语义~~ **已解（2026-09-25 实机闭环 + ARM64 A 级）**：dropValues = 按 AddADCGroup 的掉落价值预算，**主载体 = 264 C2L_FightDropData（客户端战斗状态上报）→ 266 L2C_FightDropData{result,data=FightDropData{dropValues,missionId}}**：`FightModule.OnFightDropData(0x1447E1C)` 校验 result==10 → 反序列化 data → `UpdateDropValue` 经 `LogicBattle.OnInput` 更新预算；次载体 = 130 入场响应 `FightData.dropData`（`SetSceneInfo` AddRange）。`JudgeDropItem` 消费预算（装备=组5，扣 `EquibStage[Star].EquibValue×ItemValue/1000×num`），**预算空 ⇒ 客户端拒绝全部 ItemStruct 掉落 ⇒ outsideItems 恒空**（2133101 两次实机复现；Revival 旧应答 dropValues 恒空为直接原因）。Revival 现按官方 DifficultyLevel 下发分级预算 LOW/MID/HIGH = 1000/3000/5000（REVIVAL_COMPAT/USER_DECISION，decisions/compatibility/equip_dropvalues_budget.md；旧 27×1,000,000 策略已废弃）。**残留**：官方每组预算数值未知；Section.DropValueID(106xxxxx) 是否即官方预算的静态来源仍未证（关联 #1） | SetSceneInfo/JudgeDropItem 反汇编（A）+ 实机 wire 抓包（battle_checkout_wire） | 已下发 REVIVAL_COMPAT 预算；实机复测待用户验证 | 低 | 实机复测兽主本掉落 + 记录 dropValues 官方样本（若可抓） |
| 3 | Equipment | ~~初始副词条数量公式~~ **已解决（2026-09-25 升级）**：条数 = 所选 EquibAttribBD 行 MinorAttrNum（A，GM opt=15 证据）；合法范围 = EquibStage.MinorListMin..MinorListMax（A，客户端强化门强制 Max）；掉落星级 = 客户端 IdentifyItem 掷骰（DropBase 6/5/4 + Cv/MF/level 公式，A）经 DroopLimit3 带收敛，outsideItems.quality 直接携带（Star=quality，A）。**官方选行概率未知，但 Revival 已采用 65/35 兼容策略**（base/Min 档 65% / Max 档 35%，仅 4/5/6★；REVIVAL_COMPATIBILITY/USER_DECISION，见 decisions/compatibility/equip_attribbd_tier_selection.md）。**剩余未知仅**：(a) 官方 AttribBD 选行概率（客户端不可见；Revival 已定 65/35）；(b) 随机件数值 3 档取档——官方映射仍未知（ChanceSec 客户端零消费），但 Revival 已采用逐段升级链兼容策略（ValueSec[0] 起步，ChanceSec[0]%→tier1，再 ChanceSec[1]%→tier2；主 [60,40]→40/36/24、副 [80,20]→20/64/16；适用于 src0 主初始/src2 副初始/src3 强化增量；REVIVAL_COMPATIBILITY/USER_DECISION，见 decisions/compatibility/equip_valuesec_tier_roll.md） | IdentifyItem/JudgeDropItem/GMMainPage.GetEquip/CheckSubAttruib/GetAttrNum 反汇编（A）+ item/dropprop/dropbase/sectiontable/equibattribbd/equibstage 全量静态验证 | Star=quality 直采；条数=所选档行 MinorAttrNum（65/35 兼容）；数值按 EquibAttrib 阶梯 + 逐段升级链取档（REVIVAL_COMPAT，已决策） | 低（规则已恢复） | 实机掉落样本核对 quality=Star 与初始条数分布（校准 65/35） |
| 4 | Gift | E_RandomInterval/E_Pick/E_BlindBox 语义 | 解析器 Num 维度未展开；交互 UI 未逆向 | GetItemByGiftGroup/GetItemNumByGiftGroup | 拒绝执行 | 低 | 定点 disasm GetItemNumByGiftGroup |
| 5 | Special | WeeklyDungeon 里程碑触发 | 无独立协议枚举项 | protocol_catalog | 不并入 VReward | 低 | 等热更 DLL 或实机样本 |
| 6 | Special | 宝箱开启 C2L（E_Chest 物品使用通道） | Send 泛型清单无独立出现 | PROTOCOL_CATALOG | 只登记数据源 | 中 | 物品使用通道逆向（ItemOpt/热更） |
| 7 | Shop | 大部分官方 GoodsID→ItemID/Num、库存/限购次数/刷新池 | 客户端无完整映射；原服数据失传 | 客户端表、QuickBuy 反查、A/B 包审计 | 809 沿用原映射；其他店使用 B 包兼容目录，安全可交付商品可购买，限购每周期 1 次（REVIVAL_COMPATIBILITY / USER_DECISION） | 中 | 原服非空 L2C_ShopGoods 样本替换兼容值 |
| 12 | Affection | 双值 EffData 的英雄偏好选择、触摸增量/限额、突破与联结完整规则 | 官方静态表只有两档效果值，缺偏好选择及服务端限制 | Item/Favorability 全表、协议 send point、A/B 包审计 | 单值礼物事务扣物加好感；双值礼物及未知交互拒绝且不扣物 | 中 | 客户端算法或原服送礼报文 |
| 13 | Collection | 133103 的 E_Medal 奖励落账位置 | 当前 RewardGrant 不支持 ItemType 20；不能把勋章当普通背包物伪发 | canonical Collection/Gift/Item 与当前 RewardGrant | 该条拒绝且不标记已领取；其他 25 条可领 | 中 | 恢复勋章账户状态与客户端显示链 |
| 8 | Task | 宝箱 boxId 索引基数/季节切换 | 需非空 boxList 实测 | OnBoxReadyStateClick 链 | 不开放领取 | 中 | 实机抓 310 |
| 9 | Battle | CheckFightProfile 续战语义 | 固定 false 兼容 | 447 结构 | 拒绝续战 | 中 | 447/399 样本 |
| 10 | Client | ILRuntime 热更程序集本体 | 未随包（乐变下载链失传） | phase2 全量扫描 | 原生层足够 | 信息级 | 无 |
| 11 | Reward | ~~E_ReportCurrency 折算语义~~ **已实施（2026-09-26）**：结算折算为账户货币（EffData=[桶,单件值]×num；桶→账户 Item 为官方表派生映射，68/68 全覆盖），原物不入包/不入rewardItem（实机金币本空白贴图根因）；金币本手打 MopReward 兼容金同步删除。**残留**：官方折算公式的精确语义（EffData[1]×num 为 Revival 解释）无官方样本 | 官方 item/language 表全量 + 实机 2130104 的 887/152 对账 + 修复后实机待复核 | 折算已实施（USER_DECISION，equip_report_currency_conversion.md） | 低 | 实机复核金币本结算无空白项、金额一致 |
| 14 | College | 590/591 官方初始配方/生产槽/元素，622/623 初始遗迹列表及开放条件，728 BuildingOpen 缺失；559/561/617 注册与推送顺序 | native handler 确认消费与空列表循环安全，但不能证明原服初始内容；无原服线包 | `analysis/white_night_planet/phase0_response_audit.md` | 仅持久化官方建筑初始快照；590/622 保留未完成，不返回猜测的成功态 | 高（白夜行星主入口） | 捕获一次原服或可信客户端启动报文，并追下游 UI consumer |

