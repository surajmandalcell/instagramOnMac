"""Package containers must be complete, consistent, and signed by the publisher."""
from pathlib import Path
import hashlib
import os
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zipfile
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import apk_tools
import workflow


class ContainerTest(unittest.TestCase):
    def setUp(self):
        root = Path(os.environ.get("AGENT_DATA_DIR", "/Volumes/External1TB/data/_custom/codex")) / "instagramOnMac"
        root.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="container-test-", dir=root)
        self.root = Path(self.temp.name)
        self.flow = SimpleNamespace(work=self.root, options=SimpleNamespace(apk_signer_sha256=None))
        self.signer = "a" * 64
        self.toolset = ("aapt2", "apksig.jar", self.root, {"instagram_signers_sha256": [self.signer]})

    def tearDown(self):
        self.temp.cleanup()

    def container(self, names):
        target = self.root / "package.xapk"
        with zipfile.ZipFile(target, "w") as archive:
            for name in names:
                archive.writestr(name, b"owned test package")
        return target

    def metadata(self, apk):
        fields = dict(name="com.instagram.android", versionName=apk_tools.SUPPORTED_VERSION, versionCode="1")
        if apk.name != "base.apk":
            fields["split"] = "config.xhdpi"
            fields["versionName"] = ""
        return fields, {self.signer}

    def verify(self, package, metadata=None, manifest=""):
        with patch.object(apk_tools, "tools", return_value=self.toolset), \
             patch.object(apk_tools, "metadata", side_effect=lambda apk, *args, **kwargs: (metadata or self.metadata)(apk)), \
             patch.object(workflow, "run", return_value=manifest):
            apk_tools.verify(self.flow, package)

    def test_complete_split_container_is_verified_without_changing_source(self):
        package = self.container(["base.apk", "config.xhdpi.apk", "manifest.json"])
        original = package.read_bytes()
        self.verify(package)
        self.assertEqual(package.read_bytes(), original)
        self.assertEqual(list(self.root.glob("verify-package-*")), [])

    def test_mixed_split_versions_are_rejected(self):
        package = self.container(["base.apk", "config.xhdpi.apk"])
        def metadata(apk):
            fields, signers = self.metadata(apk)
            if fields.get("split"):
                fields["versionCode"] = "2"
            return fields, signers
        with self.assertRaisesRegex(workflow.Failure, "same package"):
            self.verify(package, metadata)

    def test_only_the_exact_tested_base_version_is_accepted(self):
        for version in ("445.0", "445.0.0.45.82", "445.0.0.45.84", "446.0.0.45.83", ""):
            with self.subTest(version=version), patch.object(workflow, "resolve_jdk", return_value=self.root / "jdk"), \
                 patch.object(workflow, "run", side_effect=[self.signer, "package: name='com.instagram.android' versionName='" + version + "' versionCode='1'"]):
                with self.assertRaisesRegex(workflow.Failure, apk_tools.SUPPORTED_VERSION):
                    apk_tools.metadata(self.root / "base.apk", "aapt2", "apksig.jar", self.root, trusted={self.signer})

    def test_exact_version_and_versionless_split_use_resolved_java(self):
        for split in ("", " split='config.arm64_v8a'"):
            version = "" if split else apk_tools.SUPPORTED_VERSION
            with self.subTest(split=bool(split)), patch.object(workflow, "resolve_jdk", return_value=self.root / "jdk"), \
                 patch.object(workflow, "run", side_effect=[self.signer, "package: name='com.instagram.android' versionName='" + version + "' versionCode='1'" + split, ""]) as command:
                apk_tools.metadata(self.root / "base.apk", "aapt2", "apksig.jar", self.root, trusted={self.signer})
                self.assertEqual(command.call_args_list[0].args[0][0], self.root / "jdk/bin/java")

    def test_signature_verifier_compiles_with_the_same_resolved_jdk(self):
        verifier = self.root / "apksig.jar"
        verifier.write_bytes(b"owned verifier fixture")
        aapt = self.root / "aapt2.jar"
        with zipfile.ZipFile(aapt, "w") as archive:
            archive.writestr("aapt2", b"owned native tool fixture")
        self.flow.download = lambda url, sha, name: aapt if name == "aapt2.jar" else verifier
        target = self.root / "apk-tools"
        target.mkdir()
        (target / "PublisherVerifier.class").write_bytes(b"previous compiler output")
        (target / "verifier.sha256").write_text(hashlib.sha256(apk_tools.VERIFIER.encode() + verifier.read_bytes()).hexdigest())
        with patch.object(workflow, "resolve_jdk", return_value=self.root / "jdk"), patch.object(workflow, "run", return_value="") as command:
            apk_tools.tools(self.flow)
        self.assertEqual(command.call_args.args[0][0], self.root / "jdk/bin/javac")

    def test_mixed_signers_are_rejected(self):
        package = self.container(["base.apk", "config.xhdpi.apk"])
        def metadata(apk):
            fields, signers = self.metadata(apk)
            return fields, {"b" * 64} if fields.get("split") else signers
        with self.assertRaisesRegex(workflow.Failure, "publisher"):
            self.verify(package, metadata)

    def test_no_base_is_rejected(self):
        with self.assertRaisesRegex(workflow.Failure, "exactly one base"):
            self.verify(self.container(["config.xhdpi.apk"]))

    def test_missing_required_density_split_type_is_rejected(self):
        package = self.container(["base.apk", "config.xhdpi.apk"])
        def metadata(apk):
            fields, signers = self.metadata(apk)
            if not fields.get("split"):
                fields["_required_types"] = {"base__density"}
            return fields, signers
        with self.assertRaisesRegex(workflow.Failure, "missing required"):
            self.verify(package, metadata)

    def test_traversal_and_nested_packages_are_rejected(self):
        for name in ("../base.apk", "nested/base.apk", "/base.apk"):
            with self.subTest(name=name), self.assertRaises(workflow.Failure):
                self.verify(self.container([name]))

    def test_case_collisions_and_symbolic_links_are_rejected(self):
        with self.assertRaisesRegex(workflow.Failure, "duplicate"):
            self.verify(self.container(["base.apk", "BASE.APK"]))
        package = self.root / "link.xapk"
        with zipfile.ZipFile(package, "w") as archive:
            entry = zipfile.ZipInfo("base.apk")
            entry.create_system = 3
            entry.external_attr = 0o120777 << 16
            archive.writestr(entry, "outside.apk")
        with self.assertRaisesRegex(workflow.Failure, "symbolic link"):
            self.verify(package)

    def test_oversized_apk_is_rejected_before_signature_tools(self):
        package = self.root / "base.apk"
        with package.open("wb") as stream:
            stream.truncate(512 * 1024**2 + 1)
        with self.assertRaisesRegex(workflow.Failure, "512 MiB"):
            self.verify(package)

    def test_standalone_base_requiring_splits_is_rejected(self):
        package = self.root / "base.apk"
        package.write_bytes(b"owned test")
        with self.assertRaisesRegex(workflow.Failure, "needs resource splits"):
            self.verify(package, manifest="A: android:isSplitRequired(0x0101064e)=(type 0x12)0xffffffff")


if __name__ == "__main__":
    unittest.main()
