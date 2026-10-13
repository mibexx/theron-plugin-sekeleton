#!/usr/bin/env python3
"""Pack (and sign) the plugin without Theron installed – the same format as ``theron plugin pack``.

    python scripts/pack.py                         → dist/<id>-<version>.theronplugin
    python scripts/pack.py --sign signing.key      → signed (needs: pip install cryptography)
    python scripts/pack.py --keygen signing.key    → a new signing key (+ signing.pub) – keep the .key secret
    python scripts/pack.py --check                 → only check plugin.toml and list the files that go in

Files listed in .theronignore stay out of the package and the signature. Install the result in Theron under
Settings → Plugins → "Upload plugin …" or with ``theron plugin install dist/<file>``.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import tomllib
import zipfile
from fnmatch import fnmatch
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SIGNATURE = "SIGNATURE.json"
IGNORE_FILE = ".theronignore"
KEY_HEADER = "theron-plugin-signing-key v1"
SKIP_DIRS = {"__pycache__", ".git", ".pytest_cache", ".mypy_cache", ".ruff_cache", ".venv", ".idea", ".vscode"}
SKIP_NAMES = {".DS_Store", "Thumbs.db"}


def patterns(folder: Path) -> list[str]:
    path = folder / IGNORE_FILE
    if not path.is_file():
        return []
    return [x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip() and not x.startswith("#")]


def ignored(rel: str, pats: list[str]) -> bool:
    parts = rel.split("/")
    for pat in pats:
        pat = pat.lstrip("/")
        if pat.endswith("/"):
            name = pat.rstrip("/")
            if any(fnmatch(x, name) for x in parts[:-1]) or fnmatch("/".join(parts[:-1]) + "/", pat):
                return True
        elif fnmatch(rel, pat) or fnmatch(parts[-1], pat):
            return True
    return False


def plugin_files(folder: Path) -> list[Path]:
    pats = patterns(folder)
    out = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
        for name in sorted(files):
            if name in SKIP_NAMES or name.endswith((".pyc", ".pyo")):
                continue
            path = Path(root) / name
            rel = path.relative_to(folder).as_posix()
            if rel in (SIGNATURE, IGNORE_FILE) or ignored(rel, pats):
                continue
            out.append(path)
    return out


def manifest(folder: Path) -> dict:
    data = tomllib.loads((folder / "plugin.toml").read_text(encoding="utf-8"))
    if not re.match(r"^[a-z0-9][a-z0-9-]{1,40}$", str(data.get("id", ""))):
        sys.exit("plugin.toml: id – lower case letters, digits and '-' (2–41 characters)")
    if not data.get("version"):
        sys.exit("plugin.toml: version is missing")
    entry = data.get("entry") or data["id"].replace("-", "_")
    if not (folder / entry / "__init__.py").is_file():
        sys.exit(f"the package {entry}/__init__.py is missing")
    return data


def keygen(path: Path) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    if path.exists():
        sys.exit(f"{path} exists already")
    key = Ed25519PrivateKey.generate()
    raw = key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    pub = base64.b64encode(key.public_key().public_bytes(serialization.Encoding.Raw,
                                                         serialization.PublicFormat.Raw)).decode()
    path.write_text(f"{KEY_HEADER}\n{base64.b64encode(raw).decode()}\n")
    os.chmod(path, 0o600)
    path.with_suffix(".pub").write_text(pub + "\n")
    print(f"key: {path} (keep it secret)\npublic key: {pub}\n"
          f"trust it in Theron: theron plugin trust {pub} --name \"Your name\"")


def sign(folder: Path, key_path: Path) -> None:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    lines = [x.strip() for x in key_path.read_text().splitlines() if x.strip()]
    if len(lines) != 2 or lines[0] != KEY_HEADER:
        sys.exit(f"{key_path} is no Theron plugin signing key")
    key = Ed25519PrivateKey.from_private_bytes(base64.b64decode(lines[1]))
    files = {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest() for p in plugin_files(folder)}
    message = json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    pub = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    doc = {"format": 1, "key": base64.b64encode(pub).decode(), "files": files,
           "signature": base64.b64encode(key.sign(message)).decode()}
    (folder / SIGNATURE).write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sign", metavar="KEY", type=Path, help="sign with this key")
    ap.add_argument("--keygen", metavar="KEY", type=Path, help="create a signing key and exit")
    ap.add_argument("--out", type=Path, default=ROOT / "dist", help="target folder (default: dist/)")
    ap.add_argument("--check", action="store_true", help="only check and list the files")
    args = ap.parse_args()
    if args.keygen:
        keygen(args.keygen)
        return 0
    data = manifest(ROOT)
    files = plugin_files(ROOT)
    if args.check:
        print(f"{data['id']} {data['version']} – {len(files)} files:")
        for p in files:
            print("  " + p.relative_to(ROOT).as_posix())
        return 0
    (ROOT / SIGNATURE).unlink(missing_ok=True)   # an old signature would no longer match
    if args.sign:
        sign(ROOT, args.sign)
        files.append(ROOT / SIGNATURE)
    args.out.mkdir(parents=True, exist_ok=True)
    target = args.out / f"{data['id']}-{data['version']}.theronplugin"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            zf.write(p, p.relative_to(ROOT).as_posix())
    print(f"✔ {target}" + ("  (signed)" if args.sign else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
