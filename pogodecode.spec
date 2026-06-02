# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: builds BOTH standalone apps in one pass.
#   PoGoGameMasterDecoder  - decode GAME_MASTER -> JSON
#   PoGoPokedexViewer      - browse decoded data (stats/moves/types/etc.)
# Build with:  pyinstaller pogodecode.spec
#
# Cross-platform: produces .exe on Windows, a binary on macOS/Linux. The icon
# and Windows version resource are applied when present / on Windows.

import os
import sys

block_cipher = None

# Icon (.ico) and the Windows version resource only apply on Windows.
_ICON = os.path.join("assets", "icon.ico")
icon = _ICON if (sys.platform == "win32" and os.path.exists(_ICON)) else None
version = "version_info.txt" if (sys.platform == "win32"
                                 and os.path.exists("version_info.txt")) else None


def _build(entry, name):
    a = Analysis(
        [entry],
        pathex=[],
        binaries=[],
        # Bundle the embedded UI fonts (SIL OFL) so the app can register them.
        datas=[("pogodecode/assets/fonts", "pogodecode/assets/fonts")],
        hiddenimports=[],
        hookspath=[],
        runtime_hooks=[],
        excludes=[],
        cipher=block_cipher,
        noarchive=False,
    )
    pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
    return EXE(
        pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
        name=name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,          # GUI apps: no console window
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
        icon=icon,
        version=version,
    )


decoder = _build('run_gui.py', 'PoGoGameMasterDecoder')
viewer = _build('run_viewer.py', 'PoGoPokedexViewer')
