# Security policy

This project is an experimental prerelease. It has no security support guarantee. Its tested scope is Apple Silicon, macOS 26.4 or newer, Mac.apk 1.0.2303, and Instagram 445.0.0.45.83. Other app versions are unsupported until their pins and patches are reviewed and tested.

## Report a vulnerability

Use [GitHub's private vulnerability reporting](https://github.com/surajmandalcell/instagramOnMac/security/advisories/new) when it is available. If it is disabled, open a brief issue asking for a private reporting channel. Do not post exploit steps or private data publicly.

Do not include APK files, account names, credentials, session data, screenshots, media, logs, or local file paths in a report. Share only the affected version, a short impact description, and safe reproduction steps.

## Scope

Reports about this recipe should cover its download checks, source and patch pins, build, signing, installer, rollback, or selected-media handling. Report Mac.apk or Instagram vulnerabilities to their respective maintainers.

The runtime is not sandboxed from the Mac user's files. Use only Mac.apk releases and Instagram packages that you trust. The installer verifies the Mac.apk release digest and checks Instagram package signatures against pinned publisher certificates. These checks do not make an untrusted package safe.
