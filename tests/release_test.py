"""Check that public recipes refer to the exact reviewed source patches."""
import hashlib
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReleaseTests(unittest.TestCase):
    def test_manifest_covers_every_patch_in_order_with_exact_hashes(self):
        lock = json.loads((ROOT / "upstream.lock.json").read_text())
        paths = [entry["path"] for entry in lock["patches"]]
        self.assertEqual(paths, sorted(str(path.relative_to(ROOT)) for path in (ROOT / "patches").glob("*.patch")))
        self.assertEqual(len(paths), len(set(paths)))
        for entry in lock["patches"]:
            path = (ROOT / entry["path"]).resolve()
            self.assertTrue(path.is_relative_to(ROOT / "patches"))
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry["sha256"])
        self.assertIn(lock["commit"], lock["source_url"])
        self.assertIn("/v" + lock["version"] + "/", lock["release_asset_url"])


if __name__ == "__main__":
    unittest.main()
