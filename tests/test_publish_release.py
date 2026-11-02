"""Exercise release API sequencing without GitHub credentials or live releases."""
import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request

from scripts.publish_release import SafeRedirect, publish

COMMIT = "a" * 40
TAG = "v0.2.1"


class FakeAPI:
    def __init__(self, *, draft=None, target=COMMIT, corrupt=None, interrupt=None, annotated=False):
        self.release = None if draft is None else {"id": 1, "draft": draft, "tag_name": TAG,
                                                   "target_commitish": target, "assets": [], "html_url": "https://example.invalid/release"}
        self.log = []
        self.data = {}
        self.next_id = 10
        self.corrupt = corrupt
        self.interrupt = interrupt
        self.remote_commit = COMMIT
        self.annotated = annotated
        self.publication_count = 0

    def request(self, method, path, body=None, **options):
        self.log.append((method, path))
        if path.startswith('/git/ref/tags/'):
            return {"object": {"type": "tag" if self.annotated else "commit", "sha": "b" * 40 if self.annotated else self.remote_commit}}
        if path.startswith('/git/tags/'):
            return {"object": {"type": "commit", "sha": self.remote_commit}}
        if method == "GET" and path.startswith('/releases?'):
            return copy.deepcopy([self.release] if self.release else [])
        if method == "POST" and path == '/releases':
            self.release = {**body, "id": 1, "assets": [], "html_url": "https://example.invalid/release"}
            return copy.deepcopy(self.release)
        if method == "GET" and path == '/releases/1':
            return copy.deepcopy(self.release)
        if method == "DELETE":
            assert self.release["draft"]
            asset_id = int(path.rsplit('/', 1)[1])
            self.release['assets'] = [asset for asset in self.release['assets'] if asset['id'] != asset_id]
            self.data.pop(asset_id, None)
            return None
        if method == "POST" and path.startswith('/releases/1/assets?'):
            assert self.release["draft"] and options["upload"]
            name = parse_qs(urlsplit(path).query)['name'][0]
            if name == self.interrupt:
                raise OSError("synthetic interrupted upload")
            self.next_id += 1
            asset = {"id": self.next_id, "name": name}
            self.release['assets'].append(asset)
            self.data[asset['id']] = body
            return copy.deepcopy(asset)
        if method == "GET" and path.startswith('/releases/assets/'):
            assert options['binary']
            asset_id = int(path.rsplit('/', 1)[1])
            name = next(a['name'] for a in self.release['assets'] if a['id'] == asset_id)
            return b'corrupted bytes' if name == self.corrupt else self.data[asset_id]
        if method == "PATCH" and path == '/releases/1':
            assert self.release["draft"]
            self.publication_count += 1
            self.release.update(body)
            return copy.deepcopy(self.release)
        raise AssertionError((method, path, body, options))


class PublicationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.filename = 'kobra-lan-cli_0.2.1-1_all.deb'
        (self.root / self.filename).write_bytes(b'synthetic package bytes')
        self.digest = hashlib.sha256((self.root / self.filename).read_bytes()).hexdigest()
        (self.root / 'SHA256SUMS').write_text(f'{self.digest}  {self.filename}\n')
        (self.root / 'proofs').mkdir()
        for name, distro in (("debian13", "debian:13"), ("ubuntu2404", "ubuntu:24.04")):
            (self.root / 'proofs' / f'{name}.json').write_text(json.dumps(
                {"distribution": distro, "version": "0.2.1", "sha256": self.digest, "passed": True}))
        self.notes = self.root / 'CHANGELOG.md'
        self.notes.write_text('# Changelog\n\n## Unreleased\n\nNot published.\n\n## 0.2.1\n\nVersion notes.\n\n## 0.2.0\n\nOld notes.\n')

    def publish(self, api):
        return publish(api, self.root, '0.2.1', TAG, COMMIT, self.notes)

    def assert_unpublished(self, api):
        self.assertEqual(api.publication_count, 0)
        if api.release:
            self.assertTrue(api.release['draft'])

    def test_create_verify_then_publish_exact_assets_and_notes(self):
        api = FakeAPI(annotated=True)
        self.assertEqual(self.publish(api), 'https://example.invalid/release')
        self.assertFalse(api.release['draft'])
        self.assertEqual({a['name'] for a in api.release['assets']}, {self.filename, 'SHA256SUMS'})
        self.assertEqual(api.release['target_commitish'], COMMIT)
        self.assertIn('Version notes.', api.release['body'])
        self.assertNotIn('Not published.', api.release['body'])
        self.assertNotIn('Old notes.', api.release['body'])
        self.assertIn(COMMIT, api.release['body'])
        reads = [p for m, p in api.log if m == 'GET' and p.startswith('/releases/assets/')]
        self.assertEqual(len(reads), 2)
        self.assertEqual(api.log[-1], ('PATCH', '/releases/1'))

    def test_interrupted_upload_leaves_draft_and_retry_replaces_only_draft_assets(self):
        api = FakeAPI(interrupt='SHA256SUMS')
        with self.assertRaises(OSError):
            self.publish(api)
        self.assert_unpublished(api)
        self.assertEqual(len(api.release['assets']), 1)
        api.interrupt = None
        self.publish(api)
        self.assertTrue(any(method == 'DELETE' for method, _ in api.log))
        self.assertEqual(api.publication_count, 1)

    def test_remote_corruption_never_publishes(self):
        for filename in (self.filename, 'SHA256SUMS'):
            with self.subTest(filename=filename):
                api = FakeAPI(corrupt=filename)
                with self.assertRaisesRegex(ValueError, 'Remote checksum mismatch'):
                    self.publish(api)
                self.assert_unpublished(api)

    def test_missing_failed_or_wrong_package_acceptance_has_no_api_calls(self):
        proof = self.root / 'proofs/ubuntu2404.json'
        original = proof.read_text()
        for replacement in ({"passed": False}, {"distribution": "ubuntu:24.04", "version": "0.2.1", "sha256": '0' * 64, "passed": True}, None):
            if replacement is None:
                proof.unlink()
            else:
                proof.write_text(json.dumps(replacement))
            api = FakeAPI()
            with self.assertRaises((ValueError, FileNotFoundError)):
                self.publish(api)
            self.assertEqual(api.log, [])
            proof.write_text(original)

    def test_local_checksum_failure_has_no_api_calls(self):
        (self.root / self.filename).write_bytes(b'changed after acceptance')
        api = FakeAPI()
        with self.assertRaisesRegex(ValueError, 'Local SHA256SUMS'):
            self.publish(api)
        self.assertEqual(api.log, [])

    def test_public_version_is_read_only_even_after_lost_publish_response(self):
        api = FakeAPI()
        self.publish(api)
        before = copy.deepcopy(api.release), copy.deepcopy(api.data)
        api.log.clear()
        with self.assertRaisesRegex(ValueError, 'already published'):
            self.publish(api)
        self.assertEqual(before, (api.release, api.data))
        self.assertTrue(all(method == 'GET' for method, _ in api.log))

    def test_existing_public_version_cannot_be_overwritten(self):
        api = FakeAPI(draft=False)
        with self.assertRaisesRegex(ValueError, 'already published'):
            self.publish(api)
        self.assertTrue(all(method == 'GET' for method, _ in api.log))

    def test_wrong_draft_commit_and_remote_tag_fail_without_mutation(self):
        for api in (FakeAPI(draft=True, target='b' * 40), FakeAPI()):
            if api.release is None:
                api.remote_commit = 'c' * 40
            with self.assertRaisesRegex(ValueError, 'mismatch|does not match'):
                self.publish(api)
            self.assertTrue(all(method == 'GET' for method, _ in api.log))

    def test_missing_version_notes_fail_before_draft_creation(self):
        self.notes.write_text('## Unreleased\nNo version section.\n')
        api = FakeAPI()
        with self.assertRaisesRegex(ValueError, 'Missing CHANGELOG'):
            self.publish(api)
        self.assertEqual(api.log, [])

    def test_bad_tag_fails_without_api_calls(self):
        api = FakeAPI()
        with self.assertRaises(ValueError):
            publish(api, self.root, '0.2.1', 'v0.2.1+metadata', COMMIT, self.notes)
        self.assertEqual(api.log, [])

    def test_cross_host_download_redirect_drops_token(self):
        request = Request('https://api.github.com/asset', headers={'Authorization': 'Bearer synthetic'})
        redirected = SafeRedirect().redirect_request(request, None, 302, 'Found', {}, 'https://release-assets.githubusercontent.com/asset')
        self.assertIsNone(redirected.get_header('Authorization'))
        with self.assertRaises(ValueError):
            SafeRedirect().redirect_request(request, None, 302, 'Found', {}, 'http://example.invalid/asset')
