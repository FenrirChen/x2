# 入场神迹配置链路修复

## 实机日志与客户端证据

`runtime/restart_20260930_223816.err.log` 中 22:40:54、22:40:59、
22:44:56 的 C2L_DoUnEquip 均返回 13；原代码拒绝客户端一键卸装的 -1。
22:44:22 的关卡 2133102 入场成功，但服务端缺失神迹请求及回包字段。

原版 ARM64 序列化确认：

- C2L_FightData.Serialize 0x366a030：selectedRelicList 在对象 +0x40，
  重复 int32 字段 10，tag 0x50。
- L2C_FightData.Serialize 0x34fa2b4：selectedRelicList 在对象 +0x48，
  重复 int32 字段 9，tag 0x48。
- FightDataProfile.Serialize 0x351177c：relicList 字段 9。
- ChapterModule.Convert_L2CFightData_To_LogicFightData 0x16c0d3c：
  0x16c0fe0/0x16c0fe4 将回包 +0x48 复制至运行时 FightData.relic。
  单纯显示已佩戴、或只修改 CommandX2.FightData.data 均不足以生效。

## 行为

按请求顺序回传选择的神迹，同时填写 profile.relicList。神迹必须已在
inventory 中且 quantity>0、属于客户端 ItemType=4；重复及非法选择拒绝。
校验失败不扣体力、不结束已有战斗、不创建新回执。选择不会消耗或发放神迹。
空选择保持空配置，不自动佩戴全部收藏。入场日志记录 selectedRelicList。

客户端 MiracleChooseModule.InitData 0x1431668 加载全局固定神迹列表。
APK ResourceManager table/globalparamstring 的 StarDefultRelic 原值是
1004943|1004944|1004945|1004946|1004947|1004948。
原始资产与 SHA256 在 analysis/relic_client/raw/manifest.json，提取数据存入
data/battle_relic_defaults.json。这些客户端固定神迹允许回传，不要求普通
库存，也不因此写入库存；仅客户端实际请求时发送，不强制开启固定神迹。

入场回包通过现有 battle_entries.response 持久化。相同请求复用 UUID、
神迹列表和回包，不重复扣体力。继续沿用现有 887/outsideItems 结算。
