# UI Design System

A centralized, token-driven system. Screens never hard-code colors or write
ad-hoc QSS.

## Tokens (`zenith/ui/theme/tokens.py`)

Semantic colors (primary/secondary/success/warning/danger/info), surfaces
(bg/surface/sidebar/border), text (primary/secondary/disabled/on-primary), and
geometry (radius, spacing, input/button/table-row heights, sidebar width) and
typography sizes. Two token sets: `LIGHT` and `DARK`.

## Stylesheet (`zenith/ui/theme/stylesheet.py`)

`build_stylesheet(tokens)` generates one application-wide QSS from the tokens.
Component looks are expressed via object names (`#Sidebar`, `#Card`, `#TopBar`)
and dynamic properties (`variant="primary|danger|ghost"`, `badge="success|..."`,
`role="h1|h2|muted|metric"`). Change a token → the whole app updates.

## Reusable widgets (`zenith/ui/widgets/`)

`PageHeader`, `Card`, `MetricCard`, `StatusBadge`, `EmptyState`, `FormSection`,
`SearchInput`, `Toast`, `PrimaryButton`/`SecondaryButton`/`DangerButton`/
`GhostButton`, and `DataTable` (search, sort, selection, double-click-to-open,
empty state, responsive columns, horizontal scroll, never shows raw DB ids).

## Responsive rules

- Only Qt layouts + size policies — **no absolute positioning**.
- Long content lives in a `QScrollArea` (`BasePage`), so pages fit 1024×768.
- The shell auto-collapses the sidebar below 1100px; the dashboard reflows its
  card grid by width; tables scroll horizontally when needed.
- Verified across 1024×768 → 1920×1080 in `tests/test_gui.py`.

## Bilingual

`zenith/ui/i18n.py` + JSON catalogs (`en_US`, `fa_AF`). Every visible string is a
key. Persian/Dari switches the whole app to RTL. Catalogs are asserted key-for-key
complete and non-empty in tests.
