#!/usr/bin/env python3
"""Verify a built artifact; optionally install it on Creatio Design."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import zipfile

parser = argparse.ArgumentParser()
parser.add_argument("artifact_directory")
parser.add_argument("--install", action="store_true")
args = parser.parse_args()

root = Path(args.artifact_directory).resolve()
lines = (root / "SHA256SUMS").read_text().strip().splitlines()
if len(lines) != 1:
    raise SystemExit("STOP: expected one package checksum")

match = re.fullmatch(
    r"([0-9a-f]{64})  (UsrOrderCalculator-[0-9.]+\.zip)",
    lines[0],
)
if not match:
    raise SystemExit("STOP: unexpected checksum format or package name")

expected, filename = match.groups()
archive = root / filename
actual = hashlib.sha256(archive.read_bytes()).hexdigest()
if actual != expected:
    raise SystemExit("STOP: package checksum mismatch")

report = json.loads((root / "build-report.json").read_text())
if (
    report.get("packageName") != "UsrOrderCalculator"
    or report.get("outputSHA256") != actual
):
    raise SystemExit("STOP: build report does not match package")

with zipfile.ZipFile(archive) as package:
    if package.namelist() != ["UsrOrderCalculator.gz"]:
        raise SystemExit("STOP: unexpected package contents")
    if package.testzip() is not None:
        raise SystemExit("STOP: damaged ZIP archive")

print(f"OK: verified {filename}; SHA256={actual}", flush=True)
if not args.install:
    print("Verification only; Creatio was not changed.")
    raise SystemExit(0)

username = os.environ.get("CREATIO_RUNTIME_USERNAME")
password = os.environ.get("CREATIO_RUNTIME_PASSWORD")
if not username or not password:
    raise SystemExit("STOP: deployment credentials are missing")

clio = Path.home() / "Desktop/creatio-tools/clio"
if not clio.is_file():
    raise SystemExit("STOP: pinned clio installation is missing")

os.umask(0o077)
with tempfile.TemporaryDirectory(
    prefix="creatio-clio-deploy.",
    dir=os.environ.get("RUNNER_TEMP"),
) as directory:
    settings = {
        "environments": {
            "creatio-lab": {
                "Uri": "https://creatio.creatio.test",
                "Login": username,
                "Password": password,
                "IsNetCore": True,
                "Maintainer": "Customer",
            }
        },
        "autoupdate": {
            "clio": {"enabled": False},
            "knowledge": {"enabled": False},
            "toolkit": {"enabled": False},
        },
    }
    config = Path(directory) / "appsettings.json"
    config.write_text(json.dumps(settings))
    config.chmod(0o600)

    environment = os.environ.copy()
    environment["CLIO_HOME"] = directory

    subprocess.run(
        [str(clio), "reg-web-app", "creatio-lab",
         "--IsNetCore", "true", "--check-login"],
        env=environment, check=True,
    )
    subprocess.run(
        [str(clio), "push-pkg", str(archive),
         "-e", "creatio-lab"],
        env=environment, check=True,
    )

print("OK: package installation command completed.", flush=True)
print("Next: validate Design, then publish/activate through Control Plane.")
