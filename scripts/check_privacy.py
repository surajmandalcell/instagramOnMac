#!/usr/bin/env python3
"""Reject private data and generated files without printing their contents."""
from __future__ import annotations

import argparse
import getpass
import hashlib
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zlib

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN_PARTS = {".cache", "cache", "build", "dist", "downloads", "logs", "node_modules", "__pycache__", ".venv", "evidence"}
FORBIDDEN_SUFFIXES = {".apk", ".apkm", ".apks", ".xapk", ".ipa", ".dmg", ".jar", ".class", ".dylib", ".p12", ".pfx", ".pem", ".key", ".db", ".sqlite", ".sqlite3", ".log", ".mov", ".mp4", ".png", ".jpg", ".jpeg", ".zip", ".gz", ".xz"}
ALLOWED_SUFFIXES = {".py", ".sh", ".md", ".json", ".txt", ".patch", ".diff", ".yml", ".yaml"}
ALLOWED_NAMES = {".gitignore", ".gitattributes", "instagram-on-mac", "LICENSE"}
PUBLIC_COVER = "assets/cover.svg"
PUBLIC_PNG_COVER = "assets/cover.png"
PUBLIC_PNG_SHA256 = "cb966fe316de69c76a4afa0a17248159a7afec9779b9c461ac2d5179119a80b0"
PUBLIC_REPOSITORY = "https://github.com/surajmandalcell/instagramOnMac"
PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----"),
    "access token": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[A-Z0-9]{16})\b"),
    "personal home path": re.compile(r"/Users/" + r"[^/\s\"']+|[A-Z]:\\Users\\" + r"[^\\\s\"']+"),
    "local temporary path": re.compile(r"/(?:private/)?var/folders/[A-Za-z0-9_/.-]+"),
    "authorization value": re.compile(r"(?i)\bBearer\s+[A-Za-z0-9_.-]{24,}"),
    "session value": re.compile(r"(?i)(?:sessionid|csrftoken|ds_user_id|ig_did|ig_nrcb|authorization)\s*[\"']?\s*[=:]\s*[\"']?[A-Za-z0-9%:_-]{8,}"),
    "signing identity": re.compile(r"Developer ID Application:\s+[^\n\"']+\([A-Z0-9]{10}\)"),
    "signing team identifier": re.compile(r"TeamIdentifier=" + r"[A-Z0-9]{10}\b"),
}


def git(*args: str) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(["git", "-C", str(ROOT), *args], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, check=False)


def personal_markers() -> set[str]:
    markers = {str(Path.home())}
    username = getpass.getuser()
    if len(username) >= 5:
        markers.add(username)
    for field in ("user.name", "user.email"):
        value = git("config", "--get", field).stdout.decode("utf-8", "replace").strip()
        if len(value) >= 5 and value not in {"Maintainer", "maintainer@localhost"}:
            markers.add(value)
    return markers


def valid_cover_png(data: bytes) -> bool:
    """Accept a complete RGB PNG with image chunks only, including valid CRCs."""
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return False
    offset, seen_header, seen_data = 8, False, False
    while offset + 12 <= len(data):
        size = int.from_bytes(data[offset:offset + 4], "big")
        end = offset + 12 + size
        if end > len(data):
            return False
        kind = data[offset + 4:offset + 8]
        payload = data[offset + 8:offset + 8 + size]
        crc = int.from_bytes(data[end - 4:end], "big")
        if zlib.crc32(kind + payload) != crc:
            return False
        if kind == b"IHDR":
            if seen_header or offset != 8 or size != 13:
                return False
            if not int.from_bytes(payload[:4], "big") or not int.from_bytes(payload[4:8], "big"):
                return False
            if payload[8:12] != b"\x08\x02\x00\x00" or payload[12] not in (0, 1):
                return False
            seen_header = True
        elif kind == b"IDAT":
            if not seen_header or not size:
                return False
            seen_data = True
        elif kind == b"IEND":
            return seen_header and seen_data and size == 0 and end == len(data)
        else:
            return False
        offset = end
    return False


def inspect_file(path: str, data: bytes, markers: set[str]) -> list[str]:
    if path == PUBLIC_PNG_COVER:
        if hashlib.sha256(data).hexdigest() != PUBLIC_PNG_SHA256 or not valid_cover_png(data):
            return ["cover must match the approved metadata-free RGB PNG"]
        return []
    relative = Path(path)
    errors = []
    if path != PUBLIC_COVER and relative.name not in ALLOWED_NAMES and relative.suffix.lower() not in ALLOWED_SUFFIXES:
        errors.append("file is outside the source-only allowlist")
    if FORBIDDEN_PARTS.intersection(relative.parts) or relative.suffix.lower() in FORBIDDEN_SUFFIXES or relative.name.startswith(".env"):
        errors.append("private or generated file type")
    if len(data) > 5_000_000 or b"\0" in data:
        errors.append("binary or oversized file")
        return errors
    try:
        content = data.decode("utf-8")
    except UnicodeDecodeError:
        return [*errors, "non-text file"]
    if path == PUBLIC_COVER:
        # The only public artwork is plain vector text and geometry, never embedded media.
        tags = {"svg", "rect", "line", "text", "tspan", "g", "title", "desc"}
        attributes = {"width", "height", "viewBox", "x", "y", "x1", "x2", "y1", "y2",
                      "fill", "stroke", "stroke-width", "stroke-dasharray", "font-family",
                      "font-size", "font-weight", "letter-spacing", "text-anchor", "role"}
        try:
            root = ET.fromstring(content)
            if "<!" in content or root.tag != "{http://www.w3.org/2000/svg}svg":
                raise ValueError
            for element in root.iter():
                if element.tag not in {"{http://www.w3.org/2000/svg}" + tag for tag in tags}:
                    raise ValueError
                if any(key not in attributes or re.search(r"(?i)url\s*\(|https?:|data:|file:", value)
                       for key, value in element.attrib.items()):
                    raise ValueError
        except (ET.ParseError, ValueError):
            errors.append("cover must contain only inert vector text and geometry")
    for label, pattern in PATTERNS.items():
        if pattern.search(content):
            errors.append(label)
    # The public destination is intentional; account identifiers elsewhere are still rejected.
    private_content = content.replace(PUBLIC_REPOSITORY, "https://github.com/public/project")
    if any(marker.casefold() in private_content.casefold() for marker in markers):
        errors.append("local personal identifier")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--staged", action="store_true", help="inspect the exact staged Git content")
    args = parser.parse_args()
    markers = personal_markers()
    failures = []
    staged_links = set()
    if args.staged:
        result = git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z")
        if result.returncode:
            parser.error("a Git index is required")
        paths = [os.fsdecode(item) for item in result.stdout.split(b"\0") if item]
        for item in git("ls-files", "--stage", "-z").stdout.split(b"\0"):
            if item.startswith(b"120000 "):
                staged_links.add(os.fsdecode(item.split(b"\t", 1)[1]))
    else:
        paths = [str(path.relative_to(ROOT)) for path in ROOT.rglob("*") if ".git" not in path.relative_to(ROOT).parts and (path.is_file() or path.is_symlink())]
    for name in sorted(paths):
        path = ROOT / name
        if name in staged_links or (not args.staged and path.is_symlink()):
            failures.append((name, "symbolic link"))
            continue
        result = git("show", ":" + name) if args.staged else None
        if result is not None and result.returncode:
            failures.append((name, "cannot inspect staged content"))
            continue
        data = result.stdout if result is not None else path.read_bytes()
        failures.extend((name, error) for error in inspect_file(name, data, markers))
    history = git("log", "--all", "--format=%an <%ae>%n%cn <%ce>%n%B")
    if history.returncode == 0:
        content = history.stdout.decode("utf-8", "replace")
        if any(marker.casefold() in content.casefold() for marker in markers):
            failures.append((".git history", "local personal identifier in commit metadata"))
        for label, pattern in PATTERNS.items():
            if pattern.search(content):
                failures.append((".git history", label + " in commit metadata or message"))
        for line in git("rev-list", "--objects", "--all").stdout.splitlines():
            object_id, separator, name = line.partition(b" ")
            if not separator:
                continue
            if git("cat-file", "-t", object_id.decode()).stdout.strip() != b"blob":
                continue
            result = git("cat-file", "blob", object_id.decode())
            failures.extend(("history:" + os.fsdecode(name), error)
                            for error in inspect_file(os.fsdecode(name), result.stdout, markers))
    for name, label in failures:
        print(f"FAIL {name}: {label}")
    if failures:
        return 1
    print(f"PASS: {len(paths)} files; no detected private data or generated payloads")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
