"""Inspect package identity and allowlist every shipped file; run before acceptance."""
import argparse
from email.parser import BytesParser
import io
from pathlib import Path
import subprocess
import tarfile

from check_python import MODULES
from release_version import source_version


def check(deb, version):
    """Verify Debian identity, dependencies and every packaged file against allowlists."""
    fields = subprocess.check_output(["dpkg-deb", "-f", str(deb), "Package", "Version", "Architecture", "Depends"], text=True)
    assert "Package: kobra-lan-cli\n" in fields, fields
    assert f"Version: {version}-1\n" in fields, fields
    assert "Architecture: all\n" in fields, fields
    assert "python3 (>= 3.11)" in fields, fields
    assert "python3-cryptography (>= 41)" in fields, fields
    raw = subprocess.check_output(["dpkg-deb", "--fsys-tarfile", str(deb)])
    prefix = "usr/lib/python3/dist-packages/"
    info = f"{prefix}kobra_lan_cli-{version}.dist-info/"
    allowed = {prefix + name for name in MODULES} | {"usr/bin/kobra-lan"}
    allowed |= {info + name for name in ("METADATA", "WHEEL", "entry_points.txt", "top_level.txt", "RECORD", "INSTALLER",
                                        "LICENSE", "NOTICE.md", "licenses/LICENSE", "licenses/NOTICE.md")}
    doc_names = {"copyright", "changelog.Debian.gz", "changelog.gz"}
    public_docs = [
        "README.md", "NOTICE.md", "ROADMAP.md", "CONTRIBUTING.md", "AGENTS.md", "SECURITY.md",
        "CODE_OF_CONDUCT.md", "docs/README.md", "docs/pairing.md", "docs/usage.md",
        "docs/development.md", "docs/releases.md", "docs/pairing-security-review.md", "docs/maintenance.md",
    ]
    doc_names |= {name + suffix for name in public_docs for suffix in ("", ".gz")}
    allowed |= {"usr/share/doc/kobra-lan-cli/" + name for name in doc_names}
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
        for name in public_docs:
            doc = "usr/share/doc/kobra-lan-cli/" + name
            assert doc in files or doc + ".gz" in files, name
        launcher = archive.extractfile("./usr/bin/kobra-lan").read()
        assert launcher.splitlines()[0].removeprefix(b"#!").strip() == b"/usr/bin/python3"
        assert b"PYTHONPATH" not in launcher
        metadata = BytesParser().parsebytes(archive.extractfile("./" + info + "METADATA").read())
        assert metadata.get_all("Requires-Dist") == ["cryptography>=41"]
    print(fields, end="")
    print(f"Allowlisted package files: {len(files)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("deb", type=Path)
    args = parser.parse_args()
    check(args.deb, source_version())
