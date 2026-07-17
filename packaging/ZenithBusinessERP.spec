# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller one-folder spec for Zenith Business ERP.

Bundles UI resources (translations, QSS, logos) so the packaged app is fully
offline and self-contained. Run:  pyinstaller packaging/ZenithBusinessERP.spec
"""

import os
from PyInstaller.utils.hooks import collect_data_files

block_cipher = None

datas = collect_data_files("zenith", includes=[
    "ui/resources/translations/*.json",
    "ui/resources/qss/*.qss",
    "ui/resources/logos/*.svg",
    "ui/resources/icons/*.svg",
])

a = Analysis(
    ["..\\run.py"] if os.name == "nt" else ["../run.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=["argon2", "cryptography", "sqlalchemy"],
    hookspath=[],
    runtime_hooks=[],
    # Never ship the private-key signing code to customers.
    excludes=["tkinter", "pytest", "vendor_tools", "zenith.vendor", "zenith.licensing.signing"],
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="ZenithBusinessERP",
    debug=False,
    strip=False,
    upx=False,
    console=False,
    icon=os.path.join("packaging", "app.ico") if os.path.exists(os.path.join("packaging", "app.ico")) else None,
    version=os.path.join("packaging", "version_info.txt") if os.name == "nt" else None,
)
coll = COLLECT(
    exe, a.binaries, a.zipfiles, a.datas,
    strip=False, upx=False, name="ZenithBusinessERP",
)
