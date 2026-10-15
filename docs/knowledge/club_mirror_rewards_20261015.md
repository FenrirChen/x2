# 镜域宝箱、今日进度与递减助战（2026-10-15）

## 协议与宝箱
用户实测日志 club_wish_reset_20261015_202933.err.log 20:44-20:45，798请求均被旧规则 mirror reward not eligible 拒绝。

原生 ClubActivityInfoView.DoSendClubReceiveReward 0x1564D38 从 GuildChallengeInfo.StageID（+0x18）取参数，以 opt=2 发送；旧服务端只接受 opt=0/BossID，两项均不符。现原生 opt2/StageID 领取对应 WinReward，已亲自参与此关（mirror.sections）免钥匙；仅NPC击败的层按 WinConsume 扣钥匙。都必须已击败且未领取。receivedLayer 下发 StageID；旧 BossID 领取记录映射到同一领取状态，不重复发放。为旧客户端保留 opt0/BossID 别名，但共享同一领奖账本。

原生 OnMBtnTodayRewardClick 0x15673E0 在进度达标且未领取时发送 opt1/param0。ClubModule.cctor 0x1588B20 写 TODAY_REWARD_MAX_SCORE=100000000。GuildLevel 一级 DailyAward=778202（静态字典 tables.json，源hash d3f495a9230eb0e4c9c2a7d3112fa79f）。奖励按恢复的 Gift778202：社团勋章1237924×160、金币×17000、票据1237918×50。DailyScore300000为同表的另一字段，客户端今日宝箱实际比较上述常量，未将其误用为门槛。

## 今日进度
玩家及NPC真正扣除的血量累计到 clubTodayScore，不含过量伤害；最多100000000，避免客户端将长整型转换为32位整数后溢出。每日北京时间00:00清零，领取资格同日一次，scoreRewardFlag正确返回。run标记、进度、奖励receipt处于原事务中，重试不重复累计/发奖。

对旧镜域代码已保存的当日战斗，按 mirror.runs 的实际 turns.applied 和本账号 battle_entries/battle_receipts 的结算时间回补，不重算伤害、不重新打BOSS、不计昨天/无receipt的记录。回补后写 score_day 标记；新结算当场标记。无日志或战斗记录的历史伤害不凭空恢复。

## 新助战规则
本轮替代上一版所有NPC固定90%的规则：以玩家本局开始挑战的 BOSS 层号为原点，NPC攻击原BOSS为玩家伤害90%，跨一只45%，再跨一只22.5%，再跨一只11.25%，依次减半；计算 playerDamage*9//(10*2**跨层数)。玩家直接击杀第一只时，所有NPC从45%起步。各成员一次，过量伤害仍丢弃。仅未来战斗采用新衰减，不重写已完成伤害记录。

## 测试
41项社团/镜域/日切测试通过。覆盖原生opt2/StageID、参与免费、未参与钥匙不足与精确扣除、正确WinReward、领奖防重、旧ID归一、每日进度及100000000上限、Gift778202、00:00重置、可信历史回补、90/45/22.5/11.25比例、剩余血量与此前日切通知修复。验收由用户完成，无APK修改。
