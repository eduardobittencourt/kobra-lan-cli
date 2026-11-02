"""Inspect package identity and allowlist every shipped file; run before acceptance."""
import argparse
import io
from pathlib import Path
import subprocess
import tarfile

from check_python import MODULES
from release_version import source_version


def check(deb, version):
    fields = subprocess.check_output(["dpkg-deb", "-f", str(deb), "Package", "Version", "Architecture", "Depends"], text=True)
    assert f"Package: kobra-lan-cli\n" in fields, fields
    assert f"Version: {version}-1\n" in fields, fields
    assert "Architecture: all\n" in fields, fields
    assert "python3 (>= 3.11)" in fields, fields
    raw = subprocess.check_output(["dpkg-deb", "--fsys-tarfile", str(deb)])
    prefix = "usr/lib/python3/dist-packages/"
    info = f"{prefix}kobra_lan_cli-{version}.dist-info/"
    allowed = {prefix + name for name in MODULES} | {"usr/bin/kobra-lan"}
    allowed |= {info + name for name in ("METADATA", "WHEEL", "entry_points.txt", "top_level.txt", "RECORD", "INSTALLER",
                                        "LICENSE", "NOTICE.md", "licenses/LICENSE", "licenses/NOTICE.md")}
    allowed |= {"usr/share/doc/kobra-lan-cli/" + name for name in
                ("copyright", "changelog.Debian.gz", "changelog.gz", "README.md", "README.md.gz", "NOTICE.md", "NOTICE.md.gz", "releases.md", "releases.md.gz")}
    allowed |= {"usr/share/man/man1/kobra-lan.1.gz"}
    files = set()
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive.getmembers():
            if member.isdir():
                continue
            name = member.name.removeprefix("./")
            assert member.isfile() and name in allowed, name
            assert member.uid == member.gid == 0, name
            assert not member.mode & 0o022, name
            files.add(name)
        assert {prefix + name for name in MODULES} | {"usr/bin/kobra-lan", info + "METADATA"} <= files
        launcher = archive.extractfile("./usr/bin/kobra-lan").read()
        assert launcher.splitlines()[0].removeprefix(b"#!").strip() == b"/usr/bin/python3"
        assert b"PYTHONPATH" not in launcher
    print(fields, end="")
    print(f"Allowlisted package files: {len(files)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deb", type=Path)
    args = parser.parse_args()
    check(args.deb, source_version())
