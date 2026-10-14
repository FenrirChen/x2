# 抽卡、赛季天赋及 PR 35–40 审查（2026-10-14）

## 本轮修复
TalentLevel.level 是客户端本次新增点数，非最终等级。TalentItemData.ResetCurPoint 0x14c5a18 把 curPoint 清零；AddPoint 0x14c7194 累加；RefreshLevelNum 0x14c6ee8 将 curPoint 与模块已保存等级相加；OnBtnAddTalentView 0x14c47a4 直接将 curPoint 写入 TalentLevel.level。旧服务端将其当绝对等级，追加低于现有等级的点数会拒绝，等于现有等级时也视作未加点。

改为校验并累加新增点数、扣除本次点数，回包仍给最终等级。允许取消待加点后留下的零值条目，不允许负值、重复 ID、超上限或超预算，全部操作在同一事务内。重置按实际退回点数乘每点费用；原客户端 OnResetTalent 确认回调 0x14c68a4 同样将保存等级乘每点费用。请求回执防重复扣费、重复退款、重复加点。

测试：天赋/抽卡 39 项，赛季协议/进度奖励/战斗蚀化 24 项，共 63 项通过。覆盖重置后再次追加、其他天赋保留、多条变更、重新构建服务、属性生效、回执重放及失败回滚。未修改 APK。

## 抽卡现状
从原 2.4 APK ResourceManager 解码 DrawParam、Gift、DrawRules、Language，逐池逐组核对全部现有奖池配置：common/security/top/limit 的物品、数量、权重全部与官方表一致，未发现数据导出漏项。高星神格内部星级为 5，对应展示三星。

普通/UP/限定神格池，按 CommonPrize 直接归一化的自然三星概率范围 0.1920%–0.5939%。当前常驻 22203 为 0.5939%，陵光 22218 为 0.4234%。十抽二星保底及四十抽三星保底正常，抽到三星立即重置计数；十连逐次抽取且保留十个奖励位置，没有限制一十连只能抽到一个三星。隔离测试证明首次两抽连续三星、同角色重复转碎片、剩余八抽计数和重放均正常。

客户端 Language 4301033 公示 4.00%（含保底），DrawParam 还含 DrawnLucky/LuckyParam/LuckyOrigin/FirstLuckyRate。【2026-10-14 订正】幸运值字段是官方遗留，但全部 48 条 DrawParam 的 DrawnLucky 实际为 0；字段存在不足以证明 2.4 仍启用幸运增长。当前 luckyValue 恒零不能单独判为缺失现行官方规则。暂未恢复幸运值，也未调整自然三星概率；2% 只是未经批准的兼容提议，非已确认的官方概率。

## PR 审查
- [#35](https://github.com/FenrirChen/x2/pull/35)：值得合并。原始 CollegeCustomer 的 Like repeated 字段确为二元素，全部 38 名顾客与 PR 配置一致；补回 991 偏好，保持每位顾客稳定选择。按顾客 ID 选一个偏好属于兼容选择，非声称官方算法。
- [#39](https://github.com/FenrirChen/x2/pull/39)：值得优先合并。已独立核对 RequestPointsReward 0x1808d50，在 0x1808e84 读取阈值，0x1808e88 覆盖输入下标，再发包；请求实际为 5/10/20/40/60。旧实现误按下标。PR 中不同 RVA 来自不同客户端版本，本地证据已核对。当前修复仅天赋，本 PR 未合入。
- [#38](https://github.com/FenrirChen/x2/pull/38)：值得合并后补修。启明之塔恢复及取出功能有价值，但 _exchange_power 将塔扣款/星能与玩家体力写入分成两个事务；第二次写失败会损失资源。应放入同一事务并补失败回滚、重复请求回执、权威资源同步验证。
- [#40](https://github.com/FenrirChen/x2/pull/40)：概率翻倍结算值得采用，需调整实现。原版 GetExpPhase 0x18a2d90 在全部阈值达到时明确返回 Count-1（0x18a2f1c），FindEffectInRecipeLevel 检查 phase>=5 才启用第五槽。PR 把 phase 改为 Count，并不是严格客户端对齐。建议保留显示阶段含义，将最后阈值达到的翻倍收益单独判定；随机种子用不可改变的 production_id，不用能加速改变的 endTime；按实际产物数增加配方经验。界面是否显示此技能是客户端遗留差异，不改 APK。
- [#36](https://github.com/FenrirChen/x2/pull/36)：暂缓。类参数虽默认关闭，正式启动入口却硬编码 True，将资源本常驻翻倍，未经本会话批准；说明称每关 10 次，实际 row_id 使同一组关卡共用 10 次。新增 extra_drop_usage 还需纳入完整存档边界。明确倍率、次数口径及保存规则后再采用。
- [#37](https://github.com/FenrirChen/x2/pull/37)：参考保留、不合并。作者明确标注不请求合并，仍含模拟玩家和兼容规则，不是已验收的真实多玩家闭环。

本轮未合并任何 PR、未推送。原生证据见同目录 gacha_talent_20261014，审查概率见 gacha_audit.json。

2026-10-14 后续：用户批准除 #37 外全部合并。#35/#36/#38/#39/#40 均已 GitHub 合并并合入本地。补修见 pr_merge_followup_20261014.md。
