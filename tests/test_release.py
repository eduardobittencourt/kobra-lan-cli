"""Release safety tests: entirely synthetic and offline."""
import unittest

from scripts.release_version import validate


class VersionTests(unittest.TestCase):
    def test_final_versions(self):
        for version in ("0.0.0", "0.2.1", "1.0.0", "12.30.40"):
            self.assertEqual(validate(version, "v" + version), version)

    def test_unsupported_versions_and_tags(self):
        for version in ("01.2.3", "1.02.3", "1.2.03", "1.2", "v1.2.3", "1.2.3rc1",
                        "1.2.3-rc.1", "1.2.3+build", "1.2.3\n", "１.2.3"):
            with self.subTest(version=version), self.assertRaises(ValueError):
                validate(version)
        for tag in ("v0.2.2", "0.2.1", "v0.2.1-rc.1", "v0.2.1+build", "v00.2.1"):
            with self.subTest(tag=tag), self.assertRaises(ValueError):
                validate("0.2.1", tag)
