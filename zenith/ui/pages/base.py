"""Base page scaffold: header + scrollable content in a consistent frame."""

from __future__ import annotations

from PyQt6.QtWidgets import QWidget, QVBoxLayout, QScrollArea

from zenith.ui.context import AppContext
from zenith.ui.widgets.common import PageHeader


class BasePage(QWidget):
    #: translation keys, overridden by subclasses
    title_key = "app.name"
    subtitle_key = ""

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setObjectName("Root")
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 20, 24, 20)
        root.setSpacing(14)

        self.header = PageHeader(ctx.tr(self.title_key), ctx.tr(self.subtitle_key) if self.subtitle_key else "")
        root.addWidget(self.header)

        # Long content scrolls so pages fit small screens (1024x768 and up).
        self._scroll = QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._content = QWidget()
        self._content.setObjectName("Root")
        self.content = QVBoxLayout(self._content)
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(12)
        self._scroll.setWidget(self._content)
        root.addWidget(self._scroll, 1)

    def tr(self, key: str, **p) -> str:
        return self.ctx.tr(key, **p)

    def refresh(self) -> None:
        """Called when the page becomes visible. Override to (re)load data."""
