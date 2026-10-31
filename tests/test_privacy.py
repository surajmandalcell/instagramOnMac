import contextlib
import importlib.util
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True
spec = importlib.util.spec_from_file_location("privacy", Path(__file__).resolve().parents[1] / "scripts/check_privacy.py")
privacy = importlib.util.module_from_spec(spec)
spec.loader.exec_module(privacy)


class PrivacyTests(unittest.TestCase):
    def test_only_the_public_destination_is_exempt_from_personal_markers(self):
        account = privacy.PUBLIC_REPOSITORY.split("/")[-2]
        self.assertFalse(privacy.inspect_file("README.md", (privacy.PUBLIC_REPOSITORY + "/releases").encode(), {account}))
        self.assertTrue(privacy.inspect_file("README.md", (privacy.PUBLIC_REPOSITORY + " private account: " + account).encode(), {account}))

    def test_public_cover_accepts_only_inert_vector_art(self):
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"><text x="0">Source only</text></svg>'
        self.assertFalse(privacy.inspect_file("assets/cover.svg", svg, set()))
        self.assertTrue(privacy.inspect_file("private/capture.svg", svg, set()))
        for payload in (
            b'<script>run()</script>',
            b'<image href="data:image/png;base64,cHJpdmF0ZQ=="/>',
            b'<text onclick="run()">Click</text>',
            b'<rect fill="url(https://example.invalid/image)"/>',
            b'<foreignObject/>',
        ):
            unsafe = b'<svg xmlns="http://www.w3.org/2000/svg">' + payload + b'</svg>'
            self.assertTrue(privacy.inspect_file("assets/cover.svg", unsafe, set()))

    def test_source_only_allowlist(self):
        for name in ("photo.heic", "movie.m4v", "key.p8", "capture.webp", "image.gif", "sign.mobileprovision", "bundle.xcarchive", "backup.cookies"):
            self.assertTrue(privacy.inspect_file(name, b"synthetic", set()), name)
        self.assertFalse(privacy.inspect_file("src/workflow.py", b"print('ready')\n", set()))

    def test_identifiers_and_credentials_are_not_printed(self):
        fixtures = [
            ("/Users/" + "synthetic-person/private").encode(),
            ("ghp_" + "x" * 36).encode(),
            ("sessionid=" + "synthetic-secret-value").encode(),
            ("Developer ID Application: " + "Synthetic Person (A1B2C3D4E5)").encode(),
            ("TeamIdentifier=" + "A1B2C3D4E5").encode(),
            ("-----BEGIN" + " PRIVATE KEY-----").encode(),
        ]
        for data in fixtures:
            self.assertTrue(privacy.inspect_file("src/config.py", data, set()))
        self.assertTrue(privacy.inspect_file("README.md", b"synthetic-owner", {"synthetic-owner"}))

    def test_staged_blobs_are_checked_instead_of_worktree(self):
        root = os.environ.get("AGENT_DATA_DIR") or "/Volumes/External1TB/data/_custom/codex"
        scratch_root = Path(root) / "instagramOnMac"
        scratch_root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="privacy-test-", dir=scratch_root) as scratch:
            repository = Path(scratch)
            subprocess.run(["git", "-c", "init.templateDir=", "init", "-q", scratch], check=True)
            token = "ghp_" + "x" * 36
            (repository / "source.py").write_text(token)
            subprocess.run(["git", "-C", scratch, "add", "source.py"], check=True)
            (repository / "source.py").write_text("safe worktree\n")
            original = privacy.ROOT
            arguments = sys.argv
            try:
                privacy.ROOT = repository
                sys.argv = ["check_privacy.py", "--staged"]
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(privacy.main(), 1)
                self.assertNotIn(token, output.getvalue())
            finally:
                privacy.ROOT = original
                sys.argv = arguments

    def test_old_commits_and_staged_symlinks_are_checked(self):
        root = Path(os.environ.get("AGENT_DATA_DIR") or "/Volumes/External1TB/data/_custom/codex") / "instagramOnMac"
        root.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="privacy-history-", dir=root) as scratch:
            repository = Path(scratch)
            command = ["git", "-C", scratch]
            subprocess.run([*command, "-c", "init.templateDir=", "init", "-q"], check=True)
            environment = dict(os.environ, GIT_AUTHOR_NAME="Maintainer", GIT_AUTHOR_EMAIL="maintainer@localhost",
                               GIT_COMMITTER_NAME="Maintainer", GIT_COMMITTER_EMAIL="maintainer@localhost")
            source = repository / "source.py"
            source.write_text("ghp_" + "x" * 36)
            subprocess.run([*command, "add", "source.py"], check=True)
            subprocess.run([*command, "commit", "-qm", "Synthetic history"], env=environment, check=True)
            source.unlink()
            subprocess.run([*command, "add", "-u"], check=True)
            subprocess.run([*command, "commit", "-qm", "Remove fixture"], env=environment, check=True)
            source.symlink_to("synthetic-target")
            subprocess.run([*command, "add", "source.py"], check=True)
            source.unlink()
            source.write_text("safe worktree\n")
            original, arguments = privacy.ROOT, sys.argv
            try:
                privacy.ROOT = repository
                sys.argv = ["check_privacy.py", "--staged"]
                output = io.StringIO()
                with contextlib.redirect_stdout(output):
                    self.assertEqual(privacy.main(), 1)
                self.assertIn("history:source.py", output.getvalue())
                self.assertIn("symbolic link", output.getvalue())
            finally:
                privacy.ROOT, sys.argv = original, arguments

    def test_commit_messages_are_checked_without_printing_values(self):
        result = subprocess.CompletedProcess([], 0, b"", b"")
        secret = "ghp_" + "x" * 36

        def command(*args):
            if args[0] == "log":
                return subprocess.CompletedProcess([], 0, ("Synthetic commit\n" + secret).encode(), b"")
            return result

        from unittest.mock import patch
        with patch.object(privacy, "git", side_effect=command), patch.object(sys, "argv", ["check_privacy.py", "--staged"]):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                self.assertEqual(privacy.main(), 1)
            self.assertIn("commit metadata or message", output.getvalue())
            self.assertNotIn(secret, output.getvalue())


if __name__ == "__main__":
    unittest.main()
