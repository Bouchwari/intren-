import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from PySide6.QtCore import QCoreApplication, QEvent, QRect, QSize
from PySide6.QtGui import QColor, QImage
from PySide6.QtWidgets import QApplication, QDialog

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from core.models import DailyContact, DailyReceptionRecord, MonthlyReceptionRecord, SchoolSettings, Student
from data import database
from ui import document_branding as branding
from ui.document_header import _template_header_image, serialize_docx_xml
from ui.header_editor import HeaderEditorDialog
from ui.daily_contact_screen import _write_daily_contact_docx
from ui.daily_reception_screen import _write_reception_docx
from ui.monthly_reception_screen import _write_monthly_reception_docx
from ui.expense_roster_export import write_expense_roster_excel


class DocumentBrandingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self) -> None:
        self.windows = set(self.app.topLevelWidgets())
        self.temp = tempfile.TemporaryDirectory()
        self.folder = Path(self.temp.name)
        self.header_patch = patch.object(branding, "DOCUMENT_HEADER_PATH", self.folder / "header.png")
        self.header_patch.start()
        self.db_patch = patch.object(database, "DB_PATH", self.folder / "test.db")
        self.db_patch.start()
        database.init_database()
        self.image = QImage(1800, 414, QImage.Format.Format_RGB32)
        self.image.fill(QColor("#c02c32"))

    def tearDown(self) -> None:
        for window in self.app.topLevelWidgets():
            if window not in self.windows:
                window.close()
                window.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        self.header_patch.stop()
        self.db_patch.stop()
        self.temp.cleanup()

    def _save(self) -> None:
        branding.save_header(self.image, self.image.rect())

    def test_no_custom_header_leaves_original_bytes_unchanged(self) -> None:
        original = branding.image_bytes(self.image)
        self.assertEqual(branding.replace_header_image(original, "png"), original)

    def test_upload_and_reset_are_reflected_without_restarting(self) -> None:
        original = _template_header_image()
        self._save()
        updated = _template_header_image()
        self.assertEqual(updated.pixelColor(updated.width() // 2, updated.height() // 2), QColor("#c02c32"))
        self.assertAlmostEqual(updated.width() / updated.height(), original.width() / original.height(), places=2)
        branding.reset_header()
        self.assertEqual(_template_header_image(), original)

    def test_portrait_image_is_fitted_without_stretching_or_cropping(self) -> None:
        portrait = self.image.copy(QRect(0, 0, 100, 400))
        fitted = branding.fitted_header(portrait)
        self.assertEqual(fitted.size(), branding.HEADER_SIZE)
        self.assertEqual(fitted.pixelColor(0, 200), QColor("white"))
        self.assertEqual(fitted.pixelColor(900, 200), QColor("#c02c32"))

    def test_rejecting_editor_does_not_replace_header(self) -> None:
        self._save()
        before = branding.DOCUMENT_HEADER_PATH.read_bytes()
        dialog = HeaderEditorDialog(self.image)
        dialog.sliders["left"].setValue(45)
        dialog.reject()
        self.assertEqual(branding.DOCUMENT_HEADER_PATH.read_bytes(), before)

    def test_crop_limits_prevent_empty_region_and_apply_saves_png(self) -> None:
        dialog = HeaderEditorDialog(self.image)
        for slider in dialog.sliders.values():
            slider.setValue(95)
        self.assertTrue(self.image.rect().contains(dialog.crop_rect()))
        self.assertFalse(dialog.crop_rect().isEmpty())
        dialog._apply()
        self.assertEqual(dialog.result(), QDialog.DialogCode.Accepted)
        self.assertEqual(branding.custom_header().size(), branding.HEADER_SIZE)

    def test_invalid_source_and_invalid_crop_keep_existing_header(self) -> None:
        self._save()
        before = branding.DOCUMENT_HEADER_PATH.read_bytes()
        bad = self.folder / "bad.png"
        bad.write_bytes(b"not an image")
        with self.assertRaises(ValueError):
            branding.load_header_source(bad)
        with self.assertRaises(ValueError):
            branding.save_header(self.image, QRect())
        self.assertEqual(branding.DOCUMENT_HEADER_PATH.read_bytes(), before)

    def test_docx_changes_header_only_not_text_layout_or_other_media(self) -> None:
        baseline, custom = self.folder / "original.docx", self.folder / "custom.docx"
        contacts = [DailyContact(date="2026-11-05", meal_type="ghada", collegial_granted=25)]
        _write_daily_contact_docx(baseline, "2026-11-05", contacts)
        self._save()
        _write_daily_contact_docx(custom, "2026-11-05", contacts)
        with ZipFile(baseline) as first, ZipFile(custom) as second:
            changed = [name for name in first.namelist() if first.read(name) != second.read(name)]
            self.assertTrue(changed)
            self.assertTrue(set(changed) <= {"word/media/image1.jpeg", "word/media/image2.jpeg"})
            image = QImage.fromData(second.read("word/media/image1.jpeg"))
            self.assertGreater(image.pixelColor(image.width() // 2, image.height() // 2).red(), 180)

    def test_word_blank_secondary_artwork_is_not_replaced(self) -> None:
        path = self.folder / "images.docx"
        original = branding.image_bytes(self.image, "jpeg")
        blank = QImage(100, 20, QImage.Format.Format_RGB32)
        blank.fill(QColor("white"))
        blank_bytes = branding.image_bytes(blank, "jpeg")
        with ZipFile(path, "w") as output:
            output.writestr("word/media/image1.jpeg", original)
            output.writestr("word/media/image2.jpeg", blank_bytes)
        self._save()
        with ZipFile(path) as source:
            self.assertEqual(branding.docx_header_part("word/media/image2.jpeg", blank_bytes,
                                                     branding.docx_template_header(source)), blank_bytes)

    def test_reception_header_images_print_inside_page_without_stretching(self) -> None:
        wp = "{http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing}"
        pic = "{http://schemas.openxmlformats.org/drawingml/2006/picture}"
        a = "{http://schemas.openxmlformats.org/drawingml/2006/main}"
        for custom in (False, True):
            if custom:
                self._save()
            for name, write, period, record in (
                ("daily", _write_reception_docx, "2026-11-05", DailyReceptionRecord(date="2026-11-05")),
                ("monthly", _write_monthly_reception_docx, "2026-11", MonthlyReceptionRecord(month="2026-11")),
            ):
                with self.subTest(document=name, custom=custom):
                    output = self.folder / f"{name}.docx"
                    write(output, period, record)
                    count = 0
                    with ZipFile(output) as archive:
                        image = QImage.fromData(archive.read("word/media/image1.jpeg"))
                        for member in archive.namelist():
                            if not (member.startswith("word/header") and member.endswith(".xml")):
                                continue
                            root = ET.fromstring(archive.read(member))
                            self.assertIsNone(root.find(f".//{wp}wrapTopAndBottom"))
                            for anchor in root.iter(f"{wp}anchor"):
                                picture = anchor.find(f".//{pic}pic")
                                if picture is None:
                                    continue
                                count += 1
                                position = anchor.find(f"{wp}positionV")
                                self.assertEqual(position.get("relativeFrom"), "page")
                                self.assertGreaterEqual(int(position.find(f"{wp}posOffset").text), 180000)
                                extent = anchor.find(f"{wp}extent")
                                self.assertAlmostEqual(int(extent.get("cx")) / int(extent.get("cy")),
                                                       image.width() / image.height(), places=4)
                                transform = picture.find(f"{pic}spPr/{a}xfrm/{a}ext")
                                self.assertEqual(transform.attrib, extent.attrib)
                    self.assertGreater(count, 0)

    def test_word_compatibility_prefixes_survive_xml_serialization(self) -> None:
        original = b'''<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
            xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"
            xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" mc:Ignorable="w14">
            <mc:AlternateContent><mc:Choice Requires="w14"/></mc:AlternateContent></w:document>'''
        result = serialize_docx_xml(ET.fromstring(original), original)
        namespaces = dict(value for _, value in ET.iterparse(BytesIO(result), events=("start-ns",)))
        self.assertIn("w14", namespaces)
        self.assertEqual(ET.fromstring(result).attrib, ET.fromstring(original).attrib)

    def test_excel_changes_header_only_and_preserves_a4_and_formulas(self) -> None:
        baseline, custom = self.folder / "original.xlsx", self.folder / "custom.xlsx"
        settings = SchoolSettings(school_name="Test", school_year="2026/2027", director="Test")
        student = Student(full_name="Test", massar_number="M1", gender="male",
                          cycle="الثانوي الإعدادي", student_class="الأولى إعدادي",
                          section="internat", grant_type="full")
        quarter = [(2026, 10), (2026, 11), (2026, 12)]
        write_expense_roster_excel(baseline, settings, [student], quarter)
        self._save()
        write_expense_roster_excel(custom, settings, [student], quarter)
        with ZipFile(baseline) as first, ZipFile(custom) as second:
            changed = [name for name in first.namelist() if name != "docProps/core.xml"
                       and first.read(name) != second.read(name)]
            self.assertEqual(changed, ["xl/media/image1.png"])
