# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import PureWindowsPath

a = Analysis(
    ['src/main.py'],
    pathex=[SPECPATH],
    binaries=[],
    datas=[
        ('templets', 'templets'),
        ('assets/fonts', 'assets/fonts'),
        ('assets/icons', 'assets/icons'),
        ('assets/app_icon.png', 'assets'),
        ('assets/holidays_2026_2027.webp', 'assets'),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
if sys.platform == 'win32':
    # Qt uses Windows' ICU API. Other tools on PATH may supply incompatible
    # DLLs with these same names, which break QtGui in the frozen application.
    system_icu = {'icu.dll', 'icuuc.dll', 'icuin.dll'}
    a.binaries = [entry for entry in a.binaries
                  if PureWindowsPath(entry[0]).name.lower() not in system_icu]
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    exclude_binaries=False,
    name='TadbirInternat',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    icon='assets/app_icon.ico',
    version='assets/version_info.txt',
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
