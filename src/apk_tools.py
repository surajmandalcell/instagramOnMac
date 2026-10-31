"""Verify complete Android packages with pinned Android publisher tools."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import stat
import tempfile
import zipfile

SUPPORTED_VERSION = "445.0.0.45.83"

VERIFIER = """
import com.android.apksig.ApkVerifier;
import java.io.File;
import java.security.MessageDigest;
import java.util.HexFormat;
import java.util.TreeSet;
public class PublisherVerifier {
  public static void main(String[] args) throws Exception {
    var result = new ApkVerifier.Builder(new File(args[0])).build().verify();
    if (!result.isVerified()) throw new SecurityException("APK signature verification failed");
    var hashes = new TreeSet<String>();
    for (var cert : result.getSignerCertificates())
      hashes.add(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(cert.getEncoded())));
    if (hashes.isEmpty()) throw new SecurityException("APK has no verified signer");
    for (var hash : hashes) System.out.println(hash);
  }
}
"""


def tools(flow):
    from workflow import REPO, run, resolve_jdk
    lock = json.loads((REPO / "tools.lock.json").read_text())
    jdk = resolve_jdk()
    jars = {}
    for name in ("apksig", "aapt2"):
        item = lock[name]
        jars[name] = flow.download(item["url"], item["sha256"], name + ".jar")
    target = flow.work / "apk-tools"
    target.mkdir(exist_ok=True)
    with zipfile.ZipFile(jars["aapt2"]) as archive:
        binary = archive.read("aapt2")
    executable = target / "aapt2"
    if not executable.exists() or executable.read_bytes() != binary:
        executable.write_bytes(binary)
        executable.chmod(0o755)
    source = target / "PublisherVerifier.java"
    stamp = target / "verifier.sha256"
    identity = hashlib.sha256(b"jdk21\0" + VERIFIER.encode() + jars["apksig"].read_bytes()).hexdigest()
    if not stamp.exists() or stamp.read_text() != identity or not (target / "PublisherVerifier.class").exists():
        source.write_text(VERIFIER)
        run([jdk / "bin/javac", "-cp", jars["apksig"], "-d", target, source])
        stamp.write_text(identity)
    return executable, jars["apksig"], target, lock


def metadata(apk, aapt, jar, classes, trusted=None):
    from workflow import run, Failure, REPO, resolve_jdk
    signers = set(run([resolve_jdk() / "bin/java", "-cp", str(jar) + ":" + str(classes), "PublisherVerifier", apk]).splitlines())
    if not signers or any(not re.fullmatch(r"[0-9a-f]{64}", signer) for signer in signers):
        raise Failure("APK signature verification did not return a verified signer.")
    if trusted is None:
        trusted = set(json.loads((REPO / "tools.lock.json").read_text())["instagram_signers_sha256"])
    if not signers <= trusted:
        raise Failure("APK publisher is not a trusted Instagram signer.")
    # Native manifest parsing happens only after cryptographic publisher verification.
    badging = run([aapt, "dump", "badging", apk])
    package_line = next((line for line in badging.splitlines() if line.startswith("package:")), "")
    fields = dict(re.findall(r"([A-Za-z]+)='([^']*)'", package_line))
    if fields.get("name") != "com.instagram.android":
        raise Failure("Every APK package must be com.instagram.android.")
    version = fields.get("versionName", "")
    if not fields.get("versionCode") or (version and version != SUPPORTED_VERSION) or (not fields.get("split") and version != SUPPORTED_VERSION):
        raise Failure("This patch set supports Instagram " + SUPPORTED_VERSION + " only.")
    manifest = run([aapt, "dump", "xmltree", "--file", "AndroidManifest.xml", apk])
    for attribute, key in (("requiredSplitTypes", "_required_types"), ("splitTypes", "_split_types")):
        values = re.findall(r":" + attribute + r'\([^)]*\)="([^"]*)"', manifest)
        fields[key] = {part.strip() for value in values for part in value.split(",") if part.strip()}
    fields["_required_splits"] = set(re.findall(r"^uses-split: name='([^']+)'", badging, re.M))
    return fields, signers


def verify(flow, package):
    from workflow import Failure, run
    flow.work.mkdir(parents=True, exist_ok=True)
    aapt, jar, classes, lock = tools(flow)
    trusted = set(lock["instagram_signers_sha256"])
    suffix = package.suffix.lower()
    if suffix not in (".apk", ".xapk", ".apkm", ".apks"):
        raise Failure("Select an APK, XAPK, APKM, or APKS package.")
    with tempfile.TemporaryDirectory(prefix="verify-package-", dir=flow.work) as temporary:
        apks = [package]
        if suffix != ".apk":
            apks = []
            with zipfile.ZipFile(package) as archive:
                entries = archive.infolist()
                if len(entries) > 4096 or sum(entry.file_size for entry in entries) > 2 * 1024**3:
                    raise Failure("Package container exceeds the safe verification limit.")
                seen = set()
                for entry in entries:
                    path = Path(entry.filename)
                    if path.is_absolute() or ".." in path.parts or "\\" in entry.filename or entry.filename.casefold() in seen:
                        raise Failure("Package container contains an unsafe or duplicate path.")
                    seen.add(entry.filename.casefold())
                    kind = stat.S_IFMT(entry.external_attr >> 16)
                    if kind not in (0, stat.S_IFREG, stat.S_IFDIR):
                        raise Failure("Package contains a symbolic link or special file.")
                    if path.suffix.lower() == ".obb":
                        raise Failure("OBB expansion packages are not supported by this installer.")
                    if path.suffix.lower() != ".apk":
                        continue
                    if entry.file_size > 512 * 1024**2:
                        raise Failure("An APK exceeds the 512 MiB verification limit.")
                    if len(path.parts) != 1 or entry.is_dir():
                        raise Failure("Only flat APK split containers are supported.")
                    destination = Path(temporary) / path.name
                    with archive.open(entry) as source, destination.open("wb") as target:
                        shutil.copyfileobj(source, target)
                    apks.append(destination)
        if not apks or len(apks) > 128:
            raise Failure("Package must contain one base APK and its split APKs.")
        if any(apk.stat().st_size > 512 * 1024**2 for apk in apks):
            raise Failure("An APK exceeds the 512 MiB verification limit.")
        expected = None
        base = []
        split_names = set()
        required_types = set()
        supplied_types = set()
        required_splits = set()
        version_names = set()
        for apk in apks:
            fields, signers = metadata(apk, aapt, jar, classes, trusted=trusted)
            if not signers <= trusted:
                raise Failure("APK publisher is not a trusted Instagram signer.")
            identity = (fields["name"], fields["versionCode"], frozenset(signers))
            if expected is not None and identity != expected:
                raise Failure("All APK splits must have the same package, version, and verified signer.")
            expected = identity
            if fields.get("versionName"):
                version_names.add(fields["versionName"])
            if len(version_names) > 1:
                raise Failure("All APK splits must have the same package version name.")
            required_types.update(fields.get("_required_types", ()))
            supplied_types.update(fields.get("_split_types", ()))
            required_splits.update(fields.get("_required_splits", ()))
            split = fields.get("split", "")
            if split in split_names:
                raise Failure("Package contains duplicate APK split identities.")
            split_names.add(split)
            if not split:
                base.append(apk)
        if len(base) != 1:
            raise Failure("Package must contain exactly one base APK.")
        if not required_types <= supplied_types or not required_splits <= split_names:
            raise Failure("Package is missing required resource or feature splits. Select the complete XAPK or APKM package.")
        if len(apks) == 1:
            manifest = run([aapt, "dump", "xmltree", "--file", "AndroidManifest.xml", base[0]])
            if re.search(r"isSplitRequired[^\n]*(?:0xffffffff|true)", manifest) or "com.android.vending.splits.required" in manifest:
                raise Failure("This base APK needs resource splits. Select the complete XAPK or APKM package.")
    print("Verified Instagram publisher, version, and " + str(len(apks)) + " APK file(s).")
