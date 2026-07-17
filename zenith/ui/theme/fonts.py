"""Font helpers and a filter for the benign ``setPointSize <= 0`` Qt warning.

The design system sizes text via QSS ``font-size`` in pixels. A pixel-sized QFont
reports ``pointSize() == -1``; some Qt internals then re-apply that value with
``setPointSize`` and print:

    QFont::setPointSize: Point size <= 0 (-1), must be greater than 0

We do not call ``setPointSize`` ourselves. To keep behaviour correct and the log
clean we (1) install a valid application base font with a positive point size, and
(2) install a message filter that drops only that one benign warning and passes
every other Qt message through. A ``safe_point_size`` guard is provided for any
future code that does set point sizes.
"""

from __future__ import annotations

import logging

from PyQt6.QtCore import QtMsgType, qInstallMessageHandler
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QApplication

log = logging.getLogger("zenith.ui")

DEFAULT_POINT_SIZE = 10
_BENIGN_POINTSIZE = "setPointSize: Point size <= 0"
_installed = False


def safe_point_size(size, fallback: int = DEFAULT_POINT_SIZE) -> int:
    """Return a strictly-positive point size, never <= 0."""
    try:
        value = int(size)
    except (TypeError, ValueError):
        return fallback
    return value if value > 0 else fallback


def apply_base_font(app: QApplication | None = None, point_size: int = DEFAULT_POINT_SIZE) -> None:
    """Give the application a base font with a valid positive point size."""
    app = app or QApplication.instance()
    if app is None:
        return
    font = app.font()
    font.setPointSize(safe_point_size(point_size))
    app.setFont(font)


def _message_filter(msg_type, context, message):
    if message and _BENIGN_POINTSIZE in message:
        # Known-benign (pixel-sized QSS fonts). Log once at debug, then swallow.
        log.debug("Suppressed benign Qt font warning: %s", message)
        return
    # Re-emit everything else so real warnings/errors still surface on stderr.
    import sys
    stream = sys.stderr
    prefix = {
        QtMsgType.QtDebugMsg: "Qt Debug",
        QtMsgType.QtInfoMsg: "Qt Info",
        QtMsgType.QtWarningMsg: "Qt Warning",
        QtMsgType.QtCriticalMsg: "Qt Critical",
        QtMsgType.QtFatalMsg: "Qt Fatal",
    }.get(msg_type, "Qt")
    try:
        stream.write(f"{prefix}: {message}\n")
    except Exception:
        pass


def install_font_warning_filter() -> None:
    """Install the Qt message filter once."""
    global _installed
    if _installed:
        return
    qInstallMessageHandler(_message_filter)
    _installed = True
