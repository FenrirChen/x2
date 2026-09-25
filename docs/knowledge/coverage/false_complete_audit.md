---
Document-Type: Current Knowledge
Domain: Coverage
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - (none; still authoritative)
---

# 假完成 / 硬编码 / Compat / Stub 审计

扫描范围：`src/x2server/` 与 `tools/`（测试文件命中标 BENIGN_TEST_CONSTANT，不展开）。共 64 处命中；机器可读：`analysis/coverage/hardcoded_business_rules.json`。

## SINGLE_SAMPLE_IMPLEMENTATION（8）

- `src/x2server/player/progression.py:193` [HARDCODED_ID:1237907] `costs[1237907] = row["exp_required"]` — god exp item id
- `tools/dev/probe_all_section_battles.py:21` [HARDCODED_ID:1003] `heroes=[{"id": 1003, "state": 2, "level": 1, "star": 1}])` — hero Behemoth (dev sample)
- `tools/dev/render_daily_dungeon_reward_audit.py:23` [HARDCODED_ID:2130101] `"", "## 2130101 四种奖励", "",` — gold resource dungeon (dev sample)
- `tools/dev/render_daily_dungeon_reward_audit.py:33` [HARDCODED_ID:2130101] `"更新服务后的实机请求实际为金币本第二关 `2130102`（非提问中指定的 2130101）。用户反馈正常；该 run 的 SQLite `economy_grants` 为金币 1、光辉 30、神格经验 120、解神者经验 12，结算与金币持久化得到双重核对。第二个不同 Dungeon 的奖励隔离、入账、推送及重登` — gold resource dungeon (dev sample)
- `tools/dev/repair_phase20_state.py:26` [HARDCODED_ID:1003] `artifact = next(h for h in snapshot["heroes"] if h["id"] == 1003)["god_equip"]` — hero Behemoth (dev sample)
- `tools/export_economy_catalog.py:16` [HARDCODED_ID:2110001] `next_id = 2110001` — main chapter/section seed (dev sample)
- `tools/prepare_hero_mobility_account.py:29` [HARDCODED_ID:2010000] `main_chapter=2010000, main_section=2110001,` — main chapter (dev sample)
- `tools/prepare_hero_mobility_account.py:30` [HARDCODED_ID:1003] `heroes=[{"id": 1003, "state": 2, "level": 1, "star": 1}],` — hero Behemoth (dev sample)

## TEMP_COMPAT（43）

- `src/x2server/__init__.py:1` [MARKER:compat] `"""X2 protocol compatibility research package."""`
- `src/x2server/bootstrap/local_identity.py:3` [MARKER:temporary] `TEMPORARY_COMPAT: one configured development account, ephemeral tokens, no`
- `src/x2server/bootstrap/models.py:135` [MARKER:compat] `Values supplied here are local compatibility values, not recovered official`
- `src/x2server/bootstrap/models.py:183` [MARKER:compat] `"""Serialize a deterministic UTF-8 compatibility response."""`
- `src/x2server/bootstrap/models.py:250` [MARKER:compat] `"""Serialize a deterministic UTF-8 compatibility response."""`
- `src/x2server/bootstrap/models.py:325` [MARKER:compat] `"""Build local-only compatibility values from safe runtime settings."""`
- `src/x2server/bootstrap/models.py:329` [MARKER:compat] `service_app_id="x2-local-compat",`
- `src/x2server/config/settings.py:8` [MARKER:temporary] `# TEMPORARY_COMPAT: defensive local limit, not a recovered original constant.`
- `src/x2server/player/battle.py:116` [MARKER:compat] `This is a single-account compatibility receipt, not replay verification.`
- `src/x2server/player/battle_entry.py:19` [MARKER:compat] `"""Client-compatible entry rejection; reason remains server-side."""`
- `src/x2server/player/battle_entry.py:43` [MARKER:compat] `# Explicit Revival compatibility: the original weekly calendar and attempt`
- `src/x2server/player/economy.py:386` [MARKER:compat] `"RUNTIME_BATTLE_DROP", "SWEEP_REWARD", "EXTRA_DROP", "COMPAT_REWARD")}`
- `src/x2server/player/economy.py:406` [MARKER:compat] `compat = RewardCompatibilityPolicy.manual_gold(profile, run_uuid)`
- `src/x2server/player/economy.py:407` [MARKER:compat] `if compat:`
- `src/x2server/player/economy.py:409` [MARKER:compat] `grants.append(compat)`
- `src/x2server/player/economy.py:414` [MARKER:compat] `key = "COMPAT_REWARD" if grant.source == "COMPAT_GOLD_DUNGEON" else grant.source`
- `src/x2server/player/hero.py:12` [MARKER:temporary] `# TEMPORARY_COMPAT: the client initializes GoldEquipAttr for every owned hero.`
- `src/x2server/player/login.py:39` [MARKER:compat] `# Explicit empty collections for the first controlled compatibility probe.`
- `src/x2server/player/progression.py:118` [MARKER:compat] `"compat": "REVIVAL_COMPAT"}`
- `src/x2server/player/progression.py:182` [MARKER:compat] `"compat": "REVIVAL_COMPAT"}`
- `src/x2server/player/reward_system.py:71` [MARKER:compat] `"source": "COMPAT_GOLD_DUNGEON", "official": False,`
- `src/x2server/player/reward_system.py:78` [MARKER:compat] `config = profile.get("compat_policy")`
- `src/x2server/player/reward_system.py:81` [MARKER:compat] `return RewardGrant("COMPAT_GOLD_DUNGEON", profile["section_id"], run_id,`
- `src/x2server/player/shop.py:25` [MARKER:compat] `COMPAT_STOCK = 999999`
- `src/x2server/player/shop.py:67` [MARKER:compat] `"canBuyTimes": self.COMPAT_STOCK, "hasBuyTimes": self._count(player_id, goods_id),`
- `src/x2server/player/shop.py:111` [MARKER:compat] `or self._count(player_id, goods_id) + buy_num > self.COMPAT_STOCK):`
- `src/x2server/player/store.py:1` [MARKER:compat] `"""SQLite player storage. Initial values are explicit local compatibility defaults."""`
- `src/x2server/player/wish.py:216` [MARKER:compat] `"compat": "REVIVAL_COMPAT"})`
- `src/x2server/player/wish.py:257` [MARKER:compat] `# most recently drawn compatible pool if the client asks for a result.`
- `src/x2server/protocol/protobuf.py:170` [MARKER:compat] `"""Decode known fields and safely skip protobuf-compatible unknown fields."""`
- `tools/dev/export_equipment_strengthen_catalog.py:22` [MARKER:compat] `"interpretation": "AttribSRC 3 candidate range for compatibility strengthen events; random roll is REVIVAL_COMPAT"},`
- `tools/dev/render_daily_dungeon_reward_audit.py:26` [MARKER:temporary] `"- NORMAL_DROP：`DroopDisplay=[1237901]` 预览金币；`DropValueID=10630101`。官方金币数量与概率未解；Revival 临时规则在普通胜利结算追加金币 1。",`
- `tools/dev/render_daily_dungeon_reward_audit.py:31` [MARKER:temporary] `"用户明确授权临时将普通胜利资源掉落数量设为 **1**，后续再替换为实际数据。实现只在每节 `DroopDisplay` 恰有一个可入账 ItemID 时使用该 ItemID ×1；不从名称、相邻 ID 或扫荡数值推算。4 个 Dungeon/20 个 Section 可完整执行此兼容规则，其余 16 个有预览但多候`
- `tools/dev/render_daily_dungeon_reward_audit.py:32` [MARKER:compat] `"固定奖励继续按各节 FirVReward/VReward 解析，`Gift.E_Random` 按客户端静态 `Probability` 抽取并与收据共同持久化；正常掉落单独由 `DailyDungeonRewardCatalog.compat_normal_drop` 决定。结算事务同时交付固定奖与临时掉落，重试读`
- `tools/dev/repair_phase20_state.py:1` [MARKER:compat] `"""One-time, guarded repair of the Phase 20 test player's earlier compat writes."""`
- `tools/dev/repair_phase20_state.py:27` [MARKER:compat] `if artifact != {"compat": "REVIVAL_COMPAT", "id": 1503, "level": 0, "star": 5}:`
- `tools/first_contact_preflight.py:56` [MARKER:placeholder] `"""Allow only the tracked placeholder in the runtime directory."""`
- `tools/first_contact_runner.py:120` [MARKER:compat] `service_app_id="x2-local-compat",`
- `tools/first_contact_runner.py:183` [MARKER:temporary] `parser.add_argument("--local-account", action="store_true", help="Use X2_LOCAL_ACCOUNT and X2_LOCAL_PASSWORD for the temporary local identity bridge")`
- `tools/local_game_server.py:32` [MARKER:compat] `RecoveredWebGameConfig(service_app_id="x2-local-compat", pbs_server=guest_http,`
- `tools/patch_wish_thumbnails.py:1` [MARKER:fallback] `"""Build a reversible IL2CPP thumbnail fallback for the confirmed X2 2.4 client.`
- `tools/patch_wish_thumbnails.py:4` [MARKER:fallback] `pool covers are present, so the fallback loads a cover only when the original`
- `tools/prepare_hero_mobility_account.py:22` [MARKER:placeholder] `raise ValueError("expected the Phase 15 placeholder chapter and section")`

## DATA_DRIVEN_DEFAULT（13）

- `src/x2server/player/economy.py:28` [HARDCODED_ID:1237901] `CURRENCIES = {1237901: "gold", 1237902: "crystal", 1237906: "equip_exp", 1237907: "hero_exp",` — gold item id
- `src/x2server/player/economy.py:408` [HARDCODED_ID:1237901] `grants = [g for g in grants if not (g.source == "RUNTIME_BATTLE_DROP" and g.item_id == 1237901)]` — gold item id
- `src/x2server/player/progression.py:166` [HARDCODED_ID:1237901] `costs[1237901] += row["level_up_gold_cost"]` — gold item id
- `src/x2server/player/progression.py:176` [HARDCODED_ID:1237901] `costs[1237901] += row["fuse_gold_cost"]` — gold item id
- `src/x2server/player/progression.py:191` [HARDCODED_ID:1237907] `if not row["next_level"] or hero["level"] >= snapshot["level"] or req.get("upstarConsumeItemId",0) not in (0,1237907):` — god exp item id
- `src/x2server/player/progression.py:227` [HARDCODED_ID:1237901] `costs[1237901] += row["gold_cost"]` — gold item id
- `tools/dev/audit_daily_dungeon_coverage.py:19` [HARDCODED_ID:1237901] `currencies = {1237900, 1237901, 1237902, 1237906, 1237907, 1237908, 1237910, 1237911}` — gold item id
- `tools/dev/audit_daily_dungeon_rewards.py:20` [HARDCODED_ID:1237901] `currencies = {1237900, 1237901, 1237902, 1237906, 1237907, 1237908, 1237910, 1237911}` — gold item id
- `tools/dev/render_daily_dungeon_reward_audit.py:26` [HARDCODED_ID:1237901] `"- NORMAL_DROP：`DroopDisplay=[1237901]` 预览金币；`DropValueID=10630101`。官方金币数量与概率未解；Revival 临时规则在普通胜利结算追加金币 1。",` — gold item id
- `tools/dev/render_daily_dungeon_reward_audit.py:29` [HARDCODED_ID:2130101] `"25 个 Dungeon 中，20 个有关联 E_Daily 的资源预览（1 个单一资源，19 个多资源），5 个只关联其他 SectionType。SectionTable 邻近的 `DroopDisplayProbability` 在资源本中仍是 ItemID 列表；`DroopLimit`/`DroopLimi` — gold resource dungeon (dev sample)
- `tools/dev/repair_phase20_state.py:46` [HARDCODED_ID:1237901] `delta[1237901] += row["level_up_gold_cost"]` — gold item id
- `tools/dev/repair_phase20_state.py:50` [HARDCODED_ID:1237901] `delta[1237901] -= ranks[1]["level_up_gold_cost"]` — gold item id
- `tools/dev/repair_phase20_state.py:61` [HARDCODED_ID:1237901] `snapshot["gold"] += delta.pop(1237901)` — gold item id
