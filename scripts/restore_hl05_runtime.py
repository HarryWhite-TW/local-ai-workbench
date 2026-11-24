"""Restore the isolated HL-05 venv from its sealed local dependency archive."""
from hashlib import file_digest
import json
from pathlib import Path, PurePosixPath
import struct
import subprocess
import sys
import venv
from zipfile import ZipFile

root = Path(__file__).resolve().parents[2]
archive = root / "runtime" / "site-packages.zip"
lock = json.loads(archive.with_name("runtime-lock.json").read_text(encoding="utf-8"))
target = root / ".venv"
if list(sys.version_info[:3]) != lock["python"] or struct.calcsize("P") != 8:
    raise SystemExit("HL-05 requires the pinned Python 3.14.6 x64.")
if target.resolve() != target:
    raise SystemExit("The HL-05 runtime directory is redirected.")
if target.exists():
    raise SystemExit("HL-05 runtime already exists. Keep it or move it aside explicitly before a restore.")
with archive.open("rb") as stream:
    if file_digest(stream, "sha256").hexdigest() != lock["sha256"]:
        raise SystemExit("Dependency archive does not match its lock.")
with ZipFile(archive) as zipped:
    for name in zipped.namelist():
        relative = PurePosixPath(name)
        if relative.is_absolute() or ".." in relative.parts or ":" in name or "\\" in name:
            raise SystemExit("Unsafe path in the dependency archive.")
    venv.EnvBuilder(with_pip=False).create(target)
    zipped.extractall(target / "Lib" / "site-packages")
subprocess.run([str(target / "Scripts" / "python.exe"), "-I", "-B", "-m", "pip", "check"], check=True)
print("HL-05 isolated runtime restored without a network installation.")
