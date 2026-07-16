"""Generate a full Qt stylesheet from design tokens.

One stylesheet is applied application-wide, so all screens share the same visual
system. Component-specific looks are expressed with Qt object names / dynamic
properties (e.g. ``#Sidebar``, ``[variant="danger"]``) rather than per-screen QSS.
"""

from __future__ import annotations

from zenith.ui.theme.tokens import Tokens


def build_stylesheet(t: Tokens) -> str:
    return f"""
* {{
    font-family: {t.font_family};
    font-size: {t.font_size}px;
    color: {t.text};
}}
QWidget#Root, QMainWindow, QDialog {{ background: {t.bg}; }}

/* ---- Cards / surfaces ---- */
QFrame#Card, QFrame#Surface {{
    background: {t.surface};
    border: 1px solid {t.border};
    border-radius: {t.radius}px;
}}
QLabel[role="h1"] {{ font-size: {t.font_size_xl}px; font-weight: 700; }}
QLabel[role="h2"] {{ font-size: {t.font_size_lg}px; font-weight: 600; }}
QLabel[role="muted"] {{ color: {t.text_secondary}; }}
QLabel[role="metric"] {{ font-size: {t.font_size_xl}px; font-weight: 700; color: {t.primary}; }}

/* ---- Buttons ---- */
QPushButton {{
    background: {t.surface};
    border: 1px solid {t.border};
    border-radius: {t.radius_sm}px;
    padding: 8px 16px;
    min-height: {t.button_height - 16}px;
    color: {t.text};
}}
QPushButton:hover {{ border-color: {t.primary}; }}
QPushButton:disabled {{ color: {t.text_disabled}; }}
QPushButton[variant="primary"] {{
    background: {t.primary}; color: {t.on_primary}; border: none; font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{ background: {t.primary_hover}; }}
QPushButton[variant="primary"]:disabled {{ background: {t.text_disabled}; }}
QPushButton[variant="danger"] {{ background: {t.danger}; color: #FFFFFF; border: none; }}
QPushButton[variant="ghost"] {{ background: transparent; border: none; }}
QPushButton[variant="ghost"]:hover {{ background: {t.surface_alt}; }}

/* ---- Inputs ---- */
QLineEdit, QComboBox, QSpinBox, QDoubleSpinBox, QDateEdit, QPlainTextEdit, QTextEdit {{
    background: {t.surface};
    border: 1px solid {t.border};
    border-radius: {t.radius_sm}px;
    padding: 6px 10px;
    min-height: {t.input_height - 14}px;
    selection-background-color: {t.primary};
    selection-color: {t.on_primary};
}}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QDateEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {{
    border: 1px solid {t.primary};
}}
QLineEdit[invalid="true"] {{ border: 1px solid {t.danger}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}

/* ---- Tables ---- */
QTableView, QTableWidget {{
    background: {t.surface};
    border: 1px solid {t.border};
    border-radius: {t.radius}px;
    gridline-color: {t.border};
    selection-background-color: {t.primary};
    selection-color: {t.on_primary};
}}
QHeaderView::section {{
    background: {t.surface_alt};
    color: {t.text_secondary};
    padding: 8px;
    border: none;
    border-bottom: 1px solid {t.border};
    font-weight: 600;
}}
QTableView::item, QTableWidget::item {{ padding: 6px; }}

/* ---- Sidebar ---- */
QFrame#Sidebar {{ background: {t.sidebar_bg}; border: none; }}
QLabel#SidebarBrand {{ color: #FFFFFF; font-size: {t.font_size_lg}px; font-weight: 700; }}
QLabel#SidebarProfile {{ color: #93A4BF; font-size: {t.font_size_sm}px; }}
QLabel#SidebarGroup {{ color: #6B7A93; font-size: {t.font_size_sm}px; font-weight: 700; padding: 8px 14px 4px 14px; }}
QPushButton#NavItem {{
    background: transparent; border: none; text-align: left;
    padding: 9px 14px; color: #C7D2E1; border-radius: {t.radius_sm}px; font-weight: 500;
}}
QPushButton#NavItem:hover {{ background: {t.sidebar_active}; color: #FFFFFF; }}
QPushButton#NavItem:checked {{ background: {t.primary}; color: #FFFFFF; font-weight: 600; }}

/* ---- Top bar ---- */
QFrame#TopBar {{ background: {t.surface}; border: none; border-bottom: 1px solid {t.border}; }}
QLabel#PageTitle {{ font-size: {t.font_size_lg}px; font-weight: 700; }}
QLabel#Breadcrumb {{ color: {t.text_secondary}; font-size: {t.font_size_sm}px; }}

/* ---- Badges ---- */
QLabel[badge="success"] {{ background: {t.success}; color: #FFFFFF; border-radius: 8px; padding: 2px 10px; }}
QLabel[badge="warning"] {{ background: {t.warning}; color: #FFFFFF; border-radius: 8px; padding: 2px 10px; }}
QLabel[badge="danger"]  {{ background: {t.danger};  color: #FFFFFF; border-radius: 8px; padding: 2px 10px; }}
QLabel[badge="info"]    {{ background: {t.info};    color: #FFFFFF; border-radius: 8px; padding: 2px 10px; }}
QLabel[badge="muted"]   {{ background: {t.surface_alt}; color: {t.text_secondary}; border-radius: 8px; padding: 2px 10px; }}

/* ---- Scrollbars ---- */
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.border}; border-radius: 5px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: {t.secondary}; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t.border}; border-radius: 5px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}

/* ---- Login / branding ---- */
QFrame#BrandPanel {{ background: {t.sidebar_bg}; border: none; }}
QLabel#BrandTitle {{ color: #FFFFFF; font-size: {t.font_size_xl}px; font-weight: 800; }}
QLabel#BrandSubtitle {{ color: #93A4BF; }}
QFrame#LoginCard {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: {t.radius}px; }}
"""
