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

MODULES = {f"kobra_lan/{name}.py" for name in
           ("__init__", "cli", "config", "mqtt", "printer", "start", "upload")}
DOCS = {"README.md", "LICENSE", "NOTICE.md", "CHANGELOG.md", "docs/releases.md"}
EGG_FILES = {"PKG-INFO", "SOURCES.txt", "dependency_links.txt", "entry_points.txt", "top_level.txt"}


def check_sdist(path, version):
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
        archive.extractall(path.parent / "source", filter="data")
    return path.parent / "source" / parts[0]


def check_wheel(path, version):
    prefix = f"kobra_lan_cli-{version}.dist-info/"
    with zipfile.ZipFile(path) as archive:
        files = set(archive.namelist())
        metadata_files = {"METADATA", "WHEEL", "entry_points.txt", "top_level.txt", "RECORD",
                          "LICENSE", "NOTICE.md", "licenses/LICENSE", "licenses/NOTICE.md"}
        assert files <= MODULES | {prefix + name for name in metadata_files}, files
        assert MODULES <= files
        metadata = BytesParser().parsebytes(archive.read(prefix + "METADATA"))
        assert metadata["Name"] == "kobra-lan-cli" and metadata["Version"] == version
        assert metadata["Requires-Python"] == ">=3.11"
        assert metadata["License-Expression"] == "GPL-3.0-only"
        assert not metadata.get_all("Requires-Dist")
        assert "kobra-lan = kobra_lan.cli:main" in archive.read(prefix + "entry_points.txt").decode()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
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
    subprocess.run([str(python), "-m", "pip", "install", "--no-deps", "--no-index", str(wheel)], check=True, env=env)
    outside = output / "outside"
    outside.mkdir()
    command = output / "venv/bin/kobra-lan"
    assert subprocess.check_output([str(command), "--version"], cwd=outside, env=env, text=True).strip() == version
    assert subprocess.check_output([str(python), "-c", "import importlib.metadata as m; print(m.version('kobra-lan-cli'))"],
                                   cwd=outside, env=env, text=True).strip() == version
    subprocess.run([str(command), "--help"], cwd=outside, env=env, check=True, stdout=subprocess.DEVNULL)
    print(f"Python archives and independent installation verified: {version}")


if __name__ == "__main__":
    main()
