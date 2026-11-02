"""Publish only verified artifacts through an unpublished GitHub draft.

The workflow grants a token only after all reusable package checks pass. No
automatic retries: interrupted publication leaves a draft for a complete rerun.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.error import HTTPError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

try:
    from .release_version import ROOT, source_version, validate
except ImportError:
    from release_version import ROOT, source_version, validate


class SafeRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != "https":
            raise ValueError("Refusing non-HTTPS API redirect")
        redirected = super().redirect_request(req, fp, code, msg, headers, newurl)
        if urlsplit(req.full_url).netloc != urlsplit(newurl).netloc:
            redirected.remove_header("Authorization")
        return redirected


class GitHub:
    def __init__(self, repository, token):
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
            raise ValueError("Invalid repository")
        self.base = f"https://api.github.com/repos/{repository}"
        self.upload_base = f"https://uploads.github.com/repos/{repository}"
        self.token = token
        self.opener = build_opener(SafeRedirect())

    def request(self, method, path, body=None, *, binary=False, upload=False):
        url = (self.upload_base if upload else self.base) + path
        headers = {"Authorization": f"Bearer {self.token}", "User-Agent": "kobra-lan-cli-release",
                   "X-GitHub-Api-Version": "2022-11-28",
                   "Accept": "application/octet-stream" if binary else "application/vnd.github+json"}
        if isinstance(body, bytes):
            data = body
            headers["Content-Type"] = "application/octet-stream"
        elif body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        else:
            data = None
        try:
            with self.opener.open(Request(url, data=data, headers=headers, method=method), timeout=120) as response:
                raw = response.read()
                return raw if binary else json.loads(raw) if raw else None
        except HTTPError as error:
            # Do not include response bodies, token-bearing request objects or signed URLs.
            raise RuntimeError(f"GitHub {method} failed with HTTP {error.code}") from None


def release_notes(changelog, version, tag, commit):
    text = changelog.read_text()
    match = re.search(rf"^## {re.escape(version)}\s*\n(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not match or not match[1].strip():
        raise ValueError(f"Missing CHANGELOG.md notes for {version}")
    return (match[1].strip() + f"\n\nSource: `{tag}` at `{commit}`.\n"
            "Package acceptance: Debian 13 and Ubuntu 24.04, amd64.\n"
            "Experimental printer support remains limited to the README qualification.\n"
            "Downloadable .deb only; no hosted apt feed.\n")


def candidate_files(artifacts, version):
    filename = f"kobra-lan-cli_{version}-1_all.deb"
    data = (artifacts / filename).read_bytes()
    digest = hashlib.sha256(data).hexdigest()
    sums = (artifacts / "SHA256SUMS").read_bytes()
    if sums != f"{digest}  {filename}\n".encode():
        raise ValueError("Local SHA256SUMS does not match the release package")
    for name, distribution in (("debian13", "debian:13"), ("ubuntu2404", "ubuntu:24.04")):
        proof = json.loads((artifacts / "proofs" / f"{name}.json").read_text())
        if proof != {"distribution": distribution, "version": version, "sha256": digest, "passed": True}:
            raise ValueError(f"Acceptance did not pass for the tested package: {distribution}")
    return {filename: data, "SHA256SUMS": sums}


def tagged_commit(api, tag):
    obj = api.request("GET", "/git/ref/tags/" + quote(tag, safe=""))["object"]
    seen = set()
    while obj["type"] == "tag":
        if obj["sha"] in seen:
            raise ValueError("Cyclic annotated tag")
        seen.add(obj["sha"])
        obj = api.request("GET", "/git/tags/" + obj["sha"])["object"]
    if obj["type"] != "commit":
        raise ValueError("Release tag does not point to a commit")
    return obj["sha"]


def require_draft(release, tag, commit):
    if release.get("draft") is not True:
        raise ValueError("Version already published; changed assets require a new version")
    if release["tag_name"] != tag or release["target_commitish"] != commit:
        raise ValueError("Draft tag/commit identity mismatch")


def publish(api, artifacts, version, tag, commit, changelog):
    validate(version, tag)
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Expected exact 40-character source commit")
    files = candidate_files(artifacts, version)
    body = release_notes(changelog, version, tag, commit)
    if tagged_commit(api, tag) != commit:
        raise ValueError("Remote tag does not match checked source commit")
    matches = []
    page = 1
    while True:
        releases = api.request("GET", f"/releases?per_page=100&page={page}")
        matches.extend(release for release in releases if release["tag_name"] == tag)
        if len(releases) < 100:
            break
        page += 1
    if len(matches) > 1:
        raise ValueError("Multiple releases for the same tag")
    if matches:
        release = matches[0]
        require_draft(release, tag, commit)
    else:
        release = api.request("POST", "/releases", {"tag_name": tag, "target_commitish": commit,
                              "name": tag, "body": body, "draft": True, "prerelease": False})
        require_draft(release, tag, commit)
    release_path = f"/releases/{release['id']}"
    # Refresh before any deletion; never clobber an already public release.
    release = api.request("GET", release_path)
    require_draft(release, tag, commit)
    for asset in release["assets"]:
        api.request("DELETE", f"/releases/assets/{asset['id']}")
    for filename, data in files.items():
        api.request("POST", release_path + "/assets?" + urlencode({"name": filename}), data, upload=True)
    release = api.request("GET", release_path)
    require_draft(release, tag, commit)
    assets = release["assets"]
    if len(assets) != len(files) or {asset["name"] for asset in assets} != set(files):
        raise ValueError("Draft assets are incomplete or unexpected")
    for asset in assets:
        remote = api.request("GET", f"/releases/assets/{asset['id']}", binary=True)
        if remote != files[asset["name"]]:
            raise ValueError(f"Remote checksum mismatch: {asset['name']}")
    if tagged_commit(api, tag) != commit:
        raise ValueError("Remote tag changed during publication")
    require_draft(api.request("GET", release_path), tag, commit)
    published = api.request("PATCH", release_path, {"draft": False, "body": body, "name": tag})
    if published.get("draft") is not False:
        raise ValueError("GitHub did not confirm publication; inspect the release before retrying")
    return published["html_url"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifacts", required=True, type=Path)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--repository", required=True)
    args = parser.parse_args()
    version = source_version(tag=args.tag)
    api = GitHub(args.repository, os.environ["GITHUB_TOKEN"])
    print(publish(api, args.artifacts, version, args.tag, args.commit, ROOT / "CHANGELOG.md"))
