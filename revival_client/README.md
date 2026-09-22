# X2 Revival Client

This directory contains reproducible, minimal compatibility patches derived
from the immutable Reference Client. APKs, signing keys and runtime logs are
local build artifacts and are excluded from Git.

Build v0.1 from the repository root:

```powershell
python tools\patch_gameconfig.py ..\X2_Eclipse_v2_4.apk revival_client\build\X2_Eclipse_v2_4_Revival_v0.1-unsigned.apk --patched-asset revival_client\build\42c44a368fc3544296d1e717a485b306.ab
```

The patch preserves every existing entry offset/alignment and neutralizes the
invalidated original v1 signature filenames without deleting or moving their
payloads. The output must be signed with the local development key before
installation. It is not signed by the original publisher.
