# Phase 18 — Quiet chat and first battle

2026-09-23, development checkpoint. Revival v0.2 / official 2.4 remains unchanged.

## Confirmed

- `/apply/chatNode` now supplies a loopback-backed quiet channel on guest
  `10.0.2.2:29001`. The outer JSON list contains `ChannelInfo`; `channel` is
  itself a JSON string containing the channel list. ChatJoin 521/522 uses
  channelId field **6**, success code 10. The client joined successfully.
- No message delivery, history, broadcasts or chat persistence are implemented.
  Lobby observations showed no repeated chat handshake after the initial main
  connection reconnect. During battle the client stopped chat traffic and the
  idle connection closed after 120 seconds; this is not evidence of a retry loop.
- First selectable mission is **2110801**, chapter **2010100**, scene **2210801**,
  `LevelMap_YuRenChuan`. Clicking Start Battle sends FightData 126 directly.
- Added bounded FightData 130 and DelFightProfile 399/398 responses. FightData's
  nested hero list starts at protobuf field 2. HeroGodEquip must be a present
  empty object. Entries and replay responses are retained in SQLite
  `battle_entries`; player snapshot and economy are unchanged.
- After a cold emulator start, the client loaded the scene and introductory
  dialogue. Movement and skill cooldown were verified. The user then manually
  completed combat and confirmed it worked. This mission uses scripted trial
  characters, so this does not validate ordinary hero combat scaling.
- Two paths back to the hall (team page and its hero picker) did not reproduce
  the reported stacked interactive UI. User explicitly permitted deferral.

## Remaining work / current probe

- FightDropData **264/266** was requested during battle; its missing response
  triggered a **main game** reconnect. The new build explicitly returns unsupported
  code 13; no authoritative drop ledger exists and drops are not verified.
- Skipping the post-combat story sent CheckoutMainMissionSign **887** and
  FightKillInfo **316**. Added a local practice receipt for 887 -> 152, with
  duplicate-result replay and rejection of conflicting submissions. It closes
  the latest matching entry within one hour, trusting the local completion claim;
  it does not verify combat replay, grant rewards or advance the chapter.
  Kill/task accounting 316 -> 318 explicitly returns unsupported code 13.
  These responses are deployed in server04 but **client settlement UI validation
  is pending another user-played battle**. Do not report it as verified yet.
  There is no L2C_CheckoutMainMissionSign; the existing result message is 152.
- CollegeModule.RefreshTrainRedDot still throws during hall initialization at
  level 60 because the recovered growth-base snapshot is incomplete.
- A warm process stalled while loading with Unity's
  `Using memoryadresses from more that 16GB of memory`. A cold emulator restart
  avoided it in this run. This is a workaround, not a permanent compatibility fix.
- Fight attributes are bounded compatibility values for local hero 1003;
  no cost, rewards, completion or inventory changes are made by entry.

## Evidence and protection

- `runtime/phase18/server03.err.log`, `cold-fight-later.png`, `playfield.png`,
  `move-skill.png`, `user-completed.png`, `checkout.png` retain local evidence.
- SQLite backup: `runtime/phase18/before-battle.sqlite3`, created before the
  battle table. Never overwrite. Active DB remains `runtime/phase14/player.sqlite3`.
- Player remains level 60, power 149. No APK replacement, data wipe or Reference
  modification. Visible emulator remains available for manual play.
- Tests: **147 passed**, including chat framing/heartbeat, entry replay and
  practice receipt replay/conflict protection with unchanged player snapshot.
- Phase 17 records an earlier failed startup attempt; its "no changes" statement
  is historical and does not describe this working tree. Existing hero godEquip
  and three lobby-query corrections were present when Phase 18 resumed and are
  preserved alongside the current work.
