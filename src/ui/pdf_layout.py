"""Vector-preserving, two-up PDF sheets with explicit recipient counts."""
import logging
from pathlib import Path
from typing import Callable, Iterable

from PySide6.QtCore import QMarginsF, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QPageLayout, QPageSize, QPaintDevice, QPainter, QPdfWriter,
    QPen, QPicture, QFont, QTextOption,
)
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)


class _Picture96(QPicture):
    def metric(self, metric: QPaintDevice.PaintDeviceMetric) -> int:
        if metric in (
            QPaintDevice.PaintDeviceMetric.PdmDpiX,
            QPaintDevice.PaintDeviceMetric.PdmDpiY,
            QPaintDevice.PaintDeviceMetric.PdmPhysicalDpiX,
            QPaintDevice.PaintDeviceMetric.PdmPhysicalDpiY,
        ):
            return 96
        return super().metric(metric)


class _TextRecordingPainter(QPainter):
    """Keep form text out of QPicture's bidi-unsafe text serialization.

    Official forms use non-overlapping cells and text boxes. Their graphics
    can be replayed first, then their text with its original painter state.
    Native drawText at replay time preserves punctuation AND selectable text.
    """

    def __init__(self, picture: QPicture) -> None:
        super().__init__(picture)
        self._text_commands: list[tuple] = []

    def drawText(self, rect: QRectF, text: str, option: QTextOption | None = None) -> None:
        self._text_commands.append((
            QRectF(rect), text, QTextOption(option) if option is not None else QTextOption(),
            QFont(self.font()), QPen(self.pen()),
            self.worldTransform(), self.clipPath() if self.hasClipping() else None,
            self.opacity(), self.renderHints(),
        ))

    def replay_text(self, painter: QPainter) -> None:
        for rect, text, option, font, pen, transform, clip, opacity, hints in self._text_commands:
            painter.save()
            try:
                painter.setWorldTransform(transform, combine=True)
                if clip is not None:
                    painter.setClipPath(clip, Qt.ClipOperation.IntersectClip)
                painter.setFont(font)
                painter.setPen(pen)
                painter.setOpacity(opacity)
                painter.setRenderHints(painter.renderHints(), False)
                painter.setRenderHints(hints)
                painter.drawText(rect, text, option)
            finally:
                painter.restore()


def write_copy_sheets(
    path: Path, dates: Iterable[str],
    build_page: Callable[[QPainter, float, float, str], str], *, title: str = "", copies: int = 2,
) -> tuple[dict, list]:
    """Build each day once, replay the chosen copies, then pack two-up.

    Notices are printed once, not three times. Failed days get an explicit
    notice rather than a partially drawn official document.
    """
    from ui.batch_export import draw_placeholder_pdf_page

    if copies not in (2, 3):
        raise ValueError("Expected two internal copies or three including the company")
    path.parent.mkdir(parents=True, exist_ok=True)
    writer = QPdfWriter(str(path))
    writer.setResolution(96)
    writer.setPageSize(QPageSize(QPageSize.PageSizeId.A4))
    writer.setPageOrientation(QPageLayout.Orientation.Landscape)
    writer.setPageMargins(QMarginsF(0, 0, 0, 0), QPageLayout.Unit.Millimeter)
    writer.setTitle(title)
    painter = QPainter(writer)
    if not painter.isActive():
        raise OSError(f"Cannot write PDF: {path}")
    counts, failed_dates = {}, []
    slot = 0
    sheet_w, sheet_h = float(writer.width()), float(writer.height())
    source_w, source_h = sheet_h, sheet_w
    scale = min(sheet_w / 2 / source_w, sheet_h / source_h)
    try:
        for date_str in dates:
            picture = _Picture96()
            recorder = _TextRecordingPainter(picture)
            recorder.setPen(QColor("#000000"))
            try:
                category = build_page(recorder, source_w, source_h, date_str)
            except Exception:
                logger.exception("Failed to render PDF for %s", date_str)
                failed_dates.append(date_str)
                category = "failed"
            finally:
                recorder.end()
            if category == "failed":
                picture = _Picture96()
                recorder = _TextRecordingPainter(picture)
                try:
                    draw_placeholder_pdf_page(
                        recorder, source_w, source_h, date_str,
                        "تعذر إنشاء وثيقة هذا اليوم. يرجى إعادة المحاولة.",
                    )
                finally:
                    recorder.end()
            else:
                counts[category] = counts.get(category, 0) + 1
            for _ in range(copies if category == "data" else 1):
                if slot and slot % 2 == 0:
                    if not writer.newPage():
                        raise OSError(f"Cannot add PDF page: {path}")
                if slot % 2 == 0:
                    painter.setPen(QPen(QColor("#9CA3AF"), 1, Qt.PenStyle.DashLine))
                    painter.drawLine(QPointF(sheet_w / 2, 18), QPointF(sheet_w / 2, sheet_h - 18))
                # Right-hand copy first, following the app's Arabic reading order.
                left = sheet_w / 2 if slot % 2 == 0 else 0
                painter.save()
                try:
                    painter.setClipRect(QRectF(left, 0, sheet_w / 2, sheet_h))
                    painter.translate(
                        left + (sheet_w / 2 - source_w * scale) / 2,
                        (sheet_h - source_h * scale) / 2,
                    )
                    painter.scale(scale, scale)
                    painter.setPen(QColor("#000000"))
                    painter.drawPicture(QPointF(0, 0), picture)
                    recorder.replay_text(painter)
                finally:
                    painter.restore()
                slot += 1
    finally:
        painter.end()
    del painter
    del writer
    return counts, failed_dates


def write_copy_pdf(
    path: Path, draw_page: Callable[[QPainter, float, float], None], *, title: str = "", copies: int = 2,
) -> None:
    def build(painter: QPainter, width: float, height: float, _date: str) -> str:
        draw_page(painter, width, height)
        return "data"

    _, failed = write_copy_sheets(path, [""], build, title=title, copies=copies)
    if failed:
        raise RuntimeError("Could not render the document")


def choose_company_copies(parent: QWidget | None, title: str, print_layout: str) -> int | None:
    """Only company-signable daily forms call this, once per export."""
    from ui.dialogs import ask_choice

    if print_layout != "three_copies":
        return 2
    choice = ask_choice(
        parent, title, "هل تريد إضافة نسخة لمقدم الخدمة؟",
        [("نسختان: للمسير والمدير", "2"), ("3 نسخ: مع نسخة الشركة", "3"), ("إلغاء", "cancel")],
    )
    return int(choice) if choice in ("2", "3") else None
