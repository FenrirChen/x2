---
Document-Type: Current Knowledge
Domain: Coverage
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - (none)
Evidence-IDs: see evidence/manifests/evidence_manifest.json
---

# Known Unknowns（截至 2026-09-25 仍未解）

| # | Domain | Unknown | Why unknown | Evidence searched | 当前处理 | 阻塞 | 下一步 |
|---|---|---|---|---|---|---|---|
| 1 | Drop | DropValueID→掉落内容运行时映射 | 341 值全静态域零命中；第三方同结论；官方服务器数据失传 | 249 表全字段索引+二进制扫描+dump.cs xref+第三方 workbook | 未解账本，不生成 | 高（真实随机掉落） | 无静态路；只有官方报文样本可解 |
| 2 | Drop | ~~264/266 dropValues 准确语义~~ **消费端已解（2026-09-25）**：`BattleInfo.dropValues` = 按 AddADCGroup 的掉落价值预算表（`JudgeDropItem` 0x1E49C94：装备掉落扣 `EquibStage[quality].EquibValue×ItemValue/1000×num`，超组预算拒绝掉落；BattleInfo ctor 置空表 0x19A1C9C）。**残留**：该预算表的填充方（战斗入口/服务器 264/266 下发值？）仍未在客户端定位 | JudgeDropItem/SetCurItemValueTotal/SetStrengthInfo 反汇编 + InitDropValueList + BattleInfo ctor 全量 xref 扫描 | 兼容实现可保守跳过预算校验或设保守上限 | 中 | 实机抓战斗入口报文核对 dropValues 数值来源 |
| 3 | Equipment | ~~初始副词条数量公式~~ **已解决（2026-09-25 升级）**：条数 = 所选 EquibAttribBD 行 MinorAttrNum（A，GM opt=15 证据）；合法范围 = EquibStage.MinorListMin..MinorListMax（A，客户端强化门强制 Max）；掉落星级 = 客户端 IdentifyItem 掷骰（DropBase 6/5/4 + Cv/MF/level 公式，A）经 DroopLimit3 带收敛，outsideItems.quality 直接携带（Star=quality，A）。**官方选行概率未知，但 Revival 已采用 65/35 兼容策略**（base/Min 档 65% / Max 档 35%，仅 4/5/6★；REVIVAL_COMPATIBILITY/USER_DECISION，见 decisions/compatibility/equip_attribbd_tier_selection.md）。**剩余未知仅**：(a) 官方 AttribBD 选行概率（客户端不可见；Revival 已定 65/35）；(b) 随机件数值 3 档取档——官方映射仍未知（ChanceSec 客户端零消费），但 Revival 已采用逐段升级链兼容策略（ValueSec[0] 起步，ChanceSec[0]%→tier1，再 ChanceSec[1]%→tier2；主 [60,40]→40/36/24、副 [80,20]→20/64/16；适用于 src0 主初始/src2 副初始/src3 强化增量；REVIVAL_COMPATIBILITY/USER_DECISION，见 decisions/compatibility/equip_valuesec_tier_roll.md） | IdentifyItem/JudgeDropItem/GMMainPage.GetEquip/CheckSubAttruib/GetAttrNum 反汇编（A）+ item/dropprop/dropbase/sectiontable/equibattribbd/equibstage 全量静态验证 | Star=quality 直采；条数=所选档行 MinorAttrNum（65/35 兼容）；数值按 EquibAttrib 阶梯 + 逐段升级链取档（REVIVAL_COMPAT，已决策） | 低（规则已恢复） | 实机掉落样本核对 quality=Star 与初始条数分布（校准 65/35） |
| 4 | Gift | E_RandomInterval/E_Pick/E_BlindBox 语义 | 解析器 Num 维度未展开；交互 UI 未逆向 | GetItemByGiftGroup/GetItemNumByGiftGroup | 拒绝执行 | 低 | 定点 disasm GetItemNumByGiftGroup |
| 5 | Special | WeeklyDungeon 里程碑触发 | 无独立协议枚举项 | protocol_catalog | 不并入 VReward | 低 | 等热更 DLL 或实机样本 |
| 6 | Special | 宝箱开启 C2L（E_Chest 物品使用通道） | Send 泛型清单无独立出现 | PROTOCOL_CATALOG | 只登记数据源 | 中 | 物品使用通道逆向（ItemOpt/热更） |
| 7 | Shop | GoodsID→ItemID/Num、库存/限购/刷新执行、随机店抽取 | 客户端无映射（17 条 QuickBuy 反查除外）；原服数据失传 | reference_graph+第三方互证 | 固定拒绝 | 高 | 历史非空 L2C_ShopGoods 样本 |
| 8 | Task | 宝箱 boxId 索引基数/季节切换 | 需非空 boxList 实测 | OnBoxReadyStateClick 链 | 不开放领取 | 中 | 实机抓 310 |
| 9 | Battle | CheckFightProfile 续战语义 | 固定 false 兼容 | 447 结构 | 拒绝续战 | 中 | 447/399 样本 |
| 10 | Client | ILRuntime 热更程序集本体 | 未随包（乐变下载链失传） | phase2 全量扫描 | 原生层足够 | 信息级 | 无 |
