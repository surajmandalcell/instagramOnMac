# Contributing

This repository contains a source recipe, compatibility patches, public dependency pins, documentation, and synthetic tests. It does not accept app binaries, Instagram packages, account data, media, logs, screenshots, signing keys, personal paths, or local account identifiers.

The approved cover at `assets/cover.png` is the sole raster artwork exception. Its exact SHA-256 and metadata restrictions are enforced by the privacy check. Do not add screenshots or other images.

## Supported target

Keep changes gated to the tested Apple Silicon and macOS 26.4+ setup, Mac.apk 1.0.2303, and Instagram 445.0.0.45.83. Treat other package versions as unsupported until their compatibility is tested and the source pin is reviewed.

## Set up and check

Install the tools listed in [README.md](README.md), then run the checks from the repository root:

```sh
python3 -B scripts/check_privacy.py
python3 -B -m unittest discover -s tests -p '*test*.py'
```

The optional `python3 -B tests/workflow_tools_smoke.py PATH_TO_APK --cache PATH_ON_EXTERNAL_DRIVE` check verifies a supplied Instagram package with the pinned Google tools. Use only a trusted package outside the repository. It checks the publisher and version; it does not install the package.

For changes to patches or upstream pins, update the exact SHA-256 values in `upstream.lock.json` and run the build checks. Do not advance a pin just because upstream published a new version. Keep the installer fail-safe when a source, release, signature, patch, build, or signing check fails.

## Review checklist

- Use synthetic fixtures. Do not use personal media or account data in tests.
- Keep selected originals read-only and keep generated files separate.
- Keep downloads, build output, logs, and test caches outside the repository.
- Do not add network calls that send account or media data.
- Run the privacy check after editing files and before sharing a change.
- Describe what the tests prove. Do not claim an Instagram screen or publish flow works unless it was tested in the running app.

Report security issues using the private process in [SECURITY.md](SECURITY.md).
