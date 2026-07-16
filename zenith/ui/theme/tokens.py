"""Design tokens.

The single source of truth for colors, spacing, radii and sizing. The QSS is
generated from these tokens, so a page never hard-codes a color -- change a token
here and the whole app updates consistently in both light and dark themes.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Tokens:
    name: str

    # brand / semantic colors
    primary: str
    primary_hover: str
    secondary: str
    success: str
    warning: str
    danger: str
    info: str

    # surfaces
    bg: str            # main background
    surface: str       # cards / panels
    surface_alt: str   # subtle alternate rows
    sidebar_bg: str
    sidebar_active: str
    border: str

    # text
    text: str
    text_secondary: str
    text_disabled: str
    on_primary: str    # text on primary color

    # geometry (px)
    radius: int = 10
    radius_sm: int = 6
    spacing: int = 12
    input_height: int = 38
    button_height: int = 38
    table_row_height: int = 40
    sidebar_width: int = 248
    sidebar_collapsed: int = 64

    # typography
    font_family: str = "'Segoe UI', 'Vazirmatn', 'Tahoma', sans-serif"
    font_size: int = 14
    font_size_sm: int = 12
    font_size_lg: int = 18
    font_size_xl: int = 24


LIGHT = Tokens(
    name="light",
    primary="#2563EB", primary_hover="#1D4ED8", secondary="#64748B",
    success="#16A34A", warning="#D97706", danger="#DC2626", info="#0891B2",
    bg="#F1F5F9", surface="#FFFFFF", surface_alt="#F8FAFC",
    sidebar_bg="#0F172A", sidebar_active="#1E293B", border="#E2E8F0",
    text="#0F172A", text_secondary="#475569", text_disabled="#94A3B8", on_primary="#FFFFFF",
)

DARK = Tokens(
    name="dark",
    primary="#3B82F6", primary_hover="#60A5FA", secondary="#94A3B8",
    success="#22C55E", warning="#F59E0B", danger="#EF4444", info="#06B6D4",
    bg="#0B1220", surface="#111827", surface_alt="#1A2334",
    sidebar_bg="#0A0F1A", sidebar_active="#1E293B", border="#26324A",
    text="#E5EDF7", text_secondary="#9FB0C7", text_disabled="#5B6B82", on_primary="#0B1220",
)


def get_tokens(name: str) -> Tokens:
    return DARK if name == "dark" else LIGHT
