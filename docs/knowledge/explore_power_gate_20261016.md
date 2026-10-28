# 家园探险误报神力不足（2026-10-16）

## 根因与证据

原服务端用CollegeExplore.Conditon[difficulty]作100%硬门槛；中文客户端实际按50%出发线校验。

- CollegeExplorePage..ctor RVA0x1BBDA64，0x1BBDAC4调用GameAPI.IsJapanLanguage；0x1BBDACC/AD0设置0.5和1.0，FCSEL在日文时选择1.0，其他语言0.5；0x1BBDAE0写入this+0x74 (MINUAS_POINT)。
- CollegeExplorePage.OnExploreButtonClick RVA0x1BBD35C，0x1BBD494读取Conditon[difficulty]；0x1BBD49C调用GetTotalFightPoint；0x1BBD4AC计算总神力/目标；0x1BBD4B0比较MINUAS_POINT，达标进入发送分支，不足才弹提示。
- GetTotalFightPoint 0x1BBD6F0，0x1BBD884读取各已选角色的属性203 (E_Hero_Ability)，累加；SelectHeroNode.Refresh 0x1BBD07C同样读取属性203显示。

## 修改

中文服务器的最低神力改为ceil(Conditon/2)。例：配置目标10000，最低5000；5000可出发，4999不可出发。不是删除神力检查，也没有采用客户端自行提交的神力值。

成功和失败日志均包含实际power、minimum及原始target。未改官方遗迹经验阈值、难度解锁、奖励、星能成本、占用和取消/领取事务。未修改客户端。日文版1.0的分支仅作为客户端差异记录，本项目目前两份发行包均为中文版本。

## 验证

隔离数据库循环全部15处遗迹、3档难度，逐个测试50%减1拒绝、50%刚好允许、真实神力持久化、星能只扣一次、重发回执不重复扣费、取消释放。另测试真实角色计算神力处于50%-100%区间可出发、两位英雄合计达标、未拥有/重复英雄及未解锁难度仍拒绝、奇数目标向上取整、写队列异常整体回滚。原CollegeJobs训练/派遣回归同时执行。

## 2026-10-28 修正：50% 门槛改为仅告警

上述 50% 检查保留下来的是**服务端自己的神力估算**，而客户端判定用的是另一套数值，两者相差一倍以上：

- 截图（中国版客户端，冰海沉船 34012 / 普通 / 目标 13000 / 星能 54）：
  三人队总神力 12963（进度条 99%）和 13334（100%）都在点「探险」后弹 13100872
  「神力不足探险需求的50%，无法进行探险」，即服务端回了 186。
- ceil(13000/2)=6500，两次都被拒 ⇒ 服务端 `hero_power` 之和 ≤6499，
  不到客户端同队数值（12963）的一半。
- 客户端 TotalFightPoint（GetTotalFightPoint 0x1BBD6F0）逐人累加属性 203
  (E_Hero_Ability)，该属性由 ClientProperty.SetAnility 0x149398c 把
  base/phy/ice/ele/fire 写进 0x62..0x67 后再供 0xCB 取值；其中
  GetCombat 0x1495b58 还会乘上 PlayerAttribManager 的玩家级属性 [+0x98]，
  RefreshCollegeWonderAttributes 0x1492cd0 再叠加奇观。服务端 `hero_power`
  只能还原部分输入（神器/宝石/兽主/羁绊/奇观），玩家级包裹层缺失，
  因此 RVA 记录无法移植成服务端可复算的口径。

结论：这个门槛只会产生「客户端显示 99%/100% 却被拒」的假失败，且
「时而成功时而不成功」随队伍装备/奇观变化。客户端在按钮点击时已用属性 203
自己按 50% 线拦截，服务端重复用低估口径判定没有收益。

- 改动：`college_jobs._start_explore` 保留 `power` 估算与
  `required=(Conditon+1)//2`，只把它写进 INFO 日志
  （`StartExplore below native half power but allowed`），不再返回 186；
  `fightCapacity` 仍写实际估算值，星能成本/队列/难度解锁/奖励/事务不变。
- 测试：`tests/unit/test_explore_power_gate.py` 改成 15 处遗迹 × 3 档难度
  在 `power=0` 时也必须出发（并验证回执去重、扣费一次、取消退还），
  50% 线上行为保持不变；`test_shop.py` 等其它 186 用例无关。

