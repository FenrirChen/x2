---
Document-Type: Compatibility Decision
Domain: Server / Client / PointOfView
Status: ACTIVE
Updated: 2026-11-08
---

# 剧情回顾恢复与门槛保留

按用户 2026-11-08 的决定整合 PR #89，但不取消原版默契度门槛。

服务端补齐 POVChapterInfo 的 21 行（17 个常驻章节、4 个活动章节），按 ChapterID 合并，重复行必须一致；不覆盖其他活动表、轮换顺序或历史状态编号。

常驻章节真实通关进度和整章奖励保存在固定 period=-1，活动轮换及重启不会重发；活动章节使用入场时绑定的活动期，避免跨期结算丢失奖励。开发工具写入的解锁记录不等于真实通关，不自动发放整章奖励。结算记账和发奖沿用同一事务，失败可回滚。

客户端保留原始 GetFavorLevelByHeroId、POVChapterInfo.FavorLevel 和 PreviousStage 条件。不包含返回 99 的门槛绕过工具，不对本地或远程 APK 应用该补丁。原表默契度要求以每行 FavorLevel 为准（多数 3 级，部分 5 级），仍由原客户端判断。

本轮不连接远程游戏服务器，不推送代码。
