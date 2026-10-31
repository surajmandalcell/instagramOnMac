"""Verify a supplied public APK using the real pinned Google tools, without installation."""
import argparse
from pathlib import Path
import sys
import tempfile
import zipfile

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from workflow import Workflow
from apk_tools import metadata, tools, verify

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--cache", required=True)
    parser.add_argument("--split-dir", type=Path, help="Verify a temporary container of supplied public APK splits")
    options = parser.parse_args()
    workflow = Workflow(options)
    aapt, jar, classes, lock = tools(workflow)
    fields, signers = metadata(options.apk, aapt, jar, classes)
    assert signers <= set(lock["instagram_signers_sha256"]), "Publisher is not trusted"
    assert fields["versionName"].startswith("445."), "Version is not supported"
    print("PASS: real Google aapt2 and apksig verified the Instagram 445 publisher and package.")
    if options.split_dir:
        options.apk_signer_sha256 = None
        with tempfile.TemporaryDirectory(prefix="tools-smoke-", dir=workflow.work) as temporary:
            container = Path(temporary) / "package.xapk"
            with zipfile.ZipFile(container, "w") as archive:
                for apk in sorted(options.split_dir.glob("*.apk")):
                    archive.write(apk, apk.name)
            verify(workflow, container)
        print("PASS: real complete split container verified; temporary container removed.")
