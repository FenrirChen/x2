---
Document-Type: Current Knowledge
Domain: Dev
Status: AUTHORITATIVE
Updated: 2026-09-25
Supersedes:
  - (none; still authoritative)
---

# Android toolchain manifest

All downloads came from `https://dl.google.com/android/repository/`. No
third-party emulator or mirror was used.

| Component | Version/build | Verification | Install path |
|---|---|---|---|
| Repository catalog | `repository2-1.xml` | SHA-256 `20d4ac01174032e2ce024ce07523d00fffbeb30e423b46abc5ca6ef289d4528b` | external lab tools |
| Command-line tools | 23.0 / 16111833 | SHA-1 `57d04f2d75eb8e8fffc5000a987e5de4b5a63e9d` matched catalog | SDK `cmdline-tools/latest` |
| Command-line tools | 20.0 / 14742923 | SHA-1 `16b3f45ddb3d85ea6bbe6a1c0b47146daf0db450` matched catalog | SDK `cmdline-tools/20.0` |
| Platform tools | 37.0.1 | installed by official SDK tooling | SDK `platform-tools` |
| Android Emulator | 37.1.11 / 15917651 | installed by official SDK tooling | SDK `emulator` |
| Android platform 27 | rev 3 / `platform-27_r03.zip` | SHA-1 `35f747e7e70b2d16e0e4246876be28d15ea1c353` matched catalog | SDK `platforms/android-27` |
| Google APIs x86 image | API 27 rev 11 / `x86-27_r11.zip` | SHA-1 `0a130cad4f6d42c305a61265dc6c738e9e2b45c4` matched catalog | SDK `system-images/android-27/google_apis/x86` |

The latest Android CLI did not expose the legacy API 27 package correctly, and
the legacy manager stalled with a zero-byte download. The two API 27 archives
were therefore downloaded directly from the URLs in the official catalogs,
hash-verified, unpacked into their standard SDK locations, and then recognized
by `sdkmanager --list_installed`.
