"""Exact archive metadata and secret exclusion checks, using synthetic archives."""
import io
from pathlib import Path
import sys
import tarfile
import tempfile
import unittest
import zipfile

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from check_python import check_sdist, check_wheel, MODULES, DOCS


class MetadataTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(); self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.metadata = ('Name: kobra-lan-cli\nVersion: 0.3.0\nRequires-Python: >=3.11\n'
                         'License-Expression: GPL-3.0-only\nRequires-Dist: cryptography>=41\n')

    def wheel(self, metadata=None, extra=None):
        path = self.root/'app.whl'; prefix='kobra_lan_cli-0.3.0.dist-info/'
        files = {m:'' for m in MODULES}
        files[prefix+'METADATA'] = self.metadata if metadata is None else metadata
        files[prefix+'entry_points.txt'] = 'kobra-lan = kobra_lan.cli:main'
        files.update(extra or {})
        with zipfile.ZipFile(path,'w') as archive:
            for name,data in files.items(): archive.writestr(name,data)
        return path

    def test_wheel_requires_exact_dependency(self):
        check_wheel(self.wheel(),'0.3.0')
        for metadata in (self.metadata.replace('Requires-Dist: cryptography>=41\n',''),
                         self.metadata+'Requires-Dist: unexpected\n',self.metadata.replace('>=41','>=40')):
            self.assertRaises(AssertionError, check_wheel, self.wheel(metadata), '0.3.0')
        self.assertRaises(AssertionError, check_wheel, self.wheel(extra={'config.json': 'secret'}), '0.3.0')

    def sdist(self, requires='cryptography>=41',extra=None):
        path = self.root/'app.tar.gz'; prefix='kobra_lan_cli-0.3.0'
        files = {name:'' for name in MODULES | DOCS | {'pyproject.toml'}}
        files['PKG-INFO'] = self.metadata
        files['kobra_lan_cli.egg-info/requires.txt'] = requires
        files.update(extra or {})
        with tarfile.open(path,'w:gz') as archive:
            for name,content in files.items():
                member = tarfile.TarInfo(prefix+'/'+name); data=content.encode(); member.size=len(data)
                archive.addfile(member,io.BytesIO(data))
        return path

    def test_sdist_requires_exact_dependency_and_preserves_exclusions(self):
        check_sdist(self.sdist(),'0.3.0')
        for requires in ('','cryptography>=40','cryptography>=41\nunexpected'):
            self.assertRaises(AssertionError, check_sdist, self.sdist(requires), '0.3.0')
        self.assertRaises(AssertionError, check_sdist, self.sdist(extra={'private/client.key': 'secret'}), '0.3.0')
