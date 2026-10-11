# PR19–24 整合与第七章试用角色

## 合并与本地进度保护

GitHub 已通过 merge commit 合并 #24、#23、#21、#19，保留原贡献者提交。
#20 与 #23 在 EconomyService 的初始化和 handlers 发生冲突，现两边服务均保留，生成本地合并提交 7831102。用户授权后已推送该合并提交，GitHub 确认 #20 closed / merged，贡献者提交历史保留；本地开发修改不包括在该提交中。

本地原有跟踪文件修改和全部 10608 个未跟踪文件保存于 stash 2be8dce8fa3c18cef95a90587f34a30450512a06；恢复后检查所有未跟踪文件均存在。stash 保留供恢复。通讯冲突保留初始好感等级修复及本地日期、通关、选项触发与自动对话链修复。服务器冲突同时保留占卜和八活动 runtime 注册。没有合入 #22，不迁移或替换现有炼金存储。

## 后续修复

- 活动福利入口补发 BaseInfo.SignInStartTime（字段26，int64）为真实创号时间。RookieSignModule.CheckTimeEnble(0x1673ec8)在该值为零时置functionEnable=false，Show(0x16744f0)弹13101015「暂未解锁」；ActivityModule.Show(0x132d904)又因OutDate未置位优先调用七日签到，导致整个福利入口被挡。原表GameActivity[999999]期限14天，超期账号由客户端自动转星相屋，不重开期限或重置奖励。测试账号1创号已18天。需完全重登更新登录快照后手动验收。

- 炼金成交任务计数使用当笔交易发奖 UUID，防止同一槽位、同一委托再次交易时漏计；原 College receipt 保护网络重放。
- 基地完成派遣按 job_id 记录 E_HeroAdventure，重复领取不重复计数。
- 星相屋年度变化清除旧签到掩码，发奖 source 包含年份，防止次年同日奖励被旧去重记录吞掉。
- 元素合成响应和计数在同一事务保存 receipt；只选择当前会话的未结算战斗，按原生 MaxComposeNum 的 ComposeRoundLimit 限制单次合成数量。
- #23 原有免费开放首充、特别课程和积分满进度规则随用户指定 PR 引入，本次没有另行改变其奖励数值；降临纪念仍沿用 PR 的账号创建后经过天数口径。

## 云中电玩城第七章（试用独立身份续修）

实际关卡为2110606 / Chapter2010700 / Map2210606，客户端选择TrialHeroID1307。常驻UnitID1007仅用于角色展示及神权原型定位，不能作为试用战斗属性与技能来源。此前把试用角色映射到常驻角色，属于服务器实现错误；关于补回常驻大招取消技能10076即可修复此关的判断撤回。

原生ChapterModule.ConvertSingleFightHeroData(0x16c2b4c)将服务器FightHero.id传给战斗结构；UnitManager.CreatePlayerByInfo(0x1c4d6b0)按该身份查UnitBase，Property.AddBaseProperty(0x1c21434)按该身份查PlayerAttrib。APK同时保留UnitBase[1307]、PlayerAttrib[1307]，必须读取试用行。

PlayerAttrib[1307]的Damage=1090、DamageCOR=15，而常驻[1007]为64和24。当前固定50级/成长阶段15下，试用裸攻击应为14803，此前错用常驻行下发892。试用防御611、生命6480、神力3000；神权和兽主加成仍单独下发，不能把裸攻击比当作最终技能伤害倍数。

试用UnitBase[1307].SKill=[10070,10071,13072,10073,10075]，ActionFileID=1307。试用技能13072的操作与施法距离均1200，常驻10072为600；试用技能没有常驻SkillUpID。现在下发原生试用技能序列，按SkillLevel对应项取5级，不将常驻10076补入试用向量。

已恢复全部20个TrialHeroID对应的独立PlayerAttrib及UnitBase技能，metadata保留原APK表出处，导出工具为tools/analysis/export_trial_combat.py。试用请求使用TrialHeroID，兼容收到常驻ID的请求时归一化响应为该关TrialHeroID。普通角色1007的属性仍来自原常驻表；账户培养、背包及存档不修改。神权1507四星15级、皮肤1220701、官方六件兽主及无宝石配置保持原表值。

此前贝黑莫斯2110707实属Chapter2010800，该定位已纠正。试用宝石遗漏修复保留，例如1303的1251056；技能来源同样改为试用1303的五技能序列。

## 验证范围

回归在独立测试库运行，覆盖新 PR 链路、通讯、炼金、派遣、八活动及全部主线关卡入口。游戏内验收留给用户。本地实际存档 runtime/phase14/player.sqlite3 不覆盖，重启前使用 SQLite backup 并验证 quick_check。

最终整合回归 111 passed；最后调整后的七项专门检查另跑 7 passed。本地服务端已重启，三个端口正常。存档备份 runtime/before_activity_ui_followup_20261011_133738.sqlite3；启动日志 runtime/activity_ui_followup_20261011_133738.err.log。

用户纠正角色后，忒提丝两种选人请求及试用回归共12 passed（18.15秒）。2026-10-11 13:52重启本地服务，备份 runtime/before_activity_ui_followup_20261011_135244.sqlite3，日志 runtime/activity_ui_followup_20261011_135244.err.log。远程只推送已授权的7831102合并提交，本地开发修改仍保留。

独立试用身份续修：最终试用及整合回归12 passed；主线入口/战斗其他检查通过21项。2026-10-11 15:39重启服务，备份runtime/before_activity_ui_followup_20261011_153934.sqlite3。已入场战斗保留原响应；实机复测应退出旧战斗再进入。未与用户未提供的官方视频逐帧对比。

## 忒提丝普攻距离续修

用户反馈试用普攻距离比实录短。已解码原APK action/action_1307 与全局 action/attackdef：试用W00001/W00100/W00101引用130700000/130700001/130700002，弹道Path终点Z=1600；常驻动作引用100700000等，终点Z=800。试用碰撞框Length/Width=50、常驻=100，不能将弹道距离等同于横向命中宽度。

进一步确认皮肤覆盖链：ConvertSingleFightHeroData(0x16c2b4c)读取Appearance[1220701].UnitBaseID=1007到FightHero.skinUnitID；CreatePlayerByInfo将其保存到Unit.SkinUnitID(+0x540)；ActionStatus.ChangeActionGroup(0x1985b84附近)优先查SkinUnitID的UnitBase.ActionFileID，只有为零才使用试用单位自身ActionFileID1307。因此此前即使FightHero.id1307、试用属性和技能正确，battleSkinId1220701仍将普攻动作覆盖成常驻1007。

现在试用皮肤只有在Appearance.UnitBaseID与TrialHeroID一致时才下发，否则battleSkinId显式0，使用试用自身动作；普通角色皮肤处理保留。Appearance映射由原表导出，metadata随trial_units.json保存。原APK与ActivityUI-Local签名APK的action_1307、attackdef两个资源SHA256分别一致，无需重新打包客户端。12项试用及整合回归通过，游戏内实际距离由用户复测，重入关卡方可使用新入场配置。
