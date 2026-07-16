# Build & Release Guide

> Status: the build scripts and CI are provided; a verified Windows installer has
> **not** yet been produced (see `KNOWN_LIMITATIONS.md`). Do not claim the
> installer works until CI produces the artifacts on a Windows runner.

## Prerequisites (Windows)

- Python 3.11+
- `pip install -r requirements-dev.txt`
- Inno Setup 6 (for the installer)

## 1. Run checks

```bat
python -m compileall zenith
set QT_QPA_PLATFORM=offscreen
pytest -q
```

## 2. Build the one-folder app (PyInstaller)

```bat
pyinstaller packaging\ZenithBusinessERP.spec --noconfirm
```

Output: `dist\ZenithBusinessERP\ZenithBusinessERP.exe` plus bundled resources
(translations, QSS, logos). The spec bundles `zenith/ui/resources/**`.

## 3. Packaged smoke test

```bat
dist\ZenithBusinessERP\ZenithBusinessERP.exe --help
```

## 4. Build the installer (Inno Setup)

```bat
iscc packaging\installer.iss
```

Output: `dist\installer\ZenithBusinessERP-Test-Setup.exe`. Installs to
`Program Files`; customer data is stored under `%PROGRAMDATA%\ZenithBusinessERP`
so upgrades/uninstalls never delete it.

## 5. Deliverables (produced by CI)

- `Zenith-Business-ERP-Source.zip`
- `Zenith-Business-ERP-Windows-Test-Build.zip`
- `ZenithBusinessERP-Test-Setup.exe`

## Vendor artifacts (never shipped to customers)

- `ZenithLicenseManager` — build separately from `zenith.vendor.license_manager_cli`.
- The Ed25519 **private signing key** — stored only in the vendor environment.
