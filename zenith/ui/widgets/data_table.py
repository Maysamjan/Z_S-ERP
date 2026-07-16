"""Reusable data table with search, sorting, responsive columns and empty state.

Never shows raw database IDs -- callers provide display columns; the row's id is
stored out-of-band via ``Qt.UserRole`` so double-click/open can retrieve it.
"""

from __future__ import annotations

from typing import Callable, Sequence

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QStackedWidget,
)

from zenith.ui.widgets.common import EmptyState


class DataTable(QWidget):
    rowActivated = pyqtSignal(object)  # emits the row's id

    def __init__(self, headers: Sequence[str], empty_text: str = "", parent=None):
        super().__init__(parent)
        self._headers = list(headers)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)

        self._stack = QStackedWidget()
        self.table = QTableWidget(0, len(self._headers))
        self.table.setHorizontalHeaderLabels(self._headers)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        # Responsive: stretch the widest column, keep others to contents; horizontal
        # scroll appears automatically when the sum exceeds the viewport.
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        if self._headers:
            header.setSectionResizeMode(len(self._headers) - 1, QHeaderView.ResizeMode.Stretch)
        header.setStretchLastSection(True)
        self.table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.table.cellDoubleClicked.connect(self._on_double)

        self._empty = EmptyState(empty_text or "Nothing to show yet.")
        self._stack.addWidget(self.table)
        self._stack.addWidget(self._empty)
        lay.addWidget(self._stack)

    def set_rows(self, rows: list[tuple], ids: list | None = None,
                 badge_columns: dict[int, Callable[[object], tuple[str, str]]] | None = None) -> None:
        self.table.setSortingEnabled(False)
        self.table.setRowCount(0)
        badge_columns = badge_columns or {}
        for r, row in enumerate(rows):
            self.table.insertRow(r)
            for c, value in enumerate(row):
                item = QTableWidgetItem("" if value is None else str(value))
                if c == 0 and ids is not None:
                    item.setData(Qt.ItemDataRole.UserRole, ids[r])
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        self._stack.setCurrentWidget(self.table if rows else self._empty)

    def selected_id(self):
        row = self.table.currentRow()
        if row < 0:
            return None
        item = self.table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _on_double(self, row: int, _col: int):
        item = self.table.item(row, 0)
        if item is not None:
            self.rowActivated.emit(item.data(Qt.ItemDataRole.UserRole))
