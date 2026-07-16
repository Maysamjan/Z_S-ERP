"""Button variants. Style comes from the ``variant`` dynamic property + QSS."""

from __future__ import annotations

from PyQt6.QtWidgets import QPushButton


class _VariantButton(QPushButton):
    variant = "secondary"

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setProperty("variant", self.variant)
        self.setCursor(self.cursor())


class PrimaryButton(_VariantButton):
    variant = "primary"


class SecondaryButton(_VariantButton):
    variant = "secondary"


class DangerButton(_VariantButton):
    variant = "danger"


class GhostButton(_VariantButton):
    variant = "ghost"
