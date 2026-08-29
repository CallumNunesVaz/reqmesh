# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for the reqmesh desktop backend.
#
# Builds a single-file executable that the Electron shell spawns in place of
# ``python -m uvicorn app.main:app``. uvicorn and pydantic both load modules via
# importlib at runtime, so those modules must be declared as hidden imports or
# the binary builds and then dies at startup with an ImportError. `app` is
# collected wholesale because its submodules are imported lazily all over the
# codebase and PyInstaller's static analysis only follows import-time edges.

import os

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None

SPECPATH = os.path.dirname(os.path.abspath(SPEC))
BACKEND_DIR = SPECPATH  # the spec lives at backend/pyinstaller.spec

# Every dynamic import the frozen binary can reach at runtime. The lists are
# generous on purpose: an over-collected module only costs build time, an
# under-collected one fails the boot the desktop CI job exists to catch.
hiddenimports = (
    collect_submodules("app")
    + collect_submodules("uvicorn")
    + collect_submodules("pydantic")
    + collect_submodules("pydantic_settings")
    + collect_submodules("fastapi")
)

a = Analysis(
    [os.path.join(BACKEND_DIR, "desktop_server.py")],
    pathex=[BACKEND_DIR],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="reqmesh-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
