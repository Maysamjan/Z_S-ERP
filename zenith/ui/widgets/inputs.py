"""Numeric and formatted input widgets with sane minimum widths.

Manual testing showed spin buttons overlapping the value in narrow numeric fields.
These widgets enforce comfortable minimum widths, expanding size policies, visible
decimals and (for currency) a non-overlapping suffix -- and always work in Decimal.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt6.QtWidgets import QDoubleSpinBox, QSpinBox, QLineEdit, QSizePolicy

# Minimum widths from the spec (px).
QTY_MIN_WIDTH = 120
CURRENCY_MIN_WIDTH = 160


def _grow(widget) -> None:
    widget.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    widget.setMinimumHeight(34)


class QuantityInput(QDoubleSpinBox):
    """Quantity field: at least 120px wide, 3 decimals, no button overlap."""

    def __init__(self, parent=None, decimals: int = 3, maximum: float = 1_000_000_000):
        super().__init__(parent)
        self.setDecimals(decimals)
        self.setMaximum(maximum)
        self.setMinimum(0)
        self.setMinimumWidth(QTY_MIN_WIDTH)
        self.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.UpDownArrows)
        self.setAlignment(self._num_align())
        _grow(self)

    def _num_align(self):
        from PyQt6.QtCore import Qt
        return Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter

    def value_decimal(self) -> Decimal:
        return Decimal(str(self.value()))


class CurrencyInput(QDoubleSpinBox):
    """Currency field: at least 160px wide, 2 decimals, non-overlapping suffix."""

    def __init__(self, parent=None, currency: str = "", maximum: float = 1_000_000_000):
        super().__init__(parent)
        self.setDecimals(2)
        self.setMaximum(maximum)
        self.setMinimum(0)
        self.setMinimumWidth(CURRENCY_MIN_WIDTH)
        self.setGroupSeparatorShown(True)
        if currency:
            self.setSuffix(f"  {currency}")
        from PyQt6.QtCore import Qt
        self.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        _grow(self)

    def value_decimal(self) -> Decimal:
        return Decimal(str(self.value()))


class IntInput(QSpinBox):
    def __init__(self, parent=None, maximum: int = 1_000_000, minimum: int = 0):
        super().__init__(parent)
        self.setMaximum(maximum)
        self.setMinimum(minimum)
        self.setMinimumWidth(QTY_MIN_WIDTH)
        _grow(self)


class PhoneInput(QLineEdit):
    def __init__(self, parent=None, placeholder: str = ""):
        super().__init__(parent)
        self.setPlaceholderText(placeholder)
        self.setMinimumWidth(CURRENCY_MIN_WIDTH)
        _grow(self)
