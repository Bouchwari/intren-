"""Runtime path and first-run regressions for installed Windows builds."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT_DIR = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT_DIR / "src"
sys.path.insert(0, str(SRC_DIR))
sys.path.insert(0, str(ROOT_DIR))

from config.settings import _resolve_app_data_dir
from core.models import SchoolSettings
import main as app_main


class RuntimePathTests(unittest.TestCase):
    def test_installed_app_uses_local_app_data(self) -> None:
        result = _resolve_app_data_dir(
            frozen=True,
            base_dir=Path("C:/Program Files/TadbirInternat"),
            local_app_data="C:/Users/test/AppData/Local",
            home_dir=Path("C:/Users/test"),
        )
        self.assertEqual(
            result,
            Path("C:/Users/test/AppData/Local/TadbirInternat"),
        )

    def test_source_mode_keeps_the_project_data_location(self) -> None:
        project = Path("C:/code/tadbir")
        result = _resolve_app_data_dir(
            frozen=False,
            base_dir=project,
            local_app_data="C:/Users/test/AppData/Local",
            home_dir=Path("C:/Users/test"),
        )
        self.assertEqual(result, project)


class FirstRunTests(unittest.TestCase):
    def test_missing_settings_require_setup(self) -> None:
        with patch.object(app_main, "get_school_settings", return_value=None):
            self.assertTrue(app_main.needs_initial_setup())

    def test_incomplete_settings_require_setup(self) -> None:
        settings = SchoolSettings(
            school_name="ثانوية اختبار",
            school_year="2026/2027",
            director="",
        )
        with patch.object(
            app_main,
            "get_school_settings",
            return_value=settings,
        ):
            self.assertTrue(app_main.needs_initial_setup())

    def test_complete_settings_skip_setup(self) -> None:
        settings = SchoolSettings(
            school_name="ثانوية اختبار",
            school_year="2026/2027",
            director="مدير",
        )
        with patch.object(
            app_main,
            "get_school_settings",
            return_value=settings,
        ):
            self.assertFalse(app_main.needs_initial_setup())


if __name__ == "__main__":
    unittest.main()
