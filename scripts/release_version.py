"""Shared final-release identity checks; never import application code."""
import argparse
import ast
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
FINAL = re.compile(r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)", re.ASCII)


def validate(version, tag=None):
    if not FINAL.fullmatch(version):
        raise ValueError("Expected final X.Y.Z without leading zeroes, prerelease or build metadata")
    if tag is not None and tag != f"v{version}":
        raise ValueError(f"Release tag must equal v{version}; received {tag!r}")
    return version


def source_version(root=ROOT, tag=None):
    tree = ast.parse((root / "kobra_lan/__init__.py").read_text())
    versions = [ast.literal_eval(node.value) for node in tree.body
                if isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "__version__" for t in node.targets)]
    if len(versions) != 1 or not isinstance(versions[0], str):
        raise ValueError("Expected one literal __version__")
    return validate(versions[0], tag)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag")
    args = parser.parse_args()
    try:
        print(source_version(tag=args.tag))
    except ValueError as error:
        parser.exit(1, f"{error}\n")
