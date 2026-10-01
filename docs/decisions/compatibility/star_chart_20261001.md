# 星图恢复（2.4 客户端，2026-10-01）

## 已核实客户端契约

- `StarChartModule.UpdateAbilityData` RVA `0x1720018` 从 PlayerData.StarMap.StarAbility 初始化能力；`UpdateSkillData` `0x1720358` 读取 StarSkill。服务器过去均未发送。
- PlayerDataProto 第8字段 StarMap：StarAbility=1、StarSkill=2（ContainerIntIntProto），AIPoint=3。DailyProto 第18字段 AddAIPointCount；BaseInfoProto 第44字段 AIPointAutoAdd。
- 升级请求 413/414：skillID=1、targetLevel=2（回包 code=1、skillID=2、targetLevel=3）。客户端 `UpSkillLevel` `0x1721a48` 按当前等级下标读取消耗，并请求当前等级+1。
- 661/662 自动充能开关，663/664 充能请求；成功回调读取已同步的 NetSyncData，因此先推送状态、背包变化再发送响应。
- `StarChartsBase` 仅5种 OpenType=1 的能力开放。UnlockDescID 文案要求完成章节1..5，对应 ChapterInfo.StageID 的最后一幕（ChapterNumber 包含序章）。直接依据现有 economy_clears 推导，无人工修改存档。
- 15项有效技能；392001、392004 不在开放能力 SkillID 中，不可购买。17项原始技能完整保留在导出数据中。
- `BattleX2.InitBattle` `0x14ce23c` 读取效果6（伙伴伤害）、7（伙伴被动）、5（换人冷却）；参数由客户端本地表和服务器技能等级共同决定，无需把星图增益重复加到基础攻击。
- `StarChartAddPower.UpdateInfo` `0x171a358`：394001/效果11 是每日充能次数3/5/7/10；394002/效果12 是价格减免0/2/6/10；394003/效果13 是每次充能100/120/135/150；394004/效果14 是容量150/200/250/300。价格来自 StarDefultConsume 的10项阶梯，最低为0。394005 控制自动充能开关；连续战斗客户端按开关自行调用663。
- 星图空间：391001 的 Param1/2 为训练章节及4个场景等级；进度允许对应或更低等级训练，未解锁不得进入。训练可退出、可结算，没有背包奖励、经验、主线通关、DP或击杀任务累计。训练掉落预算为0；回显的临时拾取不进入正式背包。

## 持久化与兼容边界

技能、AI点数、自动充能开关、当天次数保存于 snapshot.star_chart；每日次数按项目北京时间日历重置。升级/充能的扣费、保存和回执在同一事务中完成。相同 session/request/body 的重试不再次扣费，升级不接受跳级或重复等级。

AI战斗费用使用 SectionTable.ContinueFightConsume。原官方服务器的扣费时点无法从静态客户端完整证明；Revival 在请求 useAIPoint 时入场扣费，若首次在战斗中启用则在签名结算时扣费，二者通过战斗回执防重复。已使用的AI不因失败退还。未开启AI的正常战斗不收费。默认免费自动战斗（训练）仍免费。

保留当前 battle receipt / 887 入口、RewardGrant、outsideItems 校验和所有兽主/神器增益实现。活动入口继续关闭。未给账号补发技能点、AI币或人工解锁能力。

导出脚本：`tools/analysis/export_star_chart.py`；运行时仅依赖随仓库的静态 JSON，不依赖 APK、Windows路径或反编译文件。临时数据库测试覆盖解锁、升级费用/回滚/满级、重试、重登、AI容量/次数/跨日/减免、训练和战斗回执。客户端实机界面及效果仍需验收。
