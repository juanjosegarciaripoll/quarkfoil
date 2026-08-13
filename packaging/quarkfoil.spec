# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path
import sys


ROOT = Path(SPECPATH).parent
APP = ROOT / "app"
ICON_NAMES = {"win32": "quarkfoil.ico", "darwin": "quarkfoil.icns", "linux": "quarkfoil.png"}
ICON = ROOT / "build" / "desktop-branding" / ICON_NAMES[sys.platform]
datas = [
    (str(APP), "scientific_slides/app"),
    (str(ROOT / "THIRD_PARTY_LICENSES.md"), "."),
    (str(ROOT / "LICENSE"), "."),
]
if sys.platform == "linux":
    datas.append((str(ICON), "."))
linux_tk_libraries = [Path(sys.base_prefix) / "lib" / name for name in ("libtcl9.0.so", "libtcl9tk9.0.so")]
binaries = [(str(path), ".") for path in linux_tk_libraries if sys.platform == "linux" and path.is_file()]

a = Analysis(
    [str(ROOT / "tools" / "quarkfoil_desktop.py")],
    pathex=[str(ROOT / "src")],
    binaries=binaries,
    datas=datas,
    hiddenimports=["tkinter", "tkinter.filedialog", "tkinter.messagebox"],
    excludes=["selenium", "mkdocs", "pytest"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe_options = dict(
    name="Quarkfoil",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=sys.platform == "darwin",
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
if sys.platform in {"win32", "darwin"}:
    exe_options["icon"] = str(ICON)
if sys.platform == "win32":
    exe_options["version"] = str(ROOT / "packaging" / "windows_version_info.txt")

exe = EXE(pyz, a.scripts, [], exclude_binaries=True, **exe_options)
collection = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Quarkfoil",
)

if sys.platform == "darwin":
    app = BUNDLE(
        collection,
        name="Quarkfoil.app",
        icon=str(ICON),
        bundle_identifier="io.github.juanjosegarciaripoll.quarkfoil",
        info_plist={
            "CFBundleDisplayName": "Quarkfoil",
            "CFBundleShortVersionString": "0.3.0",
            "CFBundleVersion": "0.3.0",
            "NSHighResolutionCapable": True,
            "CFBundleDocumentTypes": [{
                "CFBundleTypeName": "Markdown presentation",
                "CFBundleTypeRole": "Editor",
                "CFBundleTypeExtensions": ["md", "markdown"],
                "LSHandlerRank": "Alternate",
            }],
        },
    )
