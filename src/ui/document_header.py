"""Shared official document header drawing helpers for exported UI documents."""
import sys
from pathlib import Path
from zipfile import ZipFile

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import (
    QColor, QFont, QFontDatabase, QImage, QPainter, QPen, QTextOption,
)

from config.settings import BASE_DIR
from core.models import SchoolSettings


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
) -> None:
    font = QFont(official_font_family())
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
        f"الأكاديمية الجهوية للتربية والتكوين {academy}",
        f"المديرية الإقليمية {province}",
        f"المؤسسة {school}",
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
