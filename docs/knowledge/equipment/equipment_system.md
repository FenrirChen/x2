---
Document-Type: Current Knowledge
Domain: Equipment
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - 本文件早前版本（"Star roll"、"初始词条公式未证实"、"quality 与星级无关"表述已废弃）
Evidence-IDs: see evidence/manifests/evidence_manifest.json
---

# 兽主（Equib/Equipment）系统

**OFFICIAL_STRUCTURE（A）**：`HeroEquip{Id, TypeId=1240xxx, Level, Exp, Star,
Param=EquipParam{At1/Av1=主属性, At2..6/Av2..6=副词条×5, Lock1..6}, LockState, TimeSec, SeasonId}`；
实例整只由服务器经 `RewardData.rewardEquip` 下发（152/1028/邮件），后续 L2C_EquipUpdate(536)，
全量 L2C_EquipAll(555)。客户端零生成、零随机。

**掉落→实例（实机已通 2026-09-26）**：战斗 ADC 掉落（Section.DroopLimit=id 白名单、
DroopLimit2=AddADCGroup 白名单、DroopLimit3=[min,max] 星级带）→ 客户端 IdentifyItem 掷星
（DropBase 档公式，带收敛）→ outsideItems{id,num,quality=★} → 服务器 EquipmentInstanceFactory
（Star=quality；条数档 65/35；ValueSec 逐段链）→ equipment_instances 落库 →
152.rewardEquip + L2C_EquipUpdate(536)。**关键前置**：264/266 dropValues 预算下发
（缺失=客户端掉落全灭），详见 [equipment_drop_pipeline.md](equipment_drop_pipeline.md)。
eNum 仅迷宫物品填写，outside 恒 0。星级判定链与概率公式见
[equipment_star_quality_semantics.md](equipment_star_quality_semantics.md)（A）。

**星级编码（A，全量验证）**：部位级 TypeId(1240|SS|P) **末位=部位、无星级维度**；
1245|SS|S 族（20 套装×6 星，末位=星级，品质白→红对应）是套装级展示/图鉴物品
（无部位、无 EquibBase 行），**不能作为实例 TypeId**。详见
[equipment_id_star_mapping.md](equipment_id_star_mapping.md)。

**初始副词条数（A/选行 REVIVAL_COMPAT）**：条数 = 官方工厂所选 EquibAttribBD 行的 MinorAttrNum；
合法范围 = [EquibStage.MinorListMin, MinorListMax]（1/2/3/[3,4]/[4,5]/[4,5]，客户端强化门强制
Max 上限）。MinorListMin 客户端 0 读者；官方掉落路径选行概率未知——**Revival 兼容策略：
base/Min 档 65% / Max 档 35%（仅 4/5/6★ 两档星级；1-3★ 固定唯一档），
REVIVAL_COMPATIBILITY/USER_DECISION，非官方概率**。强化事件（EquibExp.IsEvent=1 的 +3/6/9/12/15）
未满上限才新增一条；`GetAttrNum` = Av2..Av6 非零计数。详见
[equipment_initial_affix_semantics.md](equipment_initial_affix_semantics.md)。

**初始数值（A，2026-09-25 第二轮）**：类型=EquibBase 池（主属性单候选固定）；数值宇宙=
EquibAttrib[star, src, type] 3 档阶梯（src0 主基础/src1 主成长/src2 副基础/src3 副增量，
384 行已恢复）；EquibAttribBD=固定发放盘（base 行全零值，仅决定条数）。取档算法官方未知——
Revival 已采用逐段升级链兼容策略（REVIVAL_COMPAT/USER_DECISION，见
decisions/compatibility/equip_valuesec_tier_roll.md）。
详见 [equipment_initial_value_semantics.md](equipment_initial_value_semantics.md)。

**UNKNOWN_OFFICIAL（已收窄）**：掉落星级带内分布公式已恢复（IdentifyItem，A）；
仅剩官方选行概率、官方数值取档映射（Revival 已定 65/35 + 逐段升级链两决策）、
BattleInfo.dropValues 填充方。
**REVIVAL_COMPATIBILITY**：选行 65/35 策略（base/Min 档 65% / Max 档 35%，仅 4/5/6★；
USER_DECISION 2026-09-25，见 decisions/compatibility/equip_attribbd_tier_selection.md）
与"无星级载体场景的 Star 选择"为 Revival 自定，须标注，不得写成官方。

成本/曲线细节见 [progression_system.md](../progression/progression_system.md)；
生成链详情：[equipment_instance_generation.md](equipment_instance_generation.md)；
星级/quality 语义：[equipment_star_quality_semantics.md](equipment_star_quality_semantics.md)；
实例修复方案：[equipment_server_fix_plan.md](equipment_server_fix_plan.md)。
