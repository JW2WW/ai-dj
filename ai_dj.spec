# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for AI DJ.

Build:  pyinstaller ai_dj.spec
Output: dist/AI_DJ/AI_DJ.exe (~70 MB)

Minimal exclusions — only runtime data dirs.  Let PyInstaller auto-detect
everything else so we don't accidentally exclude a required dependency.
"""
import os
from pathlib import Path

import PyInstaller.utils.hooks

ASSETS_DIR = Path("assets")

# PyYAML has a _yaml C extension (.pyd) that must be explicitly bundled
yaml_datas, yaml_binaries, yaml_hidden = PyInstaller.utils.hooks.collect_all("yaml")

# pystray also has a C extension
pystray_datas, pystray_binaries, pystray_hidden = PyInstaller.utils.hooks.collect_all("pystray")

block_cipher = None

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=yaml_binaries + pystray_binaries,
    datas=[
        (str(ASSETS_DIR / "dj_images"), "assets/dj_images"),
        ("dj_manager_ui.py", "."), # Include dj_manager_ui.py explicitly
        ("playback_controller.py", "."), # Explicitly include playback_controller.py as a data file
    ] + yaml_datas + pystray_datas,
    hiddenimports=yaml_hidden + pystray_hidden + [
        "dj_manager_ui",     # Explicitly include DJ manager UI
        "playback_controller", # Explicitly include playback_controller
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "data",
        "tests",
    ],
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
    name="AI_DJ",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=True,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
    uac_admin=False,
    uac_uiaccess=False,
)

COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="AI_DJ",
)