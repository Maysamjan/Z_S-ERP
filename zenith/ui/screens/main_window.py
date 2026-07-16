"""Main application shell: responsive sidebar + top bar + stacked pages.

The sidebar is built from the active profile's enabled modules intersected with
registered pages (no placeholders). It collapses to an icon rail at narrow widths.
Pages are lazily created and cached; the top bar shows the page title, breadcrumb,
current date, language/theme switchers and the user menu.
"""

from __future__ import annotations

from datetime import date

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout, QFrame, QLabel, QPushButton,
    QStackedWidget, QScrollArea, QComboBox, QSizePolicy,
)

from zenith import __version__
from zenith.profiles import modules as M
from zenith.profiles.features import F_INVENTORY_FIRST
from zenith.ui.context import AppContext
from zenith.ui.pages import registry
from zenith.ui.widgets.buttons import GhostButton

COLLAPSE_WIDTH = 1100

# sidebar group display order
GROUP_ORDER = [
    M.G_MAIN, M.G_SALES, M.G_PURCHASES, M.G_PRODUCTS, M.G_INVENTORY,
    M.G_PARTIES, M.G_FINANCE, M.G_REPORTS, M.G_ADMIN,
]


class MainWindow(QMainWindow):
    logoutRequested = pyqtSignal()
    languageChanged = pyqtSignal(str)

    def __init__(self, ctx: AppContext, parent=None):
        super().__init__(parent)
        self.ctx = ctx
        self.setWindowTitle(f"{ctx.tr('app.name')} — {ctx.business_name}")
        self.setMinimumSize(1024, 700)
        self._pages: dict[str, QWidget] = {}
        self._nav_buttons: dict[str, QPushButton] = {}
        self._collapsed = False

        central = QWidget(); central.setObjectName("Root")
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.sidebar = self._build_sidebar()
        root.addWidget(self.sidebar)

        right = QVBoxLayout()
        right.setContentsMargins(0, 0, 0, 0)
        right.setSpacing(0)
        self.topbar = self._build_topbar()
        right.addWidget(self.topbar)
        self.stack = QStackedWidget()
        right.addWidget(self.stack, 1)
        right_host = QWidget(); right_host.setLayout(right)
        root.addWidget(right_host, 1)
        self.setCentralWidget(central)

        self._populate_nav()
        # open the profile's first module by default
        first = self._ordered_modules()[0] if self._ordered_modules() else M.DASHBOARD
        self.navigate(first)

    # -- sidebar -----------------------------------------------------------
    def _build_sidebar(self) -> QFrame:
        frame = QFrame(); frame.setObjectName("Sidebar")
        frame.setFixedWidth(248)
        v = QVBoxLayout(frame)
        v.setContentsMargins(10, 16, 10, 12)
        v.setSpacing(2)

        brand = QLabel("◆ " + self.ctx.tr("app.name"))
        brand.setObjectName("SidebarBrand")
        v.addWidget(brand)
        prof = QLabel(self.ctx.tr(self.ctx.profile.name_key))
        prof.setObjectName("SidebarProfile")
        v.addWidget(prof)
        v.addSpacing(8)

        self._nav_scroll = QScrollArea()
        self._nav_scroll.setWidgetResizable(True)
        self._nav_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._nav_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._nav_host = QWidget()
        self._nav_layout = QVBoxLayout(self._nav_host)
        self._nav_layout.setContentsMargins(0, 0, 0, 0)
        self._nav_layout.setSpacing(2)
        self._nav_scroll.setWidget(self._nav_host)
        v.addWidget(self._nav_scroll, 1)

        # footer: user + logout
        self.user_label = QLabel("👤 " + (self.ctx.user.full_name or self.ctx.user.username if self.ctx.user else ""))
        self.user_label.setObjectName("SidebarProfile")
        v.addWidget(self.user_label)
        logout = QPushButton("⎋ " + self.ctx.tr("nav.logout"))
        logout.setObjectName("NavItem")
        logout.clicked.connect(self.logoutRequested.emit)
        v.addWidget(logout)
        return frame

    def _ordered_modules(self) -> list[str]:
        """Profile modules that have a registered page, in group order."""
        enabled = set(self.ctx.profile.enabled_modules)
        out: list[str] = []
        # group by catalog group, then emit in GROUP_ORDER
        by_group: dict[str, list[str]] = {}
        for key, mod in M.MODULE_CATALOG.items():
            if key in enabled and registry.has_page(key):
                by_group.setdefault(mod.group, []).append(key)
        for group in GROUP_ORDER:
            out.extend(by_group.get(group, []))
        return out

    def _populate_nav(self) -> None:
        enabled = set(self.ctx.profile.enabled_modules)
        by_group: dict[str, list[str]] = {}
        for key, mod in M.MODULE_CATALOG.items():
            if key in enabled and registry.has_page(key):
                by_group.setdefault(mod.group, []).append(key)
        for group in GROUP_ORDER:
            keys = by_group.get(group, [])
            if not keys:
                continue
            if group != M.G_MAIN:
                gl = QLabel(self.ctx.tr(group))
                gl.setObjectName("SidebarGroup")
                self._nav_layout.addWidget(gl)
            for key in keys:
                mod = M.MODULE_CATALOG[key]
                btn = QPushButton("  " + self.ctx.tr(mod.title_key))
                btn.setObjectName("NavItem")
                btn.setCheckable(True)
                btn.clicked.connect(lambda _c=False, k=key: self.navigate(k))
                self._nav_layout.addWidget(btn)
                self._nav_buttons[key] = btn
        self._nav_layout.addStretch(1)

    # -- top bar -----------------------------------------------------------
    def _build_topbar(self) -> QFrame:
        bar = QFrame(); bar.setObjectName("TopBar")
        bar.setFixedHeight(60)
        h = QHBoxLayout(bar)
        h.setContentsMargins(16, 8, 16, 8)

        self.toggle_btn = GhostButton("☰")
        self.toggle_btn.setFixedWidth(40)
        self.toggle_btn.clicked.connect(self.toggle_sidebar)
        h.addWidget(self.toggle_btn)

        col = QVBoxLayout(); col.setSpacing(0)
        self.page_title = QLabel(""); self.page_title.setObjectName("PageTitle")
        self.breadcrumb = QLabel(""); self.breadcrumb.setObjectName("Breadcrumb")
        col.addWidget(self.page_title); col.addWidget(self.breadcrumb)
        h.addLayout(col)
        h.addStretch(1)

        self.date_label = QLabel(date.today().isoformat())
        self.date_label.setProperty("role", "muted")
        h.addWidget(self.date_label)

        self.lang = QComboBox()
        self.lang.addItem("EN", "en_US"); self.lang.addItem("دری", "fa_AF")
        self.lang.setCurrentIndex(0 if self.ctx.locale == "en_US" else 1)
        self.lang.currentIndexChanged.connect(lambda _i: self._change_lang(self.lang.currentData()))
        h.addWidget(self.lang)

        self.theme_btn = GhostButton("🌙" if self.ctx.theme_name == "light" else "☀")
        self.theme_btn.setFixedWidth(40)
        self.theme_btn.clicked.connect(self._toggle_theme)
        h.addWidget(self.theme_btn)
        return bar

    def _change_lang(self, locale: str) -> None:
        if locale and locale != self.ctx.locale:
            self.languageChanged.emit(locale)

    def _toggle_theme(self) -> None:
        new = "dark" if self.ctx.theme_name == "light" else "light"
        self.ctx.set_theme(new)
        self.theme_btn.setText("🌙" if new == "light" else "☀")

    # -- navigation --------------------------------------------------------
    def navigate(self, module_key: str) -> None:
        if module_key not in self._pages:
            if not registry.has_page(module_key):
                return
            page = registry.build_page(module_key, self.ctx)
            self._pages[module_key] = page
            self.stack.addWidget(page)
        page = self._pages[module_key]
        self.stack.setCurrentWidget(page)
        if hasattr(page, "refresh"):
            page.refresh()
        for key, btn in self._nav_buttons.items():
            btn.setChecked(key == module_key)
        mod = M.MODULE_CATALOG.get(module_key)
        if mod:
            self.page_title.setText(self.ctx.tr(mod.title_key))
            self.breadcrumb.setText(f"{self.ctx.tr(mod.group)} › {self.ctx.tr(mod.title_key)}")

    # -- responsive --------------------------------------------------------
    def toggle_sidebar(self) -> None:
        self._collapsed = not self._collapsed
        self._apply_sidebar_state()

    def _apply_sidebar_state(self) -> None:
        self.sidebar.setVisible(not self._collapsed)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # auto-collapse on narrow widths
        auto = self.width() < COLLAPSE_WIDTH
        if auto != self._collapsed:
            self._collapsed = auto
            self._apply_sidebar_state()
