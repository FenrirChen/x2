---
Document-Type: Current Knowledge
Domain: Coverage
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - (none; still authoritative)
---

# Runtime Coverage 静态数据重审（基于新发现的 209 张表）

方法：将 76 个 coverage feature 与 265 张注册表逐一对照；只更新 `static_data_status_v2`/`static_data_note`，**runtime_logic_status 一律不动**。机器可读差异已写回 `analysis/coverage/runtime_coverage.json`（`static_data_reaudit` 节）。

共 69 个 feature 的静态数据状态发生变化。

| 旧 static_data_status → 新 | 数量 |
|---|---:|
| partial → partial (note added) | 56 |
| complete → complete (note added) | 7 |
| unknown → FOUND_BUT_UNMAPPED | 4 |
| missing → FOUND_BUT_UNMAPPED | 2 |

## 逐项明细

- **A Bootstrap / Login / Session / full re-login state restoration**: `partial` → `partial (note added)` — 静态表已全部解码：['activityboxgoods', 'activitytask', 'chapterinfo', 'drawparam', 'drawrules', 'functionopen']
- **B Lobby / Navigation / Guide / lobby init and UI stack**: `partial` → `partial (note added)` — 静态表已全部解码：['functionopen', 'titofightguidetable', 'titoguidetable']
- **B Lobby / Navigation / Guide / GuideStep/Tito persistence**: `partial` → `partial (note added)` — 静态表已全部解码：['functionopen', 'titofightguidetable', 'titoguidetable']
- **B Lobby / Navigation / Guide / ButtonClick/module opening**: `partial` → `partial (note added)` — 静态表已全部解码：['functionopen', 'titofightguidetable', 'titoguidetable']
- **B Lobby / Navigation / Guide / newbie skip/initial Chapter**: `partial` → `partial (note added)` — 静态表已全部解码：['functionopen', 'titofightguidetable', 'titoguidetable']
- **C Inventory / Item / Currency / stackable ItemAll/ItemUpdate**: `partial` → `partial (note added)` — 静态表已全部解码：['currencydisplay', 'currencytype']
- **C Inventory / Item / Currency / fixed grant/consume/negative balance**: `partial` → `partial (note added)` — 静态表已全部解码：['currencydisplay', 'currencytype']
- **C Inventory / Item / Currency / instance item reward destination**: `partial` → `partial (note added)` — 静态表已全部解码：['currencydisplay', 'currencytype', 'equibattrib', 'equibbase', 'equibexp', 'equibstage']
- **C Inventory / Item / Currency / lock/reclaim/compose**: `partial` → `partial (note added)` — 静态表已全部解码：['currencydisplay', 'currencytype']
- **D Hero / HeroAll/show/selection**: `partial` → `partial (note added)` — 静态表已全部解码：['playerattrib', 'playerlevelbonus', 'playerstage']
- **D Hero / fragment synthesis**: `partial` → `partial (note added)` — 静态表已全部解码：['playerattrib', 'playerlevelbonus', 'playerstage']
- **D Hero / level/star**: `partial` → `partial (note added)` — 静态表已全部解码：['playerattrib', 'playerlevelbonus', 'playerstage']
- **D Hero / attribute refresh**: `partial` → `partial (note added)` — 静态表已全部解码：['artifactbase', 'artifactfuse', 'mapinfo', 'playerattrib', 'playerlevelbonus', 'playerstage']
- **E Artifact / initial weapon unlock**: `partial` → `partial (note added)` — 静态表已全部解码：['artifactbase', 'artifactfuse', 'playerattrib', 'playerlevelbonus', 'playerstage']
- **E Artifact / level up/fuse/costs**: `partial` → `partial (note added)` — 静态表已全部解码：['artifactbase', 'artifactfuse']
- **E Artifact / socket/replace/remove**: `partial` → `partial (note added)` — 静态表已全部解码：['artifactbase', 'artifactfuse']
- **E Artifact / compose/god slot lock**: `partial` → `partial (note added)` — 静态表已全部解码：['artifactbase', 'artifactfuse']
- **F Equipment / equipment instances/list**: `partial` → `partial (note added)` — 静态表已全部解码：['dropbase', 'dropprop', 'equibattrib', 'equibbase', 'equibexp', 'equibstage']
- **F Equipment / equip/unequip/replace**: `partial` → `partial (note added)` — 静态表已全部解码：['equibattrib', 'equibbase', 'equibexp', 'equibstage', 'equibsuit']
- **F Equipment / experience/gold/random +3**: `partial` → `partial (note added)` — 静态表已全部解码：['currencydisplay', 'currencytype', 'equibattrib', 'equibbase', 'equibexp', 'equibstage']
- **F Equipment / lock/reclaim/set/loadout**: `partial` → `partial (note added)` — 静态表已全部解码：['equibattrib', 'equibbase', 'equibexp', 'equibstage', 'equibsuit']
- **G Skill / hero skill list**: `partial` → `partial (note added)` — 静态表已全部解码：['playerattrib', 'playerlevelbonus', 'playerstage', 'skillbase', 'skillhelper', 'skilllevel']
- **G Skill / skill level/material/prerequisite**: `partial` → `partial (note added)` — 静态表已全部解码：['playerattrib', 'playerlevelbonus', 'playerstage', 'skillbase', 'skillhelper', 'skilllevel']
- **G Skill / StarSkill/GodHole**: `partial` → `partial (note added)` — 静态表已全部解码：['playerattrib', 'playerlevelbonus', 'playerstage', 'skillbase', 'skillhelper', 'skilllevel']
- **H Battle Entry / ordinary MainMission FightData**: `partial` → `partial (note added)` — 静态表已全部解码：['chapterinfo', 'mapinfo', 'missionpredecessor', 'missiontable', 'playerattrib', 'playerlevelbonus']
- **H Battle Entry / resource/daily entry**: `partial` → `partial (note added)` — 静态表已全部解码：['dropbase', 'dropprop', 'extradroop', 'mapinfo', 'scenebase', 'sectiontable']
- **H Battle Entry / challenge/endless/special entry**: `partial` → `partial (note added)` — 静态表已全部解码：['challengetask', 'endlessdungeontask', 'mapinfo', 'scenebase', 'sectiontable']
- **H Battle Entry / activity/event battle entry**: `partial` → `partial (note added)` — 静态表已全部解码：['activityboxgoods', 'activitytask', 'mapinfo', 'monopolygrid', 'scenebase', 'seasonconfig']
- **H Battle Entry / retry/next stage/prepare/formation**: `partial` → `partial (note added)` — 静态表已全部解码：['mapinfo', 'playerattrib', 'playerlevelbonus', 'playerstage', 'scenebase', 'sectiontable']
- **H Battle Entry / sweep**: `partial` → `partial (note added)` — 静态表已全部解码：['mapinfo', 'scenebase', 'sectiontable']
- **I Battle Runtime / UUID/sign/session/disconnect**: `partial` → `partial (note added)` — 静态表已全部解码：['mapinfo', 'scenebase', 'sectiontable']
- **I Battle Runtime / FightDropData/DropValues**: `missing` → `FOUND_BUT_UNMAPPED` — 静态表已全部解码：['dropbase', 'dropprop', 'extradroop', 'mapinfo', 'scenebase', 'sectiontable']
- **I Battle Runtime / FightKillInfo**: `partial` → `partial (note added)` — 静态表已全部解码：['dailytask', 'mapinfo', 'scenebase', 'sectiontable', 'taskcondition', 'taskcontrol']
- **I Battle Runtime / disconnect/abandon/retry profile**: `partial` → `partial (note added)` — 静态表已全部解码：['mapinfo', 'scenebase', 'sectiontable']
- **J Battle Checkout / Settlement / signed checkout/idempotency**: `partial` → `partial (note added)` — 静态表已全部解码：['mapinfo', 'scenebase', 'sectiontable']
- **J Battle Checkout / Settlement / first clear/normal fixed gift**: `complete` → `complete (note added)` — 静态表已全部解码：['mapinfo', 'scenebase', 'sectiontable']
- **J Battle Checkout / Settlement / random/monster/sweep rewards**: `missing` → `FOUND_BUT_UNMAPPED` — 静态表已全部解码：['dropbase', 'dropprop', 'extradroop', 'mapinfo', 'scenebase', 'sectiontable']
- **J Battle Checkout / Settlement / XP/task/next unlock**: `partial` → `partial (note added)` — 静态表已全部解码：['dailytask', 'mapinfo', 'scenebase', 'sectiontable', 'taskcondition', 'taskcontrol']
- **K Mission / Chapter / mission/chapter/story list**: `partial` → `partial (note added)` — 静态表已全部解码：['chapterinfo', 'missionpredecessor', 'missiontable']
- **K Mission / Chapter / current chapter/section and next unlock**: `partial` → `partial (note added)` — 静态表已全部解码：['chapterinfo', 'missionpredecessor', 'missiontable']
- **K Mission / Chapter / chapter chest/star/story trigger**: `partial` → `partial (note added)` — 静态表已全部解码：['chapterinfo', 'collection', 'collectiondisplay', 'missionpredecessor', 'missiontable']
- **L DailyDungeon / Resource Dungeon / 25 dungeons/available sections**: `complete` → `complete (note added)` — 静态表已全部解码：['dailydungeon', 'extradroop']
- **L DailyDungeon / Resource Dungeon / stamina/attempts/unlock/reset**: `partial` → `partial (note added)` — 静态表已全部解码：['dailydungeon', 'dropbase', 'dropprop', 'extradroop']
- **L DailyDungeon / Resource Dungeon / fixed/random reward/attempt count**: `partial` → `partial (note added)` — 静态表已全部解码：['dailydungeon', 'dropbase', 'dropprop', 'extradroop']
- **L DailyDungeon / Resource Dungeon / MopReward/limit**: `complete` → `complete (note added)` — 静态表已全部解码：['dailydungeon', 'extradroop']
- **M Task / daily/weekly instance/period**: `complete` → `complete (note added)` — 静态表已全部解码：['challengetask', 'dailytask', 'taskcondition', 'taskcontrol']
- **M Task / battle/stamina/growth/online progress**: `complete` → `complete (note added)` — 静态表已全部解码：['dailytask', 'mapinfo', 'scenebase', 'sectiontable', 'taskcondition', 'taskcontrol']
- **M Task / fixed reward/idempotency**: `complete` → `complete (note added)` — 静态表已全部解码：['activityboxgoods', 'activitytask', 'challengetask', 'dailytask', 'seasonconfig', 'taskcondition']
- **M Task / activity point boxes**: `complete` → `complete (note added)` — 静态表已全部解码：['activityboxgoods', 'activitytask', 'dailytask', 'seasonconfig', 'taskcondition', 'taskcontrol']
- **M Task / daily 00/week Mon05**: `partial` → `partial (note added)` — 静态表已全部解码：['dailytask', 'taskcondition', 'taskcontrol']
- **N Shop / shop list/goods/query**: `partial` → `partial (note added)` — 商品 GoodsID→ItemID/数量、库存与刷新执行仍无静态定义（ShopGoodsGroup 无商品内容字段）
- **N Shop / buy/price/limit**: `partial` → `partial (note added)` — 商品 GoodsID→ItemID/数量、库存与刷新执行仍无静态定义（ShopGoodsGroup 无商品内容字段）
- **N Shop / refresh/cost/reset**: `partial` → `partial (note added)` — 商品 GoodsID→ItemID/数量、库存与刷新执行仍无静态定义（ShopGoodsGroup 无商品内容字段）
- **O Achievement / overview/detail/progress**: `partial` → `partial (note added)` — 静态表已全部解码：['achievement', 'achievementcondition', 'achievementconditionline', 'medal']
- **O Achievement / achievement reward**: `partial` → `partial (note added)` — 静态表已全部解码：['achievement', 'achievementcondition', 'achievementconditionline', 'medal']
- **P Draw / Gacha / pool config/rotation/cost**: `partial` → `partial (note added)` — 静态表已全部解码：['drawparam', 'drawrules']
- **P Draw / Gacha / single/ten/result/pity**: `partial` → `partial (note added)` — 静态表已全部解码：['drawparam', 'drawrules']
- **Q Mail / list/read/delete**: `unknown` → `FOUND_BUT_UNMAPPED` — 静态表已全部解码：['mailconfig', 'mailinfo', 'privatemail', 'privatemailcontrol', 'privatemailsystem']
- **Q Mail / claim/all**: `unknown` → `FOUND_BUT_UNMAPPED` — 静态表已全部解码：['mailconfig', 'mailinfo', 'privatemail', 'privatemailcontrol', 'privatemailsystem']
- **R Friend / list/apply/accept/delete**: `unknown` → `FOUND_BUT_UNMAPPED` — 静态表已全部解码：['friendlevel']
- **R Friend / stamina/friend coin/tasks**: `partial` → `partial (note added)` — 静态表已全部解码：['dailytask', 'friendlevel', 'taskcondition', 'taskcontrol']
- **S Club / Guild / create/join/member/donate**: `unknown` → `FOUND_BUT_UNMAPPED` — 静态表已全部解码：['guildchallengeinfo', 'guildlevel', 'guildpicture', 'guildwish']
- **S Club / Guild / guild challenge/reward**: `partial` → `partial (note added)` — 静态表已全部解码：['challengetask', 'guildchallengeinfo', 'guildlevel', 'guildpicture', 'guildwish', 'mapinfo']
- **U Activity / Event / activity list/open conditions**: `partial` → `partial (note added)` — 静态表已全部解码：['activityboxgoods', 'activitytask', 'seasonconfig']
- **U Activity / Event / activity task/shop/reward**: `partial` → `partial (note added)` — 商品 GoodsID→ItemID/数量、库存与刷新执行仍无静态定义（ShopGoodsGroup 无商品内容字段）
- **U Activity / Event / activity battle/tower/boss**: `partial` → `partial (note added)` — 静态表已全部解码：['activityboxgoods', 'activitytask', 'mapinfo', 'scenebase', 'seasonconfig', 'sectiontable']
- **U Activity / Event / season/battlepass/New Year/monopoly**: `partial` → `partial (note added)` — 静态表已全部解码：['activityboxgoods', 'activitytask', 'battlepass', 'battlepassaward', 'battlepasslevel', 'battlepasstask']
- **V Tutorial / Guide / skip flags/newbie finish/GuideStep163**: `partial` → `partial (note added)` — 静态表已全部解码：['functionopen', 'titofightguidetable', 'titoguidetable']
- **W Growth / Progression / hero/artifact/equipment/skill aggregation**: `partial` → `partial (note added)` — 静态表已全部解码：['artifactbase', 'artifactfuse', 'equibattrib', 'equibbase', 'equibexp', 'equibstage']

## 口径提醒

- `FOUND_BUT_UNMAPPED` 只表示客户端静态表已解码，不代表服务器运行态可用。
- Shop 保持缺口：商品内容字段在客户端不存在；随机掉落保持 SERVER_ONLY。
- 若重跑 `analysis/coverage/build_runtime_coverage.py` 会重建该 JSON，需合并 `static_data_status_v2` 字段（本轮脚本可重复执行）。
