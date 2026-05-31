# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: builds BOTH standalone Windows apps in one pass:
#   dist/PoGoGameMasterDecoder.exe  - decode GAME_MASTER -> JSON
#   dist/PoGoPokedexViewer.exe      - browse decoded data (stats/moves/etc.)
# Build with:  pyinstaller pogodecode.spec

block_cipher = None


def _build(entry, name):
    a = Analysis(
        [entry],
        pathex=[],
        binaries=[],
        datas=[],
        hiddenimports=[],
        hookspath=[],
        runtime_hooks=[],
        excludes=[],
        cipher=block_cipher,
        noarchive=False,
    )
    pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
    exe = EXE(
        pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
        name=name,
        debug=False,
        bootloader_ignore_signals=False,
        strip=False,
        upx=True,
        upx_exclude=[],
        runtime_tmpdir=None,
        console=False,
        disable_windowed_traceback=False,
        target_arch=None,
        codesign_identity=None,
        entitlements_file=None,
    )
    return exe


decoder = _build('run_gui.py', 'PoGoGameMasterDecoder')
viewer = _build('run_viewer.py', 'PoGoPokedexViewer')
