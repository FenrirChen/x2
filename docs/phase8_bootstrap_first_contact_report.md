# Phase 8 — Bootstrap Contract Closure and First Contact

## 1. Starting state

- Branch: `feat/network-bootstrap`
- Worktree: clean at phase start
- M0/M1/M2: Done; M3: Partial
- Baseline: 102 passed, 0 failed

## 2. Gate A result

**Done for static contract closure.** Targeted IL2CPP analysis recovered two
POST contracts: `/apply/connectInfo` and `/apply/address`. The first populates
HTTP/service configuration. The second parses `result.data[]`; its first
selected `ip` and `port` flow through `MarsNetManager.SetIP`, `MarsNet.SetConnect`
and `SocketTcp.SetConnectEndPoint`.

The strict machine-readable result is `minimal_webgameconfig_contract.json`.
`docs/bootstrap_contract.md` contains the xref-level evidence map.

## 3. Request and response summary

| Endpoint | Request fields | Response minimum |
|---|---|---|
| `/apply/connectInfo` | `packageName`, `fromCH`, `adChannel`, `adSubChannel`, `lebianVersion` | `result` with 5 scalar service fields, 3 list fields and `areaId` |
| `/apply/address` | `clientType`, `timestamp`, `sign` | non-empty `result.data`, first entry with `ip` and `port` |

Both use URL-encoded POST dictionaries. The address sign is
`MD5(clientType + timestamp + Server_Key)`. It is not packet CRC32.

## 4. Implementation and tests

The Phase 7 synthetic fixture is retained. New recovered models encode and parse
the confirmed subset, tolerate unrelated unknown fields, enforce required fields,
and expose both confirmed routes. Concrete addresses are localhost
`TEMPORARY_COMPAT` values, not retired production data.

Added fixtures:

- `tests/fixtures/bootstrap/recovered_minimal_webgameconfig.json`
- `tests/fixtures/bootstrap/recovered_minimal_server_address.json`

Added tests cover deterministic encoding/decoding, required fields, optional
unknown fields, host/port mapping, endpoint-list validation, and route/method
behavior.

Final test result: **118 passed, 0 failed**. `ruff` and `mypy` are unavailable
in the current local environment.

## 5. Gate B decision

**Not Started; highest level below FC0.** The effective packaged local
`GameConfig.txt` row and its base URL/TLS behavior are not yet resolved. An
unmodified APK therefore cannot be proven to route exclusively to localhost.
The APK was not launched, no first packet exists, CRC/protobuf status is N/A,
and no client fixture was saved.

No protocol mismatch document was created because no live protocol observation
occurred.

## 6. Milestone and readiness

- M3 remains **Partial**: client acceptance has not been observed.
- FC remains **Not Started**.
- M4 remains **Not Started**; no Login response was implemented.
- Bootstrap readiness: **B** — static contract and local implementation complete,
  original-client routing unverified.
- First Contact readiness: **D** — safe redirect is not established.
- Login implementation readiness: **D** — no real Login frame was captured or
  decoded in this phase.

## 7. Remaining blockers

1. Recover the effective packaged `GameConfig.txt` row selected for
   `com.siva.project.x2` without broad rescanning.
2. Determine its HTTP/HTTPS base and certificate behavior.
3. Establish and verify a localhost/host-only redirect without APK patching or
   external connectivity.
4. Only then execute one controlled run and stop at the first decoded frame.

No merge to `main` and no `v0.2-first-contact` tag are permitted until M3 and FC
are both Done.
