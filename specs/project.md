# Instagram on Mac

- Keep only portable source, patches, public dependency pins, documentation, and synthetic tests in this repository.
- Never include account data, tokens, cookies, app databases, logs, screenshots, media, APKs, build products, signing keys, personal paths, account identifiers, or local signing identities.
- Keep Git author and committer metadata generic for this repository. Do not add a remote or publish it without a separate request.
- Publish a source-only experimental release with a reproducible setup, clear limitations, and approved cover art. Never publish personal screenshots or account media.
- Use C2 / Editorial Serif as the final cover: a large pink camera, thin window rule without traffic lights, large serif Instagram title, and smaller on Mac text. Align both footer lines with the title's visible I left edge and the end of on Mac with its final m right edge. Preserve the approved style and remove image metadata. The only approved raster asset is assets/cover.png, pinned by the privacy check.
- Download Mac.apk from its official GitHub release. Pin the tested source commit and download checksums. Retain upstream license notices.
- Fetch, patch, build, install, check for updates, and update through one command-line entry point.
- Fail before changing installed apps if a new release is unsupported, a checksum fails, a patch does not apply, a build fails, or signing fails.
- Keep downloads and build output outside the repository on the external data drive. Honor an external work-root override.
- Use a local signing identity supplied at runtime or recovered from existing public signature metadata. Never export keys or store an identity in the repository.
- Preserve the installed package's app data during updates. Never reset, uninstall, log out, copy credentials, or replace saved-account stores.
- Validate the Instagram package and publisher signature before installation. Downloading an APK does not make it an official publisher download.
- Keep version-specific Instagram compatibility fixes gated to their tested version. Do not claim a newer APK is tested automatically.
- Test build reproducibility, privacy checks, failed-update safety, and app-data preservation with isolated fixtures.

## Media flow

- Show only files explicitly chosen through Browse. Do not query Photos, PhotoKit, camera rolls, arbitrary host folders, or background media scans. Remove Photos and alternative-source choices from this flow.
- Replace the gallery Camera option with one Browse action. Draw a clear folder icon with vector paths, keep its label readable, and preserve normal media-item selection positions.
- Remember selected files by reference. Do not copy originals into an import library or change their contents, names, dates, or permissions. Editing and filters must write separate output files.
- Prepare MOV uploads as separate compatible MP4 cache files. Reuse the cached MP4 from both the gallery and Browse when source identity, size, and modification time match. Keep originals unchanged; invalidate changed sources and show conversion progress or failure.
- Enforce read-only access to selected originals at all applicable provider and runtime file-access boundaries. Remember missing files safely without scanning for replacements.
- Keep file selection, gallery thumbnails, media preview, and Next-to-editor navigation responsive. Measure these paths before and after changes.
- Next must open a visible, usable image or video editor. Test with synthetic fixtures through selection, preview, Next, filters, and cancellation. Never press Share, publish, or send a test post.
- Show real conversion and media-player progress, with actionable errors when those jobs fail or exceed their deadlines. Native editor rendering can bypass Java frame hints; missing hints must not claim failure, cover the editor, or block its normal controls. Mark a preview ready only from a verified frame.
- Preserve Android dimension rules: nonzero fractional layout sizes round to at least one pixel; offsets truncate, and zero and layout enums stay unchanged.
- Ship verified fixes to the installed app with its stable local signature, while preserving app data and the repository's privacy rules.
