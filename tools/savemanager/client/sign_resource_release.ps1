# sign_release.ps1 - X2 Revival release APK signing (long-term tool).
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File sign_release.ps1 -InputApk <unsigned.apk> -OutputApk <signed.apk>
#
# Rules implemented (do not weaken):
#   1. Reads secrets from <projectRoot>\.runtime\signing\signing.env  (never echoed).
#   2. RELEASE_KEY_INITIALIZED must exist. If it exists but the keystore does not:
#      FATAL ERROR - never generate a replacement key automatically.
#   3. Signs with apksigner via environment-variable password references
#      (--ks-pass env: / --key-pass env:), so the password never appears on the
#      command line or in console output.
#   4. Verifies with `apksigner verify --verbose --print-certs` and compares the
#      signer certificate SHA-256 against RELEASE_SIGNING_IDENTITY.md.
param(
    [Parameter(Mandatory = $true)][string]$InputApk,
    [Parameter(Mandatory = $true)][string]$OutputApk
)
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Resolve-Path (Join-Path $ScriptDir "..\..\..\..")
$SigningDir = Join-Path $ProjectRoot ".runtime\signing"
$Keystore = Join-Path $SigningDir "x2-revival-release.jks"
$EnvFile = Join-Path $SigningDir "signing.env"
$Marker = Join-Path $SigningDir "RELEASE_KEY_INITIALIZED"
$IdentityFile = Join-Path $ProjectRoot "逆向\报告\RELEASE_SIGNING_IDENTITY.md"
$ApksignerJar = if ($env:X2_APKSIGNER_JAR) { $env:X2_APKSIGNER_JAR } else { Join-Path $ProjectRoot ".runtime\build-tools\apksigner.jar" }

function Fail($msg) { Write-Host "FATAL: $msg" -ForegroundColor Red; exit 1 }

if (-not (Test-Path $Marker)) { Fail "RELEASE_KEY_INITIALIZED marker missing - release signing identity was never initialized." }
if (-not (Test-Path $Keystore)) {
    Fail "Existing release signing identity is missing.`nDo NOT generate a replacement key automatically."
}
if (-not (Test-Path $EnvFile)) { Fail "signing.env missing (keystore exists but credentials file lost). Restore from backup - do NOT regenerate." }
if (-not (Test-Path $ApksignerJar)) { Fail "apksigner.jar not found at $ApksignerJar" }
if (-not (Test-Path $InputApk)) { Fail "input APK not found: $InputApk" }

# parse signing.env into process env (no output of values)
Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*X2_([A-Z_]+)\s*=\s*(.+)\s*$') { Set-Item -Path ("Env:X2_" + $Matches[1]) -Value $Matches[2] }
}
if (-not $env:X2_STORE_PASSWORD -or -not $env:X2_KEY_PASSWORD) { Fail "signing.env incomplete" }
$Alias = $env:X2_KEY_ALIAS
if (-not $Alias) { Fail "X2_KEY_ALIAS missing" }

Write-Host "Signing identity : $Alias"
Write-Host "Keystore         : $Keystore"
Write-Host "Input APK        : $InputApk"
Write-Host "Output APK       : $OutputApk"

# sign (passwords passed to the JVM via inherited environment variables)
$env:X2_KEYSTORE_PATH = $Keystore
& java -jar $ApksignerJar sign `
    --ks $Keystore `
    --ks-key-alias $Alias `
    --ks-pass env:X2_STORE_PASSWORD `
    --key-pass env:X2_KEY_PASSWORD `
    --out $OutputApk $InputApk
if ($LASTEXITCODE -ne 0) { Fail "apksigner sign failed" }
Write-Host "sign: OK" -ForegroundColor Green

# verify
$verifyOut = & java -jar $ApksignerJar verify --verbose --print-certs $OutputApk
$verifyOut | ForEach-Object { Write-Host $_ }
if ($LASTEXITCODE -ne 0) { Fail "apksigner verify failed" }
$joined = ($verifyOut | Out-String)
if ($joined -notmatch 'Verified\s+using\s+v1\s+scheme.*:\s*true') { Fail "v1 scheme not verified" }
if ($joined -notmatch 'Verified\s+using\s+v2\s+scheme.*:\s*true') { Fail "v2 scheme not verified" }
if ($joined -notmatch '(?m)^\s*Verifies\s*$') { Fail "apksigner verify did not report Verified" }

# certificate fingerprint must match the registered release identity
$fpLines = $verifyOut | Where-Object { $_ -match 'certificate SHA-256 digest' } |
    ForEach-Object { ($_ -replace '^.*certificate SHA-256 digest:\s*','').Trim() } | Select-Object -Unique
$idLine = ((Select-String -Path $IdentityFile -Pattern '[0-9A-F]{2}(:[0-9A-F]{2}){31}') |
    Select-Object -First 1).Matches.Value
if (-not $idLine) { Fail "could not read fingerprint from RELEASE_SIGNING_IDENTITY.md" }
$matched = $false
foreach ($fp in $fpLines) {
    if (($fp -replace ':','') -ieq ($idLine -replace ':','')) { $matched = $true }
}
if (-not $matched) { Fail "certificate fingerprint mismatch: signed=$($fpLines -join ',') identity=$idLine" }
Write-Host "certificate fingerprint matches RELEASE_SIGNING_IDENTITY.md: OK" -ForegroundColor Green

$size = (Get-Item $OutputApk).Length
Write-Host "signed APK size  : $size bytes"
if ($size -ge 4294967295) { Fail "signed APK reaches the ZIP32 boundary" }
Write-Host "release signing COMPLETE" -ForegroundColor Green
