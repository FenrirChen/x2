# 美食幻境多试用角色入口修复（2026-10-15）

日志 runtime/arcade_dp_20261015_163608.err.log：16:50:39 请求 126，section=2161191/chapter=2060760，输出 trial=1327 后立即返回 code=13。

SectionTable 中该关 AssistType=E_Trial，AssistParam=[1327,1328,1331]。旧代码 section_trial 只返回第一个试用角色，并对队伍内每个角色调用 trial_hero(1327, selected_id)，因此其他合法队员被判无效。旧测试仅选第一名试用角色，未覆盖三人队伍。

新增 trial_team 按本关允许的全部试用角色逐一解析，兼容 TrialHeroID 与 UnitID，维持玩家选择顺序；拒绝外来角色以及同一角色的两个别名重复上场。普通关卡仍使用玩家自有角色；第七章第七幕单人贝黑莫斯补偿保留。

覆盖美食幻境原生三人、普通ID别名、调整站位的进入及结算/重试。遍历所有 E_Trial 关卡核验完整名单；正式存档角色和背包装备不替换为试用数据。
