"""Release version and GitHub payload parsing tests."""
import json
import sys
import unittest
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from core.update_check import is_newer_version, parse_release_payload


class VersionComparisonTests(unittest.TestCase):
    def test_only_a_higher_semantic_version_is_newer(self) -> None:
        self.assertTrue(is_newer_version("1.1.0", "1.2.0"))
        self.assertTrue(is_newer_version("1.9.9", "2.0.0"))
        self.assertFalse(is_newer_version("1.1.0", "1.1.0"))
        self.assertFalse(is_newer_version("1.1.0", "1.0.9"))

    def test_malformed_versions_do_not_trigger_an_update(self) -> None:
        self.assertFalse(is_newer_version("development", "1.2.0"))
        self.assertFalse(is_newer_version("1.1.0", "latest"))


class ReleasePayloadTests(unittest.TestCase):
    @staticmethod
    def _payload(**overrides: object) -> bytes:
        document = {
            "tag_name": "v1.2.0",
            "html_url": "https://github.com/Bouchwari/intren-/releases/tag/v1.2.0",
            "body": "## Changes\n\n- Fixed generation",
            "assets": [{
                "name": "TadbirInternatSetup.exe",
                "browser_download_url": (
                    "https://github.com/Bouchwari/intren-/releases/download/"
                    "v1.2.0/TadbirInternatSetup.exe"
                ),
            }],
        }
        document.update(overrides)
        return json.dumps(document).encode("utf-8")

    def test_installer_asset_and_release_notes_are_extracted(self) -> None:
        release = parse_release_payload(
            self._payload(), "TadbirInternatSetup.exe")

        self.assertEqual(release.version, "1.2.0")
        self.assertIn("Fixed generation", release.notes)
        self.assertTrue(release.download_url.endswith("TadbirInternatSetup.exe"))

    def test_release_page_is_the_fallback_when_installer_is_missing(self) -> None:
        release = parse_release_payload(
            self._payload(assets=[]), "TadbirInternatSetup.exe")

        self.assertEqual(release.download_url, release.page_url)

    def test_untrusted_download_host_is_not_opened(self) -> None:
        payload = self._payload(assets=[{
            "name": "TadbirInternatSetup.exe",
            "browser_download_url": "https://example.com/app.exe",
        }])

        release = parse_release_payload(payload, "TadbirInternatSetup.exe")

        self.assertEqual(release.download_url, release.page_url)

    def test_invalid_release_page_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            parse_release_payload(
                self._payload(html_url="http://example.com/release"),
                "TadbirInternatSetup.exe",
            )


if __name__ == "__main__":
    unittest.main()
