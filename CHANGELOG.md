# Changelog

## Unreleased

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
