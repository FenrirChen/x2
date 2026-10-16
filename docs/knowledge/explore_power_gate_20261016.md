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
