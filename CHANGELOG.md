# Changelog

## Unreleased

- Restored every 宝石姬 in shop 806: the four unused single-stone rows
  (1911701/1911901/1912001/1912701) and the 8 absent families
  (莫格尔祖母绿/蓝色晨曦猎豹/德古拉的情人/荷鲁斯之眼/琅玕玉树/希望之光/贵霜的余晖/乘雷之玉)
  now fill the client's group-150 rows as 50-stone bundles (300 魂石源质, the
  same 6/stone as the single slots); all gem slots switched from a 50-stone
  lifetime cap to an E_Month 50-stone quota so a player can keep exchanging
  after the first 4★.

- Fixed the 购买因果 (134/137) overcharge: the page prices purchases from the
  client's own `ServerData.PowerPrice` / `PowerTimesInterval` (factory defaults
  `[60,60,60,60,60]` and `{1,2,4,6,10}`), which this server never published, so
  every tier displayed 60 while `POWER_BUY_PRICES` charged a 20-tier ladder
  (20/20/40/…/220/…/1000). The price is now flat 60 and `server_config`
  publishes the same two tables, so the displayed price equals the charge.
- Added `player/power_refund.py`: on login/reconnect it replays the
  `power-buy:<day>:<ordinal>` ledger entries against the old ladder and mints a
  one-off 光辉 refund mail (`source_key = power_refund_20261031:<player_id>`),
  so players already overcharged get the difference back exactly once.


- Element compose limits now refresh at Beijing Monday 00:00, preserving
  lifetime element experience. PR97's half-month inference misread the native
  one-based AnswerConfig.RightAnswer and is not used.
- Compose limits include the current run once and reject the next unit after
  the period cap, instead of allowing the cap to be bypassed within one run.
- The native profile week number follows time instead of the constant 272;
  actual reward and compose resets keep the approved Monday calendar.
- Preserved the Phase 11 Revival client patch and controlInfo work as a Git baseline.
- Added a hash-checked startup probe, cold-boot launcher and per-run local evidence.
- Identified GLES version declaration as a graphics compatibility issue; enabling
  GLESDynamicVersion with host GPU restores the loading screen without changing APKs.

- Resolved the packaged GameConfig row and HTTP bootstrap base for
  `com.siva.project.x2` from targeted static evidence.
- Added fail-closed, read-only First Contact preflight checks and routing docs.
- Recovered and implemented the minimal two-stage X2 bootstrap contract from
  static client evidence.
- Added offline fixtures and tests for WebGameConfig and server-address mapping.

- Initialized the protocol-core workspace and engineering documentation.
- Added recovered X2 PackInt, CRC32, protobuf, packet framing and stream decoding.
- Added the confirmed core message registry, synthetic fixtures and packet inspector.
- Added the asyncio TCP connection lifecycle, dispatcher, backpressure and localhost tests.
- Added a standard-library bootstrap HTTP service and explicitly synthetic config model.
