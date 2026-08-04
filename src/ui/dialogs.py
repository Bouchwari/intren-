"""
Small app-native dialogs used instead of raw Qt/Windows popups.

The Windows-native QMessageBox/QInputDialog styling was fighting our light UI
theme and produced invisible buttons. These helpers keep popups readable,
Arabic, and visually consistent across the app without changing every caller.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog, QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QInputDialog, QVBoxLayout, QWidget,
)

from config.settings import COLOR_ACCENT, COLOR_DANGER, COLOR_PANEL_ALT, COLOR_TEXT_PRIMARY, FONT_BODY
from ui.widgets.icon_button import IconButton

_INK = "#5A5A40"
_PAGE = "#f5f5f0"
_BORDER = "#d6d6c8"
_TEXT = COLOR_TEXT_PRIMARY
_MUTED = "#64748b"
_BLUE = COLOR_ACCENT
_RED = COLOR_DANGER
_GREEN = "#16a34a"

_ORIGINAL_GET_SAVE_FILE_NAME = QFileDialog.getSaveFileName
_ORIGINAL_GET_OPEN_FILE_NAME = QFileDialog.getOpenFileName


def _button(label: str, *, primary: bool = False, danger: bool = False) -> QPushButton:
    bg = _BLUE if primary else (_RED if danger else COLOR_PANEL_ALT)
    fg = "#ffffff" if (primary or danger) else _TEXT
    btn = IconButton(
        label, bg=bg, text_color=fg, border=bg,
        border_radius=12, padding_h=18, font_size=13, bold=True, min_height=38,
        hover_bg=_INK,
    )
    btn.setMinimumWidth(92)
    return btn


class _AppDialog(QDialog):
    def __init__(self, parent: QWidget | None, title: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft)
        self.setModal(True)
        self.setMinimumWidth(440)
        self.setStyleSheet(f"""
            QDialog {{
                background: {_PAGE};
                color: {_TEXT};
            }}
            QLabel {{
                background: transparent;
                color: {_TEXT};
            }}
            QLineEdit {{
                background: white;
                color: {_TEXT};
                border: 1px solid {_BORDER};
                border-radius: 12px;
                padding: 7px 12px;
                font-size: {FONT_BODY}px;
                selection-background-color: {_INK};
                selection-color: white;
            }}
        """)


class _MessageDialog(_AppDialog):
    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        text: str,
        kind: str,
        buttons: list[tuple[str, QMessageBox.StandardButton, str]],
    ) -> None:
        super().__init__(parent, title)
        self._choice = QMessageBox.StandardButton.NoButton

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(18)

        body = QHBoxLayout()
        body.setSpacing(18)

        icon = QLabel({"info": "i", "warning": "!", "critical": "!", "question": "?"}.get(kind, "i"))
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_color = {
            "info": _BLUE,
            "warning": "#f59e0b",
            "critical": _RED,
            "question": _BLUE,
        }.get(kind, _BLUE)
        icon.setFixedSize(58, 58)
        icon.setStyleSheet(f"""
            QLabel {{
                background: {icon_color};
                color: white;
                border-radius: 29px;
                font-size: 30px;
                font-weight: 900;
            }}
        """)

        text_col = QVBoxLayout()
        title_lbl = QLabel(title)
        f = QFont()
        f.setPointSize(14)
        f.setBold(True)
        title_lbl.setFont(f)
        title_lbl.setStyleSheet(f"color: {_TEXT};")

        msg = QLabel(text)
        msg.setWordWrap(True)
        msg.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        msg.setStyleSheet(f"color: {_TEXT}; font-size: {FONT_BODY}px; line-height: 1.4;")
        msg.setMinimumWidth(260)

        text_col.addWidget(title_lbl)
        text_col.addWidget(msg)
        body.addLayout(text_col, 1)
        body.addWidget(icon)
        root.addLayout(body)

        row = QHBoxLayout()
        row.addStretch()
        for label, value, role in buttons:
            btn = _button(label, primary=(role == "primary"), danger=(role == "danger"))
            btn.clicked.connect(lambda _checked=False, v=value: self._finish(v))
            row.addWidget(btn)
        root.addLayout(row)

    def _finish(self, value: QMessageBox.StandardButton) -> None:
        self._choice = value
        self.accept()

    @property
    def choice(self) -> QMessageBox.StandardButton:
        return self._choice


class _TextInputDialog(_AppDialog):
    def __init__(
        self,
        parent: QWidget | None,
        title: str,
        label: str,
        mode: QLineEdit.EchoMode,
        text: str,
    ) -> None:
        super().__init__(parent, title)
        self.setMinimumWidth(460)
        self._ok = False

        root = QVBoxLayout(self)
        root.setContentsMargins(24, 22, 24, 18)
        root.setSpacing(14)

        heading = QLabel(title)
        f = QFont()
        f.setPointSize(14)
        f.setBold(True)
        heading.setFont(f)
        heading.setStyleSheet(f"color: {_INK};")
        root.addWidget(heading)

        prompt = QLabel(label)
        prompt.setWordWrap(True)
        prompt.setStyleSheet(f"color: {_TEXT}; font-size: {FONT_BODY}px;")
        root.addWidget(prompt)

        self._line = QLineEdit()
        self._line.setEchoMode(mode)
        self._line.setText(text)
        self._line.selectAll()
        self._line.returnPressed.connect(self._accept)
        root.addWidget(self._line)

        row = QHBoxLayout()
        cancel = _button("إلغاء")
        ok = _button("موافق", primary=True)
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._accept)
        row.addWidget(cancel)
        row.addWidget(ok)
        root.addLayout(row)

    def _accept(self) -> None:
        self._ok = True
        self.accept()

    @property
    def result_text(self) -> str:
        return self._line.text()


def _button_specs(
    buttons: QMessageBox.StandardButton | QMessageBox.StandardButtons,
    kind: str,
) -> list[tuple[str, QMessageBox.StandardButton, str]]:
    specs: list[tuple[str, QMessageBox.StandardButton, str]] = []
    if buttons & QMessageBox.StandardButton.Yes:
        specs.append(("نعم", QMessageBox.StandardButton.Yes, "danger" if kind == "question" else "primary"))
    if buttons & QMessageBox.StandardButton.No:
        specs.append(("لا", QMessageBox.StandardButton.No, "secondary"))
    if buttons & QMessageBox.StandardButton.Cancel:
        specs.append(("إلغاء", QMessageBox.StandardButton.Cancel, "secondary"))
    if buttons & QMessageBox.StandardButton.Ok:
        specs.append(("حسناً", QMessageBox.StandardButton.Ok, "primary"))
    return specs or [("حسناً", QMessageBox.StandardButton.Ok, "primary")]


def _message(
    parent: QWidget | None,
    title: str,
    text: str,
    kind: str,
    buttons: QMessageBox.StandardButton | QMessageBox.StandardButtons,
) -> QMessageBox.StandardButton:
    dlg = _MessageDialog(parent, title, text, kind, _button_specs(buttons, kind))
    dlg.exec()
    return dlg.choice


def ask_choice(
    parent: QWidget | None,
    title: str,
    text: str,
    options: list[tuple[str, str]],
) -> str | None:
    """App-native question dialog with custom button labels — e.g. "PDF" /
    "Word" — for choices QMessageBox's fixed Yes/No/Ok wording can't
    express. Pass the cancel option last; returns its value's counterpart
    (or None) when cancelled, otherwise the chosen option's value.

    A raw QMessageBox has produced invisible buttons in this app before
    (see the module docstring) — this reuses the same proven dialog chrome
    as every other popup instead of building a new unstyled QMessageBox."""
    cancel_value = options[-1][1]
    specs = [
        (label, value, "secondary" if value == cancel_value else "primary")
        for label, value in options
    ]
    dlg = _MessageDialog(parent, title, text, "question", specs)
    dlg.exec()
    choice = dlg.choice
    return choice if isinstance(choice, str) and choice != cancel_value else None


def install_dialog_overrides() -> None:
    """Patch Qt static dialogs so existing screens use the app-native dialogs."""

    def information(parent, title, text, buttons=QMessageBox.StandardButton.Ok, defaultButton=QMessageBox.StandardButton.NoButton):
        return _message(parent, title, text, "info", buttons)

    def warning(parent, title, text, buttons=QMessageBox.StandardButton.Ok, defaultButton=QMessageBox.StandardButton.NoButton):
        return _message(parent, title, text, "warning", buttons)

    def critical(parent, title, text, buttons=QMessageBox.StandardButton.Ok, defaultButton=QMessageBox.StandardButton.NoButton):
        return _message(parent, title, text, "critical", buttons)

    def question(parent, title, text, buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, defaultButton=QMessageBox.StandardButton.No):
        return _message(parent, title, text, "question", buttons)

    def get_text(parent, title, label, mode=QLineEdit.EchoMode.Normal, text="", flags=Qt.WindowType.Widget, inputMethodHints=Qt.InputMethodHint.ImhNone):
        dlg = _TextInputDialog(parent, title, label, mode, text)
        ok = dlg.exec() == QDialog.DialogCode.Accepted and dlg._ok
        return dlg.result_text, ok

    def get_save_file_name(parent=None, caption="", dir="", filter="", selectedFilter="", options=QFileDialog.Option(0)):
        options = options | QFileDialog.Option.DontConfirmOverwrite
        path, selected = _ORIGINAL_GET_SAVE_FILE_NAME(parent, caption, dir, filter, selectedFilter, options)
        if path and Path(path).exists():
            reply = _message(
                parent,
                "تأكيد الاستبدال",
                f"الملف موجود مسبقاً:\n{Path(path).name}\n\nهل تريد استبداله؟",
                "question",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return "", selected
        return path, selected

    def get_open_file_name(parent=None, caption="", dir="", filter="", selectedFilter="", options=QFileDialog.Option(0)):
        return _ORIGINAL_GET_OPEN_FILE_NAME(parent, caption, dir, filter, selectedFilter, options)

    QMessageBox.information = staticmethod(information)  # type: ignore[method-assign]
    QMessageBox.warning = staticmethod(warning)  # type: ignore[method-assign]
    QMessageBox.critical = staticmethod(critical)  # type: ignore[method-assign]
    QMessageBox.question = staticmethod(question)  # type: ignore[method-assign]
    QInputDialog.getText = staticmethod(get_text)  # type: ignore[method-assign]
    QFileDialog.getSaveFileName = staticmethod(get_save_file_name)  # type: ignore[method-assign]
    QFileDialog.getOpenFileName = staticmethod(get_open_file_name)  # type: ignore[method-assign]
