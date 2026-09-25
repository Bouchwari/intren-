"""Vector-preserving, two-up PDF sheets for three recipients."""
import logging
from pathlib import Path
from typing import Callable, Iterable

from PySide6.QtCore import QMarginsF, QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor, QPageLayout, QPageSize, QPaintDevice, QPainter, QPdfWriter,
    QPen, QPicture,
)

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


def write_copy_sheets(
    path: Path, dates: Iterable[str],
    build_page: Callable[[QPainter, float, float, str], str], *, title: str = "",
) -> tuple[dict, list]:
    """Build each day once, replay its three identical copies, then pack two-up.

    Notices are printed once, not three times. Failed days get an explicit
    notice rather than a partially drawn official document.
    """
    from ui.batch_export import draw_placeholder_pdf_page

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
            recorder = QPainter(picture)
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
                recorder = QPainter(picture)
                try:
                    draw_placeholder_pdf_page(
                        recorder, source_w, source_h, date_str,
                        "تعذر إنشاء وثيقة هذا اليوم. يرجى إعادة المحاولة.",
                    )
                finally:
                    recorder.end()
            else:
                counts[category] = counts.get(category, 0) + 1
            for _ in range(3 if category == "data" else 1):
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
                finally:
                    painter.restore()
                slot += 1
    finally:
        painter.end()
    del painter
    del writer
    return counts, failed_dates


def write_three_copy_pdf(
    path: Path, draw_page: Callable[[QPainter, float, float], None], *, title: str = "",
) -> None:
    def build(painter: QPainter, width: float, height: float, _date: str) -> str:
        draw_page(painter, width, height)
        return "data"

    _, failed = write_copy_sheets(path, [""], build, title=title)
    if failed:
        raise RuntimeError("Could not render the document")
