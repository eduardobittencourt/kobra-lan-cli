"""Exercise installed-documentation contracts with real synthetic Debian archives."""
import contextlib
import gzip
import io
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from build_deb import SOURCE_FILES
from check_deb import check
from check_python import MODULES
from release_version import ROOT, source_version


@unittest.skipUnless(shutil.which("dpkg-deb"), "Debian archive probes require dpkg-deb")
class DebianDocumentationTests(unittest.TestCase):
    """Keep the distributed document graph readable at its original relative paths."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.stage = self.root / "stage"
        self.docs = self.stage / "usr/share/doc/kobra-lan-cli"
        self.docs.mkdir(parents=True)
        self.version = source_version()
        for name in SOURCE_FILES:
            if name.endswith(".md") and name != "CHANGELOG.md":
                target = self.docs / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / name, target)
        (self.docs / "changelog.gz").write_bytes(gzip.compress((ROOT / "CHANGELOG.md").read_bytes()))
        for name in MODULES:
            target = self.stage / "usr/lib/python3/dist-packages" / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("")
        info = self.stage / f"usr/lib/python3/dist-packages/kobra_lan_cli-{self.version}.dist-info"
        info.mkdir()
        (info / "METADATA").write_text("Requires-Dist: cryptography>=41\n\n")
        launcher = self.stage / "usr/bin/kobra-lan"
        launcher.parent.mkdir(parents=True)
        launcher.write_text("#!/usr/bin/python3\n")
        launcher.chmod(0o755)
        control = self.stage / "DEBIAN"
        control.mkdir()
        (control / "control").write_text(
            f"Package: kobra-lan-cli\nVersion: {self.version}-1\nArchitecture: all\n"
            "Maintainer: Synthetic <test@example.invalid>\nDescription: Synthetic documentation probe\n"
            "Depends: python3 (>= 3.11), python3-cryptography (>= 41)\n")

    def check_archive(self):
        # Fixture permissions must not depend on the caller's umask, including
        # files added by individual corruption probes after setUp.
        launcher = self.stage / "usr/bin/kobra-lan"
        for path in [self.stage, *self.stage.rglob("*")]:
            path.chmod(0o755 if path.is_dir() or path == launcher else 0o644)
        archive = self.root / "package.deb"
        subprocess.run(["dpkg-deb", "--build", "--root-owner-group", str(self.stage), str(archive)],
                       check=True, stdout=subprocess.DEVNULL)
        with contextlib.redirect_stdout(io.StringIO()):
            check(archive, self.version)

    def test_uncompressed_document_graph_is_readable(self):
        self.check_archive()

    def test_compression_cannot_hide_a_broken_markdown_target(self):
        target = self.docs / "docs/releases.md"
        target.with_suffix(".md.gz").write_bytes(gzip.compress(target.read_bytes()))
        target.unlink()
        with self.assertRaises(AssertionError):
            self.check_archive()

    def test_missing_relative_target_is_rejected(self):
        with (self.docs / "README.md").open("a") as markdown:
            markdown.write("\n[Unavailable guide](docs/not-shipped.md)\n")
        with self.assertRaisesRegex(AssertionError, "not-shipped"):
            self.check_archive()
