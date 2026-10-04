<#
.SYNOPSIS
Signs an APK with this repository's release key and verifies its certificate.
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$ApkPath,
    [string]$PropertiesPath = (Join-Path $PSScriptRoot '../keystore.properties'),
    [string]$SdkRoot = $(if ($env:ANDROID_HOME) { $env:ANDROID_HOME } else { Join-Path $env:LOCALAPPDATA 'Android/Sdk' })
)

$ErrorActionPreference = 'Stop'
$signingProfile = Get-Content -LiteralPath (Join-Path $PSScriptRoot 'android-signing.json') -Raw | ConvertFrom-Json
$signingProperties = @{}
foreach ($line in (Get-Content -LiteralPath $PropertiesPath)) {
    $line = $line.Trim()
    if (-not $line -or $line.StartsWith('#')) { continue }
    $parts = $line.Split('=', 2)
    if ($parts.Count -ne 2) { throw 'Expected key=value in keystore.properties.' }
    $name = $parts[0].Trim()
    if ($signingProperties.ContainsKey($name)) { throw "Duplicate signing property: $name" }
    $signingProperties[$name] = $parts[1].Trim()
}
foreach ($requiredProperty in @('storeFile', 'storePassword', 'keyAlias', 'keyPassword')) {
    if (-not $signingProperties[$requiredProperty]) { throw "Missing signing property: $requiredProperty" }
}
$keystore = $signingProperties.storeFile
if (-not [IO.Path]::IsPathFullyQualified($keystore)) { throw 'storeFile must be an absolute path.' }
foreach ($requiredFile in @($ApkPath, $keystore)) {
    if (-not (Test-Path -LiteralPath $requiredFile -PathType Leaf)) {
        throw "Required signing file is missing: $requiredFile"
    }
}
$buildTools = Get-ChildItem -LiteralPath (Join-Path $SdkRoot 'build-tools') -Directory |
    Where-Object { $_.Name -match '^\d+\.\d+\.\d+$' } |
    Sort-Object { [version]$_.Name } -Descending |
    Where-Object { Test-Path -LiteralPath (Join-Path $_.FullName 'apksigner.bat') } |
    Select-Object -First 1
if (-not $buildTools) { throw 'Android SDK build-tools with apksigner are required.' }
$apksigner = Join-Path $buildTools.FullName 'apksigner.bat'
$zipalign = Join-Path $buildTools.FullName 'zipalign.exe'
$apk = (Resolve-Path -LiteralPath $ApkPath).Path
$signedApk = [IO.Path]::ChangeExtension($apk, '.signed.apk')
if (Test-Path -LiteralPath $signedApk) { throw "Signing output already exists: $signedApk" }

& $zipalign -c -P 16 4 $apk
if ($LASTEXITCODE -ne 0) { throw 'APK alignment check failed.' }
$previousSecret = $env:ENGLISH_PRACTICE_SIGNING_SECRET
$previousKeySecret = $env:ENGLISH_PRACTICE_SIGNING_KEY_SECRET
try {
    $env:ENGLISH_PRACTICE_SIGNING_SECRET = $signingProperties.storePassword
    $env:ENGLISH_PRACTICE_SIGNING_KEY_SECRET = $signingProperties.keyPassword
    & $apksigner sign --ks $keystore --ks-key-alias $signingProperties.keyAlias `
        --ks-pass env:ENGLISH_PRACTICE_SIGNING_SECRET --key-pass env:ENGLISH_PRACTICE_SIGNING_KEY_SECRET `
        --v4-signing-enabled false --out $signedApk $apk
    if ($LASTEXITCODE -ne 0) { throw 'APK signing failed.' }
    $certificate = & $apksigner verify --print-certs $signedApk
    if ($LASTEXITCODE -ne 0) { throw 'APK signature verification failed.' }
    $digests = @($certificate | Select-String '^(?:Signer #\d+|V\d+\.\d+ Signer):? certificate SHA-256 digest: ([a-fA-F0-9]{64})$')
    if ($digests.Count -ne 1 -or $digests[0].Matches[0].Groups[1].Value -ne $signingProfile.certificateSha256) {
        throw 'APK signing certificate does not match this repository.'
    }
    Move-Item -LiteralPath $signedApk -Destination $apk -Force
    Write-Host "Signed and verified: $apk"
    Write-Host "Certificate SHA256: $($signingProfile.certificateSha256)"
} finally {
    if ($null -eq $previousSecret) {
        Remove-Item Env:ENGLISH_PRACTICE_SIGNING_SECRET -ErrorAction SilentlyContinue
    } else {
        $env:ENGLISH_PRACTICE_SIGNING_SECRET = $previousSecret
    }
    if ($null -eq $previousKeySecret) {
        Remove-Item Env:ENGLISH_PRACTICE_SIGNING_KEY_SECRET -ErrorAction SilentlyContinue
    } else {
        $env:ENGLISH_PRACTICE_SIGNING_KEY_SECRET = $previousKeySecret
    }
}
