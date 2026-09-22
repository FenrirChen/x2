# Packaged GameConfig resolution

## Result

For APK SHA-256
`26a47aa684576549142cf0e4d096a78b90446314506626d2f9e57e6f76450bbe`,
package `com.siva.project.x2` selects row 0. Its bootstrap base is
`http://ssl-x2zh1login-release.17m3.com`. Both conclusions are **CONFIRMED** by
packaged data and the IL2CPP selection path; no retired endpoint was contacted.

## Source and parser

| Item | Evidence | Status |
|---|---|---|
| Logical resource name | `LoadLocalGameConfig.MoveNext`, RVA `0x17DD6FC` onward | CONFIRMED |
| APK filename | `MD5("GameConfig" + "x2") = 42c44a368fc3544296d1e717a485b306` | CONFIRMED |
| APK entry | `assets/42c44a368fc3544296d1e717a485b306.ab`, 1536 bytes | CONFIRMED |
| Content wrapper | `X2Engine.GameStream` | CONFIRMED |
| Cipher settings | Rijndael/AES, ECB, no padding | CONFIRMED |
| Key derivation | `MD5(UTF8("x2_GAME_ds" + (encryptedLength * 4289702650)))` | CONFIRMED |
| Parsed format | UTF-8 JSON through `LitJson.JsonMapper.ToObject` | CONFIRMED |

`GameStream.GenIV` is called, but ECB mode does not consume the IV. The decoded
payload contains a top-level `configs` array with three rows. This was a targeted
read of the single derived APK entry, not a new whole-APK scan.

## Selection function

`AppConfig.DoGameConfig` (RVA `0x17DC398`) reads `configs` and selects as follows:

1. If `PlayerPrefs.GetInt("GrayTestSwtich", 0) == 1`, compare each row's
   `packageName[]` against the literal `gray`.
2. Otherwise obtain `PlatformHelper.getPkgName()` and compare it for exact string
   equality against every value in each row's `packageName[]`.
3. Pass the first matching row to `LoadGameConfigSuccess`; failure to find one
   calls `LoadGameConfigFail`.

The normal installed package is `com.siva.project.x2`, so it matches row 0.
Channel, client version, release/debug state and platform are not read by this
selection function. The debug-like override is only the misspelled persisted
key `GrayTestSwtich` described above.

## Effective row

| Field | Effective value | Status |
|---|---|---|
| `packageName` | includes `com.siva.project.x2` | CONFIRMED |
| `client_Type` | `product` | CONFIRMED |
| `packageType` | `product` | CONFIRMED |
| `gameServerName` | `TAP_BiliBili_Server` | CONFIRMED |
| `Login_Url` | `http://ssl-x2zh1login-release.17m3.com` | CONFIRMED |
| `language` | `CN` | CONFIRMED |

The machine-readable recovered subset is
`reverse_data/effective_gameconfig.json`.

## Confidence and unknowns

Confidence is **high** for the packaged row, normal package-name selection and
base URL. Whether a particular historical installation persisted
`GrayTestSwtich=1` is unknowable from the APK; the compatibility test must start
from clean app data. DNS history and retired-service behavior remain out of
scope and were not queried.
