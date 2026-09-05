<#
.SYNOPSIS
Builds the Android APK and attaches it to the draft release the CI workflow created.

.DESCRIPTION
`flet build apk` needs the source book database (data/production.db), which is
gitignored on purpose and never reaches GitHub Actions -- so this step runs on
a workstation that has it, plus Flutter and the Android SDK. Run after pushing
the release tag and letting .github/workflows/release.yml draft the release.

.PARAMETER Tag
The release tag, e.g. app-v0.1.0. Must already have a matching draft release
(see .github/workflows/release.yml) and match packages/app/pyproject.toml's
version.

.EXAMPLE
pwsh scripts/release-apk.ps1 -Tag app-v0.1.0
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$Tag
)

$ErrorActionPreference = "Stop"

Set-Location (git rev-parse --show-toplevel)

# cp1252 can't encode the emoji flet prints while building; see the
# apk-build-workflow memory for the UnicodeEncodeError this avoids.
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Write-Host "Rebuilding the bundled exercise database..."
uv run --directory packages/extraction practice-content bundle

Write-Host "Building the APK (about 6 minutes)..."
uv run --directory packages/app flet build apk --project "English Practice"

$apk = Get-ChildItem "packages/app/build/apk/*.apk" | Select-Object -First 1
if (-not $apk) {
    throw "No APK found under packages/app/build/apk/ -- did flet build apk fail?"
}

Write-Host "Uploading $($apk.Name) to the $Tag release..."
gh release upload $Tag $apk.FullName --clobber
gh release edit $Tag --draft=false

Write-Host "Published: https://github.com/seblful/english-practice/releases/tag/$Tag"
