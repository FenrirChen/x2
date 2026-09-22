param(
    [Parameter(Mandatory=$true)][string]$SdkRoot,
    [Parameter(Mandatory=$true)][string]$AndroidUserHome,
    [Parameter(Mandatory=$true)][string]$AvdHome,
    [Parameter(Mandatory=$true)][ValidatePattern('^[a-zA-Z0-9_-]+$')][string]$RunId,
    [ValidateRange(15,180)][int]$ObserveSeconds = 60
)
$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '../..')).Path
$runRoot = Join-Path $repoRoot "runtime/phase12/$RunId"
if (Test-Path -LiteralPath $runRoot) { throw "Run already exists: $runRoot" }
$adb = Join-Path $SdkRoot 'platform-tools/adb.exe'
$emulator = Join-Path $SdkRoot 'emulator/emulator.exe'
$python = Join-Path $repoRoot '.venv/Scripts/python.exe'
foreach ($executable in @($adb, $emulator, $python)) {
    if (!(Test-Path -LiteralPath $executable)) { throw "Missing executable: $executable" }
}
$previousUserHome = $env:ANDROID_USER_HOME
$previousAvdHome = $env:ANDROID_AVD_HOME
$previousPythonPath = $env:PYTHONPATH
$launched = $false
try {
    $env:ANDROID_USER_HOME = $AndroidUserHome
    $env:ANDROID_AVD_HOME = $AvdHome
    $env:PYTHONPATH = Join-Path $repoRoot 'src'
    $devices = & $adb devices
    if ($LASTEXITCODE -ne 0) { throw 'ADB inventory failed' }
    if ($devices -match '^emulator-5554\s') { throw 'Port 5554 already has an emulator; stop it explicitly first' }
    New-Item -ItemType Directory -Path $runRoot | Out-Null
    $arguments = @('-avd','X2-ABI-Probe-API30','-port','5554','-no-window',
                   '-no-boot-anim','-no-snapshot','-gpu','host','-feature','GLESDynamicVersion')
    $manifest = [ordered]@{
        startedUtc = [DateTime]::UtcNow.ToString('o')
        arguments = $arguments
        avd = 'X2-ABI-Probe-API30'
        preservesAppData = $true
        snapshots = 'disabled: load and save'
        referenceApkModified = $false
        avdConfigSha256 = (Get-FileHash -Algorithm SHA256 -LiteralPath (Join-Path $AvdHome 'X2-ABI-Probe-API30.avd/config.ini')).Hash
    }
    $manifest | ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8 (Join-Path $runRoot 'launch.json')
    $process = Start-Process -FilePath $emulator -ArgumentList $arguments -WindowStyle Hidden `
        -RedirectStandardOutput (Join-Path $runRoot 'emulator.stdout.log') `
        -RedirectStandardError (Join-Path $runRoot 'emulator.stderr.log') -PassThru
    $launched = $true
    Write-Output "Cold boot started: $RunId; launcher PID $($process.Id)"
    $deadline = [DateTime]::UtcNow.AddSeconds(180)
    $booted = $false
    while ([DateTime]::UtcNow -lt $deadline) {
        $boot = & $adb -s emulator-5554 shell getprop sys.boot_completed 2>$null
        if ($LASTEXITCODE -eq 0 -and "$boot".Trim() -eq '1') { $booted = $true; break }
        Start-Sleep -Seconds 3
    }
    if (!$booted) { throw 'Cold boot did not complete within 180 seconds' }
    & $adb -s emulator-5554 root
    if ($LASTEXITCODE -ne 0) { throw 'Lab adb root failed' }
    Start-Sleep -Seconds 2
    Write-Output 'Android booted; verifying APK and observing client startup'
    Push-Location $repoRoot
    try {
        & $python -m tools.android.startup_probe --adb $adb --output "$runRoot/probe" --seconds $ObserveSeconds
        if ($LASTEXITCODE -ne 0) { throw 'Startup observation failed; inspect result.json' }
    } finally { Pop-Location }
} catch {
    if (Test-Path -LiteralPath $runRoot) {
        $_.ToString() | Set-Content -Encoding utf8 (Join-Path $runRoot 'failure.txt')
    }
    throw
} finally {
    if ($launched) {
        $currentAvd = & $adb -s emulator-5554 emu avd name 2>$null
        if ($currentAvd -contains 'X2-ABI-Probe-API30') {
            & $adb -s emulator-5554 emu kill
        }
    }
    $env:ANDROID_USER_HOME = $previousUserHome
    $env:ANDROID_AVD_HOME = $previousAvdHome
    $env:PYTHONPATH = $previousPythonPath
}
