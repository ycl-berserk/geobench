# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe for the Windows studio.

**One folder, not one file.**  A one-file build unpacks itself on every
launch (slow, and antivirus software dislikes it); a folder starts like a
normal program.  The zip is the distribution.

What is inside:

- the application and its Python runtime;
- PySide6 (QtWidgets / QtGui / QtSvg) and SymPy;
- ``prompts/`` -- the AI skill reads these at runtime, so they are data;
- ``icon.png`` -- the window icon (the .exe carries the .ico).

What is **not** inside: samples and the teacher's guide.  The packaging
script copies them next to the executable, where a person can find them
without opening ``_internal``.
"""

from pathlib import Path

ROOT = Path(SPECPATH).resolve().parent

analysis = Analysis(
    [str(ROOT / "src" / "geobench" / "app" / "main.py")],
    pathex=[str(ROOT / "src")],
    binaries=[],
    datas=[
        (str(ROOT / "prompts"), "prompts"),
        (str(ROOT / "packaging" / "icon.png"), "."),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "pytest", "IPython", "matplotlib", "PIL"],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(analysis.pure)

exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="geobench",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(ROOT / "packaging" / "geobench.ico"),
)

collect = COLLECT(
    exe,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=False,
    name="geobench",
)
