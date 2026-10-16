## 2026-10-13 兽主洗练闭环与第七章试用补偿（最新）

1055–1058 已实现增加/随机删除副词条、锁定、等级重置与数值预览保存。按客户端费用表、708星级和等级效果扣料，重复请求不重复扣费；预览、强化历史及存档跨账号迁移已处理。仅2110607试用1303通过兽主平攻词条将攻击小计提升至原来的10倍，不改APK、账号装备或其他试用。详见 [college_washing_20261013.md](college_washing_20261013.md)。

---
Document-Type: Current Knowledge
Domain: College/GrowthBase
Status: entry/query chain connected; ordinary building progression implemented
Updated: 2026-10-02
Evidence: official 2.4 decoded tables (rows, not just schemas); dump.cs/script.json/libil2cpp.so; analysis/white_night_planet/*
---

# 白夜行星

## 2026-10-10 炼金解锁门槛纠正

炼金 CollegeRecipe（360xx）的解锁只依据前置配方制作经验与 RecipeEffect=3。此前误用707熔炉的 StarEffectType10（GetFurnaceRecipeLevel，用于292xx熔炉配方）限制炼金 RecipeLevel，导致初始熔炉一星时制作经验达标仍无法解锁二级配方。原生 CollegeAlchemyModule.RefreshRecipeMaxUnlock(0x189caa4)依据非负配方经验计算已解锁级别，没有熔炉星级条件。

现查询下发全部炼金配方，未解锁经验=-1；已达标存档按解锁链补齐经验0，保留已积累经验。制造仍校验配方已解锁、真实材料和空闲队列。一件产物一点经验的既定规则不变。

## 2026-10-10 祈神提示残留与顾客操作闭环

- 祈神领取/取消后，584给八座奇迹各自的空闲PrayQueue，而非仅buildingId=0哨兵。原生Civilization.Refresh(0x1db5e64–0x1db5f38)只替换匹配buildingId的缓存；缺行会保留status=2的旧对象，造成红点及领取提示残留。持久化任务仍只保存实际进行/待领取项目；其他建筑的任务不清除。
- 加价、折扣走598/599真实交易：AlchemyPriceNum=2000、AlchemyDiscountNum=500均按千分比，即售价×2或×0.5（向下取整）。熟练度售价加成仍保留；不能同时选择两者。加价星能为ceil(CollegeRecipe.Gold/5000×15)，折扣好感为ceil(Gold/(2500×2)×5)，输入是官方基础Gold，不是加成后的售价。参数来源为原APK GlobalParamString；GetAddPriceStarEnergy(0x18a1cf4)、GetDiscountFavory(0x18a1e40)和Refresh(0x1bac83c)核对float32运算与向上取整。
- 建议600/601 type=1按推荐配方的基础Gold扣ceil(Gold/10000×2)星能，更新该位置求购商品/数量并持久化；593/591及重登同源，后续上交只扣新商品。601原生回调先用旧adviseItemId替换itemId[0]，再将result安装为新的adviseItemId，因此591必须在601之后发送。建议后保留原商品为下一建议（同一偏好元素内两种官方产物切换，Revival兼容选择），不发0图标或伪造好感奖励。建议本身不销售；折扣成交才提升已有神格好感。
- 折扣好感沿用FavorService等级/突破门槛，发送PlayerDataProto、HeroUpdate和FavorChangeInfo(type=13 AlchemyDiscount)。材料不足、星能不足、写库失败时不扣费/不增好感；成功回执、防重复奖励和订单/资源/好感同一事务。type=2闲聊仍未接入，不将建议成功套到闲聊。

邮件及兽主预算审计见[本轮交付记录](../decisions/college_followup_20261010.md)。下方历史“加价/折价继续拒绝”记录作废；普通订单重复成交和顾客更换规则沿用已有兼容决定。

## 2026-10-02 顾客白图、祈神闭环及通讯续修（最新）

- 顾客白图来自协议错位，并非图集缺失。`CommandX2.CustomerInfo.Serialize(0x38f05a8)`：1 questId、2 itemId、3 type、4 adviseItemId、5 param、6 result、7 itemNum。原实现按声明顺序将数量1写入字段3，头顶`CollegeShopMain.CustomerNode.Refresh(0x19636e4)`因type不是TRANSACTION(2)而读取空的E_Sell任务Icon；详情页直接读取itemId仍正常。591与593共享schema已修正；回归以独立原始wire解析验证type及数量，避免同一错误schema自证。
- 祈神369/373开始、367/371道具加速、366/370取消、368/372领取全部接入事务和成功回执。584持久化PrayQueue完整字段，1进行/2完成，514 PrayEnd在线通知只发一次，重登/离线到期保留待领取任务；372 rewardData实际为字段4（原生tag0x22），不是字段3。神格PRAY占用与探索/训练互斥，到期仍占用，取消或领取才释放。
- **官方约束更正**：完整repeated表导出显示成本为金币1237901×3000与祈神符1237840×1，时长28800秒；历史“无金币”结论作废。`ServerData.ctor`、`OnCheckTabOpen`、`RefreshPaiQian`及`RefreshSacrifice`分别确认祈神二星开放、守护者三星开放、献祭四星开放，普通/月卡每日均5次。Language13101058明确北京时间05:00日切；登录和在线日切都同步Daily.PrayCount（字段12）。Language13102257规定献祭一枚神格碎片使收益翻倍；13102273取消返还祈神符，不返还已用加速卡，金币和献祭碎片不返还。
- **兼容收益边界**：沿用已有用户决定的基础碎片×5，添加守护者时给该神格碎片；未添加守护者时从该奇迹源流已开放神格中等概率选择，开始即持久化结果。献祭后×10。随机权重是Revival兼容值，不能宣称恢复官方权重。守护者PrayBouns按客户端千分比作用于成本，官方已开放神格当前均1000。
- 通讯`ReplyContent=[0]`是无选项哨兵（944条），旧代码将非空列表视作需要回复，阻断自动行到下一选项。修复全部表的自动续行、已有已回复进度续接、重登查询持久化修复；三条缺HeroID的原始行按所属主线归属校验，不能改换已完成分支。通关型通讯依据真实economy_clears记录，选项效果型依据历史对应OptionEffectID；日历型已到日期内容保留可读是Revival兼容归档规则，未来日期仍拒绝。伊南娜1019全部八组及全部官方通讯选项边覆盖测试，不跳过真实默契/剧情前置。

验证：基地/通讯/世界BOSS相关126项、登录/战斗/协议21项通过，共147项；全部4034条通讯中的2179个选择边及伊南娜51个选择覆盖，祈神12项含回滚/离线/日切。使用隔离数据库；60级活跃存档在线备份至runtime/before_college_upgrade_20261002_231042_346518.sqlite3，23:11重启本地服务（日志runtime/college_restart_20261002_231119.err.log），三个端口监听正常。客户端视觉及交互仍需重新登录复测。

## 2026-10-02 以太奇迹位面：解锁、升级、加成

- 旧活跃存档只有721–727，缺728；load迁移仅补缺失官方初始行，不修改已有等级/星级/队列/资源。Civilization.Refresh(0x1db5748)按buildingId查找buildInfo，RefreshPage(0x1db3754)直接解引用；八行civilization和wonderQueue均需下发。
- 25级入口；721–727由235 type=2升星0→1解锁，按目标CollegeStarLevel.PreconditionType/Value和Consume/ConsumeNum执行。CheckHeroHelper(0x1979898)：奇数条件1/3/…/13看对应文明已拥有神格数量（初始需2）；偶数2/4/…/14累加PlayerStage.BigStarNum，不能使用HeroData.star内部阶数。已有星级的LimitLevel限制等级及下一星最低等级；728 BuildingOpen缺失，仍拒绝解锁。
- 233 type=2按官方CollegeLevel成本/时长/主建筑或账号等级前置升级；普通/奇迹队列独立，234加速卡真实扣库存。271光辉完成按客户端MainModule.ServerData ctor(0x13cd020)的SpeedUpTimes=5分钟，InitData(0x1973758)乘60；GetFastNeedCurrency(0x1977b40)为max(0,ceil(剩余秒/300)-1)，最后五分钟免费。此前“价格无法恢复/水晶完成拒绝”作废。
- 所有成功操作先推584及真实资产，再成功应答；扣费/状态/成功回执原子保存，重传不重复扣费。完成事件持久化在upgrade_notifications，查询/战斗先结算也不会吞掉507通知；在线watch一次消费。
- 加成沿现有官方battle_bonuses的文明、星级技能列表及AttributeValue[level-1]计算，只作用对应文明。战斗/派遣读取属性前结算到期任务（无schema初始化提交，保留外层事务），不必先打开基地。已验证真实FightData.attrAdd携带新攻击加成，裸成长属性和神器分别计算，避免重复加成。七座奇迹初次解锁门槛逐座测试，缺行迁移保留进度。

验证：相关回归91项通过，补充外层事务回滚/终级等级星级门槛2项通过，共93项。隔离测试库；实机UI需重新登录复测。活跃账号1等级60，各开放文明拥有神格数量均达到初次解锁2名门槛，仍需自行按官方材料成本解锁。

## 2026-10-02 拒绝顾客

客户端CollegeCustomerDetil.OnSendRegist(0x1ba6fec)发送598 type=2；599成功回调OnReceiveAlchemyFinishMsg(0x189ebd8)重新查询592对应位置。服务端现接受合法位置拒绝，忽略随请求携带的价格开关，不扣资源、不发奖励；兼容行为为沿官方顾客表顺序替换该位置，customer_rotations持久化，没有恢复定时器或收费依据，未加入这些规则。事务回滚及成功回执保证重传不重复替换，其他位置保持原顾客。炼金/基地相关测试31项通过（含拒绝、重传、查询、重登及回滚）。

## 2026-10-02 训练/派遣完整链路与结晶补充续修（当前结论）

- 派遣624/625光辉加速按官方GlobalParamString.AlchemyExploreParam=`902|720|1`计费：剩余秒数÷720向上取整，成功只结束计时，保持神格占用直到领取；请求回执防重、余额不足不改结束时间。原生CollegeExploreSpeedUp.OnInit/Tick/SpeedUp确认客户端计算一致。此前“加速计费未知/待兼容决策”作废。
- 派遣Gift761001随机结晶1237991/1237992绕过普通背包奖励目的地，写入基地元素仓库并封顶；其他奖励沿用实际经济系统。测试穷举11个官方奖励分支，避免随机抽到元素时领取失败。
- **更正上一轮派遣状态判断：0锁定、1空闲、2占用。**RefreshItem的status=1分支0x1bb8768显示添加队员；status=2分支0x1bb867c读取遗迹/队员/结束时间。此前空槽发送2进入活动分支，ruinId=0最终触发持续NRE，打断列表布局并造成UI重叠。Unity日志`runtime/college_ui_unity_20261002.log`确认异常位于CollegeExploreItem.RefreshItem→CollegeExploreTab.RefreshExploreNode。
- **训练StartTrain.heroId不是字段2，而是字段4。**原生Serialize 0x3b8e9a4写tag08=trainId、tag20=heroId；原schema按声明顺序写字段2，实机英雄ID被忽略、回13，选择回调立即开始训练后清空暂存，看起来选择失败。已改字段4，并用独立原始字节080020eb07测试1003神格的开始→取消→再开始→到期→领取，不再只做自己schema的编码解码。
- 训练0锁/1空/2进行/3完成保持正确，buildID引用开始时CollegeLevel行；在线到期通过562 TrainingUpdate（trainList字段1，具名handler0x1afb648刷新事件d1）通知完成页面/红点，旧任务和离线任务不清除、不自动领收益。派遣完整覆盖队伍请求、星能/战力/难度、占用、取消、离线重进及实际领取，活动行始终带有效ruinId/非空heroList/真实结束时间。
- **604 AlchemyBuy已实现：type1星能补充/type2光辉补满，typeId为991–996元素键。**原生CollegeRecipeLackBaseMaterial 0x1b18448/0x1b18378；官方GlobalParamString.Element01–06Param均为100|100|3（补100、花100星能、每元素每天3次），Pay均5（缺口÷5向上取整为光辉费用）。706容量封顶，满仓拒绝不扣费，星能次数独立于光辉补满；每日次数沿用现有用户定义Revival北京时间零点日历，不宣称恢复了官方日切。
- 605立即刷新窗口，因此先同步584星能、591元素/次数、经济资产，再返回成功；购买状态、扣费、回执同一事务，重传防重复扣费，异常回滚。再生工具保留Pay/Param原表值。下方历史“派遣2空闲/1占用”“元素购买未实现”已作废。

## 2026-10-02 队列锁定与顾客上交修复（最新，覆盖旧状态说明）

- 客户端训练状态是 **0锁定、1空闲、2训练中、3待领取**，证据 `CollegeTrainingItem.RefreshItem(0x196f730)/RefreshOpen(0x196fa6c)`；派遣是 **0锁定、1空闲、2占用**，到期通过 `exploreEndTime` 判断可领取，证据 `CollegeExploreItem.RefreshItem(0x1bb8334)/TimeTick(0x1bb941c)`。此前发送省略状态的空槽等同0，导致已开放槽仍显示未解锁；此前训练把进行中写1、到期写2也不符合客户端。
- 训练数据buildID引用CollegeLevel行（初始24401），不是建筑704；完成页会调用CollegeLevelManager.GetItem，错误704会产生空引用。旧存档的704引用在下发时兼容修正，新任务保存开始时的等级行。
- 584 按704/705星级生成已开放槽的真实空闲状态，任务存在时由结束时间修正状态，保留旧任务英雄/时长/收益，不清档；额外槽仍需对应建筑升星。训练259/257/258、派遣242/236/239使用持久化任务、英雄占用、星能扣除和领取事务，训练收益于2026-10-16修正为开始任务时CollegeLevel的EffectType2=8/EffectValue2[0]，不再采用旧25%兼容值；尚未领取的旧任务也按保存的buildID修正。
- 实机日志20:43:52确认普通顾客上交598请求 **type=1**，并非CustomerInfo.type=2；`CollegeCustomerDetil.OnSendTransaction(0x1ba6ce0)`同样证实。599成功回复type=1、alchemyType=2、posIndex及真实金币rewardData，之后客户端自动查询593。
- 普通上交按服务器订单校验材料，全部扣料后发放CollegeRecipe.Gold金币，熟练度效果2按`GetRecipeSell(0x18a3858)`的首个千分比加成；不把售价扣为成本。同会话requestId成功回执持久化，重传不重扣/重奖；写库失败同时回滚商品、金币和回执。加价/折价、芯片及特殊顾客规则未恢复，继续拒绝。
- 订单补充采用兼容规则：暂保留同一顾客的同一普通订单，可再次正常支付材料交易；不引入未经确定的日切/恢复周期。已向用户询问是否改为每位顾客每日一次，若用户指定则调整。每次新交易都实际扣料，重传只重放旧结果。
- 前轮已实现596星能/光辉炼金加速：星能按剩余秒数向上除10，光辉按官方Pay与WaitTimes比例向上取整。星能恢复采用MainModule.ServerData ctor的Energy=600秒，按702星级恢复量及等级容量封顶。下文旧“制作/派遣/训练/水晶炼金加速未实现”不再代表当前代码。

## 2026-10-02 加速卡、元素和炼金制作修复（最新，覆盖下文旧结论）

- **881 是本地加速窗口的前置检查，也用于协助，不能全部回 type=3。**原生 `OnGetHelpPowerSpeedVaild(0x1b060e0)` 对 type=1/2 调用窗口回调，对 type=3 只重新查询基地。现在检查相应建造队列后原样应答类型；五种官方道具 1237831–1237835 时长为 600/3600/7200/14400/28800 秒。245.buildStatus=1 表示已完成，0 表示仍建造。
- **701 星级决定生产槽数 3–8，顾客固定 5 位。**证据为 `GetFirstEmptyProductionPosition/GetMainHallNum`、`MAX_CUSTOMER_NUM` 和官方 GlobalParamString.AlchemyCustomerNum。旧“701 星级决定顾客数”结论作废。
- **元素周期可以恢复，不能继续称缺失。**从官方 APK GlobalParamString 重解 Element01–06=1800 秒（特殊容器需跳过 4 字节），706 效果12给六元素各自仓库容量，703 效果16给每周期数量。初始容量各120、产速 `[1,1,1,1,0,0]`。旧 lastRecoverTime=0 被客户端当作自1970年累计，导致超上限；现在保存真实时间戳、保留不足一周期余量、按容量封顶，满仓不积攒溢出，未来/零时间戳不补发几十年产量。已有空状态从存档创建时间开始恢复；升级结束前按旧产速结算，再使用新效果。
- **594/595、602/603、826/827 已实现。**保留 CollegeRecipe 完整 ItemGroup/ItemNum/Exp/效果数组；制作扣元素及其他实际材料，不把 Gold 售价误扣为制作费用；校验生产槽、配方解锁和炉星级，持久化结束时间；到时单个/批量领取实际 ProductID/ProductNum。同 requestId 防重扣，生产唯一标识防重奖，写库失败回滚。领取后推591及资产同步。
- **配方经验每件领取产物增加1点：用户于本轮明确批准的兼容规则。**Exp是官方阈值数组，按原生 GetExpPhase/FindEffectInRecipeLevel 对齐扣料减免、等待缩短和后继配方解锁。707等级消耗/经验效果的原生消费者位于另一套 ComRecipe 合成界面，不能未经证据套进 CollegeRecipe 元素制作。
- 新数据 `college_alchemy_rules.json` 保留官方六元素货币映射、周期、生产/顾客参数和五种加速卡来源；完整60配方进入 `college_upgrade_catalog.json`。再生工具 `export_college_alchemy_rules.py` 和 `export_college_upgrade_catalog.py`。
- 取消制作的返还规则、水晶炼金加速、元素购买、顾客交易等本轮未恢复的操作继续回13；普通制作、完成领取和一键领取已经闭环。

验证：基地/存档管理原39项通过；新增五种加速卡和经验解锁后炼金专项14项通过（累计覆盖45项）。生产测试使用隔离数据库，不修改活跃账号资源。实机界面效果待用户重新登录验证。

## 2026-10-02 升级实现与证据更正（优先于下文旧结论）

上轮 `college_tables/final/*.json` 导出把 repeated int 覆盖成最后一个值，**不能据此断言成本只有材料、无金币，或效果只有单值**。本轮从加密原表重解，保留完整 `LevelID/StarID/Consume/ConsumeNum/EffectValue/StarEffectValue` 列表，结果进入 `src/x2server/data/college_upgrade_catalog.json`，附来源文件和 SHA256；再生工具 `tools/analysis/export_college_upgrade_catalog.py`。

- 701 升至 2 级：金币 1237901×10000 + 1237801×3，等待 600 秒；702–707 升至 2 级：金币×6000 + 材料×3，等待 300 秒；708 消耗装备经验 1237906 和材料。旧“无金币”结论作废。
- `PreconditionType=1` 为账号等级，`=2` 为主建筑 701 等级。当前星级行的 `LimitLevel` 是本星级等级上限，也是升到下一星的最低等级，**不是下一星行的 LimitLevel**。原生证据 `RefreshIsStar(0x1975410)`、`CheckTableLimit(0x1979124)`。
- 正确映射：701 星级=生产槽数 3–8；702 等级=星能/额外体力上限，星级=恢复/转化；703 等级=各元素产速；704 星级=训练槽；705 星级=派遣槽；706 等级=各元素仓库上限；707 星级=配方阶数，等级=ComRecipe制作消耗/额外经验；708=洗炼功能和消耗倍率。效果向量保留全部元素。
- 服务端实现 233/244 升级、235/246 普通建筑升星、234/245 已恢复的官方加速道具（Item.FunctionEff=8/EffData 秒数）。建造普通/奇迹各一队列，持久化绝对结束时间，到时只结算一次，离线后登录/查询补结算；在线每秒检查，先推 584 最新快照，再推 507 刷新事件。244/246/245 成功之前先同步快照和资产，避免 UI 用旧等级。重复同会话 requestId 不重复扣费。
- 基地存取改用 SAVEPOINT，材料/货币/状态/成功回执同一事务；写库异常全部回滚。未升级字段和已有账号保留，不覆盖活跃库。
- 顾客固定5位、生产槽按701星级、训练槽按704星级；591的有效360xx配方按707允许阶数返回，未解锁配方经验=-1。旧StarEffectValue2中292xx ID不属于live CollegeRecipe，不能直接下发给客户端。
- 尚未批准的水晶秒数兑换参数仍回 13；奇迹升星涉及神格文明/数量/星级条件，本次未实现。训练、派遣、制作、祈祷、洗炼业务仍按未实现操作回 13；相关建筑等级效果已进入权威快照及表查询，但这些业务的收益结算不在本轮范围。星能/元素被动产出公式涉及 GlobalParam，本轮不引入未批准参数。

稳定性审计详见 [college_upgrade_audit_20261002.md](../decisions/college_upgrade_audit_20261002.md)。修复上一轮误删的 `QueryWorldBossOpenTime` 全天开放应答；savemanager/账号校验遗留改动未改写。

## Identity

显示名“白夜行星”在官方语言表 Key 1499039 的设施说明中出现；Key 2820171 明言玩家获得进入其**基地**的权限。客户端内部主模块是 `CollegeModule`，数据根名 `GrowthBase`，子模块为 `CollegeUpgradeModule`、`CollegeAlchemyModule`、`CollegeWonderModule`。入口 `FunctionOpen` 21902=`E_Base`（`FunctionOpenEFunctionType`=3，19 级）、21912=`E_Wonder`（FunctionType=14，25 级）。没有可信的“白夜行星 ActivityID”；`activity.json` 的 28001 与 College 键域不连。别名及易混淆文案见 [aliases.md](../../analysis/white_night_planet/aliases.md)。以上为 A 级客户端证据。

**注意：**`EntryidStatus` 的功能键空间是 `FunctionOpenEFunctionType`（E_Base=3、E_Wonder=14、E_HeroBossBattle=19）。Revival 当前 EntryidStatus 下发的 `Key=19,Value=2` 关闭的是英雄 Boss 战，与基地无关。

## Entry / Unlock

**入口使能门（2026-10-02 实机“未开启”问题根因）：**反汇编 `CollegeModule.IsCollegeEnable`（0x1AF9FF8）证实基地按钮启用需同时满足：① `!IsClientFunctionClose(21902)`（客户端开关，21902=FunctionOpen ID）；② `!IsServerFunctionClose(0x11=17)`（服务器关闭集合，来自 EntryidStatus；Revival 只关 19，17 未关，通过）；③ **`PlayerData.ModuleStatus.GrowthBaseStatus == 1`**（`PlayerDataProto` 字段 4=`ModuleStatusProto`，其字段 3=GrowthBaseStatus）。未下发 ModuleStatus 时判定失败——点击入口**不发送任何 579/622/590**，客户端直接提示未开启（2026-10-02 实机日志证据）。Revival 已在登录 `snapshot_push` 下发 `ModuleStatus{GrowthBaseStatus=1}`（REVIVAL_COMPAT，官方值不可恢复；其余 5 个状态字段保持不下发）。注意需**完整登录**（重启客户端）而非断线重连才会刷新 PlayerData。

`CollegeEntry.OnOpen/OnShow` → `CollegeModule.SendQueryGrowthBase` (579/584)；`CollegeMainEntry.OnOpen` → 依次发 `SendUnlockExploreRuin` (622/623) 与 `SendAlchemyMainData` (590/591)（RVA 0x1AF3FA4/0x1AF4024），均不阻塞等待。`MainHallFSM.UpdateLoadModule` 亦按功能开关发 590。19/25 是静态开放等级。**2026-10-02 起三入口查询（579/622/590）均由服务器应答，入口导航已闭环。**

## Static Tables（2026-10-02 起为“行数据级”证据）

官方静态表行数据已从 2.4 APK 重新提取并解码（TextAsset + RSA/XOR 容器，见仓库外 `D:/demo/x2/college_tables/final/`；再生工具：UnityPy + `tools/analysis/_client_table_wire.py`）。行数与 static_catalog 一致：Building 16、Level 555、StarLevel 95、Explore 15、Recipe 60、Quest 120、Customer 42、EquibReset 5、WonderSkill 54。**行数据修正了此前“成本/时间 MISSING”的结论：**

- **建筑/奇迹升级成本与时长是官方静态值**：使用完整 `CollegeLevel.Consume/ConsumeNum/WaitTimes` 列表。普通建筑含金币或装备经验及材料，前置类型1=账号等级、2=主建筑等级；701 二级=600s+10000金币+3×1237801。奇迹二级=3600s+5×1237801。728 BuildingOpen 缺失，维持未开放。
- **星级效果即槽位/解锁表**：701=顾客数、702=恢复/转化、704=训练槽、705=派遣槽、707=配方阶数、708=新功能；详见顶部更正和完整向量 catalog。旧整数列表最后值不能代表全部效果。
- **派遣（CollegeExplore 两个版本共存于 APK）**：live 版=Reward 761001–761015（与 static_catalog/锚点一致）：`Conditon`=**战力门槛** 300–32000（消费者 `GetNeedFightPoint`、ExploreData.fightCapacity）、`PowerConsume` 6–72、`WaitTimes` 3–36h、`Num1/2/3`=三档难度人数 4/6/8、`Exp`=遗迹经验 12–96、效果 3 链=派遣点逐级解锁（34001→34002→…）。900301 版本为同表旧/新修订，Gift 900301–900315 也存在，live 判定需一次实机预览复核。
- **炼金（CollegeRecipe）**：60 行全字段有值。RecipeType=元素类别 991–996（每类 RecipeLevel 1–10）、材料/产物/数量/等待齐全、`Gold` 2400–25920、`Pay` 5–39、逐级 `Exp`。`Pay` 语义仍未知。
- **顾客（CollegeCustomer）**：38 神格（Param=神格ID 1003+，Type=1）+4 NPC（38201–38204，Param 6459/6434/6473/6474，Type=2）。`Like`=**单元素偏好**（992–996 各一，非“两类偏好”）。**`ChatChance/ChatParam` 在所有变体全为 0**——2.4 静态数据没有任何闲聊概率；此前草案记载的五格数值 [400,300,0,300,0] 与 APK 不符，作废。
- **任务（CollegeQuest）**：120 行 = E_Chip 38 + E_Sell 38 + E_SellUp 38 + E_Superbuy/E_PriceBuff/E_MakeBuff 各 1 + E_Gift 3；AwardType：E_Gift 41 / E_Gold 77 / E_Buff 2。E_Chip 行 Hero=神格、Param=顾客ID、AwardGroup=782xxx Gift。
- **洗炼（CollegeEquibReset）**：5 档成本，材料含 **1237805/06/07**（不止 1237801–06）；行内容与 official_economic_anchors.json 记载的三材料结构不同，以 live 变体重核后为准。
- 祈祷官方静态：奇迹 `PrayItem=1237840×1`、`PrayWaitTimes=28800s`（8 小时）——CollegeBuilding 内**无 3000 金币项**，此前“3000 金币+祈神符”的说法作废。

关系图见 [state_machine.md](../../analysis/white_night_planet/state_machine.md)；行数据样例另见仓库外 `D:/demo/x2/college_tables/final/`（建议后续迁入 evidence/derived 并登记 manifest）。

## Client Classes

主要方法、RVA、直接调用见 [client_code_map.md](../../analysis/white_night_planet/client_code_map.md)。**2026-10-02 新增关键结论：**训练/星能/派遣槽等数值由客户端从 `LogicX2.TableMgr.GetIntGlobalParam` 读取（`GetHeroTrainTime`=键7、`GetHeroTrainExp`=键8、`GetHeroMaxNum`=键6、`GetExploreNum`=键1、`GetEnergyRecovery/GetEnergySpeed`=键4、`GetEnergyMaxEnergy/GetPowerConversion`=键5、`GetElementSpeed`=键16），APK 内**没有**数值型 GlobalParam 表资源（TextAsset 全扫描证实），配合 `LoadWebGameConfig`/`OnServerParamaChange` 证明这些参数原架构由**服务器下发**。`GetFastNeedCurrency` 按剩余秒数折算加速费用，单价同样来自服务器参数。

## Protocol

[protocol_matrix.csv](../../analysis/white_night_planet/protocol_matrix.csv) 共 32 条基地请求链（30 REAL_SEND + 2 INDIRECT）。2026-10-02 起请求/响应字段集已从 dump.cs 逐一确认，要点：

- `C2L_ExploreSpeed(624)` **只有 exploreId，无任何消耗字段**——派遣加速的官方计费在服务器（兼容决策）。
- `C2L_StartExplore(242)`=exploreId/diffdifficulty/heroIds(List)/ruinId；`L2C_StartExplore(253)` **只回 code**；客户端成功后清空暂存请求并**本地预测倒计时**（读缓存的请求字段 + 静态 WaitTimes），561 推送非必需，重进 579 校正（反汇编 0x1AFD324，B 级）。
- `L2C_StartTrain(262)` 回 trainTime/trainEndTime/starEnergy/buildId——**训练时长与星能消耗是服务器授权值**；`L2C_FinishTrain(261)` 回 heroLevel/heroExp/gainExp。
- `L2C_WashingRoomRandomAttri(1056)` 回 equipParam（At1–6/Av1–6 + **Lock1–6 锁定标志**）+ washingCountDay；`L2C_WashingRoomOpt(1058)` 另带 rewardData。
- `L2C_SingleCustomerInfo(593)` 带 **transactionNum + transactionLastRecoverTime**——每位顾客有随时间恢复的交易次数上限（兼容草案原未覆盖）。
- `L2C_UnlockExploreRuin(623)`：code=10 + 非空列表替换客户端缓存，null 列表会保留旧值并弹错误；空列表安全。重复请求应返回相同状态。
- `L2C_AlchemyMainData(591)` handler 0x189CC90 循环四个列表：**空构造列表安全，null 列表崩溃**——所有列表字段必须在类型上存在。
- `AlchemyFinish(598)`=type/posIndex/plusPrice(bool)/discountPrice(bool)，两布尔互斥；`AlchemyButtonClick(600)`/`AlchemyBuy(604)`/`MakIngSpeed(596)` 的 type 语义对应 `AlchemyType` 枚举（1 芯片任务/2 交易/3 低价售/4 高价售/5 超购/6 赠礼/7 加速Buff/8 提价Buff）。
- 错误码：客户端 `GameLogicErrCode` 除 E_Ok=10 外有细分（E_MAX_LEVEL=14、E_NO_ITEM=22、E_NO_EQUIP=27、E_LIMIT_GOLD=35、E_NO_ENOUGH_POWER=38 等），服务器应使用细分码，不再一律回 13。
- Push：562/507/695/514 有具名 handler（A）；559/561/617 无具名 handler（dump.cs 全文无 OnReceiveBuildingUpdateMsg 等），注册与消费者 UNKNOWN——在“响应只回结果码 + 重进全量”模式下均非必需。

## State Machine

真实模型是建筑、派遣、训练、炼金、祈祷、洗炼的**并行队列和账户状态**（图见 [state_machine.md](../../analysis/white_night_planet/state_machine.md)）。wire 类型证实建造队列=1 普通+1 奇迹（BuildQueue/WonderQueue 为单体对象）。英雄占用四态 `HeroStatus`：IDLE/PRAY/EXPLORE/TRAIN。`L2C_Login.growthBase` 与 579/584 共享结构；`CurWonderIndex`/最近配方是客户端 UI 偏好。

## Battle Flow

没有 College 子模块到 `FightData(126)`/`CheckoutMainMissionSign(887)` 的调用边。派遣是计时事务；主线“白夜大厅”“白夜崩解”是同名故事关卡，不属于基地。

## Reward Flow

派遣奖励指 Gift 组 761001–761015（live 版本），由 `L2C_FinishExplore.rewardData` 交付；`ruinId/exp` 是遗迹进度线。炼金 603/599/827、祈祷 372 均含 rewardData。静态 Gift 决定候选内容；官方随机/倍率/收费公式仍是 SERVER_ONLY_UNKNOWN。顾客订单带交易次数上限与恢复时间（见 Protocol）。`plusPrice/discountPrice` 是请求表达值，服务器必须独立计价。

## Persistence

服务端需持久化：建筑/奇迹等级与星级、星能与金币仓库及结算时点、额外体力、遗迹解锁/经验、派遣/训练/建造/祈祷/炼金的槽位及结束时间、英雄占用、顾客订单与交易次数、配方经验、洗炼日次数、奖励领取凭证。`college_state` 表（`src/x2server/player/college.py`）当前承载：buildings/wonders/star_energy/warehouse_gold/extra_power/gold_gain_time/star_gain_time/washing_count_day/explore/training/pray/ruins/alchemy。

## Reset / Season

周期边界只有计时队列和 `washingCountDay`；日切时区仍为 SERVER_ONLY_UNKNOWN（兼容决策维持 UTC+8 00:00 候选）。没有基地专属赛季/排行榜协议正证据。

## Server Dependencies / Coverage

`server_gap_matrix.csv` 为 2026-09-27 快照（COMPLETE 0 / PARTIAL 1 / STUB 1 / MISSING 30）。**2026-10-02 起：622/623、590/591 升级为 PARTIAL（幂等查询闭环，返回持久化初始状态）**；579/584 PARTIAL 不变。入口导航已闭环：CollegeEntry（579）、CollegeMainEntry（622→590）全部有应答，不再弹错误码气泡。623/591 的初始空状态（遗迹未解锁、炼金无配方经验/顾客/元素）是 **REVIVAL_COMPAT 初始态决定**（客户端侧安全已由 native 审计证实），待实机复测；正式玩法变更（升级/派遣/炼金/祈祷/洗炼）仍未实现。

## Official Unknowns

1. 7 个服务器参数的官方数值：训练时长(7)/训练经验(8)/派遣位(1)/训练位(6)/星能恢复(4)/星能上限(5)/元素恢复(16)——客户端证实原架构即服务器下发，APK 无默认值。
2. 派遣 Gift 随机算法、顾客生成/交易次数恢复、洗炼随机的权威规则。
3. `Pay`、`AlchemyType` 各 type 的服务端结算细节、559/561/617 是否曾被原服推送。
4. CollegeExplore 两个版本的 live 判定（一次实机预览即可分辨）。
5. 原服日切、退费、加速计费单价。

## Revival Compatibility Needed

**原则（2026-10-02 用户决定）：兼容方案与客户端证据相悖时，以客户端为准。**据此修订：建筑/奇迹升级成本、时长、前置、星级解锁、派遣门槛/时长/消耗、祈祷材料与等待全部采用官方静态行数据；已作废条目：自创金币升级曲线、3000 金币祈祷成本、顾客双偏好类别、ChatChance 五格数值。仍需兼容参数的只有服务器下发类：7 个 GlobalParam 键（建议实现服务器参数通道下发以保持 UI 一致）、派遣加速计费、顾客交易次数上限/恢复、洗炼日次数与结转、日切时点、初始遗迹/炼金状态。整体规则与审核表见 [college_growthbase_compatibility_PROPOSAL.md](../decisions/compatibility/college_growthbase_compatibility_PROPOSAL.md)。

## Implementation Plan

| 阶段 | 请求/响应及 push | 静态与持久化 | 测试 / DoD | 状态 |
|---|---|---|---|---|
| 0. 证据封口 | 584/591/623 native 审计；请求/响应字段集 | 表行数据解码 | 字段集=真实读取集合 | **完成 2026-10-02** |
| 1. 双入口与一致快照 | 579/584、622/623、590/591；无 push 依赖 | `college_state`、官方初始建筑/奇迹 | 两入口、重登、幂等、无效等级拒绝 | **完成 2026-10-02（入口闭环；隔离库测试通过，待实机复测）** |
| 2. 建筑/奇迹与资源 | 233/244、234/245、235/246、271/272、238/249、695 | 用官方 CollegeLevel/StarLevel 成本/时长/前置；星能事务 | 资源不足拒绝（细分错误码）、不扣重、时钟跳跃 | 待实施（成本数据已就绪） |
| 3. 派遣与训练 | 242/253、236/247、624/625、239/250；259/262、257/260、258/261 | 派遣/训练槽、英雄占用（HeroStatus）、Gift 领取凭证 | 同英雄不重复占用、幂等、重登恢复 | 待实施（训练时长/经验为服务器参数，需决策） |
| 4. 炼金与顾客 | 590–605、824–827 | 配方/生产槽/顾客订单+交易次数/材料/经验 | 制作扣料与收取原子化、交易服务端计价 | 待实施 |
| 5. 祈祷与洗炼 | 366–373、514、1055–1058 | 祈祷队列、装备属性、日次数 | 奖励只领一次、日切兼容决策 | 待实施 |

社交协助 879–882 维持用户 2026-09-27 决定：不实施。


### 2026-10-16 训练经验更正

重新反汇编CollegeModule.GetHeroTrainExp(0x1AFC734)：直接检查建筑等级行EffectType2==8并返回EffectValue2[0]，并非读取全局参数。以上早期关于训练经验“键8/官方值缺失”的结论已被此证据替代。光之密室1级500经验、2级800、10级4000、30级12000。训练时长仍取等级行效果7（小时），消耗仍取PowerConsume。

服务端按任务开始时保存的buildID冻结收益，升级建筑不改变已有任务；旧任务尚未领取时重算正确收益。使用PlayerLevelBonus经验链逐级升级，账号等级封顶，不新增封顶溢出经验，不删除旧存档已有经验。已领取历史任务不重发。
