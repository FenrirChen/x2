---
Document-Type: Historical Report
Date: 2026-09-22
Status: CURRENT_AT_TIME
Superseded-By:
  - (read alongside current knowledge)
---

# Phase 10 — Android compatibility lab and First Contact

## 1. Starting point

- Branch: `feat/network-bootstrap`
- Start commit: `41a2f50 docs: record Phase 9 gate results`
- Worktree: clean
- Baseline: **123 passed, 0 failed**
- M3 Partial; Phase 9 Gate C Partial; FC and M4 Not Started

## 2. Host and toolchain

The host is Windows 10 Home China 25H2 build 26200 on x64, with an Intel
i9-13900HX, 32 logical processors and 31.74 GiB RAM. Java 22.0.2 already
existed. Android SDK, ADB, emulator and AVDs were absent.

After the user freed disk space, D: had 70.92 GiB free. Official Google Android
components were installed outside Git. `docs/android_toolchain_manifest.md`
records versions, official source, paths and matched hashes.

## 3. AVD and APK readiness

`X2-Recovery-Lab` was created with Android 8.1/API 27, Google APIs x86, 2
cores, 4 GiB RAM and an 8 GiB data partition. The image and AVD definition are
complete, but no boot reached ADB.

The original APK was rechecked:

```text
SHA-256: 26a47aa684576549142cf0e4d096a78b90446314506626d2f9e57e6f76450bbe
size: 2144761791 bytes
```

It was not installed. Guest ABI execution, package path and clean snapshot are
therefore not available.

## 4. Provisioning blocker

Emulator 37.1.11 reports accelerator code 6 and no current Android Emulator
hypervisor driver. Both `-accel off` and `-no-accel` boot attempts fail before
ADB because the installed HAXM is no longer supported and WHPX is recommended.

Enabling WHPX/Hyper-V or installing the current official emulator hypervisor
driver requires administrator access and modifies Windows system components.
Per the Phase 10 authority boundary, this is:

```text
PROVISIONING_BLOCKER
USER_APPROVAL_REQUIRED
```

No driver, Windows feature, firewall, hosts file or certificate store was
modified.

## 5. Isolation and preflight

The proposed network uses QEMU `restrict=on` with only:

```text
10.0.2.100:80    -> 127.0.0.1:18080
10.0.2.101:29000 -> 127.0.0.1:29000
```

and a guest-only exact hostname override. This should deny all other egress,
but it cannot be accepted until a running guest proves it. No isolation evidence
was generated.

`tools/android/android_preflight.py` was added. It checks the ADB binary,
exactly one expected online AVD, API/AVD identity, installed-but-stopped package,
guest hosts entry, local listeners, runtime directory and exact isolation
evidence. Missing or unknown state returns `SAFE_TO_RUN=false`.

Current preflight: **SAFE_TO_RUN=false**.

## 6. Gate and First Contact results

| Item | Result |
|---|---|
| Android Lab | Partial |
| ADB | Binary ready; device not ready |
| AVD | Defined; boot blocked |
| APK install | Not attempted |
| ABI result | Image x86; APK compatibility not tested |
| Clean snapshot | Not created |
| Hostname redirect | Designed, not applied |
| Local reachability | Not tested in guest |
| Egress isolation | Designed, not proven |
| Gate C | Partial |
| Gate D | Not executed |
| First Contact run ID | N/A |
| Highest FC level | Not Started |
| Bootstrap endpoints | Not observed |
| TCP connection | Not observed |
| First message | N/A |
| CRC / protobuf | N/A / N/A |
| Fixture | None |

No sensitive data was collected. The APK never ran, and no retired or
third-party service was contacted.

## 7. Verification and Git policy

- Final tests: **127 passed, 0 failed** (123 previous + 4 Android preflight).
- Ruff: unavailable.
- Mypy: unavailable.
- M3 remains Partial; FC and M4 remain Not Started.
- No merge to `main`; no `v0.2-first-contact` tag.
- Implementation commit: `89d1c07 test(android): add fail-closed lab preflight`.
- Audit/lab/report documentation is committed separately with this report.

## 8. Ratings

| Area | Grade | Basis |
|---|---|---|
| Android Lab | C | official SDK/image and AVD exist; boot/ADB blocked |
| Isolation | C | restrictive design and preflight exist; no runtime proof |
| Bootstrap Compatibility | B | static/local contract unchanged; no client observation |
| First Contact | D | safety gate correctly prevented execution |
| Login Implementation Readiness | D | no real frame; M4 remains out of scope |

## 9. Largest remaining blocker

Obtain explicit approval for one supported Windows accelerator path, preferably
WHPX, then reboot if Windows requires it. Resume at headless restricted AVD boot,
not at SDK download. Only after ADB, APK installation, guest override, isolation
evidence and `SAFE_TO_RUN=true` may one bounded First Contact run begin.
