# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for AvatarProductionByMIB (windowed Windows exe)."""
from pathlib import Path

ROOT = Path.cwd()

a = Analysis(
    # NOTE: entry is the root-level shim (absolute imports). Do NOT point this
    # at mib/app.py directly — frozen __main__ has no parent package and the
    # relative imports inside mib/ would crash the exe on startup.
    [str(ROOT / "run_app.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[
        # Bundle defaults only — NEVER secrets.yaml (user keys stay on disk).
        (str(ROOT / "config" / "config.yaml"), "config"),
        (str(ROOT / "config" / "secrets.yaml.example"), "config"),
        (str(ROOT / "assets"), "assets"),
    ],
    hiddenimports=[
        "imageio_ffmpeg",
        "edge_tts",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="AvatarProductionByMIB",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # windowed: no console window
    disable_windowed_traceback=False,
)
