"""Common reusable widgets: header, cards, badges, empty state, form sections."""

from __future__ import annotations

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QFrame, QLabel, QVBoxLayout, QHBoxLayout, QLineEdit, QWidget, QSizePolicy,
    QGridLayout, QGraphicsOpacityEffect,
)

from zenith.ui.widgets.buttons import PrimaryButton


class Card(QFrame):
    """A rounded surface panel."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(16, 16, 16, 16)
        self._layout.setSpacing(10)

    def body(self) -> QVBoxLayout:
        return self._layout


class PageHeader(QWidget):
    """Title + subtitle + optional primary action, top of every page."""

    def __init__(self, title: str, subtitle: str = "", action_text: str = "", parent=None):
        super().__init__(parent)
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        col = QVBoxLayout()
        col.setSpacing(2)
        self.title = QLabel(title)
        self.title.setProperty("role", "h1")
        col.addWidget(self.title)
        self.subtitle = QLabel(subtitle)
        self.subtitle.setProperty("role", "muted")
        self.subtitle.setVisible(bool(subtitle))
        col.addWidget(self.subtitle)
        row.addLayout(col)
        row.addStretch(1)
        self._row = row
        self.action = None
        if action_text:
            self.set_action(action_text)

    def set_action(self, text: str) -> PrimaryButton:
        """Create (or relabel) the header's primary action button."""
        if self.action is None:
            self.action = PrimaryButton(text)
            self._row.addWidget(self.action, 0, Qt.AlignmentFlag.AlignTop)
        else:
            self.action.setText(text)
        return self.action


class MetricCard(Card):
    """A dashboard KPI card: label + big value + optional caption."""

    def __init__(self, label: str, value: str = "—", caption: str = "", parent=None):
        super().__init__(parent)
        self.setMinimumWidth(180)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        lbl = QLabel(label)
        lbl.setProperty("role", "muted")
        self.value = QLabel(value)
        self.value.setProperty("role", "metric")
        self.body().addWidget(lbl)
        self.body().addWidget(self.value)
        if caption:
            cap = QLabel(caption)
            cap.setProperty("role", "muted")
            self.body().addWidget(cap)

    def set_value(self, value: str) -> None:
        self.value.setText(value)


class StatusBadge(QLabel):
    def __init__(self, text: str = "", kind: str = "muted", parent=None):
        super().__init__(text, parent)
        self.setProperty("badge", kind)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMaximumHeight(24)

    def set_status(self, text: str, kind: str) -> None:
        self.setText(text)
        self.setProperty("badge", kind)
        self.style().unpolish(self)
        self.style().polish(self)


class EmptyState(QWidget):
    def __init__(self, message: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon = QLabel("📭")
        icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon.setStyleSheet("font-size: 40px;")
        msg = QLabel(message)
        msg.setProperty("role", "muted")
        msg.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lay.addWidget(icon)
        lay.addWidget(msg)


class FormSection(QFrame):
    """A titled group of form rows (Basic Information, Pricing, …)."""

    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        head = QLabel(title)
        head.setProperty("role", "h2")
        outer.addWidget(head)
        self.grid = QGridLayout()
        self.grid.setColumnStretch(1, 1)
        self.grid.setColumnStretch(3, 1)
        self.grid.setHorizontalSpacing(14)
        self.grid.setVerticalSpacing(10)
        outer.addLayout(self.grid)
        self._row = 0

    def add_row(self, label: str, field: QWidget, *, required: bool = False, span: bool = False) -> QWidget:
        text = label + (" *" if required else "")
        lbl = QLabel(text)
        if span:
            self.grid.addWidget(lbl, self._row, 0)
            self.grid.addWidget(field, self._row, 1, 1, 3)
            self._row += 1
        else:
            # two field-pairs per row
            col = 0 if self.grid.itemAtPosition(self._row, 1) is None else 2
            self.grid.addWidget(lbl, self._row, col)
            self.grid.addWidget(field, self._row, col + 1)
            if col == 2:
                self._row += 1
        return field


class SearchInput(QLineEdit):
    def __init__(self, placeholder: str = "", parent=None):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setClearButtonEnabled(True)
        self.setMinimumWidth(200)


class Toast(QLabel):
    """A transient, auto-dismissing notification pinned to a parent widget."""

    def __init__(self, parent, text: str, kind: str = "success", msec: int = 2500):
        super().__init__(text, parent)
        self.setProperty("badge", kind)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.adjustSize()
        self.setMinimumHeight(32)
        self.move(max(12, (parent.width() - self.width()) // 2), 16)
        self.show()
        effect = QGraphicsOpacityEffect(self)
        self.setGraphicsEffect(effect)
        QTimer.singleShot(msec, self.deleteLater)

    @staticmethod
    def show_message(parent, text: str, kind: str = "success") -> "Toast":
        return Toast(parent, text, kind)
