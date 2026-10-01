# 抽卡组合支付与线上皮肤诊断

## 已确认并修复

玩家线上日志 2026-10-01 08:55:01 的 303/C2L_LuckDraw 返回 13，
补充操作说明确认在许愿币与光能组合支付后发生。
旧实现逐种检查是否足够支付整次十连，没有组合扣款。

客户端 LuckDrawModule.CheckCanDrawCard（ARM64 0x1a7e0dc）依次检查
DrawParam.ItemConsum（+0x20）、Currency（+0x28）、CurrencyThird（+0x30）。
0x1a7e3d0、0x1a7e634 用余额整除单次单价，取剩余次数的最小值；
0x1a7e548、0x1a7e7a0、0x1a7e9d0 减去已覆盖次数。

服务端现按同一顺序计划支付：许愿币/对应券 → 光能 → 水晶。
单价取现有客户端导出的 wish_catalog，宝石池光能单价 0 不参与。
全部次数足够后才扣款，并与奖品、计数、回执处于同一 SQLite 事务。
剩余不足一次的零头不扣；总资源不足不扣任何一项。保底、概率、卡池开放
与新手十次上限规则保持原有实现。

查询卡池前同步 PlayerDataProto 和完整 ItemAll。失败和回执重放同样同步
当前余额；失败额外刷新卡池目录。成功在抽卡结果后同步余额、ItemUpdate、
ItemRemove 和完整 ItemAll，避免客户端缓存中遗留已消费的物品。
BagModule.OnRefreshAllItemData（0x19bb5cc）先 Clear 再重建物品缓存，
完整 ItemAll 可清除当前数据库不存在的旧堆叠。
拒绝日志包含卡池、drawType、原因、余额、单价及缺少次数；成功日志记录
各资源实际扣款。不把仅有 code=13 的日志等同于必然余额不足。

## 皮肤状态

本地存档穿戴表和最近入场回包均有 hero=1028、battleSkinId=1222804。
测试也确认 type=1 战斗皮肤在保存、重启后通过 FightHero 字段 10 入场，
初次测试将 type=3 误认为仅外观；该假设已在随后客户端反汇编核对中纠正，
正确类型为 1=局内、2=局外、3=同步，详见 skin_apply_types_20261001.md。
客户端 ConvertSingleFightHeroData
（0x16c2b4c）复制 battleSkinId 后经 AppearanceManager 获取模型 UnitID。

用户补充日志只有按钮点击和 264 掉落查询，不能证明线上换肤保存或入场字段。
本轮未更改皮肤权限、入场皮肤 ID 或擅自从外观槽位回填战斗皮肤。
新增 skin wear saved/denied、battle hero battleSkinId、active database 日志。
tools/diagnose_wish_skin.py 以 SQLite mode=ro 读取实际 DB 路径、代码提交、
抽卡余额、穿戴表和最近五次持久化入场回包，不初始化服务或迁移数据库。
随后线上诊断已证只有 type=3，且战斗回包 ID=0，现已定位并修正类型映射。

## 验证

25 项抽卡、组合支付及外观测试通过；最新完整背包同步再次通过 8 项定向
测试。包含三种资源组合、优先顺序、零头、余额不足全量不扣、回执重放、
查询时余额同步，以及皮肤穿戴保存重启后入场。未操作线上存档。
