# 主界面时序之门：WorldBoss 恢复

## 故障与客户端证据

入口是 WorldBossModule，不是 Type 7 周常无尽。实机 407/C2L_WorldBossSearch 原先 unknown、无回包。入口 679 原先 code=208，使客户端显示每天 17–23 点开放。

恢复 407/409/415/417/419/421/471/701 的请求及对应回包、431 血量和排行通知、494 集结玩家通知。WorldBossInfo 原生 Serialize（0x18342a4）跳过字段 12；topPlayers=13、joinRound=14、selfPlayer=15、joinPlayerNum=16、level=17。

客户端 A/B 按钮实际发送 0/1（0x136892c、0x1368a44）；答题 ContentIndex 为 0..N-1（0x14dfbdc），Step 同样从 0 开始。最终宝箱已领取条件为 UsedExploreTimes > TotalExploreTimes（0x136f2a0），领取后同步次数 6，实际探索仍限制为 5 次。

Monster.Hurt（0x1c01778）用命令 131 上报上一段累计伤害，再于 0x1c017e4 清空累计值；网络上报是增量。不同请求中相同伤害必须均累计；同一请求的传输重发由持久化回执去重。旧回执重发返回当前 Boss 状态，防止客户端血量回退。

## 原始配置与奖励

tools/analysis/export_world_boss.py 从标准 APK 导出 WorldBossInfo、WorldBossExplore、WorldBossEvent、AnswerConfig、BoxConfig、Activity、PlayerAttrib、MonsterLevelBonus。导出结果及来源在 data/world_boss.json。

- Activity 28001：等级 17、每日探索 5 次、Gift 770000 最终奖励。探索事件原概率 [0,0,20,80]，因此只产生宝箱和答题。
- 保留事件上限、A/B 分支、答题奖励倍数、宝箱 902 货币费用和各 GiftGroup；发奖使用现有 EconomyService._grant。
- WorldBoss 的 MonsterLevel=30；普通 Boss 未填等级，采用已有 battle_monster_levels.json 的地图等级 10，与入场回包一致。HP 使用 PlayerAttrib 与 MonsterLevelBonus，保留 HPMaxCOR。
- ChallengeReward 和 FindReward 是 **MailInfo 模板 ID**，不是 Item 或 Gift ID。APK 的 table/mailinfo 无 IL2CPP 类，但保留了服务端表：字段 1=ID、4=发件组、6=标题、8=正文、9=奖励种类、10=GiftGroup。严格读取 54 个所需模板并记录来源；没有猜测排名奖励。
- 排名按贡献伤害和配置 RewardRegion 选择模板；保留 LowestDamage=500 门槛。结束后插入可由既有邮件系统领取的原始 Gift 附件，以 player_id+source_key 唯一索引防止重发。排名邮件独立于 887 的战场拾取结算。

## Revival 兼容决策

按用户要求全天开放，未改全局时间。保留星期轮换（DateTime.DayOfWeek 从 Sunday=0 开始）、等级和日次数。

原概率没有 Boss 探索事件。按用户最终要求，每个玩家独立拥有当日星期世界 Boss，不再展示三个普通 Boss。world_boss_player_days 以 `(player_id,上海日期)` 为主键固定当天个人实例；重启、重登及重复查询复用同一实例，个人击杀后当天不补生。旧共享表保留审计，升级只转移本人贡献和入场绑定，个人剩余 HP=最大 HP-本人贡献，不继承其他玩家击杀/伤害；旧成员的活动绑定和扣次标志移到个人实例，避免重复累计。旧普通实例保留审计记录，但查询和动作拒绝使用。

客户端个人雷达读取 WorldBossSearch.Slots/WorldBoss，而非仅 415 的其他 Boss 列表。415 查询前创建个人 Boss 槽位并先推送该字段；按会话只推送有变化的数据，避免更新回调再次查询形成循环。没有查询过的账号第一次 407 也会发现当天 Boss，后续搜索仍按原宝箱/问答概率。补槽不重排已有槽位索引，不改宝箱/问答领取进度；票据与 415 返回的玩家专属 ID 一致。

原多人集结人数配置面向官方在线规模；当前采用第一个经认证的玩家加入后进入 FIGHT，世界 Boss 仍走原生集结场景及本地约 10 秒开战倒计时，无需其他玩家或长时间集结。Boss 实例持续到上海时间当天结束；battle UUID 仍遵循现有一小时入场结算边界。支持共享血量、玩家加入/离开通知、排行和结束/过期推送，尚未由多台客户端实机验收。

没有 WorldBossInfo 配置的未发布 Type 6 关卡继续拒绝准入；不为它们制造怪物/奖励配置。

## 持久化、认证与战斗边界

world_boss_accounts/runs/members/receipts 存储日次数、槽位、问答、最终领奖、共享 Boss、队伍、伤害、绑定 UUID 和请求回执。通过代码创建表，不修改测试玩家的已有存档内容。

独立 C2W 连接验证 game token 或已认证大厅 session。实机确认原生客户端两者均未填写，因此通过已认证大厅查询返回玩家专属、32 字节随机生成的 opaque Boss ID，持久化映射真实 Boss；独立连接必须持有这个 ID、匹配玩家、已大厅报名且 Boss 未过期，才可认证。共享血量仍按内部 Boss ID 聚合，不凭 playerid 或 IP 授权，不记录票据到业务日志。队伍必须是拥有的角色。伤害必须绑定自己的未结算 battle UUID；结算后停止累计。

次数在有效 264 战斗请求、绑定 UUID 的实际伤害、或有效 887 结算时确认，同一成员重入不再扣。combat_confirmed 代码迁移根据已保存的 264、887、伤害证据保留真实战斗次数，恢复旧版仅报名/收到 126 但客户端未进战的次数。放弃未进战入场也不扣次。未结算战斗重入复用 UUID，相同队伍的 701 重发允许通过；失败结算后按原始 DeadPenaltyTime=60 秒冷却重试，保留伤害贡献；成功结算后不能重试。查询不推送整份账号数据，避免客户端重复查询。

Type 6 入场要求已加入、进入 FIGHT 且队伍一致；战斗 entry 回执先处理重发，不能重复创建 UUID。887 保留 outsideItems 校验、RewardGrant、battle receipt，结算与成员退出在同一事务。费用不足或无效输入返回错误并完整回滚。

服务端启动增加 Boss 过期巡检任务；退出时取消。沿用 tools/local_game_server.py 启动和邮件推送。

## 验证

测试使用临时数据库：探索重发、A/B 分支、付费不足回滚、背包和货币同步、零下标答题、持久化、跨日重置、最终箱防重复、全部可达事件的原奖励配置；Boss 列表、伪造连接拒绝、真实会话准入、队伍绑定、战斗重发、连续相同伤害、负数拒绝、887 幂等、结算后拒绝伤害、排行邮件原 Gift/发放/领取/重启去重、共享状态推送。

实机验收应重新登录后测试探索、选择、答题、宝箱、Boss 入场和结算。自动化通过不等同于所有客户端界面已验收。
