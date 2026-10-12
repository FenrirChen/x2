# 年兽盛宴棱镜兑换结算

## 真实报文

2026-10-12 14:43:37，玩家1结束2161190，run c340d7c6-ec5e-450b-a78e-26f327e93c5a。success=false，outsideItems为空；checkout字段11 extraData包含Key1237903/Value840，字段11原来没有进入服务端业务schema。原版FightModule.SetCheckout_Currency(0x14427b8)使用GameAPI.GetCurrencyNum(3)构造这一项：1237903是棱镜，对应货币903。

原版教程Illustration1343015/图片NewYearNian_ShuoMing2写明“棱镜按对应比例转换成新年红包”。活动类型28的两个年兽版本配置一致：Param2=1237903输入，Param3=520兑换单位，Param4=1203021输出，ActivityReward=3当日上限。退役的另一GamePlay1活动使用相同字段布局、1000兑换单位及其他输出，不能将此类型的Param3与抽签页面的语言字段混用。

## 修复

恢复C2L_CheckoutMainMission.extraData字段11。仅绑定到本期ActivityGamePlay1的战斗按配置兑换，840棱镜得到floor(840/520)=1个红包。负数、超大报告和重复同一货币拒绝并回滚；其他货币不用于兑换。成功与失败/结束的小游戏均结算已取得棱镜，失败不记通关、不发首次通关30光辉；普通失败关卡仍为空。

当日最多3个，以现有活动北京时间零点业务日切记录在activity_state的期别/day命名空间。收据和奖励来源以run UUID防重，进入下一轮活动使用新的期别。兑换产物不再同时接受outsideItems的第二份客户端申报，避免重复发奖。

ItemData.dayGet同步当日已得数量。红包用完、背包数量0时仍下发该计数，且不被ItemRemove删除；次日清零，下一期隔离。不新建数据库表，现有完整存档导入/导出仍包含这些activity_state数据。

单元覆盖两个年兽活动、真实840上报、兑换阈值、每日上限、失败与胜利、重传、用完红包、日切、下一轮、非法报告、普通失败不兑换以及outsideItems重复申报。相关107项回归通过，增加防重复申报后小游戏11项复测通过，合计108个不同用例。

runtime/backfill_nian_report_20261012.py仅处理上述已保存原始报文的漏发局，备份后一次性补发1个红包并修正旧结算回执和审计；奖励来源防重，不改通关状态。

2026-10-12 15:07已执行该补发，玩家1获得1203021×1；独立source记录保证重复执行不再补发。随后服务端重启，活跃存档备份保存于忽略的runtime目录。
