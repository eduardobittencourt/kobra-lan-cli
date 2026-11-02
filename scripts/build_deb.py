"""Shared local/CI binary build. Requires Debian build dependencies; no host install.

Builds in a fresh allowlisted staging tree and leaves artifacts in OUTPUT.
"""
import argparse
from datetime import datetime, timezone
from email.utils import format_datetime
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

from release_version import ROOT, source_version

SOURCE_FILES = ["pyproject.toml", "MANIFEST.in", "README.md", "LICENSE", "NOTICE.md",
                "CHANGELOG.md", "docs/releases.md"]
MODULES = ["__init__", "cli", "config", "mqtt", "printer", "start", "upload"]
DEBIAN_FILES = ["control", "rules", "source/format", "docs", "copyright", "kobra-lan.1", "manpages"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    version = source_version(tag=args.tag)
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    stage = output / f"source-{version}"
    stage.mkdir(exist_ok=False)
    paths = SOURCE_FILES + [f"kobra_lan/{name}.py" for name in MODULES]
    paths += [f"debian/{name}" for name in DEBIAN_FILES]
    for name in paths:
        source = ROOT / name
        if source.is_symlink():
            raise ValueError(f"Refusing symlink in staging: {name}")
        target = stage / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o755 if name == "debian/rules" else 0o644)
    epoch = os.environ.get("SOURCE_DATE_EPOCH")
    if epoch is None:
        epoch = subprocess.check_output(["git", "-C", str(ROOT), "show", "-s", "--format=%ct", "HEAD"], text=True).strip()
    date = format_datetime(datetime.fromtimestamp(int(epoch), timezone.utc))
    (stage / "debian/changelog").write_text(
        f"kobra-lan-cli ({version}-1) unstable; urgency=medium\n\n"
        f"  * Package upstream release {version}.\n\n"
        f" -- Eduardo Bittencourt <eduardo@bittencourt.dev>  {date}\n")
    env = dict(os.environ, SOURCE_DATE_EPOCH=epoch, PYBUILD_DISABLE="test")
    env.pop("PYTHONPATH", None)
    subprocess.run(["dpkg-buildpackage", "--build=binary", "--no-sign"], cwd=stage, env=env, check=True)
    deb = output / f"kobra-lan-cli_{version}-1_all.deb"
    digest = hashlib.sha256(deb.read_bytes()).hexdigest()
    (output / "SHA256SUMS").write_text(f"{digest}  {deb.name}\n")
    print(deb)


if __name__ == "__main__":
    main()
