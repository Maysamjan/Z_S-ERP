"""Dashboard page: profile-driven KPI cards backed by real aggregate queries.

Cards wrap responsively in a flow grid so the dashboard reorganizes from
multi-column (wide) to fewer columns (narrow) without clipping.
"""

from __future__ import annotations

from decimal import Decimal

from PyQt6.QtWidgets import QWidget, QGridLayout

from zenith.db.base import session_scope
from zenith.services import reporting
from zenith.ui.pages.base import BasePage
from zenith.ui.widgets.common import MetricCard


class DashboardPage(BasePage):
    title_key = "dashboard.title"
    subtitle_key = "dashboard.subtitle"

    def __init__(self, ctx, parent=None):
        super().__init__(ctx, parent)
        self._grid_host = QWidget()
        self._grid = QGridLayout(self._grid_host)
        self._grid.setSpacing(14)
        self.content.addWidget(self._grid_host)
        self.content.addStretch(1)
        self._cards: dict[str, MetricCard] = {}
        self._build_cards()
        self.refresh()

    def _columns(self) -> int:
        w = self.width() or 1200
        if w >= 1400:
            return 4
        if w >= 1000:
            return 3
        if w >= 640:
            return 2
        return 1

    def _build_cards(self) -> None:
        cards = self.ctx.profile.dashboard_cards
        cols = self._columns()
        for i, key in enumerate(cards):
            card = MetricCard(self.ctx.tr(f"card.{key}"))
            self._cards[key] = card
            self._grid.addWidget(card, i // cols, i % cols)

    def _relayout(self) -> None:
        cols = self._columns()
        for i, (key, card) in enumerate(self._cards.items()):
            self._grid.removeWidget(card)
            self._grid.addWidget(card, i // cols, i % cols)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._relayout()

    def _fmt(self, raw: str, kind: str) -> str:
        if kind == "money":
            try:
                val = Decimal(raw)
                return f"{val:,.2f} {self.ctx and ''}".strip()
            except Exception:
                return raw
        return raw

    def refresh(self) -> None:
        with session_scope(self.ctx.db) as session:
            for key, card in self._cards.items():
                raw, kind = reporting.card_value(session, key)
                card.set_value(self._fmt(raw, kind))
