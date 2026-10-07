"""Builds Cellbox.exe (one file) with PyInstaller.

    python tools/build.py

Result: Cellbox.exe in the project folder, a portable single file with Python, Qt, numba and the sounds
inside. The build runs the exe's --self-check afterwards (which also compiles the engine into the
user's cache, so the first real launch is quick) and fails if the engine does not work.
"""

import io
import shutil
import struct
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

ICON = ROOT / "assets" / "cellbox.ico"
SPLASH = ROOT / "build" / "splash.png"
WORK = ROOT / "build"
ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)

# Parts of Qt that Cellbox never uses. Paths are as PyInstaller places them inside the bundle.
TRIM = (
    "PyQt6/Qt6/bin/opengl32sw.dll",                # software OpenGL; everything is raster-painted
    "PyQt6/Qt6/translations",                      # Qt's own UI translations; the app is English-only
    "PyQt6/Qt6/plugins/tls",                       # no networking
    "PyQt6/Qt6/plugins/imageformats/qpdf.dll",
    "PyQt6/Qt6/bin/Qt6Pdf.dll",
    "PyQt6/Qt6/bin/av*.dll",                       # FFmpeg: QSoundEffect decodes WAV itself
    "PyQt6/Qt6/bin/sw*.dll",
    "PyQt6/Qt6/plugins/multimedia/ffmpegmediaplugin.dll",
    "libcrypto-3-x64.dll",
    "libssl-3-x64.dll",
)

SPEC = """import fnmatch
TRIM = {trim!r}

def keep(entry):
    dest = entry[0].replace("\\\\", "/")
    return not any(fnmatch.fnmatch(dest, pat) or dest.startswith(pat + "/") for pat in TRIM)

a = Analysis([{main!r}], pathex=[{root!r}], datas=[({sounds!r}, "assets/sounds")],
             excludes=["tkinter", "matplotlib", "scipy", "IPython", "pytest"])
a.binaries = [b for b in a.binaries if keep(b)]
a.datas = [d for d in a.datas if keep(d)]
pyz = PYZ(a.pure)
splash = Splash({splash!r}, binaries=a.binaries, datas=a.datas, text_pos=None, always_on_top=False)
exe = EXE(pyz, a.scripts, splash, splash.binaries, a.binaries, a.datas, [], name="Cellbox", icon={icon!r},
          version={version!r}, console=False, upx=False)
"""

# Version resource: what Explorer's Properties → Details and Task Manager show for the exe.
VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'KosmoStars'),
      StringStruct('FileDescription', 'Cellbox'),
      StringStruct('FileVersion', '{ver}'),
      StringStruct('InternalName', 'Cellbox'),
      StringStruct('LegalCopyright', 'KosmoStars'),
      StringStruct('OriginalFilename', 'Cellbox.exe'),
      StringStruct('ProductName', 'Cellbox (portable)'),
      StringStruct('ProductVersion', '{ver}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def render_icon() -> None:
    """Draws the app icon at every size and packs the PNGs into a multi-size .ico."""
    from PyQt6.QtCore import QBuffer, QIODevice, Qt
    from PyQt6.QtGui import QImage, QPainter
    from PyQt6.QtWidgets import QApplication

    from cellbox.icon import draw_icon

    app = QApplication.instance() or QApplication([])
    images = []
    for size in ICON_SIZES:
        img = QImage(size, size, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        draw_icon(p, size)
        p.end()
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        img.save(buf, "PNG")
        images.append((size, bytes(buf.data())))
    del app

    # ICO container: header, one directory entry per size, then the PNG blobs.
    out = io.BytesIO()
    out.write(struct.pack("<HHH", 0, 1, len(images)))
    offset = 6 + 16 * len(images)
    for size, data in images:
        dim = 0 if size >= 256 else size  # 0 means 256 in the ICO format
        out.write(struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    for _, data in images:
        out.write(data)
    ICON.parent.mkdir(parents=True, exist_ok=True)
    ICON.write_bytes(out.getvalue())
    print(f"icon   {ICON.relative_to(ROOT)} ({len(images)} sizes)")


def render_splash() -> None:
    """The startup window as a picture, shown by the exe while it unpacks (a couple of seconds),
    until the real one takes its place. 1x: Windows scales it up like the real one on HiDPI screens."""
    from PyQt6.QtWidgets import QApplication

    from cellbox.splash import Splash
    from cellbox.win95 import apply_theme

    app = QApplication.instance() or QApplication([])
    apply_theme(app)
    SPLASH.parent.mkdir(exist_ok=True)
    Splash().still_image("Unpacking...").save(str(SPLASH))
    print(f"splash {SPLASH.relative_to(ROOT)}")


def main() -> None:
    subprocess.run([sys.executable, str(ROOT / "tools" / "make_sounds.py")], check=True)
    render_icon()
    render_splash()
    WORK.mkdir(exist_ok=True)
    from cellbox import __version__

    nums = tuple(int(x) for x in __version__.split(".")) + (0,)
    version_file = WORK / "version_info.txt"
    version_file.write_text(VERSION_INFO.format(nums=nums, ver=__version__), encoding="utf-8")
    spec = WORK / "Cellbox.spec"
    spec.write_text(SPEC.format(trim=TRIM, main=str(ROOT / "main.py"), root=str(ROOT), icon=str(ICON),
                                sounds=str(ROOT / "assets" / "sounds"), splash=str(SPLASH),
                                version=str(version_file)),
                    encoding="utf-8")
    subprocess.run([
        sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
        "--distpath", str(WORK / "dist"), "--workpath", str(WORK / "tmp"), str(spec),
    ], check=True, cwd=ROOT)
    target = ROOT / "Cellbox.exe"
    shutil.copy2(WORK / "dist" / "Cellbox.exe", target)

    check = subprocess.run([str(target), "--self-check"])
    report = ROOT / "cellbox_check.txt"
    print(report.read_text(encoding="utf-8"))
    report.unlink()
    if check.returncode != 0:
        raise SystemExit("self-check failed: see the report above")
    print(f"done   {target.relative_to(ROOT)} ({target.stat().st_size / 2**20:.0f} MB)")


if __name__ == "__main__":
    main()
