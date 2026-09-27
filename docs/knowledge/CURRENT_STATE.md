---
Document-Type: Current Knowledge
Domain: Coverage
Status: AUTHORITATIVE
Updated: 2026-09-27
Supersedes:
  - (none)
Evidence-IDs: see evidence/manifests/evidence_manifest.json
---

# 当前状态快照（2026-09-27）

- **白夜行星 Phase 0/安全子集（2026-09-27）**：实际字段审计见 `analysis/white_night_planet/phase0_response_audit.md`。579/584 使用独立 SQLite `college_state` 快照，登录同源，官方初始建筑/奇迹可重登恢复；590/591 和 622/623 因初始炼金/遗迹状态证据不足仍未闭环。`CollegeExplore` 是计时派遣，不复用主线战斗入场/结算。基地入口仍为 PARTIAL。

- **可运行**：登录/大厅/物品/英雄(1003)/装备测试实例/**装备实例真交付(887→Factory→落库→152.rewardEquip)/**
  魂器基础/技能/抽卡/固定奖励结算/主线 78 关 + 资源本 20 关/扫荡(41 关静态)/日周任务/聊天空频道。
- **测试**：外部包合并后全量 282 passed（2026-09-27 隔离 SQLite 单元测试）。
- **已恢复领域**：见 knowledge/ 各域文档；运行态口径：coverage/runtime_coverage.md。
- **主要 PARTIAL**：Battle Entry 扩展类型、DailyDungeon 剩余变体、Mission 真进度。
- **掉落经济**：E_ReportCurrency 代理物结算折算已实施（金币本实机空白贴图已修）；dropValues 预算改为 DifficultyLevel 分级 LOW/MID/HIGH=1000/3000/5000（REVIVAL_COMPAT）。
- **兽主本结算 blocker 修复待实机复测（2026-09-26）**：2133101 的 887 含 1101060×90 时，resolver 已折算为 1237912×900，但 `_grant` 缺少非 BaseInfo 货币落账路径，导致 result=13；现按官方 E_Currency Item 把这类账户货币记入 item ledger，并保持代理物不入包。隔离库回归覆盖 68 个代理物和 8 个货币桶；实机 152/客户端表现仍待复测。
- **本轮修复待实机复测**：体力按客户端原始 300 秒的 75% 恢复，即 225 秒/点，恢复进度随账号持久化；兽主分解按静态强化/品阶表返还货币并删除实例；40 条日周任务的静态奖励已全部通过隔离库领取测试。现有玩法的消耗体力、通关、入场、击杀、装备强化、商店购买等成功事件已接任务进度。好友、炼金、基地等未接入玩法所对应任务按用户决定留待后期。
- **生日提交修复待实机复测（2026-09-27）**：客户端 364 C2L_FillBirthday（月、日）此前没有服务端注册，导致无响应。现回 365 L2C_FillBirthday，校验日期并把 MMDD 写入 BaseInfoProto.Birthday（字段 32），在响应前推送玩家资料；隔离库验证持久化与重复请求。
- **主要 known unknowns**：coverage/known_unknowns.md（10 项）。
- **兼容决策**：docs/decisions/compatibility/。
- **下一步推荐**：reward_system_server_fix_plan.md 的 FIX-1/2/3。
- **本轮外部包合并**：图鉴 26 个官方 Collection 条件已接入，25 个 Gift 可领取；133103 的 E_Medal 目标未被当前 RewardGrant 支持，会明确拒绝且不标记已领。好感协议、HeroData 档案/联结、FavorMap 与手账查询已接入，单值 EffData 礼物可事务送礼，双值偏好及突破等未知规则仍拒绝；商店除原 809 外接入明确标注的兼容目录。59 种官方好感礼物已按用户指令补到活跃测试账号每种 100 个，修改前已备份。上述功能尚待客户端实测。
- **保护范围**：Reference APK、已有备份；活跃 SQLite 除本轮获授权的定向测试礼物 seed 外不可覆盖/重置。
