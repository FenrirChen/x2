param(
    [string]$SdkRoot = 'C:/Users/18207/AppData/Local/X2RecoveryLab/android-sdk',
    [string]$AndroidUserHome = 'D:/demo/x2/x2_lab_tools/android-home',
    [string]$AvdHome = 'D:/demo/x2/x2_lab_tools/avd'
)
$ErrorActionPreference = 'Stop'
$adb = Join-Path $SdkRoot 'platform-tools/adb.exe'
$emulator = Join-Path $SdkRoot 'emulator/emulator.exe'
$env:ANDROID_USER_HOME = $AndroidUserHome
$env:ANDROID_AVD_HOME = $AvdHome
$devices = & $adb devices
if ($LASTEXITCODE -ne 0) { throw 'ADB inventory failed' }
if ($devices -match '^emulator-5554\s') { throw 'An emulator already uses port 5554; inspect it before restarting' }
# Visible by user request. Keep the existing AVD and application data intact.
$arguments = @('-avd','X2-ABI-Probe-API30','-port','5554',
    '-no-boot-anim','-no-snapshot','-gpu','host','-feature','GLESDynamicVersion')
$process = Start-Process -FilePath $emulator -ArgumentList $arguments -WindowStyle Normal -PassThru
Write-Output "Visible emulator launched; PID $($process.Id). Close its window to stop it."
