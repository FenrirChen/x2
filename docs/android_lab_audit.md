# Android compatibility lab audit

Audit date: 2026-09-22 (Asia/Shanghai)

## Host

| Item | Result |
|---|---|
| OS | Windows 10 Home China, display version 25H2, build 26200 |
| Host/process architecture | x64 / x64 |
| CPU | Intel Core i9-13900HX, 32 logical processors |
| RAM | 31.74 GiB total; 17.89 GiB available at audit |
| Disk before user cleanup | C: 16.91 GiB free; D: 2.74 GiB free |
| Disk after user cleanup | C: 15.29 GiB free; D: 70.92 GiB free |
| Java | Oracle Java/Javac 22.0.2 |

Windows system-information/CIM virtualization queries were access denied in the
managed shell, so firmware virtualization state is **UNKNOWN** from those
interfaces. The Android emulator provides the actionable result:

```text
emulator-check accel: code 6
Android Emulator hypervisor driver is not installed on this machine

emulator 37 boot:
current hypervisor HAXM is no longer supported
Using WHPX is recommended
```

Thus hardware virtualization may exist, but no accelerator supported by
emulator 37 is currently usable. Enabling WHPX/Hyper-V or installing the current
Android Emulator Hypervisor Driver requires administrator/system-component
changes and was not attempted.

## Android tooling at start

| Component | Initial state |
|---|---|
| `adb` | Not found |
| `sdkmanager` | Not found |
| `emulator` | Not found |
| Android SDK root | Not present |
| Existing AVDs | None |

## Provisioned user-local assets

- SDK root: `C:\Users\18207\AppData\Local\X2RecoveryLab\android-sdk`
- AVD home: `D:\demo\x2\x2_lab_tools\avd`
- AVD: `X2-Recovery-Lab`
- Image: Android 8.1 / API 27 / Google APIs / x86
- Resources: 2 vCPU, 4 GiB RAM, 8 GiB data partition
- Play Store: disabled

The SDK, archives, image and AVD are outside the Git repository. AVD creation
succeeded, but no boot completed; therefore guest ABI properties and ADB device
state are not yet verified.
