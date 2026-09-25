---
Document-Type: Historical Report
Date: 2026-09-22
Status: CURRENT_AT_TIME
Superseded-By:
  - (read alongside current knowledge)
---

# Phase 9 — Packaged GameConfig and First Contact gates

## 1. Starting state

- Branch: `feat/network-bootstrap`
- Start commit: `328d503 feat(bootstrap): recover minimal WebGameConfig contract`
- Worktree: clean at phase start
- Baseline: 118 passed, 0 failed
- M2: Done; M3: Partial; FC and M4: Not Started

## 2. Gate results

| Gate | Result | Evidence |
|---|---|---|
| A — effective GameConfig | Done | targeted packaged entry decode and package-name selector |
| B — URL and transport | Done | effective `Login_Url`, literal endpoint construction |
| C — safe local redirect | Partial | design and fail-closed preflight exist; isolated guest does not |
| D — First Contact | Not Started | Gate C did not pass; APK was not launched |

## 3. Effective packaged configuration

`LoadLocalGameConfig` derives
`assets/42c44a368fc3544296d1e717a485b306.ab` from
`MD5("GameConfig" + "x2")`. The 1536-byte entry is decoded by the recovered
`X2Engine.GameStream` AES/Rijndael ECB path and parsed as UTF-8 JSON.

`AppConfig.DoGameConfig` normally calls `PlatformHelper.getPkgName()` and finds
the first exact match in each row's `packageName[]`. Therefore
`com.siva.project.x2` selects row 0:

```text
client_Type: product
packageType: product
gameServerName: TAP_BiliBili_Server
Login_Url: http://ssl-x2zh1login-release.17m3.com
language: CN
```

`GrayTestSwtich == 1` is a separate persisted override that selects the `gray`
row; a controlled compatibility run must use clean application data. Detailed
evidence is in `docs/gameconfig_resolution.md`; the recovered subset is in
`reverse_data/effective_gameconfig.json`.

## 4. URL, HTTP and TLS

The selected base has scheme `http`, host
`ssl-x2zh1login-release.17m3.com`, implicit port 80 and no base path.
`LoadGameConfigSuccess` appends `/apply/connectInfo` and `/apply/address`.
TLS classification is **Not Applicable**; no certificate bypass or APK patch is
needed for this selected path.

## 5. Local redirect and preflight

`docs/startup_routing.md` specifies an unmodified-client design using a
guest-local hostname override, guest-reachable local services, and
deny-by-default guest egress. Only the local bootstrap and X2 TCP destinations
may be allowed.

`tools/first_contact_preflight.py` is read-only and fail-closed. It checks exact
hostname resolution, bootstrap/TCP listeners, a matching operator-supplied
isolation record, runtime cleanliness and readable Git state. It never edits
hosts, firewall, certificate or routing configuration. Its local diagnostic run
returned `SAFE_TO_RUN=false`, as expected: no listeners or isolation evidence
were supplied. Production hostname resolution was deliberately not queried.

The present host has no available Android emulator/debug toolchain or audited
guest firewall policy. Consequently external isolation cannot be proved and
Gate C cannot pass.

## 6. First Contact result

Gate D was not executed. No APK process was started, no retired or third-party
endpoint was contacted, and no run ID was allocated.

| Observation | Result |
|---|---|
| Highest FC level | Not Started (below FC0) |
| Bootstrap endpoints hit | N/A |
| TCP connection | N/A |
| First frame | N/A |
| Message ID/name | N/A |
| CRC | N/A |
| Protobuf | N/A |
| Client-derived fixture | None |

M3 remains **Partial**, FC remains **Not Started**, and M4 remains **Not
Started**. No Login response or player business logic was implemented.

## 7. Verification

- Tests: **123 passed, 0 failed** (118 prior + 5 preflight tests).
- Ruff: unavailable.
- Mypy: unavailable.
- `git diff --check`: passed; line-ending conversion notices only.
- Pytest cache provider is disabled in project options because cache-directory
  creation stalls in this managed workspace; this does not change test logic.

## 8. Ratings

| Area | Grade | Basis |
|---|---|---|
| GameConfig Resolution | A | packaged bytes, decoder and selection function agree |
| Local Redirect Safety | C | fail-closed design exists, but no enforceable guest environment |
| Bootstrap Compatibility | B | static contract and local service tested; real client not observed |
| First Contact | D | correctly not attempted below the safety gate |
| Login Implementation Readiness | D | no real client frame exists; M4 remains out of scope |

## 9. Remaining blocker and next action

The largest blocker is a disposable Android emulator/VM with a documented
hostname override, host-only reachability and technically enforced
deny-by-default egress. After provisioning it, start the two local listeners,
produce the isolation evidence record, rerun preflight, and proceed only if it
prints `SAFE_TO_RUN=true`.

Phase 9 commits:

- `6e6b5d1 docs(config): resolve effective packaged GameConfig`
- `b814878 test(integration): add First Contact preflight checks`

Phase 9 stops here. No merge to `main` and no `v0.2-first-contact` tag are
permitted because M3 and FC are not Done.
