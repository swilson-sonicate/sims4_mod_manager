# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller spec file for Sims 4 Mod Manager

Build command:
    pyinstaller sims4_mod_manager.spec

This creates a single-file Windows executable.
"""

import sys
from pathlib import Path

block_cipher = None

# Get version from the main script
spec_dir = Path(SPECPATH)
version_info = {}
with open(spec_dir / 'sims4_mod_manager.py', 'r', encoding='utf-8') as f:
    for line in f:
        if line.startswith('__version__'):
            exec(line, version_info)
            break

version = version_info.get('__version__', '1.0.0')
version_parts = [int(x) for x in version.split('.')]
while len(version_parts) < 4:
    version_parts.append(0)
version_tuple = tuple(version_parts[:4])

# Generate Windows version info file BEFORE it's needed
version_info_path = None
if sys.platform == 'win32':
    version_info_path = spec_dir / 'version_info.txt'
    version_info_content = f'''# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version_tuple},
    prodvers={version_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo(
      [
      StringTable(
        u'040904B0',
        [StringStruct(u'CompanyName', u''),
        StringStruct(u'FileDescription', u'Sims 4 Mod Manager'),
        StringStruct(u'FileVersion', u'{version}'),
        StringStruct(u'InternalName', u'Sims4ModManager'),
        StringStruct(u'LegalCopyright', u''),
        StringStruct(u'OriginalFilename', u'Sims4ModManager.exe'),
        StringStruct(u'ProductName', u'Sims 4 Mod Manager'),
        StringStruct(u'ProductVersion', u'{version}')])
      ]),
    VarFileInfo([VarStruct(u'Translation', [1033, 1200])])
  ]
)
'''
    with open(version_info_path, 'w', encoding='utf-8') as f:
        f.write(version_info_content)

a = Analysis(
    ['sims4_mod_manager_tui.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'requests',
        'bs4',
        'beautifulsoup4',
        'textual',
        'textual.app',
        'textual.widgets',
        'textual.screen',
        'textual.containers',
        'textual.binding',
        'textual.message',
        'textual.css',
        'textual.css.query',
        'textual._context',
        'textual._path',
        'rich',
        'rich.text',
        'rich.table',
        'rich.panel',
        'rich.console',
        'rich.markup',
        'rich.highlighter',
    ],
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
    name='Sims4ModManager',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,  # Keep console for CLI app
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    version=str(version_info_path) if version_info_path else None,
    icon=None,  # Add icon path here if you have one, e.g., 'icon.ico'
)
