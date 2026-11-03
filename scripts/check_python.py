"""Build an sdist, build its wheel, check every member and install outside checkout.

Requires the build frontend and venv/ensurepip. Output must be a new directory.
"""
import argparse
from email.parser import BytesParser
import os
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tarfile
import venv
import zipfile

from release_version import ROOT, source_version

RUNTIME_REQUIREMENT = "cryptography>=41"
ENTRY_POINTS_FILE = "entry_points.txt"

MODULES = {f"kobra_lan/{name}.py" for name in
           ("__init__", "cli", "config", "mqtt", "printer", "start", "upload", "provisioning", "pairing")}
DOCS = {"README.md", "LICENSE", "NOTICE.md", "CHANGELOG.md", "docs/releases.md"}
EGG_FILES = {"PKG-INFO", "SOURCES.txt", "dependency_links.txt", ENTRY_POINTS_FILE, "top_level.txt", "requires.txt"}


def check_sdist(path, version):
    """Check every source-archive member and exact dependency metadata before extraction."""
    with tarfile.open(path) as archive:
        files = set()
        for member in archive.getmembers():
            parts = PurePosixPath(member.name).parts
            assert parts[0] in {f"kobra_lan_cli-{version}", f"kobra-lan-cli-{version}"}
            assert ".." not in parts and not member.issym() and not member.islnk(), member.name
            if member.isfile():
                files.add("/".join(parts[1:]))
        allowed = MODULES | DOCS | {"MANIFEST.in", "pyproject.toml", "setup.cfg", "PKG-INFO"}
        allowed |= {f"kobra_lan_cli.egg-info/{name}" for name in EGG_FILES}
        assert files <= allowed, files - allowed
        assert MODULES | DOCS | {"pyproject.toml"} <= files
        requirements = archive.extractfile(f"{parts[0]}/kobra_lan_cli.egg-info/requires.txt").read().decode()
        assert requirements.strip() == RUNTIME_REQUIREMENT, requirements
        metadata = BytesParser().parsebytes(archive.extractfile(f"{parts[0]}/PKG-INFO").read())
        assert metadata.get_all("Requires-Dist") == [RUNTIME_REQUIREMENT]
        archive.extractall(path.parent / "source", filter="data")
    return path.parent / "source" / parts[0]


def check_wheel(path, version):
    """Check wheel contents, application identity and the exact runtime requirement."""
    prefix = f"kobra_lan_cli-{version}.dist-info/"
    with zipfile.ZipFile(path) as archive:
        files = set(archive.namelist())
        metadata_files = {"METADATA", "WHEEL", ENTRY_POINTS_FILE, "top_level.txt", "RECORD",
                          "LICENSE", "NOTICE.md", "licenses/LICENSE", "licenses/NOTICE.md"}
        assert files <= MODULES | {prefix + name for name in metadata_files}, files
        assert MODULES <= files
        metadata = BytesParser().parsebytes(archive.read(prefix + "METADATA"))
        assert metadata["Name"] == "kobra-lan-cli" and metadata["Version"] == version
        assert metadata["Requires-Python"] == ">=3.11"
        assert metadata["License-Expression"] == "GPL-3.0-only"
        assert metadata.get_all("Requires-Dist") == [RUNTIME_REQUIREMENT]
        assert "kobra-lan = kobra_lan.cli:main" in archive.read(prefix + ENTRY_POINTS_FILE).decode()


def main():
    """Build from source archives and verify an independent installed command."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--wheelhouse", type=Path, help="Prepared runtime dependency closure for offline installation")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    version = source_version()
    env = dict(os.environ)
    env.pop("PYTHONPATH", None)
    subprocess.run([sys.executable, "-m", "build", "--sdist", "--outdir", str(output), str(ROOT)], check=True, env=env)
    source = check_sdist(next(output.glob("*.tar.gz")), version)
    subprocess.run([sys.executable, "-m", "build", "--wheel", "--outdir", str(output), str(source)], check=True, env=env)
    wheel = next(output.glob("*.whl"))
    check_wheel(wheel, version)
    venv.EnvBuilder(with_pip=True).create(output / "venv")
    python = output / "venv/bin/python"
    # Provision runtime requirements during build preparation, before offline probes.
    dependency_args = ["--no-index", "--find-links", str(args.wheelhouse.resolve())] if args.wheelhouse else []
    subprocess.run([str(python), "-m", "pip", "install", *dependency_args, RUNTIME_REQUIREMENT], check=True, env=env)
    subprocess.run([str(python), "-m", "pip", "install", "--no-deps", "--no-index", str(wheel)], check=True, env=env)
    outside = output / "outside"
    outside.mkdir()
    command = output / "venv/bin/kobra-lan"
    assert subprocess.check_output([str(command), "--version"], cwd=outside, env=env, text=True).strip() == version
    assert subprocess.check_output([str(python), "-c", "import importlib.metadata as m; print(m.version('kobra-lan-cli'))"],
                                   cwd=outside, env=env, text=True).strip() == version
    subprocess.run([str(command), "--help"], cwd=outside, env=env, check=True, stdout=subprocess.DEVNULL)
    subprocess.run([str(command), "printer", "pair", "--help"], cwd=outside, env=env, check=True, stdout=subprocess.DEVNULL)
    subprocess.run([str(python), str(ROOT / "scripts/probe_pairing.py"), "--command", str(command)],
                   cwd=outside, env=env, check=True)
    print(f"Python archives and independent installation verified: {version}")


if __name__ == "__main__":
    main()
