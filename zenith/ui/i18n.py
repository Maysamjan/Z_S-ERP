"""Localization.

Every visible string comes from a translation catalog keyed by a stable id. Two
locales ship: ``en_US`` (LTR) and ``fa_AF`` (Persian/Dari, RTL). ``tr(key)`` looks
up the active locale and falls back to English, then to the key itself, so a
missing translation is visible in tests rather than crashing.
"""

from __future__ import annotations

import json
from pathlib import Path

from zenith.core import paths

RTL_LOCALES = {"fa_AF", "fa_IR", "ps_AF", "ar"}
DEFAULT_LOCALE = "en_US"
SUPPORTED_LOCALES = ["en_US", "fa_AF"]


class Translator:
    def __init__(self, locale: str = DEFAULT_LOCALE):
        self._catalogs: dict[str, dict[str, str]] = {}
        self._locale = DEFAULT_LOCALE
        self.set_locale(locale)

    def _load(self, locale: str) -> dict[str, str]:
        if locale in self._catalogs:
            return self._catalogs[locale]
        path = paths.resource_dir() / "translations" / f"{locale}.json"
        data: dict[str, str] = {}
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
        self._catalogs[locale] = data
        return data

    def set_locale(self, locale: str) -> None:
        if locale not in SUPPORTED_LOCALES:
            locale = DEFAULT_LOCALE
        self._locale = locale
        self._load(locale)
        self._load(DEFAULT_LOCALE)

    @property
    def locale(self) -> str:
        return self._locale

    @property
    def is_rtl(self) -> bool:
        return self._locale in RTL_LOCALES

    def tr(self, key: str, **params) -> str:
        text = self._load(self._locale).get(key)
        if text is None:
            text = self._load(DEFAULT_LOCALE).get(key, key)
        if params:
            try:
                text = text.format(**params)
            except (KeyError, IndexError, ValueError):
                pass
        return text


_translator = Translator()


def get_translator() -> Translator:
    return _translator


def set_locale(locale: str) -> None:
    _translator.set_locale(locale)


def tr(key: str, **params) -> str:
    return _translator.tr(key, **params)


def is_rtl() -> bool:
    return _translator.is_rtl
