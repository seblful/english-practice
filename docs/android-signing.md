# Android signing and backups

Every release from app 0.1.2 onward uses the same English Practice signing key.
Run the release script from the repository root; it signs and verifies the APK
before uploading it:

```powershell
pwsh scripts/release-apk.ps1 -Tag app-v0.1.2
```

To sign an APK that is already built:

```powershell
pwsh scripts/sign-apk.ps1 -ApkPath 'packages/app/build/apk/English Practice.apk'
```

Copy the repository-root template before the first release on a workstation:

```powershell
Copy-Item keystore.properties.example keystore.properties
```

Fill in `storeFile` with the absolute path to the keystore, `keyAlias` with
`english-practice`, and `storePassword` / `keyPassword` with the signing password.
Use forward slashes in Windows paths. The local file contains passwords and is
ignored by Git; keep its access restricted to your user account.

The key is `english-practice-release.jks` in `$env:USERPROFILE\keystores`, an
RSA 4096-bit key. Development and CI do not require signing properties; the release
script refuses to publish if the properties are missing or unusable.

The public certificate fingerprint is pinned in
[`scripts/android-signing.json`](../scripts/android-signing.json). An APK with
another certificate fails verification and is not published by the release script.

## Back up the signing key

Save the `.jks` file in a secure backup and save its password from your local
`keystore.properties` in your password manager. Keep both outside Git.
On a replacement computer, restore the key and fill in a fresh local properties file.

An additional `english-practice-signing-password.xml` copy in the keystore folder
is encrypted using Windows [DPAPI](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.utility/export-clixml).
It can be read only by the same Windows user on the same computer, so it does not
replace a portable password backup.

## Preserve phone settings before changing keys

App 0.1.0 uses a different signing certificate. Installing 0.1.2 under the same
package name requires uninstalling 0.1.0, which deletes its settings and progress.
Keep the old app installed until its data has been backed up and recovery verified.

The old release has no export feature, and Android denies ADB access to its private
data because it is not debuggable. A copy of its APK is not a settings or progress
backup. Future updates signed with this repository's key can update 0.1.2 normally.
