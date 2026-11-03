"""Prove runtime installation rejects unverified wheels and source archives offline."""
import hashlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
import unittest
from unittest.mock import patch
import venv
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from check_python import install_runtime


class RuntimeInstallTests(unittest.TestCase):
    def setUp(self):
        """Use a fresh pip environment so installed packages cannot bypass hash checks."""
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        venv.EnvBuilder(with_pip=True).create(self.root / 'venv')
        self.python = self.root / 'venv/bin/python'
        self.wheels = self.root / 'wheels'
        self.wheels.mkdir()
        self.requirements = self.root / 'requirements.txt'
        self.env = dict(os.environ, PIP_NO_INDEX='1', PIP_DISABLE_PIP_VERSION_CHECK='1')
        self.env.pop('PYTHONPATH', None)
        self.real_run = subprocess.run

    def run_captured(self, *args, **kwargs):
        """Capture real pip diagnostics and bound execution without mocking its checks."""
        return self.real_run(*args, **kwargs, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, timeout=30)

    def wheel(self):
        """Create a valid minimal wheel containing only a harmless synthetic module."""
        wheel = self.wheels / 'synthetic_runtime-1.0-py3-none-any.whl'
        prefix = 'synthetic_runtime-1.0.dist-info/'
        with zipfile.ZipFile(wheel, 'w') as archive:
            archive.writestr('synthetic_runtime.py', 'VALUE = 1\n')
            archive.writestr(prefix + 'METADATA',
                             'Metadata-Version: 2.1\nName: synthetic-runtime\nVersion: 1.0\n')
            archive.writestr(prefix + 'WHEEL',
                             'Wheel-Version: 1.0\nRoot-Is-Purelib: true\nTag: py3-none-any\n')
            archive.writestr(prefix + 'RECORD', '')
        return wheel

    def lock(self, artifact):
        """Pin the expected artifact bytes before a test mutates or presents them."""
        digest = hashlib.sha256(artifact.read_bytes()).hexdigest()
        self.requirements.write_text('synthetic-runtime==1.0 --hash=sha256:' + digest + '\n')

    def install(self):
        """Exercise the same locked wheelhouse installer used by package validation."""
        with patch('check_python.subprocess.run', side_effect=self.run_captured):
            install_runtime(self.python, self.root, self.wheels, self.env, self.requirements)

    def test_matching_locked_wheel_installs(self):
        """Accept a wheel whose version and bytes match the pinned manifest."""
        self.lock(self.wheel())
        self.install()
        result = self.real_run([str(self.python), '-c', 'import synthetic_runtime; print(synthetic_runtime.VALUE)'],
                               capture_output=True, text=True, env=self.env, check=True)
        self.assertEqual(result.stdout, '1\n')

    def test_modified_wheel_is_rejected(self):
        """Reject changed wheel bytes even when the filename and version still match."""
        artifact = self.wheel()
        self.lock(artifact)
        with artifact.open('ab') as stream:
            stream.write(b'corruption after locking')
        with self.assertRaises(subprocess.CalledProcessError) as failure:
            self.install()
        self.assertIn('DO NOT MATCH THE HASHES', failure.exception.stdout)

    def test_missing_hash_is_rejected(self):
        """Never silently install an available wheel when the manifest omits its hash."""
        self.wheel()
        self.requirements.write_text('synthetic-runtime==1.0\n')
        with self.assertRaises(subprocess.CalledProcessError) as failure:
            self.install()
        self.assertIn('Hashes are required', failure.exception.stdout)

    def test_matching_sdist_is_never_executed(self):
        """Reject even a hash-matching source distribution without running setup code."""
        marker = self.root / 'source-build-executed'
        source = self.wheels / 'synthetic_runtime-1.0.tar.gz'
        setup = ('from pathlib import Path\nPath(' + repr(str(marker)) + ').write_text("unsafe")\n').encode()
        with tarfile.open(source, 'w:gz') as archive:
            member = tarfile.TarInfo('synthetic_runtime-1.0/setup.py')
            member.size = len(setup)
            archive.addfile(member, io.BytesIO(setup))
        self.lock(source)
        with self.assertRaises(subprocess.CalledProcessError) as failure:
            self.install()
        self.assertIn('No matching distribution found', failure.exception.stdout)
        self.assertFalse(marker.exists())
