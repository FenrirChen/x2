---
Document-Type: Historical Report
Date: 2026-09-22
Status: CURRENT_AT_TIME
Superseded-By:
  - (read alongside current knowledge)
---

# First Contact runs

No original-client run was performed in Phase 8.

Gate A recovered the two-stage response contract and TCP endpoint mapping, but
the effective packaged `GameConfig.txt` base URL and its HTTP/TLS routing remain
unresolved. Without a proven localhost-only redirect, running the unmodified APK
could contact retired or third-party infrastructure and violates the Phase 8
isolation gate.

```text
Run: NONE
Goal: Gate B preflight
Change: none
Observed: local-only routing cannot yet be guaranteed
Result: First Contact Not Started (below FC0)
Conclusion: do not launch the APK
Next: recover the effective local GameConfig row and prove an isolated redirect
```

No credentials, device identifiers, packets, or runtime logs were collected.

## Phase 9

```text
Run: NONE
Goal: Gate C preflight
Environment: static host workspace only; no isolated Android guest available
Hypothesis: a guest-local hostname override plus deny-by-default egress can
            safely route the packaged HTTP base to local services
Change: added a read-only, fail-closed preflight; no system networking changed
Observed: packaged GameConfig and HTTP port 80 are resolved, but no enforceable
          isolation evidence or guest-reachable listeners exist
FC level: Not Started (below FC0)
Conclusion: Gate C Partial; do not launch the APK
Next: provision an isolated emulator/VM, record its hostname override and
      firewall evidence, then rerun preflight
```

No Phase 9 run ID was allocated because the client launch gate did not pass.

## Phase 10

```text
Run: NONE
Goal: provision disposable Android lab and pass Gate C
Environment: X2-Recovery-Lab, API 27 Google APIs x86, emulator 37.1.11
Change: installed official user-local SDK/image and created restricted-network AVD
Observed: emulator exits before ADB because installed HAXM is unsupported;
          WHPX/current hypervisor driver is unavailable
FC level: Not Started (below FC0)
Conclusion: USER_APPROVAL_REQUIRED for a Windows virtualization component change
Next: enable WHPX/Hyper-V or install the official current emulator hypervisor
      driver with explicit administrator approval, then resume at AVD boot
```

No APK was installed or launched. No First Contact run ID, credentials, device
identifiers or client packets were produced.
