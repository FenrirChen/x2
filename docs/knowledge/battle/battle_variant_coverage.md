---
Document-Type: Current Knowledge
Domain: Battle
Status: AUTHORITATIVE
Updated: 2026-09-25
Generated-By: tools/analysis/build_section_catalog.py
---

# Battle 变体覆盖（SectionType 全量分类）

全部 3203 个 Section 按 Type 分类（机器可读：`analysis/battle/section_type_catalog.json`）。运行态支持判定来自 `src/x2server/player/battle_entry.py` 静态阅读 + runtime_coverage_matrix，本轮未改实现。

| SectionType | 数量 | 有 DropValueID | 有关联支撑表 | 服务器运行态 |
|---|---:|---:|---|---|
| E_Battlepass | 2400 | 2400 | — | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_Daily | 147 | 141 | dailydungeon,extradroop | PARTIAL (20/141 associated sections deliverable) |
| E_Challenge | 101 | 101 | challengetask | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_PointOfView | 89 | 6 | — | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_ActivityStory | 82 | 82 | — | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_UNSET | 79 | 79 | — | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_TowerDefense | 64 | 64 | tower,towerbase | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_ActivityBattle | 62 | 62 | — | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_GuildChallenge | 52 | 0 | — | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_ShuangHanStory | 21 | 21 | — | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_ShuangHanBattle | 21 | 21 | — | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_StoryExperience | 18 | 18 | — | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_WorldBoss | 11 | 11 | worldbossinfo,worldbossevent | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_NewBloodMoon | 10 | 10 | bloodmoonconfig,bloodmooninfo | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_EndlessWeekly | 8 | 0 | endlessdungeontask | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_ActivityGamePlay2 | 7 | 7 | — | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_Memory | 7 | 0 | — | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_ActivityBoss | 6 | 6 | — | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_Trainning | 4 | 0 | — | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_Monopoly | 4 | 4 | monopolygrid | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_ActivityWave | 4 | 4 | — | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_ActivityGamePlay1 | 3 | 3 | — | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_MoonChapter | 2 | 2 | moonworldmap,mooncamp | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |
| E_Endless | 1 | 1 | endlessdungeontask | NO_RUNTIME_ENTRY (classified only; BattleEntryCatalog raises EntryDenied) |

## 代表样本（每类前 1–3 个，供未来测试定点使用）

- **E_Battlepass**: 2190001 蚀之裂隙 1  (Drop=10660990, 体力=30); 2190003 蚀之裂隙 1  (Drop=10660990, 体力=30)
- **E_Daily**: 2130101 咻咻的宝藏秘境 (Drop=10630101, 体力=6); 2130102 咻咻的宝藏秘境 (Drop=10630102, 体力=12)
- **E_Challenge**: 2110151 白夜崩解·新月 (Drop=10610151, 体力=30); 2110152 白夜崩解·娥眉月 (Drop=10610152, 体力=30)
- **E_PointOfView**: 2120301 死海巨兽 (Drop=None, 体力=6); 2120302 荒漠迷宫·一 (Drop=None, 体力=6)
- **E_ActivityStory**: 2160411 牌过三巡 (Drop=10660211, 体力=18); 2160421 谁在出千 (Drop=10660211, 体力=18)
- **E_UNSET**: 2110001 疯狂之船 (Drop=10610001, 体力=6); 2110101 现世之门再次开启 (Drop=10610101, 体力=6)
- **E_TowerDefense**: 2160561 底层防护·迭代一 (Drop=10660211, 体力=None); 2160562 底层防护·迭代二 (Drop=10660211, 体力=None)
- **E_ActivityBattle**: 2160412 牌过三巡 (Drop=10660212, 体力=18); 2160422 谁在出千 (Drop=10660212, 体力=18)
- **E_GuildChallenge**: 2170001 #N/A (Drop=None, 体力=None); 2170002 #N/A (Drop=None, 体力=None)
- **E_ShuangHanStory**: 2160211 四神学院入口 (Drop=10660211, 体力=18); 2160212 狴里 (Drop=10660212, 体力=18)
- **E_ShuangHanBattle**: 2160214 四神学院入口 (Drop=10660214, 体力=18); 2160215 狴里 (Drop=10660215, 体力=18)
- **E_StoryExperience**: 2160301 奇点·霸下之里 (Drop=10610701, 体力=6); 2160302 奇点·囚牛之里 (Drop=10610702, 体力=6)
- **E_WorldBoss**: 2140101 狮鹫 (Drop=10630800, 体力=None); 2140102 月蚀兽 (Drop=10630810, 体力=None)
- **E_NewBloodMoon**: 2160701 群星跃迁之时·血月 (Drop=10600000, 体力=None); 2180001 群星跃迁之时·血月 (Drop=10633101, 体力=None)
- **E_EndlessWeekly**: 2110191 元素之章-起源 (Drop=None, 体力=30); 2110192 元素之章-混沌 (Drop=None, 体力=30)
- **E_ActivityGamePlay2**: 2160401 美食幻境·绝味 (Drop=10660401, 体力=6); 2160402 美食幻境·珍馐 (Drop=10660401, 体力=6)
- **E_Memory**: 2181001 记忆中的小丑 (Drop=None, 体力=None); 2181002 记忆中的计都 (Drop=None, 体力=None)
- **E_ActivityBoss**: 2160103 狐影明灭 (Drop=10660103, 体力=36); 2160104 狐影乍现 (Drop=10660104, 体力=48)
- **E_Trainning**: 2119900 星图空间·初级 (Drop=None, 体力=None); 2119901 星图空间·中级 (Drop=None, 体力=None)
- **E_Monopoly**: 2139701 冬夜-炼成复刻 (Drop=10660212, 体力=None); 2139702 冬夜-时之痕 (Drop=10630402, 体力=None)
- **E_ActivityWave**: 2160101 影迹寻踪 (Drop=10660101, 体力=12); 2160102 影迹谜局 (Drop=10660102, 体力=24)
- **E_ActivityGamePlay1**: 2160400 年兽盛宴 (Drop=10600000, 体力=None); 2160900 极限碰撞 (Drop=10660211, 体力=None)
- **E_MoonChapter**: 2111001 月之荒庭 (Drop=10611001, 体力=None); 2111051 月之暗面·新月 (Drop=10610951, 体力=None)
- **E_Endless**: 2110900 #N/A (Drop=10610900, 体力=30)

## 结论

- 24 种 SectionType（含未设置 Type 的 79 个）全部建立目录；运行态入口仅 E_Normal 与 E_Daily 的受限子集。
- 每类的代表 Section 已选好，可直接用于后续 per-type 入场测试。
- E_Battlepass 2,400 个 Section 是最大未实现类型（占比 74.9%）；其余未实现类型多为活动玩法，需逐活动评估是否已停服。
