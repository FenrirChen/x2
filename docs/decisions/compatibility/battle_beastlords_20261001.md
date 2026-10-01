# 兽主战斗入场修复

## 证据

2026-10-01 11:02:55 玩家 1 进入 2110152，随后 11:03:09 失败结算。
入场回执 9da15ec4-824b-411c-996d-8ce318c02165 的神格 1028 没有
heroEquip/equipSuitAttr，尽管账号中该神格穿戴六件兽主。

原生 FightHero 序列化 0x35102b8：字段6为 heroEquip、字段11为
equipSuitAttr；EquipSuitAttr.Serialize 0x350a66c 为 suitId/suitNum/
attribType1/value1/passiveID，字段1..5。
ChapterModule.ConvertSingleFightHeroData 调用 ConvertHeroEquip 0x16c31ac
与 ConvertEquipSuitAttr 0x16c38fc。
LogicX2.Property.AddEqtsAttributes 0x1c17668 会逐条累加兽主的六组词条，
然后累加服务器提供的套装属性，并将套装被动加入玩家 passiveSpellIds。
它不再校验两件阈值，所以服务器必须只发送已满足两件的套装属性。
Player.InitEquipAndSectionPassiveSpell 0x1c15074 以四件判断套装效果。
ClientProperty.AddEqtsAttributes 0x1491674 两件时直接使用 EquibSuit.Value1，
无需乘10或100；例如奇美拉套装108/300为30%生命。

## 实现

读取玩家穿戴的普通兽主实例，按持久化 param 原值发送 HeroEquip，包括
强化后的主副属性。只统计该神格的不同部位；检查实例归属、部位、重复实例。
两件发送原生 EquibSuit 属性，四件发送该套装全部 PassiveID；六件只触发
一次两件/四件效果。配置导出自客户端 EquibSuit。
heroAttrCount 与 attrAdd 继续为基础神格数据，由客户端原生属性系统累加
兽主和套装；不在服务器重复加成。不修改装备参数、奖励结算或 active DB。
入场回执固定本次装备快照，同请求重放不会读取后续换装数据。
赛季兽主尚未实现，保留此前一键卸装同时清理普通/赛季穿戴的行为。

测试使用临时数据库，覆盖强化词条保真、0/1/2/3/4/6件阈值、归属/部位/
重复验证、实际入场字段和重放快照；客户端视觉与伤害表现待实机验收。
