# X2 Revival 2026-09-24 Preview — Release Build Report

## Artifacts

- Release root: `D:\demo\x2\releases\X2-Revival-20260924`
- ZIP: `D:\demo\x2\releases\X2-Revival-20260924-preview.zip`
- ZIP size: 2,146,414,540 bytes; SHA-256 `ada103883fffde6f86e7d0b3a793ada920d8864859ea5f3e25cbe716c3229ccd`
- Client: `client/X2-Revival.apk`, signed Revival v0.2 / original game 2.4 (202), SHA-256 `460dc657a8fb1b5410a4c0eaa5fac9433b45ecc54b7f3845afc626420946276d`
- Server entrypoint: `server/run_server.py`; `tools/start_server.ps1` starts HTTP 18080, game TCP 29000, null chat TCP 29001.
- Database: `save/demo.sqlite3`, SHA-256 `aca1328c10e81d2f1105ad6a65c2a3f4efa2759f3f0ca93481f0df24a9cd9e18`; public local account `revival / revival`.
- Base Git commit: `93c1d9753b8c218032eaff65c96587e4e4404fbb`. Current runtime includes uncommitted changes; this release is a snapshot, not that commit alone.
- Release contains 74 regular files. `FILES_SHA256.txt` lists every other file. ZIP contains a single `X2-Revival-20260924/` top level directory and passed ZIP integrity check.

## Runtime and network

Server requires Python 3.12 and standard library only. Setup creates a fresh virtual environment with no downloaded dependencies. Runtime catalogs in `server/src/x2server/data/` cover battle entry, battle hero base, economy, progression, jewels and wish; three equipment catalogs are under `server/analysis/progression/`. No raw APK extraction, asset bundles or `dump.cs` are needed at runtime.

Packaged APK `GameConfig.Login_Url` was decoded and verified as `http://10.0.2.2:18080`, `packageType=testpackage`. MuMu 12 guest to Windows host `10.0.2.2` was directly tested. Server returns the matching TCP host and null chat host. Default release service binds `127.0.0.1`. Cross-machine support is provided by `tools/configure_client.ps1 -HostIP <MuMu-reachable Windows IPv4>`: it reuses the existing GameConfig patch helpers, edits only `Login_Url`, neutralizes the old v1 signature metadata and signs with a fresh local key generated in `.runtime/`. The same chosen host is saved to `server/config/network.json`; on this path the service binds `0.0.0.0` for the private emulator network. JDK 11+ and OpenSSL are required only for this fallback. The configured APK was actually produced and `jarsigner -verify` completed in validation; the local key, passphrase, configured APK and unsigned intermediate are not in the distribution ZIP.

## Demo save

Created with SQLite backup API from the development test save, then sanitized **only in the copied database**. Removed battle entry/run/receipt/cost history and a repair-history path to the developer machine; ran `VACUUM` and `PRAGMA quick_check=ok`. Public local account retained. Login count reset. Player progression, heroes, inventory, equipment, artifact and task/wish state retained. At the user's request, staged demo stamina `mobility.power` was set to **9999** and the player revision incremented; SQLite integrity and final value were checked. This final stamina adjustment was checked in the staged database after live gameplay acceptance, rather than retesting the UI. Original active database `runtime/phase14/player.sqlite3` was not modified.

## Fresh-directory validation

- Staging was copied to `D:\demo\x2\release_validation\X2-Revival-20260924` with no packaged virtual environment. `tools/setup.ps1` created Python 3.12 venv and passed the demo database integrity check.
- Existing developer service was stopped before starting the validation server. Its `run_server.py` process listened on 18080/29000/29001. Process command line for PID 10740 was independently read and pointed to `release_validation\X2-Revival-20260924\server\run_server.py`; service log identified the matching guest host. HTTP controlInfo returned 200.
- Existing signed APK installation in MuMu was reused, as allowed. Public demo account login reached the level 60 lobby. Backpack and Hero screens opened and were visually checked. The main mission reached its formation/start panel. The user then performed manual entry checks and reported **no issue; acceptance passed**, covering main mission and DailyDungeon entry. Assistant stopped UI interaction when requested. No combat was performed by the assistant.
- The fallback client configurator was exercised in the validation copy using `10.0.2.2` as a safe test input; it created and signed an APK. The default packaged APK remained unchanged.

## Privacy and exclusions

Staging text and demo database were scanned for the developer path, username, private key headers, API key, authorization and cookie markers. No private secret was found. `revival / revival` is a deliberately public local demo credential. The ZIP excludes reference/original APK, active SQLite, backups, logs, `.venv`, `.runtime`, generated local signing key, configured APK, development docs and raw reverse engineering dumps. No upload was performed.

## Known limitations

Only 4 DailyDungeon groups and 20 sections have the current reward path; normal drop quantity 1 is a documented Revival temporary value pending recoverable official data. Broader battle types, shop, activity, mail, social, full chat, guide and some growth variants remain partial or unavailable. The default MuMu host address was verified on the current host; other machines should use the included configuration fallback if it fails. The demo account token lasts about one hour per server start. See distributed `docs/CURRENT_STATUS.md` and `docs/TROUBLESHOOTING.md`.
