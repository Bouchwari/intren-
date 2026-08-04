"""Shared official document header drawing helpers for exported UI documents."""
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from zipfile import ZipFile

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QImage, QPainter, QPen, QTextOption,
)
from PySide6.QtWidgets import QWidget

from config.settings import (
    BASE_DIR, EXPORT_FORMAT_DOCX, EXPORT_FORMAT_PDF,
)
from core.models import SchoolSettings
from ui.dialogs import ask_choice
from ui.theme import body_font_family

# Word documents declare many namespace prefixes (w, mc, wp, wps, v, o, ...)
# on the root element. ElementTree's tostring() does NOT preserve these — by
# default it invents its own generic ns0/ns1/ns2/... prefixes for everything,
# which breaks Word's mc:AlternateContent handling (used for floating text
# boxes' VML-vs-DrawingML fallback): the text becomes invisible even though
# it's still present in the XML. Registering the real prefixes up front makes
# tostring() reuse them instead, matching what Word actually expects.
_DOCX_NAMESPACES = {
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "aink": "http://schemas.microsoft.com/office/drawing/2016/ink",
    "am3d": "http://schemas.microsoft.com/office/drawing/2017/model3d",
    "cx": "http://schemas.microsoft.com/office/drawing/2014/chartex",
    "cx1": "http://schemas.microsoft.com/office/drawing/2015/9/8/chartex",
    "cx2": "http://schemas.microsoft.com/office/drawing/2015/10/21/chartex",
    "cx3": "http://schemas.microsoft.com/office/drawing/2016/5/9/chartex",
    "cx4": "http://schemas.microsoft.com/office/drawing/2016/5/10/chartex",
    "cx5": "http://schemas.microsoft.com/office/drawing/2016/5/11/chartex",
    "cx6": "http://schemas.microsoft.com/office/drawing/2016/5/12/chartex",
    "cx7": "http://schemas.microsoft.com/office/drawing/2016/5/13/chartex",
    "cx8": "http://schemas.microsoft.com/office/drawing/2016/5/14/chartex",
    "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
    "mc": "http://schemas.openxmlformats.org/markup-compatibility/2006",
    "o": "urn:schemas-microsoft-com:office:office",
    "oel": "http://schemas.microsoft.com/office/2019/extlst",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "v": "urn:schemas-microsoft-com:vml",
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "w10": "urn:schemas-microsoft-com:office:word",
    "w14": "http://schemas.microsoft.com/office/word/2010/wordml",
    "w15": "http://schemas.microsoft.com/office/word/2012/wordml",
    "w16": "http://schemas.microsoft.com/office/word/2018/wordml",
    "w16cex": "http://schemas.microsoft.com/office/word/2018/wordml/cex",
    "w16cid": "http://schemas.microsoft.com/office/word/2016/wordml/cid",
    "w16du": "http://schemas.microsoft.com/office/word/2023/wordml/word16du",
    "w16sdtdh": "http://schemas.microsoft.com/office/word/2020/wordml/sdtdatahash",
    "w16sdtfl": "http://schemas.microsoft.com/office/word/2024/wordml/sdtformatlock",
    "w16se": "http://schemas.microsoft.com/office/word/2015/wordml/symex",
    "wne": "http://schemas.microsoft.com/office/word/2006/wordml",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "wp14": "http://schemas.microsoft.com/office/word/2010/wordprocessingDrawing",
    "wpc": "http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas",
    "wpg": "http://schemas.microsoft.com/office/word/2010/wordprocessingGroup",
    "wpi": "http://schemas.microsoft.com/office/word/2010/wordprocessingInk",
    "wps": "http://schemas.microsoft.com/office/word/2010/wordprocessingShape",
}


def register_docx_namespaces() -> None:
    """Call before any ET.fromstring()/tostring() round-trip on a .docx
    part. Safe to call repeatedly — ET.register_namespace() just updates a
    process-global prefix table."""
    for prefix, uri in _DOCX_NAMESPACES.items():
        ET.register_namespace(prefix, uri)


_HEADER_TEMPLATE_NAME = "البرنامج الغذائي لشهر رمضان المبارك.docx"
_HEADER_IMAGE = "word/media/image1.jpeg"
_OFFICIAL_FONT_NAME = "maghribi-font 1.ttf"
_FALLBACK_FONT = "Segoe UI"

_FONT_FAMILY: str | None = None
_HEADER_IMAGE_CACHE: QImage | None = None


def _template_dirs() -> list[Path]:
    """Return template locations for source runs and PyInstaller one-dir bundles."""
    runtime_base = Path(getattr(sys, "_MEIPASS", BASE_DIR))
    candidates = [
        BASE_DIR / "templets",
        BASE_DIR / "_internal" / "templets",
        runtime_base / "templets",
        Path.cwd() / "templets",
    ]

    unique: list[Path] = []
    for candidate in candidates:
        if candidate not in unique:
            unique.append(candidate)
    return unique


def _template_file(name: str) -> Path | None:
    for template_dir in _template_dirs():
        path = template_dir / name
        if path.exists():
            return path
    return None


def official_font_family() -> str:
    """Return the bundled official Arabic font family when it can be loaded."""
    global _FONT_FAMILY
    if _FONT_FAMILY is not None:
        return _FONT_FAMILY

    font_path = _template_file(_OFFICIAL_FONT_NAME)
    if font_path is not None:
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        if font_id >= 0:
            families = QFontDatabase.applicationFontFamilies(font_id)
            if families:
                _FONT_FAMILY = families[0]
                return _FONT_FAMILY

    _FONT_FAMILY = _FALLBACK_FONT
    return _FONT_FAMILY


def _template_header_image() -> QImage:
    global _HEADER_IMAGE_CACHE
    if _HEADER_IMAGE_CACHE is not None:
        return _HEADER_IMAGE_CACHE

    image = QImage()
    template_path = _template_file(_HEADER_TEMPLATE_NAME)
    if template_path is not None:
        try:
            with ZipFile(template_path) as docx:
                image.loadFromData(docx.read(_HEADER_IMAGE))
        except Exception:
            image = QImage()

    _HEADER_IMAGE_CACHE = image
    return _HEADER_IMAGE_CACHE


def _text(
    painter: QPainter,
    rect: QRectF,
    value: str,
    *,
    size: int,
    color: str = "#111827",
    bold: bool = False,
    align: Qt.AlignmentFlag = Qt.AlignmentFlag.AlignRight,
    font_family: str | None = None,
) -> None:
    # The official Maghribi face is decorative and only holds up at large
    # display sizes (see ui_design.md) — small text in that font renders as
    # near-illegible mojibake, so every caller except the big title must
    # pass the regular body font explicitly.
    font = QFont(font_family or body_font_family())
    font.setPointSize(size)
    font.setBold(bold)
    painter.setFont(font)
    painter.setPen(QColor(color))

    option = QTextOption()
    option.setTextDirection(Qt.LayoutDirection.RightToLeft)
    option.setAlignment(align)
    option.setWrapMode(QTextOption.WrapMode.WordWrap)
    painter.drawText(rect, value, option)


def _setting(value: str, fallback: str = "—") -> str:
    return value.strip() if value and value.strip() else fallback


def _labeled_line(label: str, value: str) -> str:
    """"{label} {value}", but skip the label if the settings value already
    opens with its first word — some users type the whole official phrase
    into the settings field themselves (wording can vary slightly from our
    hardcoded label, e.g. "للتربية والتكوين" vs "للتربية و التعليم"), which
    would otherwise print the label twice."""
    first_word = label.split()[0]
    if value.startswith(first_word):
        return value
    return f"{label} {value}"


def draw_official_pdf_header(
    painter: QPainter,
    *,
    page_width: float,
    margin: float,
    top: float,
    settings: SchoolSettings | None,
    title: str,
) -> float:
    """Draw the ministry-style header and return the Y position for document body."""
    content_width = page_width - (margin * 2)
    y = top

    image = _template_header_image()
    if not image.isNull():
        image_width = min(content_width * 0.40, 440.0)
        image_height = image_width * image.height() / image.width()
        image_rect = QRectF((page_width - image_width) / 2, y, image_width, image_height)
        painter.drawImage(image_rect, image)
        y = image_rect.bottom() + 6

    academy = _setting(settings.aref if settings else "")
    province = _setting(settings.direction_provinciale if settings else "")
    school = _setting(settings.school_name if settings else "")

    identity_lines = [
        _labeled_line("الأكاديمية الجهوية للتربية والتكوين", academy),
        _labeled_line("المديرية الإقليمية", province),
        school,
    ]
    for line in identity_lines:
        _text(
            painter,
            QRectF(margin, y, content_width, 20),
            line,
            size=11,
            color="#374151",
            align=Qt.AlignmentFlag.AlignCenter,
        )
        y += 20
    y += 4

    title_rect = QRectF(margin, y, content_width, 40)
    _text(
        painter,
        title_rect,
        title,
        size=22,
        color="#085041",
        bold=True,
        align=Qt.AlignmentFlag.AlignCenter,
        font_family=official_font_family(),
    )
    y += 48

    return y + 14


def draw_official_pdf_footer(
    painter: QPainter,
    *,
    page_width: float,
    margin: float,
    top: float,
    settings: SchoolSettings | None,
    roles: list[str],
) -> None:
    """Draw the official signature area at the bottom of exported documents.
    roles are the Arabic signer labels for this specific document (see
    SKILL.md section 1 and documents.md's per-document signature lists) —
    every caller must pass the roles that document actually needs, since
    they differ per document."""
    content_width = page_width - (margin * 2)
    col_w = content_width / len(roles)
    footer_h = 66.0

    right = page_width - margin
    y = top + 10
    for index, role in enumerate(roles):
        rect = QRectF(right - ((index + 1) * col_w), y, col_w, footer_h)
        _text(
            painter,
            QRectF(rect.left() + 8, rect.top(), rect.width() - 16, 18),
            role,
            size=10,
            color="#085041",
            bold=True,
            align=Qt.AlignmentFlag.AlignCenter,
        )
        line_y = rect.bottom() - 12
        painter.setPen(QPen(QColor("#9CA3AF"), 1))
        painter.drawLine(int(rect.left() + 28), int(line_y), int(rect.right() - 28), int(line_y))


def ask_export_format(parent: QWidget) -> str | None:
    """Shared PDF-or-Word chooser, shown when the export-format preference
    (see settings_repo.get_document_export_format) is set to 'ask'. Returns
    EXPORT_FORMAT_PDF/DOCX, or None if the user cancelled.

    Uses the app's own dialog chrome (ui.dialogs.ask_choice) instead of a
    raw QMessageBox — this was the one dialog in the app still built that
    way, and raw QMessageBox has a documented history here of rendering
    buttons with invisible text (see dialogs.py's module docstring)."""
    return ask_choice(
        parent,
        "اختر صيغة التصدير",
        "هل تريد تصدير الوثيقة بصيغة PDF أم Word؟",
        [("PDF", EXPORT_FORMAT_PDF), ("Word", EXPORT_FORMAT_DOCX), ("إلغاء", "cancel")],
    )
