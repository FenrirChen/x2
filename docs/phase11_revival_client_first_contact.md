# Phase 11 — Revival Client v0.1 First Contact

| Item | Result |
|---|---|
| Reference APK SHA-256 | `26a47aa684576549142cf0e4d096a78b90446314506626d2f9e57e6f76450bbe` |
| Revival APK SHA-256 | `b6a95c274cd61a91d2c4ab1ea448a300669bbc91861e989c1593da8dd071f98f` |
| Patch | Success: row 0 `Login_Url` is `http://10.0.2.2:18080`; no other parsed GameConfig value changed |
| Round-trip | Original decode → encode is byte-identical |
| Signing | Success: local self-signed development key, v1/JAR signature; not the official publisher signature |
| Install | Success on `X2-ABI-Probe-API30`; package `com.siva.project.x2`, version `2.4`, versionCode `202` |
| App boot | Success (FC0); Unity 2017.4.39f1 process started through `X2UnityActivity`; hardware warning confirmed once |
| `/apply/connectInfo` | Not hit |
| `/apply/address` | Not hit |
| TCP connection | Not connected |
| First frame / message | N/A |
| CRC | N/A |
| Protobuf | N/A |
| Highest FC | FC0 |

The installed `base.apk` hash exactly matched the local signed Revival APK.
The launcher `SplashActivity` did not enter Unity. Direct ADB launch of the
non-exported `X2UnityActivity` required emulator root and then displayed the
modal warning: `Your device does not match the hardware requirements of this
application.` The client remained at that modal, so GameConfig loading and
Bootstrap communication did not begin.

## Hardware-warning continuation run

The existing AVD, Revival APK, Bootstrap service and TCP observer were reused.
UIAutomator identified the exact warning and `android:id/button1`; `Continue`
was tapped once through ADB. No screenshot was needed.

After confirmation, Unity advanced through `AppMainImpl.Awake` and
`ProgramInitEnter`. The client then sent three `POST /apply/controlInfo`
requests. This endpoint is not part of the currently recovered two-endpoint
Bootstrap contract, so all three received `404`. The requested
`/apply/connectInfo` and `/apply/address` endpoints were not reached, no TCP
connection opened, and no frame was received.

The first new compatibility mismatch is therefore the previously unrecorded
`POST /apply/controlInfo` request. Immediately afterward Android also reported
an auxiliary-process crash in `com.siva.project.x2:lebian.dns`:

```text
Unable to create service com.excelliance.lbsdk.main.BGService
Caused by: ClassNotFoundException: com.excelliance.lbsdk.main.BGService
```

The run stopped at that first new blocker without another interaction, APK
change, endpoint implementation or Login response. Highest FC remains **FC0**.

## Minimal `/apply/controlInfo` recovery

Targeted static analysis located the request in
`AppMainImpl.<_controlInfo>d__72.MoveNext` at RVA `0x17E73C4` and its callback at
RVA `0x17E072C`. It is a form POST to `/apply/controlInfo` with a 10-second
timeout. On HTTP 200 the client parses the response root with LitJson and reads
exactly two string fields: `giftCode` and `update`. The callback compares these
values with channel/update sentinels; unmatched values do not start an updater.

The existing Bootstrap now serves this minimal response:

```json
{"giftCode":"","update":""}
```

The model, routing and HTTP integration checks pass. No Login or TCP behavior
was changed.

In the bounded client rerun, the main `com.siva.project.x2` process remained
alive, while `com.siva.project.x2:lebian.dns` was not alive and its earlier
`BGService` crash did not recur. This run did not reach `/apply/controlInfo`,
`/apply/connectInfo` or `/apply/address`. Unity stopped before
`AppMainImpl.Awake` with the first new explicit error:

```text
Using memoryadresses from more that 16GB of memory
```

Therefore the runtime response remains unconsumed, there was no TCP connection
or first frame, and Highest FC remains **FC0**. No emulator, APK, SDK or TCP
change was made in response to this new blocker.
