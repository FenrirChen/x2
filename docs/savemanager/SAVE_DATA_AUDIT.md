# SAVE_DATA_AUDIT.md — 存档数据边界审计（Account → Save Ownership Graph）

2026-10-27 本地并发优化补充：持久化所有权范围与存档格式不变。导入/导出冷却复用全局`server_settings`的`save-limit:`键，不随存档迁移、回滚；后台存档子进程的临时文件会清理，正式覆盖前备份仍每账号仅保留一份。checkpoint改用后台独立连接，维持WAL和FULL同步。详见[并发优化记录](../knowledge/database_optimization_20261027.md)。

任务：存档管理（导出/导入）第一阶段审计产物。
状态：**COMPLETE — 完整回答"一个账号的完整游戏状态由哪些数据组成"**。
2026-10-11 发布复审：实际数据库共 98 张业务表，存档包括 93 张玩家表及 players.snapshot。已补入后来新增的 10 张表；下方 63/60 表数为首次审计历史基线，当前完整字段清单以 save_boundary.json 为准。`validate_boundary.py` 已对当前活体库通过。
机器可读清单：`tools/savemanager/save_boundary.json`（由 `tools/savemanager/generate_audit.py` 从活体库生成，审计与实现共用同一份清单，不允许漂移）。
审计基线：活体库 `runtime/phase14/player.sqlite3`（`PRAGMA user_version=2`）＋ `src/x2server/player/` 全部模块源码。未假设 schema，全部结论来自 `sqlite_master` 实际 DDL 与代码交叉验证。

## 1. 数据库发现

| 项 | 值 |
|---|---|
| 数据库类型 | SQLite 3（单文件） |
| 活体文件 | `runtime/phase14/player.sqlite3`（服务器启动参数 `--database`/`X2_DB_PATH` 指定，`tools/local_game_server.py` → `PlayerStore`） |
| schema 来源 | 代码内建 DDL（`PlayerStore.__init__` + 各 player 模块 `CREATE TABLE IF NOT EXISTS`/`_add_column`），`PRAGMA user_version=2` |
| journal 模式 | 当前为 `WAL`、`synchronous=FULL`；导出用一致读快照，导入用 `BEGIN IMMEDIATE` 原子写事务 |
| ORM | 无 ORM；`sqlite3.Row` + 参数化 SQL 直读直写 |
| migrations | `user_version` 门（0/1/2）+ 各模块 `_add_column` 幂等补列；无独立迁移框架 |
| 表总数 | 63（含 `accounts`/`players` 两个身份表；其余 60 张为玩家游戏状态/账本/凭据表） |

服务器全局只有这一份持久化存储。全代码检索确认：**除 SQLite 外不存在任何文件型玩家持久化**（`src/` 内仅有 DB 文件创建/备份两处 `mkdir`，无 write_text/write_bytes 落盘玩家数据）。

## 2. Ownership Graph（Auth Account → Player → 全部状态）

```
accounts（登录身份，排除于存档）
    │  accounts.player_id ──1:1── players.id
    │  accounts.username == players.account（代码级双绑，见 accounts.py get_by_player）
    ▼
players（身份行；snapshot 列 = 主存档，其余列排除）
    │  players.id = player_id（全局归属键）
    ├────────────────────────────── 直接归属（owner 列 = player_id）──────────────────────────────
    │  经济/背包：inventory, economy_events, economy_grants, economy_checkouts, economy_clears,
    │            economy_tasks, economy_runs, pending_rewards, pending_reward_instances(run_id→economy_runs),
    │            reward_settlement_audit, item_opt_receipts, shop_receipts, shop_purchase_counts,
    │            shop_compat_counts, shop_refreshes, wish_state, wish_pity, wish_last_result,
    │            wish_receipts, fight_drop_observations
    │  养成/角色：equipment_instances, equipment_enhancements(equip_id→equipment_instances.id),
    │            equipment_main_growth(equip_id→equipment_instances.id), appearance_wear,
    │            appearance_voice_unlock, appearance_shop_purchases, appearance_shop_receipts,
    │            collection_awards, favor_touch_log, birthday(在 players.snapshot), bag_jewel_seen,
    │            bag_operation_receipts, college_state(FK→players.id)
    │  战斗/关卡：battle_entries, battle_costs, battle_unresolved_rewards, battle_receipts(uuid→battle_entries),
    │            battle_checkout_wire(uuid→battle_entries), battle_shop_visits, battle_shop_purchases,
    │            battle_shop_pickups, battle_receipts 之外的章节：chapter_objectives, chapter_signals,
    │            chapter_dp_floors, chapter_dp_migrations, challenge_task_state, task_boxes,
    │            task_history, task_periods, sweep_receipts, fight_drop_items(report_id→observations.id),
    │            fight_drop_claims(report_id→observations.id)
    │  成就/系统：achievements, achievement_events, achievement_receipts, progression_receipts,
    │            player_mail, gift_package_claims, gift_package_daily_claims, gift_package_receipts,
    │            star_chart_receipts
    └──────────── 与 snapshot 的交叉引用 ────────────
       players.snapshot JSON 内 heroes[].equips[].equip_id ──→ equipment_instances.id
```

主存档 `players.snapshot`（JSON，乐观 revision）：gold/crystal/exp/hero_exp/equip_exp/daily_activity/week_activity/birthday/level/nickname/head_icon/scene_icon/show/main_chapter/main_section/mobility{power,…}/star_chart{auto_add,charge_count,day,points,skills}/terminal{blocked,blogs,letters}/test_challenge_unlocks/guide_groups/heroes[（id,state,level,star,skills[],favor{},equips[{position,equip_id}],god_equip{id,level,star,jewels{}}）]。god_equip.jewels 引用的是 inventory 道具 ID，不是装备实例 ID（`achievements.py:68`）。

## 3. 逐表清单（63 张）

图例：IN = 属于存档，导出并导入覆盖；OUT = 排除； join = 归属经外键推导。
逐表的列清单/主键/blob 列见 `save_boundary.json`（本文件不重复罗列 400+ 列，以机器清单为准）。

### 3.1 身份表

| 表 | 主键 | owner | 归属 | 判定 | 理由 |
|---|---|---|---|---|---|
| accounts | account_id | player_id→players.id | 认证 | **OUT** | password_hash/status 是登录身份；导入不得覆盖目标账号凭据（任务第六节） |
| players | id | —（本体） | 认证+存档 | **特殊** | `snapshot` 列 = 主存档（IN，导入覆盖+ID remap）；`id/account/created_at/login_count/revision` = 身份与账号活动字段（OUT，保留目标行） |

### 3.2 玩家状态表（全部 IN）

经济/背包（18）：`inventory`、`economy_events`、`economy_grants`、`economy_checkouts`、`economy_clears`、`economy_tasks`、`economy_runs`、`pending_rewards`、`pending_reward_instances`、`reward_settlement_audit`、`item_opt_receipts`、`shop_receipts`、`shop_purchase_counts`、`shop_compat_counts`、`shop_refreshes`、`wish_state`、`wish_pity`、`wish_last_result`。

养成/角色（13）：`equipment_instances`、`equipment_enhancements`、`equipment_main_growth`、`appearance_wear`、`appearance_voice_unlock`、`appearance_shop_purchases`、`appearance_shop_receipts`、`collection_awards`、`favor_touch_log`、`bag_jewel_seen`、`bag_operation_receipts`、`college_state`（唯一显式 FK：`REFERENCES players(id)`）、`wish_receipts`。

战斗/关卡/任务（20）：`battle_entries`、`battle_receipts`(join)、`battle_checkout_wire`(join)、`battle_costs`、`battle_unresolved_rewards`、`battle_shop_visits`、`battle_shop_purchases`、`battle_shop_pickups`、`chapter_objectives`、`chapter_signals`、`chapter_dp_floors`、`chapter_dp_migrations`、`challenge_task_state`、`task_boxes`、`task_history`、`task_periods`、`sweep_receipts`、`fight_drop_observations` + `fight_drop_items`(join) + `fight_drop_claims`(join)。

成就/邮件/礼包/星图（9）：`achievements`、`achievement_events`、`achievement_receipts`、`progression_receipts`、`player_mail`、`gift_package_claims`、`gift_package_daily_claims`、`gift_package_receipts`、`star_chart_receipts`。

以上每张表：owner 字段 `player_id`（或经 join 推导），导出/导入行为：导出全量行、导入先删目标全部行再插入并重映射 owner。

### 3.3 join 归属推导（无 player_id 列的表）

| 表 | 归属推导 | 判定 |
|---|---|---|
| battle_receipts | `uuid == battle_entries.uuid`（同一战斗 run 的幂等收据，battle.py:127/212/272） | IN |
| battle_checkout_wire | `uuid == battle_entries.uuid`（checkout 原始 wire 缓存） | IN |
| fight_drop_items | `report_id == fight_drop_observations.id` | IN |
| fight_drop_claims | `report_id == fight_drop_observations.id` | IN |

## 4. ID remap 规则（导入时）

| ID | 类型 | 唯一性范围 | 引用方 | remap 规则 |
|---|---|---|---|---|
| player_id | INTEGER | 全表归属键 | 所有状态表 owner 列 | 一律改写为目标账号 player_id |
| equipment_instances.id | INTEGER AUTOINCREMENT | 全局 | snapshot.heroes[].equips[].equip_id；equipment_enhancements.equip_id；equipment_main_growth.equip_id | 目标旧行删除后若该 id 空闲则原样保留；与他号冲突才分配新 id，并同步重写上述三处引用 |
| fight_drop_observations.id | INTEGER AUTOINCREMENT | 全局 | fight_drop_items.report_id；fight_drop_claims.report_id | 同上策略，冲突才 remap |
| player_mail.id | INTEGER AUTOINCREMENT | 全局 | 无 DB 内引用（客户端运行时引用） | 一律丢弃原 id 由导入分配新 id（避免跨号碰撞，最安全） |
| battle_entries.uuid / economy_runs.uuid / request_key / run_id | TEXT | 客户端生成、全局 | battle_receipts/battle_checkout_wire/pending_reward_instances/reward_settlement_audit 等 | 原样保留；导入 integrity check 发现与库内既有行冲突 → 整体 ROLLBACK 并报错（TEXT 键由客户端保证唯一） |
| sqlite_sequence | — | — | — | 导入事务内对 equipment_instances/player_mail/fight_drop_observations 提升到 max(id)，防止后续插入复用历史 id |

## 5. EXCLUDED_FROM_SAVE（逐项理由，无 UNKNOWN）

| 项 | 类别 | 排除理由 |
|---|---|---|
| accounts 整表 | 身份 | 登录名/PBKDF2 password_hash/status/last_login_at 是认证身份，存档代表游戏状态不代表登录身份；跨号导入后 B 的身份必须仍是 B（任务第六节） |
| system_mail_issues 整表 | 发放历史 | 一次性邮件发放资格由服务器保留；导入前保留目标账号历史，并识别来源存档中的既有邮件，禁止迁移或回滚重置资格。 |
| players.id / account | 身份 | player 主键与用户名绑定，是"当前 Release Server 内的账号主身份" |
| players.created_at / login_count | 身份活动 | 建档时间与登录计数属于账号活动数据，不影响游戏表现 |
| players.revision | 技术 | 乐观并发版本号，导入提交后由服务器维护 |
| repair_history 整表 | 运维 | 服务器侧修复操作记录，无 player 归属，不影响任何游戏状态 |
| 在线 session token / game token | 技术 | 仅存于 LocalIdentityService 内存 dict，重启即失效，DB 无对应列（无可导出对象） |
| 导入/导出审计日志 | 技术 | 本次功能新增的操作审计（见 SAVE_MANAGER_IMPLEMENTATION.md），属运营数据 |
| 数据库全局自增序列 | 技术 | sqlite_sequence 由导入事务按第 4 节规则维护，不进存档文件 |
| TCP connection / 临时 nonce | 技术 | 纯内存运行时对象 |

**除上表外，数据库中不存在任何其他未被分类的对象**（63 张表全部出现在第 3 节；无"UNKNOWN 但先不导出"状态）。

## 6. BLOB / JSON 大对象

- response BLOB 列（15 处）：`*_receipts.response`、`battle_entries.response`、`battle_receipts.response`、`wish_last_result.response`、`fight_drop_observations.body`、`battle_checkout_wire.checkout` — 均为服务端生成的 protobuf/原始响应缓存，导出/导入按字节原样保留（存档内以 `blobs/` 文件承载，manifest 记 SHA256）。
- JSON/TEXT 结构列（10 处）：`players.snapshot`、`college_state.state_json`、`economy_grants.rewards`、`player_mail.attachments`、`battle_entries.team_json` 等 — 原样保留；仅 `players.snapshot` 内的 `heroes[].equips[].equip_id` 按 ID remap 规则重写。

## 7. 客户端本地状态检查（任务第八节）

| 发现 | 分类 | 处理 |
|---|---|---|
| 原客户端 `LoginManager.SaveAccount/SavePassword`（dump.cs 779496/779427 等）把账号凭据写入本地持久化 | B 类（账号游戏状态？） | 属**原版客户端既有行为**（注册/登录成功后缓存凭据用于回显），本功能不新增、不读取、不修改该缓存；服务器重登录以账号密码认证为准，不依赖该缓存，不影响存档恢复一致性 |
| PlayerPrefs（画质/声音/GrayTestSwtich 等） | A 类 | 纯客户端设置，与账号游戏状态无关 |
| persistentDataPath / 本地 tutorial flag | 无证据 | 服务器登录时全量推送快照/任务/引导（login.py snapshot_push），服务器状态覆盖本地显示；无未同步的游戏状态 |
| 本功能新增客户端代码 | — | 仅内存持有凭据（Intent extra 传递），不写任何持久化存储；权限最小化（无存储权限，SAF） |

## 8. 一致性结论

一个账号的完整游戏状态 =
`players.snapshot`（主存档 JSON）
∪ 60 张玩家状态表按 player_id（含 4 张 join 推导归属表）的全部行
（身份/运维/技术字段按第 5 节排除）。

导出=该集合在单一只读事务内的一致快照；导入=目标账号同集合的删除+重放+重映射，全程单写事务，失败整体回滚。任务第四节的验证问题**已完整回答**，可以进入实现阶段。


## 2026-10-21：扫荡每日额度边界

`server_sweep_limits(player_id,day,used)` 为服务器保存的账号日限计数，每账号只保留一行；北京时间00:00后的首次扫荡切换日期，所有关卡共享15次。该表明确列入 `GLOBAL_TABLES`，不导出、不随导入替换，防止读档恢复次数。旧存档格式保持兼容。扣额度、体力、发奖与扫荡回执同事务，失败全部回滚；重试命中回执，不重复扣额度。上线前的历史扫荡不追溯扣减，本规则从上线后的首次扫荡开始计数。客户端原数量选择器仍可选择较大的数量，超过当日剩余额度由服务器拒绝，未修改APK。
