# 2026-10-01 试用角色、成就徽章和搁置奖励

- 试用关使用客户端 TrialUnitBase 的 UnitID、HeroLevel、HeroStars、ArtifactStar/Level、SkillLevel、AppearanceID，以及 EquibAttribBD 固定属性。保留试用单位的协议 ID，属性从其真实 UnitID 计算。无需写入玩家角色或装备表；试用结算不得回写玩家神器。
- 原第三方导出遗漏 1215，并将若干字段误命名。此次使用当前 APK 的既有表解析器导出 20 行；源信息在 trial_units.json。无 EquipAttrID 的配置不凭空随机生成词条。原服务器的最终战斗数值不可恢复，沿用当前项目成长公式。
- ItemType 20 徽章奖励纳入既有事务与成就回执。PlayerDataProto 字段 7 同步 MedalPack（徽章 ID -> 获得时间）及 MedalShow（0..2 槽 -> 徽章 ID）。实现 411/412 MedalOpt，验证真实库存拥有、槽位和重复佩戴，保存至玩家快照。当前 Medal 表全部 TimeLimit=-1。
- 历史 pending_rewards 中已有结算及发奖账本支持的 battle 来源，可在启动时交付当前已支持的目的地。保留原搁置记录，pending_reward_deliveries 记录一次性交付；不重新结算或补累计通关。旧固定 Gift 装备沿用现有固定奖励一星规则，不猜测丢失的掉落星级。
- 只读检查当前存档找到旧搁置兽主和许愿道具；未找到 ItemType 25 剧情物品的结算包。因此这次补交付修复已证实的历史奖励遗漏，不能据此声称所有客户端剧情提示的物品均已验证。
- 临时数据库测试覆盖试用角色、徽章成就领取和重复请求、佩戴/卸下及无效输入、历史奖励重复启动去重；主线入场、成就、RewardGrant 相关回归通过。仍需实机审查。

当前工作区另有存档管理功能改动，本次本地提交不包含这些文件。
