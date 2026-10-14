# PR #41 合并补修与占卜调查（2026-10-14）

## 勋章商店

PR #41 在 GitHub 以 merge commit 合并，保留作者 bluebird0212 的贡献记录；本地合入时保留已有修复。
新增赛特碎片（周限购20，300勋章）、日月之轨·贝黑莫斯（累计限购5，4800勋章）。第94货位按纯晶石／兽骸／许愿币逐周轮换，分别1200／500／1200勋章，周限购3。商店实际显示14货位，配置16条商品中第94位每次仅一条可见。

补修：以2026-10-12周一为首货位锚点，连续计算周数，避免 ISO 周数在跨年时重置造成跳期。轮换货位共享当周额度，计入修复前1909401购买记录；隐藏商品既不可查询也不可购买。赛特每周一北京时间00:00刷新，贝黑莫斯累计额度不随周重置。票据商店保留既有用户批准规则。

验证：test_medal_shop_rotation.py 覆盖跨年三周轮换、周一00:00边界、隐藏货位拒购、历史额度、扣币/发货/重放，以及碎片周额度和累计额度；同时回归既有商店和好感度结算用例。

## 占卜与幸运值

直接从原始2.4 APK ResourceManager指定的 AccountBuff、ConstellationContent、Language 表解码，来源与哈希在 evidence/divination_20261014/up_blessings.json。

* AccountBuff 999025／999026／999027，效果枚举 E_Wish=5，数值80／60／50；Language 9000049／9000050／9000051明确写“许愿出Up神格概率提升8%／6%／5%”。AccountItem 为1300025／1300026／1300027，可在ConstellationContent日运势配置中找到引用。
* Language 2810443：“每次占卜可以得知解神者的五项运势”；2810445：“占卜获得的光环效果持续一日”。因此提升 UP 出率的占卜设计确实有客户端证据，不只是推测。
* DivinationModule.OnQueryDivinationMsg RVA 0x14AD02C，0x14AD0AC–0x14AD0B0将QueryDivination.blessing复制到mBlessing；其字段为id、expireTime、count。它与许愿回复的luckyValue是两个独立协议结构，现有证据不能证明两者等同。
* 前轮客户端审计已经确认保底显示用ThreeStarSecurityNum-securityNum，luckyValueCurrent只发现调试打印。LuckyParam=40与保底40同值，不能证明幸运值就是保底。
* 当前服务端DivinationService只发每日奖励，query的blessing为空，WishService返回luckyValue=0且没有接入占卜E_Wish。因此占卜出率加成尚未恢复。

未擅自修改抽卡概率。本地客户端表无法给出幸运值增长公式，也不能仅凭“提升8%”区分相对倍率、百分点增加及各星级处理方式，更不能确定其与luckyValue的换算。要恢复这段需补齐官方规则证据。本轮保留可复核资料，不把未知公式作为官方逻辑上线。
