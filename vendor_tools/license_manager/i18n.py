"""Minimal bilingual translator for the License Manager (en_US / fa_AF)."""

from __future__ import annotations

import json
from pathlib import Path

RTL_LOCALES = {"fa_AF", "fa_IR", "ps_AF"}
SUPPORTED = ["en_US", "fa_AF"]
DEFAULT = "en_US"


class Translator:
    def __init__(self, locale: str = DEFAULT):
        self._cat: dict[str, dict[str, str]] = {}
        self._locale = DEFAULT
        self.set_locale(locale)

    def _load(self, locale: str) -> dict[str, str]:
        if locale not in self._cat:
            path = Path(__file__).parent / "translations" / f"{locale}.json"
            self._cat[locale] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return self._cat[locale]

    def set_locale(self, locale: str) -> None:
        self._locale = locale if locale in SUPPORTED else DEFAULT
        self._load(self._locale); self._load(DEFAULT)

    @property
    def locale(self) -> str:
        return self._locale

    @property
    def is_rtl(self) -> bool:
        return self._locale in RTL_LOCALES

    def tr(self, key: str, **params) -> str:
        text = self._load(self._locale).get(key) or self._load(DEFAULT).get(key, key)
        if params:
            try:
                text = text.format(**params)
            except (KeyError, IndexError, ValueError):
                pass
        return text


_t = Translator()


def get_translator() -> Translator:
    return _t


def tr(key: str, **params) -> str:
    return _t.tr(key, **params)
