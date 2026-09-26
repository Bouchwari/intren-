import sys
import unittest
from pathlib import Path

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QFont, QImage, QPainter, QTextOption
from PySide6.QtWidgets import QApplication

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]

from ui.document_header import official_font_family
from ui.pdf_layout import _Picture96, _TextRecordingPainter
from ui.theme import body_font_family, load_fonts


class DocumentTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        load_fonts()

    def render(self, text, family, recorded):
        image = QImage(800, 80, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        image.setDotsPerMeterX(round(96 / .0254))
        image.setDotsPerMeterY(round(96 / .0254))

        def draw(painter, value):
            painter.setFont(QFont(family, 20))
            painter.setPen(Qt.GlobalColor.black)
            option = QTextOption()
            option.setTextDirection(Qt.LayoutDirection.RightToLeft)
            option.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignAbsolute)
            painter.drawText(QRectF(10, 10, 780, 60), value, option)

        painter = QPainter(image)
        if recorded:
            picture = _Picture96()
            recorder = _TextRecordingPainter(picture)
            draw(recorder, text)
            recorder.end()
            painter.drawPicture(QPointF(0, 0), picture)
            recorder.replay_text(painter)
        else:
            draw(painter, text)
        painter.end()
        return image

    def test_recorded_arabic_punctuation_matches_direct_rendering(self):
        for family in (body_font_family(), official_font_family()):
            for text in (
                "رسالة الطلبية رقم: 001",
                "الموسم الدراسي: 2026/2027",
                "صاحب الصفقة: SOCIETE EXEMPLE (SARL)",
                "التاريخ: 2026/09/26، الساعة: 12:30",
                "ملاحظات: جيدة، حسنة؛ هل تمت المراقبة؟",
                "Date : 26/09/2026",
                "Société : EXEMPLE (SARL)",
                "2026-09-26 12:30 25.50",
            ):
                with self.subTest(family=family, text=text):
                    self.assertEqual(self.render(text, family, True), self.render(text, family, False))
