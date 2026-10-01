# 时序之门：单人兼容与血量/生成分析

## 最新规则：每日固定狮鹫（2026-10-01）

用户取消星期轮换。新生成的个人日实例固定使用兼容配置 daily_boss_id=2040101：狮鹫【剑柄】、MonsterID=5301、StageID=2140101。已生成的当日狮鹫（2040104、MonsterID=5304）保留实例、血量及击杀状态，不为了更换同名配置重置进度。之后每一天的新实例均使用 2040101。仍然每玩家每日一只、击杀当天不补生。

强度调查：WorldBossInfo 原始表的七个世界 Boss 均显式 MonsterLevel=30，相关地图的 monsterInitLevel 也为 30。2026-10-01 23:09:16 实机 section=2140104/scene=2240104 的 L2C_FightData 日志确认 monsterInitLevel=30；23:09:24 收到实际战斗确认，23:11:15 success=True 结算。WorldBoss 搜索、入场、LoadingHelper 与怪物属性链路未找到按玩家等级或战力自动计算 Boss 等级的公式；这不能证明原官方服务端没有动态规则。

客户端支持由服务端指定 monsterInitLevel，BaseLevel.InitMapInfo（0x199f21c）直接存入 MonsterBaseLevel；Property.PropertyUpdate（0x1c219e0）按怪物自身等级读取 MonsterLevelBonus。世界 Boss 的最大/当前 HP 则由 LoadingHelper -> SetBossBattleInfo 单独注入。玩家等级是另一协议字段，不会因为发送 playerLevel=60 就把 monsterInitLevel=30 提到 60。MonsterLevelBonus 高等级数据还有不同数值范围/倍率分支，不能把 30 级公式不加核对地套到全部等级。

狮鹫原始 HPMax=8,350,000，30 级 HP 倍率=7291/1000，当前初始个人 HP=60,879,850。原始 Damage=155，存在 DamageLevelBouns/DMGLevelBouns 等等级参数，实际伤害还受技能、抗性等影响。因此目前高等级玩家仍面对固定 30 级敌人，可能偏弱。原生被动 242535 的 Source=E_Section、触发=E_DamageTaken、ActionGroup=[41014,0,1]，这条配置自身没有玩家等级/战力条件。本轮只取消轮换，不虚构或实施自动强度规则。

## 本轮代码修复

- 2026-10-01 20:54 实机日志：大厅 417 成功，独立连接 421 已通过认证，但在 `invalid network team` 被拒绝。原生 OnWorldBossActJoin（0x1374b2c）从 ChapterModule.CurSelectHero 上报队伍，包含空槽时仅过滤 0；未知角色、重复角色、超出三个槽仍拒绝。增加不含 token 的角色 ID 拒绝日志以核实其他实机输入。
- 22:02:35 实机 417、421、701、126 均成功但没有 264/887。进一步核对 ChapterModule.OnL2CFightDataReceiveMsg（0x16c0468）：Type=6 在 0x16c05f8 要求 GameAppImpl 存在，且 0x16c0634 要求游戏状态为 MassScene(2)，否则直接返回。上一版 `worldBoss=false` 跳过必需场景，导致客户端静默丢弃成功的 126。本轮恢复真实 `worldBoss=true`，进入 MassScene 后才开战；单人立即进入服务端 FIGHT，不等其他玩家。原生客户端仍有本地约 10 秒 StartEnterTimer；取消它需要客户端修改，不能再通过伪造类型绕过场景。
- 次数确认从独立连接成功改为实际 264/伤害/有效 887；迁移用持久化战斗证据恢复此前未进战的次数。相同未结算 UUID/队伍重入允许 701，保留传输幂等和正常战斗次数。
- 成就原生 GetDetailData（0x1319f70）：code=10 时列表不存在会继续请求下一页，恰好满 30 条后返回空页会无限加载；code=97 在 0x131a1d4/0x131a2d0 是结束分页并更新界面的原生分支。服务端空页改为 97，非空页仍为 10。

## 客户端血量逻辑（只分析，未修改血量）

存在基础数值计算：Property.PropertyUpdate（0x1c219e0）。当前世界 Boss 30 级、普通 Boss 10 级均处于已核对的低等级公式范围：

`HPMax × HPMaxLevelBonus / 1000 + HPMaxCOR`

WorldBossInfo/PlayerAttrib/MonsterLevelBonus 原始表导出的值如下；整数为当前服务端初始共享血量，不包含战斗中已扣除的伤害。

| Boss 配置 ID | 怪物 ID | 名称 | 等级 | 初始 HP |
| --- | --- | --- | --- | --- |
| 2040101、2040104 | 5301、5304 | 狮鹫【剑柄】 | 30 | 60,879,850 |
| 2040102、2040105 | 5302、5305 | 月蚀兽【权杖】 | 30 | 62,702,600 |
| 2040103、2040106 | 5303、5306 | 月蚀兽【星币】 | 30 | 71,087,250 |
| 2040107 | 5307 | 月蚀兽【圣杯】 | 30 | 76,190,950 |
| 2040201、2040202、2040203 | 5301 | 狮鹫【剑柄】 | 10 | 13,051,050 |

客户端也支持指定血量：LoadingHelper.GetSingleGameSceneData（0x1506a88）读取 WorldBossModule.CurChallengeBossInfo（0x15087d4），读取 `maxHp/curHp`（对象偏移 0x58/0x60），调用 BattleInfo.SetBossBattleInfo（0x15090cc -> 0x19a2354）。伤害回包经 WorldBossHPSync（0x13757f4）更新局内当前 HP。这条路径没有根据 `worldBoss` 布尔值跳过血量注入。

因此服务端可指定最大血量及当前血量，必须同时保持列表、入场上下文、实时伤害响应和数据库记录一致；只改展示文字不够。自定义血量尚未实施或实机验证。

## Boss 生成（按用户本轮要求已实现每日一只）

当前生成由 WorldBossService.public_bosses/create_boss 控制。客户端只是查询实例并根据 typeId 从本地配置取名称、模型、关卡和图片；它不独立决定共享 Boss 实例数。

world_boss_player_days 以玩家和上海日期为主键，每位玩家每天独立一个世界 Boss，星期一至星期日依次使用 2040101..2040107。查询/首次搜索创建当天个人实例，个人血量、伤害、次数、击杀状态和奖励分别持久化。重复查询、重登、服务重启复用个人实例，血量为零/状态 3 时当天不补生。未击杀实例持续到当天结束。旧共享进度迁移只扣本人造成的伤害，不继承别人击杀结果。旧普通 Boss 不再展示或接受动作。

“搜索不到”根因：407 原始 EventProbability 的 Boss 权重为 0，而 415 只更新其他 Boss 列表。个人雷达必须收到 WorldBossSearch 的 Slots、WorldBoss 及匹配玩家票据；本轮补上槽位及先于查询响应的数据推送，且相同会话重复查询不重复推送，防止回调循环。已有宝箱/答题索引保持不变。

七个配置不是七种不同模型：周一/周四同为狮鹫【剑柄】，周二/周五同为月蚀兽【权杖】，周三/周六同为月蚀兽【星币】，周日为月蚀兽【圣杯】。星期配置 ID 每天不同，但名称/模型原本有重复。

## 名称与贴图的发现及限制

原客户端 WorldBossInfo 表的三个普通 Boss 均为 MonsterID=5301、BossName=53011（狮鹫），但 BossIcon 均指向 `WorldBoss01`；世界版同类狮鹫使用 `WorldBoss02`，月蚀兽使用 `WorldBoss01`。客户端 WorldBossInfoView.SetData（0x136d3d0）从本地表读取名称及 BossIcon；网络协议没有图片字段。雷达小图标另取 WorldBossExplore 的通用事件图标，不能直接当作 Boss 肖像。

该原始表存在普通 Boss 肖像映射不一致。按本轮每天只显示一个世界 Boss 的规则，已移除三个错误普通配置的可见实例，使用世界 Boss 表内正确的名称/肖像映射。没有修改客户端图片资源。

## 验证

个人实例调整后，30 项 WorldBoss/战斗准入测试通过：双玩家 Boss 血量、死亡、次数隔离；跨玩家查询/报名拒绝；雷达槽位和票据对应；同会话相同查询不重复推送；首搜发现 Boss；旧共享进度按本人贡献迁移；七天轮换/重启不复活；未进战过期 UUID 放弃退款后重新入场。均使用临时数据库，仍需客户端实机验收。

40 项 WorldBoss/战斗准入/成就测试通过，均使用临时数据库。新增验证覆盖完整七天轮换、旧普通实例隐藏、击杀后当天查询/重启不复活、未进战不扣次、真实 264 扣次/重发不重复、旧版本误扣次数的代码迁移。原生无 token 连接、空槽队伍、失败冷却重试、贡献保持、领取幂等及成就分页结束也在回归范围。服务端测试不等于客户端已实际进入战斗，仍待用户实机验收；未推送代码。
