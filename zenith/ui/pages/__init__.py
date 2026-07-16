"""Feature pages and the page registry.

Only modules with a real, data-wired page are registered here. The sidebar shows
the intersection of (profile's enabled modules) and (registered pages), so a
customer never sees a placeholder/"coming soon" screen. Modules not yet built are
tracked in docs/KNOWN_LIMITATIONS.md rather than shown as empty pages.
"""

from zenith.ui.pages.registry import PAGE_REGISTRY, build_page, has_page

__all__ = ["PAGE_REGISTRY", "build_page", "has_page"]
