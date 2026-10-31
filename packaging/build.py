#!/usr/bin/env python3
"""Create a local source snapshot and build an installable Arch package."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tarfile

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.1"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-only", action="store_true", help="Create a source archive without building an Arch package")
    arguments = parser.parse_args()
    for command in (() if arguments.source_only else ("makepkg", "fakeroot", "desktop-file-validate")):
        if shutil.which(command) is None:
            raise SystemExit(f"Missing build tool: {command}")
    destination = ROOT / "dist/arch"
    destination.mkdir(parents=True, exist_ok=True)
    archive = ROOT / "dist" / f"simplepomodoro-{VERSION}.tar.gz"
    with tarfile.open(archive, "w:gz") as output:
        names = ["src", "assets", "tests", "packaging", "docs", "README.md", "CHANGELOG.md", "run.sh"]
        if (ROOT / "LICENSE").is_file():
            names.append("LICENSE")
        for name in names:
            output.add(ROOT / name, arcname=f"simplepomodoro-{VERSION}/{name}", filter=lambda item: None if "__pycache__" in Path(item.name).parts or item.name.endswith(".pyc") else item)
    checksum = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum_file = ROOT / "dist" / "SHA256SUMS"
    checksum_file.write_text(f"{checksum}  {archive.name}\n")
    print(f"Source archive: {archive}", flush=True)
    if arguments.source_only:
        return
    shutil.copy2(archive, destination / archive.name)
    recipe = (ROOT / "packaging/PKGBUILD").read_text().replace("@SOURCE_SHA256@", checksum)
    (destination / "PKGBUILD").write_text(recipe)
    environment = dict(os.environ, PKGDEST=str(ROOT / "dist"))
    subprocess.run(["makepkg", "--force"], cwd=destination, env=environment, check=True)
    for package in sorted((ROOT / "dist").glob(f"simplepomodoro-{VERSION}-*-any.pkg.tar.zst")):
        with checksum_file.open("a") as output:
            output.write(f"{hashlib.sha256(package.read_bytes()).hexdigest()}  {package.name}\n")


if __name__ == "__main__":
    main()
