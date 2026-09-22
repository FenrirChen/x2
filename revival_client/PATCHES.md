# Revival Client v0.1 / v0.2

## Patch 001: GameConfig Login_Url

From: `http://ssl-x2zh1login-release.17m3.com`

To: development bootstrap endpoint (`http://10.0.2.2:18080`)

Purpose: redirect the retired official bootstrap to the compatibility backend.

## Patch 002: v0.2 opt-in Account login

GameConfig row 0 `packageType`: `product` → `testpackage`.
Keep `client_Type=product` and all other parsed fields unchanged.
This selects LoginManager's existing Account mode and existing SDK/update completion
branches; no native instructions, DEX, protocol or game resources are patched.
Build with `tools/patch_gameconfig.py --local-account`; without the flag v0.1 remains
the default. Reference APK is read-only and its known SHA-256 is checked.

The local bootstrap must return `update=LEBIAN`; an empty selector does not advance
the client's startup state. Local identity endpoints are opt-in lab compatibility,
not official account authentication. See [Phase 13](../docs/phase13_first_contact.md).

Verified signed artifact: `build/X2_Eclipse_v2_4_Revival_v0.2-signed.apk`.
SHA-256: `460dc657a8fb1b5410a4c0eaa5fac9433b45ecc54b7f3845afc626420946276d`.
Signed using the existing project development key and installed with `adb install -r`;
Android accepted it without removing application data. Private key/password stay out
of Git. The older `v0.2.apk` is an incomplete timed-out signing output: do not install.
