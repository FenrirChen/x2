---
Document-Type: Deployment Validation
Date: 2026-09-28
Status: SOURCE_PUBLISHED; SERVER_NOT_YET_DEPLOYED
---

# Public deployment preparation

- Source repository: `https://github.com/FenrirChen/x2`, public and empty
  before first push. Initial `main` received commit `4a7eb52e9ae7a0ab1a818318275433dac11caeb7`.
- Full test baseline: 323 passed. After deployment/config changes: 327 passed.
- Tracked Git history: no APK, SQLite, private key, keystore or large raw
  reverse-engineering binary. Production runtime data and generated APK are
  ignored. Historical documentation contains public lab credentials and local
  developer paths; no real account credential or provider token was found in
  tracked source. An unrelated untracked equipment callgraph was left alone.
- Actual entrypoint: `tools/local_game_server.py`: HTTP 18080; game TCP 29000;
  chat TCP 29001. New `DeploymentEndpoints` reads public/bind host and these
  three ports from the environment. Server replies provide game and chat hosts.
- `fenrirchen.com` A resolved to `8.134.196.134` during this check. Whether
  that is the intended server IP is not known. TCP 18080, 29000 and 29001 were
  unavailable from the development machine; no Linux host was deployed here.
- The active MuMu installation hash exactly matches input Revival v0.2 APK
  SHA-256 `460dc657a8fb1b5410a4c0eaa5fac9433b45ecc54b7f3845afc626420946276d`.
  Package `com.siva.project.x2`, version 2.4 (202). Only row-0 GameConfig
  `Login_Url` was changed from `http://10.0.2.2:18080` to
  `http://fenrirchen.com:18080`; `packageType=testpackage` remained.
- Output test-signed APK: SHA-256
  `4019d27fdb6976b0b58d857bc3fb3c271409ae2c9b7a8d5f5d8385ad54c39934`.
  ZIP alignment and apksigner v1/v2/v3 verification passed. It uses the
  previously generated local reconfiguration key, whose certificate differs
  from the currently installed Revival v0.2 certificate. In-place Android
  upgrade therefore is not supported with this test signing identity.
- The test-signed APK installed and launched on an independent read-only AVD.
  No request to the public endpoint was observed before the AVD's external
  proxy/connectivity failure; successful remote contact remains unverified.
