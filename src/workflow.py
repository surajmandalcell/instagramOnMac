"""Verified downloads, isolated builds, and explicit local installation."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time
import urllib.request
import urllib.parse
import zipfile

LATEST = "https://api.github.com/repos/kksimp/Mac.apk/releases/latest"
REPO = Path(__file__).resolve().parents[1]
LOG_DIRECTORY = None


class Failure(Exception):
    pass


def digest(path):
    result = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(chunk)
    return result.hexdigest()


def run(args, label=None, timeout=60, **kwargs):
    label = label or Path(args[0]).name
    label = re.sub(r"[^a-zA-Z0-9_-]", "_", label)
    if LOG_DIRECTORY is None:
        return subprocess.run([str(a) for a in args], check=True, text=True,
                              capture_output=True, timeout=timeout, **kwargs).stdout
    LOG_DIRECTORY.mkdir(parents=True, exist_ok=True, mode=0o700)
    LOG_DIRECTORY.chmod(0o700)
    stem = str(time.time_ns()) + "-" + label
    stdout = LOG_DIRECTORY / (stem + ".stdout.log")
    stderr = LOG_DIRECTORY / (stem + ".stderr.log")
    out_fd = os.open(stdout, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    err_fd = os.open(stderr, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(out_fd, "w") as output, os.fdopen(err_fd, "w") as errors:
            subprocess.run([str(a) for a in args], check=True, text=True,
                           stdout=output, stderr=errors, timeout=timeout, **kwargs)
    except (OSError, subprocess.SubprocessError):
        raise Failure(label + " failed. Private logs: " + str(LOG_DIRECTORY / (stem + ".*.log"))) from None
    return stdout.read_text(errors="replace")


def clean_env():
    return {key: value for key, value in os.environ.items()
            if not key.startswith("MACAPK_") or key in ("MACAPK_SIGN_IDENTITY", "MACAPK_JDK", "MACAPK_JDK_HOME")}


def resolve_jdk():
    """Use the same tested JDK for compilation and Android publisher tools."""
    if os.environ.get("MACAPK_JDK", "21") != "21":
        raise Failure("This recipe requires JDK 21; MACAPK_JDK must be 21.")
    explicit = os.environ.get("MACAPK_JDK_HOME") or os.environ.get("JAVA_HOME")
    home = (Path(explicit) if explicit else Path(os.environ.get("HOMEBREW_PREFIX", "/opt/homebrew")) / "opt/openjdk@21/libexec/openjdk.jdk/Contents/Home").expanduser().absolute()
    try:
        version = (home / "release").read_text()
        valid = re.search(r'^JAVA_VERSION="21(?:\.|\")', version, re.M)
        valid = valid and all((home / "bin" / tool).is_file() and os.access(home / "bin" / tool, os.X_OK) for tool in ("java", "javac"))
    except OSError:
        valid = False
    if not valid:
        raise Failure("Install openjdk@21 or set MACAPK_JDK_HOME to a complete JDK 21 home.")
    return home


def require_external(path):
    if platform.system() == "Darwin":
        ancestor = path
        while not ancestor.exists() and ancestor != ancestor.parent:
            ancestor = ancestor.parent
        system_roots = [Path("/"), Path("/System/Volumes/Data")]
        if ancestor.stat().st_dev in {root.stat().st_dev for root in system_roots if root.exists()}:
            raise Failure("Choose a data directory on an external drive.")


def checked_url(url):
    if not url.startswith("https://"):
        raise Failure("Downloads require HTTPS.")
    return url


def read_url(url):
    request = urllib.request.Request(checked_url(url), headers={"User-Agent": "instagram-on-mac"})
    return urllib.request.urlopen(request, timeout=60)


def latest_matches(lock, release):
    assets = release.get("assets", [])
    return (release.get("tag_name", "").lstrip("v") == lock["version"]
            and any(a.get("browser_download_url") == lock["release_asset_url"]
                    and a.get("digest") == "sha256:" + lock["release_asset_sha256"]
                    for a in assets))


class Workflow:
    def __init__(self, options):
        self.options = options
        self.lock = json.loads((REPO / "upstream.lock.json").read_text())
        self.cache = Path(options.cache).expanduser().resolve()
        if self.cache == REPO or REPO in self.cache.parents:
            raise Failure("Cache must be outside the repository.")
        require_external(self.cache)
        for key in ("source_sha256", "release_asset_sha256"):
            if not re.fullmatch(r"[0-9a-f]{64}", self.lock[key]):
                raise Failure("The tested lock has an invalid digest.")
        self.work = self.cache / self.lock["commit"]
        global LOG_DIRECTORY
        LOG_DIRECTORY = self.work / "logs"
        self.source = self.work / "source"
        self.app = self.work / "Mac.apk.app"

    def check(self):
        if getattr(self.options, "locked", False):
            if getattr(self.options, "command", None) == "update":
                raise Failure("update requires a latest-release check. Use build --locked to reproduce the tested pin.")
            return {"tag_name": "v" + self.lock["version"], "locked": True}
        with read_url(LATEST) as response:
            release = json.load(response)
        if not latest_matches(self.lock, release):
            raise Failure("Latest upstream is not tested. Existing applications remain unchanged.")
        return release

    def download(self, url, sha, name):
        self.work.mkdir(parents=True, exist_ok=True)
        target = self.work / name
        if target.exists() and digest(target) == sha:
            return target
        partial = target.with_suffix(target.suffix + ".partial")
        try:
            with read_url(url) as response, partial.open("wb") as output:
                shutil.copyfileobj(response, output)
            if digest(partial) != sha:
                raise Failure("Downloaded file does not match its SHA-256 digest.")
            partial.replace(target)
        finally:
            partial.unlink(missing_ok=True)
        return target

    def fetch(self):
        self.check()
        checked_patches = []
        for patch in self.lock["patches"]:
            patch_path = (REPO / patch["path"]).resolve()
            if REPO not in patch_path.parents or digest(patch_path) != patch["sha256"]:
                raise Failure("Patch is outside the repository or has changed.")
            checked_patches.append(patch_path)
        archive = self.download(self.lock["source_url"], self.lock["source_sha256"], "source.tar.gz")
        self.download(self.lock["release_asset_url"], self.lock["release_asset_sha256"], "macapk.dmg")
        fingerprint = hashlib.sha256(json.dumps(self.lock, sort_keys=True).encode()).hexdigest()
        marker = self.source / ".compat-lock"
        if marker.exists() and marker.read_text() == fingerprint:
            return
        stage = self.work / "source.partial"
        if stage.exists():
            shutil.rmtree(stage)
        stage.mkdir()
        try:
            with tarfile.open(archive) as tar:
                # Reject links and traversal before extraction, including archive top-level paths.
                members = tar.getmembers()
                for member in members:
                    path = Path(member.name)
                    if path.is_absolute() or ".." in path.parts or member.issym() or member.islnk():
                        raise Failure("Source archive contains an unsafe path or link.")
                    if not (member.isdir() or member.isfile()):
                        raise Failure("Source archive contains a special file.")
                tar.extractall(stage, members=members)
            roots = list(stage.iterdir())
            if len(roots) != 1 or not roots[0].is_dir():
                raise Failure("Unexpected source archive layout.")
            root = roots[0]
            for patch_path in checked_patches:
                run(["git", "apply", "--check", patch_path], cwd=root)
                run(["git", "apply", patch_path], cwd=root)
            (root / ".compat-lock").write_text(fingerprint)
            if self.source.exists():
                shutil.rmtree(self.source)
            root.rename(self.source)
        finally:
            shutil.rmtree(stage, ignore_errors=True)

    def identity(self):
        identity = os.environ.get("MACAPK_SIGN_IDENTITY", "")
        if not identity and Path(self.options.applications, "Mac.apk.app").exists():
            result = subprocess.run(["codesign", "-dvv", str(Path(self.options.applications, "Mac.apk.app"))],
                                    text=True, capture_output=True, check=True)
            identities = re.findall(r"^Authority=(.+)$", result.stderr, re.M)
            identity = identities[0] if identities else ""
        if not identity or identity == "-":
            raise Failure("Set MACAPK_SIGN_IDENTITY to a local signing identity. Ad-hoc signing is not supported.")
        return identity

    def build(self):
        self.fetch()
        if self.options.dry_run:
            print("Verified source and patches. Plan: build runtime, copy official DMG assets, relink, sign, verify.")
            return
        self.require_host()
        built_lock = self.work / "built-lock.json"
        if not getattr(self.options, "rebuild", False) and built_lock.exists() and self.app.exists():
            try:
                matches = json.loads(built_lock.read_text()) == self.lock
                if matches:
                    run(["codesign", "--verify", "--deep", "--strict", self.app], label="verify-cached-build")
                    print("Reused the verified build for the current source and patch lock.")
                    return
            except (Failure, ValueError):
                pass
        identity = self.identity()
        jdk = str(resolve_jdk())
        build_env = dict(clean_env(), MACAPK_NO_BUNDLE_SYNC="1", MACAPK_BUILD_NO_BUNDLE_SYNC="1",
                         JAVA_HOME=jdk, MACAPK_JDK="21", MACAPK_JDK_HOME=jdk)
        print("Building runtime and launcher in the external cache. Each build step has a 15-minute limit.", flush=True)
        run(["bash", "runtime/scripts/build.sh"], cwd=self.source, env=build_env, label="runtime-build", timeout=900)
        compiled = self.build_swift_products(build_env)
        mount = self.work / "dmg-mount"
        mount.mkdir(exist_ok=True)
        modern_diskutil = int(platform.mac_ver()[0].split(".")[0] or "0") >= 27
        attach = (["diskutil", "image", "attach", "--readOnly", "--nobrowse", "--mountPoint", mount, self.work / "macapk.dmg"]
                  if modern_diskutil else ["hdiutil", "attach", "-readonly", "-nobrowse", "-mountpoint", mount, self.work / "macapk.dmg"])
        run(attach, label="attach-official-dmg")
        try:
            candidates = list(mount.glob("*.app"))
            official = next((p for p in candidates if p.name == "Mac.apk.app"), None)
            if official is None:
                raise Failure("Official DMG does not contain Mac.apk.app.")
            run(["codesign", "--verify", "--deep", "--strict", official], label="verify-official-app")
            if self.app.exists():
                shutil.rmtree(self.app)
            run(["ditto", official, self.app])
        finally:
            run(["diskutil", "eject", mount] if modern_diskutil else ["hdiutil", "detach", mount], label="detach-official-dmg")
        contents = self.app / "Contents"
        for relative in ("MacOS/MacApk", "bin/macapk-installhelper", "Resources/appstub/MacApkAppStub"):
            shutil.copy2(compiled / Path(relative).name, contents / relative)
        output = self.source / "runtime/build"
        mapping = {"macapk-runtime": "Resources", "macapk-translator": "bin",
                   "macapk-elfexec": "bin", "libmacapk-bionic-shim.dylib": "bin",
                   "libmacapk-app-stub.dylib": "lib"}
        for path in (output / "bin").iterdir():
            if path.name in mapping or path.suffix == ".dylib" or path.name == "MoltenVK_icd.json":
                destination = contents / mapping.get(path.name, "Resources") / path.name
                destination.parent.mkdir(exist_ok=True)
                shutil.copy2(path, destination)
        for name in ("android-framework.jar", "macapk-loader.jar", "java_base_patch", "jdk_unsupported_patch", "pairip-refs"):
            path = output / "lib" / name
            if path.is_dir():
                shutil.copytree(path, contents / "lib" / name, dirs_exist_ok=True)
            elif path.is_file():
                shutil.copy2(path, contents / "lib" / name)
        run(["bash", self.source / "scripts/relink_bundle_deps.sh", contents, self.source])
        entitlements = self.source / "runtime/scripts/jit-entitlements.plist"
        # Re-sign native leaf code before enclosing bundles. Keep the official bundled JRE and assets.
        for path in sorted(contents.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if path.is_file() and not path.is_symlink():
                kind = run(["file", "-b", path])
                if "Mach-O" in kind:
                    run(["codesign", "--force", "--sign", identity, "--options", "runtime",
                         "--entitlements", entitlements, path])
            elif path.is_dir() and path.suffix in (".app", ".framework"):
                run(["codesign", "--force", "--sign", identity, "--options", "runtime", path])
        self.write_build_identity(contents)
        run(["codesign", "--force", "--sign", identity, "--options", "runtime", "--entitlements", entitlements, self.app])
        run(["codesign", "--verify", "--deep", "--strict", self.app])
        (self.work / "built-lock.json").write_text(json.dumps(self.lock, sort_keys=True))
        print("Built and verified the patched runtime in the external cache.")

    def build_swift_products(self, env):
        # These are the three compiler recipes from upstream build_launcher.sh.
        # Its remaining packaging stages require source-built assets; ours come from the official DMG.
        target = self.work / "swift-products"
        target.mkdir(parents=True, exist_ok=True)
        build_info = target / "BuildInfo.generated.swift"
        patch_id = hashlib.sha256(json.dumps(self.lock["patches"], sort_keys=True).encode()).hexdigest()
        build_id = (time.strftime("%y%m%d.%H%M") + "-v" + self.lock["version"]
                    + "-" + self.lock["commit"][:12] + "-" + patch_id[:12])
        build_info.write_text("enum BuildInfo { static let id = " + json.dumps(build_id)
                              + "; static let releaseVersion: String? = nil }\n")
        launcher = self.source / "launcher"
        recipes = (
            ("MacApk", ("AppKit", "SwiftUI", "UniformTypeIdentifiers", "Combine"),
             ("MacApkLauncherApp.swift", "InstallCore.swift", "BundleGenerator.swift", "UpdateCheck.swift"), True),
            ("MacApkAppStub", ("AppKit",),
             ("AppStubMain.swift", "AppStubArguments.swift", "InstallCore.swift"), False),
            ("macapk-installhelper", ("AppKit",),
             ("InstallHelperMain.swift", "InstallCore.swift", "BundleGenerator.swift"), True),
        )
        for name, frameworks, sources, needs_info in recipes:
            args = ["swiftc", "-O", "-parse-as-library", "-target", "arm64-apple-macos26.0"]
            for framework in frameworks:
                args.extend(("-framework", framework))
            args.extend(("-o", target / name))
            args.extend(launcher / source for source in sources)
            if needs_info:
                args.append(build_info)
            print("Compiling " + name + " in the external cache.", flush=True)
            run(args, env=env, label="swift-" + name, timeout=900)
        return target

    def write_build_identity(self, contents):
        identity = run([sys.executable, "-B", self.source / "runtime/scripts/build_ids.py",
                        "--lib-dir", contents / "lib", "--bin-dir", contents / "bin",
                        "--java-home", contents / "Resources/jre"], label="generate-build-identity")
        fields = dict(line.split("=", 1) for line in identity.splitlines() if "=" in line)
        expected = {"CONVERTER_ID", "FRAMEWORK_ID", "JAVA_ID", "JARS_ID", "NATIVE_ID"}
        if set(fields) != expected or any(not re.fullmatch(r"[0-9a-f]{16}", value) for value in fields.values()):
            raise Failure("Generated build identity is invalid. The app was not signed.")
        (contents / "Resources/build-id.txt").write_text(identity)

    @staticmethod
    def require_host():
        if platform.system() != "Darwin" or platform.machine() != "arm64":
            raise Failure("This runtime requires an Apple Silicon Mac.")
        version = tuple(int(part) for part in platform.mac_ver()[0].split(".")[:2])
        if version < (26, 4):
            raise Failure("This runtime requires macOS 26.4 or later.")
        for tool in ("cmake", "clang", "swiftc", "git", "patch", "file", "install_name_tool", "codesign", "hdiutil", "ditto"):
            if not shutil.which(tool):
                raise Failure("Missing build tool: " + tool)
        resolve_jdk()

    def verify_apk(self, apk):
        from apk_tools import verify
        verify(self, apk)

    def install(self):
        self.check()
        self.require_host()
        running = subprocess.run(["pgrep", "-f", r"/Mac\.apk\.app/|/Instagram\.app/|macapk-runtime"], capture_output=True)
        if running.returncode == 0:
            raise Failure("Quit Mac.apk and Instagram before installation. No files were changed.")
        data = self.data_root()
        require_external(data)
        if data == REPO or REPO in data.parents:
            raise Failure("Application data must be outside the repository.")
        marker = self.work / "built-lock.json"
        if not marker.exists() or json.loads(marker.read_text()) != self.lock:
            self.build()
            if self.options.dry_run:
                print("Install plan verified. No application or user data was changed.")
                return
        run(["codesign", "--verify", "--deep", "--strict", self.app])
        apk = Path(self.options.apk).resolve() if self.options.apk else None
        if self.options.apk_url:
            if not self.options.apk_sha256:
                raise Failure("--apk-url requires --apk-sha256.")
            suffix = Path(urllib.parse.urlparse(self.options.apk_url).path).suffix.lower()
            if suffix not in (".apk", ".xapk", ".apkm", ".apks"):
                raise Failure("APK URL must end with .apk, .xapk, .apkm, or .apks.")
            apk = self.download(self.options.apk_url, self.options.apk_sha256, "instagram" + suffix)
        if apk:
            self.verify_apk(apk)
            if (Path(self.options.applications) / "Instagram.app").exists():
                raise Failure("This command updates the shared runtime only for existing Instagram installs. APK replacement requires a verified data migration route.")
        if self.options.dry_run:
            print("Install checks passed. No application or user data was changed.")
            return
        support = Path.home() / "Library/Application Support/Mac.apk"
        if support.exists() and not support.is_symlink():
            raise Failure("Existing Mac.apk support data is not externally linked. Choose a reviewed migration before installation.")
        if support.exists():
            require_external(support.resolve())
        if not support.exists():
            external_support = data.parent / "support"
            external_support.mkdir(parents=True, exist_ok=True)
            support.parent.mkdir(parents=True, exist_ok=True)
            support.symlink_to(external_support, target_is_directory=True)
        runtime = support.resolve() / "runtime"
        previous_runtime = self.work / "runtime.previous"
        had_runtime = runtime.exists()
        if previous_runtime.exists():
            raise Failure("A previous runtime backup needs review. No application was changed.")
        if had_runtime:
            if runtime.is_symlink() or not (runtime / "Resources/macapk-runtime").is_file():
                raise Failure("Existing runtime code layout is not recognized. No application was changed.")
        destination = Path(self.options.applications) / "Mac.apk.app"
        staged = destination.with_name(".Mac.apk.installing.app")
        backup = destination.with_name(".Mac.apk.previous.app")
        if staged.exists() or backup.exists():
            raise Failure("A prior install needs review. No application was changed.")
        destination.parent.mkdir(parents=True, exist_ok=True)
        existed = destination.exists()
        env = dict(clean_env(), MACAPK_APPDATA_ROOT=str(data),
                   MACAPK_CANONICAL_APP=str(destination), MACAPK_SYSTEM_APPS_DIR=str(destination.parent))
        env.pop("MACAPK_RUNTIME_ROOT", None)
        promoted = False
        runtime_started = False
        try:
            if had_runtime:
                run(["ditto", runtime, previous_runtime])
            run(["ditto", self.app, staged])
            if existed:
                destination.rename(backup)
            staged.rename(destination)
            promoted = True
            helper = destination / "Contents/bin/macapk-installhelper"
            runtime_started = True
            run([helper, "runtime-install", "--no-ui", "--json"], env=env)
            if apk:
                run([helper, "install", "--apk", apk, "--source", "gui", "--no-ui", "--json"], env=env)
        except Exception:
            if promoted and destination.exists():
                shutil.rmtree(destination)
            if existed and backup.exists():
                backup.rename(destination)
            if runtime_started and runtime.exists():
                shutil.rmtree(runtime)
            if runtime_started and had_runtime and previous_runtime.exists():
                previous_runtime.rename(runtime)
            raise
        finally:
            if staged.exists():
                shutil.rmtree(staged)
            if not runtime_started and previous_runtime.exists():
                shutil.rmtree(previous_runtime)
        if backup.exists():
            shutil.rmtree(backup)
        if previous_runtime.exists():
            shutil.rmtree(previous_runtime)
        print("Installed the runtime. Existing application data was preserved.")

    def data_root(self):
        if self.options.appdata_root:
            return Path(self.options.appdata_root).expanduser().resolve()
        android = Path(self.options.applications) / "Instagram.app/Contents/android"
        if android.is_symlink():
            resolved = android.resolve()
            # Normal upstream layout: <appdata-root>/<package>/android.
            if resolved.name == "android" and resolved.parent.name == "com.instagram.android":
                return resolved.parent.parent
            if resolved.name == "com.instagram.android":
                return resolved.parent
            if re.fullmatch(r"com\.instagram\.android_445(?:\.\d+)+", resolved.name):
                return resolved.parent
            raise Failure("Existing Instagram data layout is ambiguous. Specify --appdata-root after checking its public directory layout.")
        if android.exists():
            raise Failure("Existing Instagram data is inside its bundle. Migrate it before updating; no files were changed.")
        mount = self.cache
        while not mount.is_mount() and mount != mount.parent:
            mount = mount.parent
        require_external(mount)
        return mount / "data/_custom/instagramOnMac/apps"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("fetch", "build", "install", "update", "doctor"))
    parser.add_argument("--check", action="store_true", help="Check tested upstream support without installing")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rebuild", action="store_true", help="Rebuild even when a matching signed artifact exists")
    parser.add_argument("--locked", action="store_true", help="Use the verified upstream pin without querying the latest release")
    base = os.environ.get("AGENT_DATA_DIR", "/Volumes/External1TB/data/_custom/codex")
    parser.add_argument("--cache", default=os.environ.get("INSTAGRAM_ON_MAC_CACHE", str(Path(base) / "instagramOnMac")))
    parser.add_argument("--applications", default="/Applications")
    parser.add_argument("--appdata-root", default=os.environ.get("MACAPK_APPDATA_ROOT"))
    parser.add_argument("--apk")
    parser.add_argument("--apk-url")
    parser.add_argument("--apk-sha256")
    options = parser.parse_args(argv)
    if options.command == "update" and options.locked:
        parser.error("update cannot use --locked; use build or install --locked for the tested pin")
    try:
        workflow = Workflow(options)
        if options.command != "doctor" and not options.check:
            workflow.cache.mkdir(parents=True, exist_ok=True)
            operation_lock = (workflow.cache / ".workflow.lock").open("a")
            try:
                fcntl.flock(operation_lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                operation_lock.close()
                raise Failure("Another installer command is running. No application was changed.")
        if options.command == "doctor":
            workflow.require_host()
            workflow.check()
            workflow.identity()
            print("Build tools and " + ("locked upstream pin" if options.locked else "tested latest upstream")
                  + " are ready. Signing identity metadata is configured; private-key access is checked only during build signing.")
        elif options.command == "update" and options.check:
            workflow.check()
            print("Latest official release matches the tested lock.")
        elif options.command == "update":
            workflow.build()
            workflow.install()
        else:
            getattr(workflow, options.command)()
        return 0
    except (Failure, OSError, ValueError, KeyError, subprocess.SubprocessError, zipfile.BadZipFile, tarfile.TarError) as error:
        # Do not print command arguments, local signing names, or subprocess logs.
        print("Error: " + (str(error) if isinstance(error, Failure) else type(error).__name__ + "; operation stopped safely."))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
