# Android lab tools

## Visible development window (Phase 15)

Run `./tools/android/open_lab_window.ps1` from the repository root to open the
existing API 30 AVD with a visible window. Defaults match this local lab; paths
can be supplied as parameters. No `-no-window` argument is used, and the window
remains open for manual testing. This only starts Android; run the local game
server separately and use the installed internal Unity activity as documented
in the Phase 15 report. The historical startup probe below still runs headless
and closes its own emulator on completion.

These utilities inspect the disposable X2 Android lab. They do not download an
SDK, install drivers, modify hosts/firewall settings, install an APK, or start
the client.

- `android_preflight.py` is a read-only, fail-closed check for the expected AVD,
  package, clean-state evidence, guest hostname override, local listeners and
  deny-by-default isolation record.

The legacy preflight applies only to the original Reference APK + host override
route. It is not the gate for the Revival APK route introduced in Phase 11.
Evidence JSON is runtime state and must not be committed.

## Revival startup (Phase 12)

`run_startup_probe.ps1` cold-boots the existing API 30 lab with no snapshots,
host GPU and `GLESDynamicVersion`. It does not install an APK, clear app data,
modify the SDK or download anything. `startup_probe.py` verifies the AVD,
Android boot completion, root and exact installed Revival v0.1 APK hash before
launching the internal Unity activity. It serves Bootstrap on `127.0.0.1:18080`
only, without a TCP listener or Login response. It closes the emulator it
started when the run finishes.

From the repository root, using the Windows account that owns the lab:

```powershell
./tools/android/run_startup_probe.ps1 `
  -SdkRoot 'C:/Users/18207/AppData/Local/X2RecoveryLab/android-sdk' `
  -AndroidUserHome 'D:/demo/x2/x2_lab_tools/android-home' `
  -AvdHome 'D:/demo/x2/x2_lab_tools/avd' `
  -RunId validation01 -ObserveSeconds 60
```

Choose a new RunId every time; existing evidence is never overwritten.
Results and screenshots are under `runtime/phase12/<RunId>/probe/`.
Only the exact Unity hardware-warning Continue button may be acknowledged
automatically. No other UI is clicked. Exit 0 requires Bootstrap contact,
Awake, a live main process and absence of the known memory/shader errors;
screenshots must still be inspected. Raw runtime evidence is ignored by Git.
This tool does not verify network isolation or solve channel authentication.
