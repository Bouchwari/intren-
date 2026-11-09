"""Preview and crop a complete official header before applying it to exports."""
import logging
from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPaintEvent, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QDialog, QGridLayout, QHBoxLayout, QLabel, QMessageBox,
    QSlider, QVBoxLayout, QWidget,
)

from ui import document_branding as branding
from ui.dialogs import _button
from config.settings import COLOR_BORDER, COLOR_TEXT_PRIMARY

_TITLE = "تعديل ترويسة الوثائق"
_GUIDANCE = ("صورة كاملة تشمل الشعار واسم الوزارة. يفضل PNG أو JPG بدقة \u20661800 × 414\u2069 بكسل "
             "أو أعلى. تُحفظ النسب دون تمديد، وتُضبط المساحة حسب كل وثيقة.")
_LOW_RESOLUTION = "دقة الجزء المختار منخفضة؛ قد لا تكون الكتابة واضحة عند الطباعة."
_SAVE_ERROR = "تعذر حفظ الترويسة. لم يتم تغيير الصورة السابقة."
_SIDES = (("top", "أعلى"), ("bottom", "أسفل"), ("right", "يمين"), ("left", "يسار"))


class _CropPreview(QWidget):
    def __init__(self, image: QImage) -> None:
        super().__init__()
        self.image = image
        self.crop = image.rect()
        self.setMinimumHeight(160)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#edf1ef"))
        size = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        rect = QRectF((self.width() - size.width()) / 2,
                      (self.height() - size.height()) / 2, size.width(), size.height())
        painter.drawImage(rect, self.image)
        scale = rect.width() / self.image.width()
        selected = QRectF(rect.x() + self.crop.x() * scale, rect.y() + self.crop.y() * scale,
                          self.crop.width() * scale, self.crop.height() * scale)
        painter.setPen(QPen(QColor("#159773"), 2))
        painter.drawRect(selected)
        painter.end()


class HeaderEditorDialog(QDialog):
    def __init__(self, image: QImage, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.image = image
        self.setWindowTitle(_TITLE)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.resize(780, 650)
        self.setMinimumSize(600, 540)
        self.setStyleSheet(f"""
            QDialog, QWidget {{ background:white; color:{COLOR_TEXT_PRIMARY}; }}
            QLabel {{ border:0; }}
            QSlider::groove:horizontal {{ background:#d7dfdc; height:6px; }}
            QSlider::handle:horizontal {{ background:#159773; width:16px; margin:-5px 0; }}
        """)
        root = QVBoxLayout(self)
        guide = QLabel(_GUIDANCE)
        guide.setWordWrap(True)
        root.addWidget(guide)
        self.source_preview = _CropPreview(image)
        root.addWidget(self.source_preview, 1)
        grid = QGridLayout()
        self.sliders: dict[str, QSlider] = {}
        self.values: dict[str, QLabel] = {}
        for row, (side, label) in enumerate(_SIDES):
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(0, 95)
            slider.setAccessibleName(label)
            self.sliders[side] = slider
            self.values[side] = QLabel("0%")
            self.values[side].setMinimumWidth(44)
            slider.valueChanged.connect(lambda _value, side=side: self._changed(side))
            grid.addWidget(QLabel(label), row, 0)
            grid.addWidget(slider, row, 1)
            grid.addWidget(self.values[side], row, 2)
        root.addLayout(grid)
        root.addWidget(QLabel("معاينة الترويسة"))
        self.output_preview = QLabel()
        self.output_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.output_preview.setMinimumHeight(100)
        self.output_preview.setStyleSheet(f"border:1px solid {COLOR_BORDER}; background:white;")
        root.addWidget(self.output_preview)
        self.warning = QLabel()
        self.warning.setWordWrap(True)
        self.warning.setStyleSheet("color:#9a5500;")
        root.addWidget(self.warning)
        actions = QHBoxLayout()
        apply = _button("اعتماد الترويسة", primary=True)
        apply.clicked.connect(self._apply)
        cancel = _button("إلغاء")
        cancel.set_style(hover_bg="#d1e8dd")
        cancel.clicked.connect(self.reject)
        reset = _button("إعادة ضبط القص")
        reset.set_style(hover_bg="#d1e8dd")
        reset.clicked.connect(self._reset_crop)
        actions.addWidget(apply)
        actions.addWidget(cancel)
        actions.addStretch()
        actions.addWidget(reset)
        root.addLayout(actions)
        self._changed("top")

    def crop_rect(self) -> QRect:
        width, height = self.image.width(), self.image.height()
        left = round(width * self.sliders["left"].value() / 100)
        top = round(height * self.sliders["top"].value() / 100)
        right = round(width * (100 - self.sliders["right"].value()) / 100)
        bottom = round(height * (100 - self.sliders["bottom"].value()) / 100)
        return QRect(left, top, max(1, right - left), max(1, bottom - top))

    def _changed(self, side: str) -> None:
        opposite = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}[side]
        if self.sliders[side].value() + self.sliders[opposite].value() > 95:
            self.sliders[opposite].setValue(95 - self.sliders[side].value())
        for key, slider in self.sliders.items():
            self.values[key].setText(f"{slider.value()}%")
        rect = self.crop_rect()
        self.source_preview.crop = rect
        self.source_preview.update()
        preview = branding.fitted_header(self.image.copy(rect))
        self.output_preview.setPixmap(QPixmap.fromImage(preview).scaled(
            560, 128, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.warning.setText(_LOW_RESOLUTION if rect.width() < 900 or rect.height() < 200 else "")

    def _reset_crop(self) -> None:
        for slider in self.sliders.values():
            slider.setValue(0)

    def _apply(self) -> None:
        try:
            branding.save_header(self.image, self.crop_rect())
        except (OSError, ValueError):
            logging.getLogger(__name__).exception("Cannot save custom document header")
            QMessageBox.warning(self, _TITLE, _SAVE_ERROR)
            return
        self.accept()
