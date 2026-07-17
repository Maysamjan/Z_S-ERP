"""Robust, responsive logo preview widget.

Fixes the PyQt6 crash caused by passing raw integers / obsolete enum aliases to
``QPixmap.scaled`` -- PyQt6 requires the typed ``Qt.AspectRatioMode`` /
``Qt.TransformationMode`` enums. This widget:

* handles an empty path, a missing file, an unreadable/invalid image, and a
  label whose size has not been computed yet;
* caps very large source images so a huge upload can't exhaust memory;
* preserves aspect ratio with smooth scaling;
* re-renders responsively on resize;
* never raises -- a bad image simply shows the placeholder.
"""

from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QImageReader, QPixmap
from PyQt6.QtWidgets import QLabel

# Formats we accept (Qt decodes by content; this guards the extension too).
_ALLOWED_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
# Cap the stored image so an enormous upload never holds a giant pixmap.
_MAX_SOURCE_EDGE = 1024


class LogoPreview(QLabel):
    def __init__(self, box: int = 96, placeholder: str = "—", parent=None):
        super().__init__(placeholder, parent)
        self._placeholder = placeholder
        self._source: QPixmap | None = None
        self._box = max(1, int(box))
        self.setFixedSize(self._box, self._box)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setScaledContents(False)

    # -- public API --------------------------------------------------------
    def set_logo(self, path: str | Path | None) -> bool:
        """Load and show a logo. Returns True if an image was rendered."""
        self._source = self._load(path)
        if self._source is None:
            self._show_placeholder()
            return False
        self._rescale()
        return True

    def clear_logo(self) -> None:
        self._source = None
        self._show_placeholder()

    # -- internals ---------------------------------------------------------
    def _show_placeholder(self) -> None:
        self.setPixmap(QPixmap())        # clear any prior image
        self.setText(self._placeholder)

    def _load(self, path: str | Path | None) -> QPixmap | None:
        if not path:
            return None
        p = Path(path)
        try:
            if not p.is_file():
                return None
            if p.suffix.lower() not in _ALLOWED_SUFFIXES:
                return None
            reader = QImageReader(str(p))
            reader.setAutoTransform(True)
            if not reader.canRead():
                return None
            # Bound the decoded size for very large images (keeps aspect ratio).
            size = reader.size()
            if size.isValid() and (size.width() > _MAX_SOURCE_EDGE or size.height() > _MAX_SOURCE_EDGE):
                bounded = size.scaled(_MAX_SOURCE_EDGE, _MAX_SOURCE_EDGE, Qt.AspectRatioMode.KeepAspectRatio)
                reader.setScaledSize(bounded)
            image = reader.read()
            if image.isNull():
                return None
            pix = QPixmap.fromImage(image)
            return None if pix.isNull() else pix
        except Exception:
            # Never let a bad image crash the page.
            return None

    def _target_size(self) -> QSize:
        rect = self.contentsRect()
        w, h = rect.width(), rect.height()
        # The label may not be laid out yet (0x0); fall back to the fixed box.
        if w <= 0 or h <= 0:
            return QSize(self._box, self._box)
        return QSize(w, h)

    def _rescale(self) -> None:
        if self._source is None or self._source.isNull():
            return
        scaled = self._source.scaled(
            self._target_size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setText("")
        self.setPixmap(scaled)

    def resizeEvent(self, event):  # responsive: re-render on size change
        super().resizeEvent(event)
        self._rescale()
