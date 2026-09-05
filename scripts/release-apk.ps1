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

# $ErrorActionPreference only covers PowerShell errors -- an external command's
# non-zero exit (or a graceful "can't run yet" no-op) does not stop the script
# on its own, so every step below is checked by hand.
function Invoke-Checked {
    param([string]$Description)
    if ($LASTEXITCODE -ne 0) {
        throw "$Description failed (exit $LASTEXITCODE)"
    }
}

Set-Location (git rev-parse --show-toplevel)

# cp1252 can't encode the emoji flet prints while building; see the
# apk-build-workflow memory for the UnicodeEncodeError this avoids.
$env:PYTHONIOENCODING = "utf-8"
$env:PYTHONUTF8 = "1"

Write-Host "Rebuilding the bundled exercise database..."
# --package, not --directory: the CLI resolves its source database as a path
# relative to the process's cwd, and --directory would chdir into extraction
# and break that -- this keeps cwd at the repo root, where it works.
uv run --package english-practice-extraction practice-content bundle
Invoke-Checked "practice-content bundle"

Write-Host "Building the APK (about 6 minutes)..."
uv run --directory packages/app flet build apk --project "English Practice"
Invoke-Checked "flet build apk"

$apk = Get-ChildItem "packages/app/build/apk/*.apk" | Select-Object -First 1
if (-not $apk) {
    throw "No APK found under packages/app/build/apk/ -- did flet build apk fail?"
}

Write-Host "Uploading $($apk.Name) to the $Tag release..."
gh release upload $Tag $apk.FullName --clobber
Invoke-Checked "gh release upload"
gh release edit $Tag --draft=false
Invoke-Checked "gh release edit --draft=false"

Write-Host "Published: https://github.com/seblful/english-practice/releases/tag/$Tag"
