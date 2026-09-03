"""Non-blocking release check and the Arabic update-details dialog."""
from __future__ import annotations

import logging

from PySide6.QtCore import QObject, Qt, QUrl, Signal, Slot
from PySide6.QtGui import QDesktopServices, QFont
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QTextBrowser, QVBoxLayout, QWidget,
)

from config.settings import (
    APP_VERSION, COLOR_ACCENT, COLOR_PANEL, COLOR_PANEL_ALT,
    COLOR_TEXT_PRIMARY, COLOR_TEXT_SECONDARY, FONT_BODY,
    UPDATE_API_URL, UPDATE_INSTALLER_ASSET_NAME, UPDATE_TIMEOUT_MS,
)
from core.update_check import ReleaseInfo, is_newer_version, parse_release_payload
from ui.widgets.icon_button import IconButton


_LOGGER = logging.getLogger(__name__)
_DIALOG_WIDTH = 580
_NOTES_HEIGHT = 230


class UpdateChecker(QObject):
    """Fetch the public release feed without delaying or interrupting startup."""

    update_available = Signal(object)

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._manager = QNetworkAccessManager(self)
        self._manager.finished.connect(self._handle_reply)
        self._request_pending = False

    def check(self) -> None:
        if self._request_pending:
            return
        request = QNetworkRequest(QUrl(UPDATE_API_URL))
        request.setRawHeader(b"Accept", b"application/vnd.github+json")
        request.setRawHeader(b"User-Agent", b"Tadbir-Internat")
        request.setTransferTimeout(UPDATE_TIMEOUT_MS)
        self._request_pending = True
        self._manager.get(request)

    @Slot(QNetworkReply)
    def _handle_reply(self, reply: QNetworkReply) -> None:
        self._request_pending = False
        try:
            if reply.error() != QNetworkReply.NetworkError.NoError:
                _LOGGER.info("Update check unavailable: %s", reply.errorString())
                return
            release = parse_release_payload(
                bytes(reply.readAll()), UPDATE_INSTALLER_ASSET_NAME)
            if is_newer_version(APP_VERSION, release.version):
                self.update_available.emit(release)
        except (UnicodeDecodeError, ValueError, TypeError) as exc:
            _LOGGER.warning("Invalid update response: %s", exc)
        finally:
            reply.deleteLater()


class UpdateDialog(QDialog):
    def __init__(self, parent: QWidget | None, release: ReleaseInfo) -> None:
        super().__init__(parent)
        self._release = release
        self.setWindowTitle("تحديث جديد")
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setModal(True)
        self.setFixedWidth(_DIALOG_WIDTH)
        self.setStyleSheet(
            f"QDialog {{ background: {COLOR_PANEL_ALT}; color: {COLOR_TEXT_PRIMARY}; }}"
            f"QLabel {{ background: transparent; color: {COLOR_TEXT_PRIMARY}; }}"
        )
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(26, 24, 26, 20)
        root.setSpacing(14)
        root.addWidget(self._heading("يتوفر تحديث جديد للبرنامج", 16))

        version_label = QLabel(
            f"الإصدار المثبت: {APP_VERSION}    •    الإصدار الجديد: {self._release.version}"
        )
        version_label.setStyleSheet(
            f"color: {COLOR_TEXT_SECONDARY}; font-size: {FONT_BODY}px;")
        root.addWidget(version_label)
        root.addWidget(self._heading("ما الجديد؟", 13))
        root.addWidget(self._notes_browser())
        root.addLayout(self._action_row())

    @staticmethod
    def _heading(text: str, size: int) -> QLabel:
        label = QLabel(text)
        font = QFont()
        font.setPointSize(size)
        font.setBold(True)
        label.setFont(font)
        return label

    def _notes_browser(self) -> QTextBrowser:
        browser = QTextBrowser()
        browser.setFixedHeight(_NOTES_HEIGHT)
        browser.setOpenExternalLinks(True)
        browser.setMarkdown(
            self._release.notes or "تحسينات وإصلاحات جديدة للبرنامج.")
        browser.setStyleSheet(
            f"QTextBrowser {{ background: {COLOR_PANEL}; color: {COLOR_TEXT_PRIMARY};"
            " border: 1px solid #d6d6c8; border-radius: 6px; padding: 10px; }"
        )
        return browser

    def _action_row(self) -> QHBoxLayout:
        actions = QHBoxLayout()
        actions.addStretch()
        later = IconButton(
            "لاحقاً", bg=COLOR_PANEL, text_color=COLOR_TEXT_PRIMARY,
            border="#d6d6c8", border_radius=6, padding_h=18,
            font_size=13, bold=True, min_height=40,
        )
        download = IconButton(
            "تنزيل التحديث", icon="↓", bg=COLOR_ACCENT, text_color="white",
            border=COLOR_ACCENT, border_radius=6, padding_h=18,
            font_size=13, bold=True, min_height=40,
        )
        later.clicked.connect(self.reject)
        download.clicked.connect(self._open_download)
        actions.addWidget(later)
        actions.addWidget(download)
        return actions

    def _open_download(self) -> None:
        QDesktopServices.openUrl(QUrl(self._release.download_url))
        self.accept()
