"""Exercise workflow safety boundaries without touching installed applications."""
import argparse
import contextlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import io
import tarfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import workflow
import apk_tools


class WorkflowTest(unittest.TestCase):
    def setUp(self):
        base = Path(os.environ.get("AGENT_DATA_DIR", "/Volumes/External1TB/data/_custom/codex")) / "instagramOnMac"
        base.mkdir(parents=True, exist_ok=True)
        self.temporary = tempfile.TemporaryDirectory(prefix="workflow-test-", dir=base)
        self.root = Path(self.temporary.name)
        self.lock = dict(version="1", commit="test", source_sha256="a" * 64,
                         release_asset_sha256="b" * 64, release_asset_url="https://example.invalid/runtime.dmg")
        self.options = argparse.Namespace(cache=str(self.root / "cache"), dry_run=False,
            applications=str(self.root / "Applications"), appdata_root=str(self.root / "data"),
            apk=None, apk_url=None, apk_sha256=None, apk_signer_sha256=None)
        with patch.object(Path, "read_text", return_value=json.dumps(self.lock)):
            self.flow = workflow.Workflow(self.options)

    def tearDown(self):
        self.temporary.cleanup()

    def test_unknown_latest_leaves_app_unchanged(self):
        app = Path(self.options.applications) / "Mac.apk.app"
        app.mkdir(parents=True)
        (app / "keep").write_text("original")
        with patch.object(workflow, "read_url") as request:
            request.return_value.__enter__.return_value.read.return_value = b'{"tag_name":"v2","assets":[]}'
            with self.assertRaises(workflow.Failure):
                self.flow.install()
        self.assertEqual((app / "keep").read_text(), "original")

    def test_locked_fetch_skips_latest_but_verifies_pinned_downloads(self):
        archive_bytes = io.BytesIO()
        with tarfile.open(fileobj=archive_bytes, mode="w:gz") as archive:
            entry = tarfile.TarInfo("source/input.txt")
            entry.size = 5
            archive.addfile(entry, io.BytesIO(b"input"))
        source = archive_bytes.getvalue()
        dmg = b"owned asset fixture"
        import hashlib
        self.options.locked = True
        self.options.command = "fetch"
        self.flow.lock.update(source_url="https://example.invalid/source.tar.gz",
            source_sha256=hashlib.sha256(source).hexdigest(),
            release_asset_sha256=hashlib.sha256(dmg).hexdigest(), patches=[])
        def response(url):
            self.assertNotEqual(url, workflow.LATEST)
            return io.BytesIO(source if url == self.flow.lock["source_url"] else dmg)
        with patch.object(workflow, "read_url", side_effect=response) as request:
            self.flow.fetch()
        self.assertEqual(request.call_count, 2)
        self.assertEqual((self.flow.source / "input.txt").read_bytes(), b"input")
        self.assertEqual(workflow.digest(self.flow.work / "macapk.dmg"), self.flow.lock["release_asset_sha256"])

    def test_update_cannot_skip_latest_with_locked(self):
        self.options.locked = True
        self.options.command = "update"
        with patch.object(workflow, "read_url") as request:
            with self.assertRaisesRegex(workflow.Failure, "latest-release"):
                self.flow.check()
        request.assert_not_called()

    def fake_jdk(self, home, version="21.0.9"):
        (home / "bin").mkdir(parents=True)
        (home / "release").write_text('JAVA_VERSION="' + version + '"\n')
        for name in ("java", "javac"):
            binary = home / "bin" / name
            binary.write_text("owned test fixture")
            binary.chmod(0o755)
        return home

    def test_jdk_uses_homebrew_21_without_java_on_path(self):
        home = self.fake_jdk(self.root / "brew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home")
        with patch.dict(os.environ, {"HOMEBREW_PREFIX": str(self.root / "brew"), "PATH": ""}, clear=True):
            self.assertEqual(workflow.resolve_jdk(), home)

    def test_explicit_jdk_precedes_legacy_home_and_rejects_wrong_release(self):
        home = self.fake_jdk(self.root / "selected")
        wrong = self.fake_jdk(self.root / "wrong", "25.0.1")
        with patch.dict(os.environ, {"MACAPK_JDK_HOME": str(home), "JAVA_HOME": str(wrong)}, clear=True):
            self.assertEqual(workflow.resolve_jdk(), home)
        with patch.dict(os.environ, {"JAVA_HOME": str(home)}, clear=True):
            self.assertEqual(workflow.resolve_jdk(), home)
        for environment in ({"MACAPK_JDK_HOME": str(wrong)}, {"MACAPK_JDK": "25", "MACAPK_JDK_HOME": str(home)}):
            with self.subTest(environment=list(environment)), patch.dict(os.environ, environment, clear=True), self.assertRaises(workflow.Failure):
                workflow.resolve_jdk()
        (home / "bin/javac").unlink()
        with patch.dict(os.environ, {"MACAPK_JDK_HOME": str(home)}, clear=True), self.assertRaises(workflow.Failure):
            workflow.resolve_jdk()

    def test_doctor_does_not_claim_private_key_access(self):
        output = io.StringIO()
        with patch.object(workflow, "Workflow", return_value=self.flow), patch.object(self.flow, "require_host"), \
             patch.object(self.flow, "check"), patch.object(self.flow, "identity", return_value="configured label"), contextlib.redirect_stdout(output):
            self.assertEqual(workflow.main(["doctor", "--locked"]), 0)
        self.assertIn("private-key access is checked only during build signing", output.getvalue())

    def test_latest_requires_digest_and_url(self):
        release = dict(tag_name="v1", assets=[dict(browser_download_url=self.lock["release_asset_url"], digest="sha256:" + "b" * 64)])
        self.assertTrue(workflow.latest_matches(self.lock, release))
        release["assets"][0]["digest"] = "sha256:" + "c" * 64
        self.assertFalse(workflow.latest_matches(self.lock, release))

    def test_matching_signed_build_is_reused_after_fetch_validation(self):
        self.flow.app.mkdir(parents=True)
        (self.flow.work / "built-lock.json").write_text(json.dumps(self.lock))
        with patch.object(self.flow, "fetch") as fetch, patch.object(self.flow, "require_host"), \
             patch.object(self.flow, "identity") as identity, patch.object(workflow, "run", return_value="") as command:
            self.flow.build()
        fetch.assert_called_once()
        identity.assert_not_called()
        self.assertEqual(command.call_count, 1)
        self.assertEqual(command.call_args.args[0][:4], ["codesign", "--verify", "--deep", "--strict"])

    def test_build_identity_uses_bundled_jre_and_captured_artifact_ids(self):
        contents = self.root / "artifact/Contents"
        (contents / "Resources").mkdir(parents=True)
        target = contents / "Resources/build-id.txt"
        target.write_text("local-build-jdk-identity")
        generated = "".join(key + "=" + str(index) * 16 + "\n" for index, key in enumerate(
            ("CONVERTER_ID", "FRAMEWORK_ID", "JAVA_ID", "JARS_ID", "NATIVE_ID"), 1))
        with patch.object(workflow, "run", return_value=generated) as command:
            self.flow.write_build_identity(contents)
        self.assertEqual(target.read_text(), generated)
        args = command.call_args.args[0]
        self.assertEqual(args[args.index("--java-home") + 1], contents / "Resources/jre")
        self.assertEqual(args[args.index("--lib-dir") + 1], contents / "lib")
        self.assertEqual(args[args.index("--bin-dir") + 1], contents / "bin")

    def test_swift_products_compile_only_upstream_sources_and_official_asset_packaging_is_skipped(self):
        self.flow.lock["patches"] = []
        with patch.object(workflow, "run", return_value="") as command:
            products = self.flow.build_swift_products({})
        self.assertEqual(command.call_count, 3)
        self.assertTrue(all(call.args[0][0] == "swiftc" for call in command.call_args_list))
        sources = [str(arg) for call in command.call_args_list for arg in call.args[0]]
        self.assertIn(str(self.flow.source / "launcher/AppStubArguments.swift"), sources)
        self.assertTrue((products / "BuildInfo.generated.swift").read_text().startswith("enum BuildInfo"))

    def test_running_application_prevents_any_install_writes(self):
        with patch.object(self.flow, "check"), patch.object(self.flow, "require_host"), \
             patch.object(workflow.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)):
            with self.assertRaisesRegex(workflow.Failure, "Quit"):
                self.flow.install()
        self.assertFalse(Path(self.options.applications).exists())
        self.assertFalse(Path(self.options.appdata_root).exists())

    def test_unsupported_macos_is_rejected_before_build(self):
        with patch.object(workflow.platform, "system", return_value="Darwin"), \
             patch.object(workflow.platform, "machine", return_value="arm64"), \
             patch.object(workflow.platform, "mac_ver", return_value=("26.3", (), "")):
            with self.assertRaisesRegex(workflow.Failure, "26.4"):
                self.flow.require_host()

    def test_apk_wrong_package_and_unsupported_version_are_rejected(self):
        self.options.apk_signer_sha256 = "a" * 64
        with patch.object(workflow, "resolve_jdk", return_value=self.root / "jdk"), patch.object(workflow, "run", side_effect=["a" * 64, "package: name='another.app' versionName='445.1'"]):
            with self.assertRaisesRegex(workflow.Failure, "package"):
                apk_tools.metadata(Path("unused.apk"), "aapt2", "apksig.jar", self.root, trusted={"a" * 64})
        with patch.object(workflow, "resolve_jdk", return_value=self.root / "jdk"), patch.object(workflow, "run", side_effect=["a" * 64, "package: name='com.instagram.android' versionName='446.0' versionCode='1'"]):
            with self.assertRaisesRegex(workflow.Failure, "445"):
                apk_tools.metadata(Path("unused.apk"), "aapt2", "apksig.jar", self.root, trusted={"a" * 64})

    def test_apk_wrong_signer_is_rejected(self):
        self.options.apk_signer_sha256 = "a" * 64
        fields = dict(name="com.instagram.android", versionName="445.0", versionCode="1")
        toolset = ("aapt2", "apksig.jar", self.root, {"instagram_signers_sha256": ["a" * 64]})
        package = self.root / "unused.apk"
        package.write_bytes(b"owned test")
        with patch.object(apk_tools, "tools", return_value=toolset), patch.object(apk_tools, "metadata", return_value=(fields, {"b" * 64})):
            with self.assertRaisesRegex(workflow.Failure, "publisher"):
                self.flow.verify_apk(package)

    def test_download_hash_failure_does_not_replace_cached_artifact(self):
        self.flow.work.mkdir(parents=True)
        cached = self.flow.work / "asset"
        cached.write_bytes(b"old")
        import io
        with patch.object(workflow, "read_url", return_value=io.BytesIO(b"wrong")):
            with self.assertRaises(workflow.Failure):
                self.flow.download("https://example.invalid/file", "0" * 64, "asset")
        self.assertEqual(cached.read_bytes(), b"old")
        self.assertFalse((self.flow.work / "asset.partial").exists())

    def test_failed_step_writes_private_logs_without_echoing_command_or_output(self):
        logs = self.root / "logs"
        with patch.object(workflow, "LOG_DIRECTORY", logs):
            with self.assertRaises(workflow.Failure) as failure:
                workflow.run([sys.executable, "-c", "import sys; print('private-output', file=sys.stderr); sys.exit(3)"], label="tool-check")
        self.assertIn("tool-check failed", str(failure.exception))
        self.assertNotIn("private-output", str(failure.exception))
        stderr = next(logs.glob("*.stderr.log"))
        self.assertEqual(stderr.read_text().strip(), "private-output")
        self.assertEqual(stderr.stat().st_mode & 0o777, 0o600)
        self.assertEqual(logs.stat().st_mode & 0o777, 0o700)

    def test_untrusted_publisher_is_rejected_before_native_manifest_parser(self):
        with patch.object(workflow, "resolve_jdk", return_value=self.root / "jdk"), patch.object(workflow, "run", return_value="b" * 64) as command:
            with self.assertRaisesRegex(workflow.Failure, "publisher"):
                apk_tools.metadata(Path("unused.apk"), "aapt2", "apksig.jar", self.root, trusted={"a" * 64})
        self.assertEqual(command.call_count, 1)
        self.assertEqual(command.call_args.args[0][0], self.root / "jdk/bin/java")

    def test_install_failure_restores_host_bundle_and_preserves_user_data(self):
        app = Path(self.options.applications) / "Mac.apk.app"
        app.mkdir(parents=True)
        (app / "old").write_text("old runtime")
        self.flow.app.mkdir(parents=True)
        (self.flow.app / "new").write_text("new runtime")
        (self.flow.work / "built-lock.json").write_text(json.dumps(self.lock))
        data = Path(self.options.appdata_root)
        data.mkdir()
        (data / "untouched").write_text("user data")
        fake_home = self.root / "home"
        support = fake_home / "Library/Application Support/Mac.apk"
        support.parent.mkdir(parents=True)
        support.symlink_to(self.root / "support")
        runtime = self.root / "support/runtime"
        (runtime / "Resources").mkdir(parents=True)
        (runtime / "Resources/macapk-runtime").write_text("old runtime code")
        def command(args, **kwargs):
            if args[0] == "ditto":
                import shutil
                shutil.copytree(args[1], args[2])
            if str(args[0]).endswith("macapk-installhelper"):
                (runtime / "Resources/macapk-runtime").write_text("new runtime code")
                raise subprocess.CalledProcessError(1, ["helper"])
            return ""
        with patch.object(self.flow, "check"), patch.object(self.flow, "require_host"), \
             patch.object(workflow.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)), \
             patch.object(workflow, "run", side_effect=command), patch.object(Path, "home", return_value=fake_home):
            with self.assertRaises(subprocess.CalledProcessError):
                self.flow.install()
        self.assertEqual((app / "old").read_text(), "old runtime")
        self.assertEqual((data / "untouched").read_text(), "user data")
        self.assertEqual((runtime / "Resources/macapk-runtime").read_text(), "old runtime code")
        self.assertFalse(app.with_name(".Mac.apk.previous.app").exists())

    def test_first_install_data_root_and_existing_root_discovery(self):
        self.options.appdata_root = None
        first_data = self.flow.data_root()
        self.assertTrue(str(first_data).endswith("data/_custom/instagramOnMac/apps"))
        self.assertNotIn(self.flow.cache, first_data.parents)
        android = Path(self.options.applications) / "Instagram.app/Contents/android"
        android.parent.mkdir(parents=True)
        target = self.root / "saved-data/com.instagram.android/android"
        target.mkdir(parents=True)
        android.symlink_to(target)
        self.assertEqual(self.flow.data_root(), self.root / "saved-data")
        android.unlink()
        flat = self.root / "saved-data/com.instagram.android_445.0.0.45.83"
        flat.mkdir()
        android.symlink_to(flat)
        self.assertEqual(self.flow.data_root(), self.root / "saved-data")
        android.unlink()
        android.symlink_to(self.root / "ambiguous")
        with self.assertRaisesRegex(workflow.Failure, "ambiguous"):
            self.flow.data_root()

    def test_agent_cache_pruning_cannot_remove_default_application_data(self):
        self.options.appdata_root = None
        mount = self.root / "external-drive"
        self.flow.cache = mount / "agent-workspace/job/instagramOnMac"
        self.flow.cache.mkdir(parents=True)
        with patch.object(Path, "is_mount", new=lambda path: path == mount):
            data = self.flow.data_root()
        self.assertEqual(data, mount / "data/_custom/instagramOnMac/apps")
        data.mkdir(parents=True)
        (data / "keep").write_text("owned data fixture")
        import shutil
        shutil.rmtree(mount / "agent-workspace")
        self.assertEqual((data / "keep").read_text(), "owned data fixture")

    def test_stage_copy_and_original_rename_failure_never_delete_original(self):
        app = Path(self.options.applications) / "Mac.apk.app"
        app.mkdir(parents=True)
        (app / "keep").write_text("working runtime")
        self.flow.app.mkdir(parents=True)
        (self.flow.app / "new").write_text("new runtime")
        (self.flow.work / "built-lock.json").write_text(json.dumps(self.lock))
        original_rename = Path.rename
        for stage in ("copy", "park"):
            def command(args, **kwargs):
                if args[0] == "ditto":
                    import shutil
                    shutil.copytree(args[1], args[2])
                    if stage == "copy":
                        raise subprocess.CalledProcessError(1, ["ditto"])
                return ""
            def rename(path, target):
                if path == app:
                    raise PermissionError("test refusal")
                return original_rename(path, target)
            with self.subTest(stage=stage), patch.object(self.flow, "check"), \
                 patch.object(self.flow, "require_host"), patch.object(Path, "home", return_value=self.root / "home"), \
                 patch.object(workflow.subprocess, "run", return_value=subprocess.CompletedProcess([], 1)), \
                 patch.object(workflow, "run", side_effect=command), patch.object(Path, "rename", new=rename):
                with self.assertRaises((PermissionError, subprocess.CalledProcessError)):
                    self.flow.install()
            self.assertEqual((app / "keep").read_text(), "working runtime")
            self.assertFalse(app.with_name(".Mac.apk.installing.app").exists())
            self.assertFalse(app.with_name(".Mac.apk.previous.app").exists())


if __name__ == "__main__":
    unittest.main()
