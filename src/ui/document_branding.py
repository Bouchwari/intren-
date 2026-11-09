"""User-approved official header, fitted without changing template geometry."""
from pathlib import Path
from zipfile import ZipFile

from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect, QSaveFile, QSize, Qt
from PySide6.QtGui import QColor, QImage, QImageReader, QPainter

from config.settings import DOCUMENT_HEADER_PATH

HEADER_SIZE = QSize(1800, 414)
MAX_IMAGE_PIXELS = 40_000_000


def load_header_source(path: Path) -> QImage:
    reader = QImageReader(str(path))
    reader.setAutoTransform(True)
    size = reader.size()
    if not size.isValid() or size.width() * size.height() > MAX_IMAGE_PIXELS:
        raise ValueError("Invalid image or image exceeds 40 megapixels")
    image = reader.read()
    if image.isNull():
        raise ValueError("Cannot decode header image")
    return image


def fitted_header(image: QImage, size: QSize = HEADER_SIZE) -> QImage:
    if image.isNull() or size.isEmpty():
        raise ValueError("Empty header image")
    canvas = QImage(size, QImage.Format.Format_RGB32)
    canvas.fill(QColor("white"))
    scaled = image.scaled(size, Qt.AspectRatioMode.KeepAspectRatio,
                          Qt.TransformationMode.SmoothTransformation)
    painter = QPainter(canvas)
    painter.drawImage((size.width() - scaled.width()) // 2,
                      (size.height() - scaled.height()) // 2, scaled)
    painter.end()
    return canvas


def image_bytes(image: QImage, extension: str = "png") -> bytes:
    content = QByteArray()
    buffer = QBuffer(content)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, extension.upper(), 95):
        raise ValueError("Cannot encode header image")
    return bytes(content)


def custom_header() -> QImage | None:
    if not DOCUMENT_HEADER_PATH.exists():
        return None
    # Do not cache: edits must affect the next export without restarting.
    return load_header_source(DOCUMENT_HEADER_PATH)


def save_header(image: QImage, crop: QRect) -> None:
    selected = crop.intersected(image.rect())
    if selected.isEmpty():
        raise ValueError("Empty header crop")
    content = image_bytes(fitted_header(image.copy(selected)))
    DOCUMENT_HEADER_PATH.parent.mkdir(parents=True, exist_ok=True)
    target = QSaveFile(str(DOCUMENT_HEADER_PATH))
    if not target.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError(target.errorString())
    if target.write(content) != len(content) or not target.commit():
        target.cancelWriting()
        raise OSError(target.errorString())


def reset_header() -> None:
    DOCUMENT_HEADER_PATH.unlink(missing_ok=True)


def replace_header_image(original: bytes, extension: str) -> bytes:
    replacement = custom_header()
    if replacement is None:
        return original
    template = QImage.fromData(original)
    if template.isNull():
        raise ValueError("Cannot read original document header")
    factor = max(1, (HEADER_SIZE.width() + template.width() - 1) // template.width())
    size = QSize(template.width() * factor, template.height() * factor)
    return image_bytes(fitted_header(replacement, size), extension)


def docx_template_header(source: ZipFile) -> bytes | None:
    name = "word/media/image1.jpeg"
    return source.read(name) if name in source.namelist() else None


def docx_header_part(member: str, original: bytes, template_header: bytes | None) -> bytes:
    # Audited templates use image1 for the header; image2 is sometimes a second
    # identical header, sometimes blank artwork that must remain untouched.
    if member not in {"word/media/image1.jpeg", "word/media/image2.jpeg"}:
        return original
    if original != template_header:
        return original
    return replace_header_image(original, "jpeg")
