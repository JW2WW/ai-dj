# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for AI DJ

from PyInstaller.utils.hooks import collect_submodules
import os

block_cipher = None

# Collect hidden imports that PyInstaller might miss
hidden_imports = [
    'edge_tts',
    'feedparser',
    'google.genai',
    'groq',
    'mutagen',
    'mutagen.id3',
    'pystray',
    'vlc',
    'PIL',
    'PIL.ImageTk',
]

a = Analysis(
    ['app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config.yaml', '.'),
        ('data', '_internal/data'),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludedimports=[],
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
    name='AI_DJ',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon.ico path here if you have one
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='AI_DJ',
)
