# Changelog

## Unreleased

- 元素之章 recipe `ComposeNumLimit` now resets every half-month (Beijing 1..15 /
  16..month end) instead of accumulating for the lifetime of the account, so the
  配方页「可合成次数」 refreshes again; the weekly refresh keeps resetting only the
  周光 (`EndlessWeekVowOfStone`). Evidence: client `AnswerConfig` 281048 answers
  「15 日」, and `ElementComposeModule_MaxComposeNum` reads the cap from
  `Weekly.FormulaComposeAll`. `ElementExpAll` stays lifetime.
- Element compose now enforces the native cap (`numLimit - (all - single)`) without
  subtracting the current run twice, so a half-month cannot exceed `numLimit`.
- `L2C_CheckFightProfile.currentWeek` follows the clock instead of the hard-coded
  272, so `EndlessInfo` "本周结束" countdown is no longer pinned to 1975.
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
