"""
╔═══════════════════════════════════════════════════════════════╗
║       YouTube Downloader — Desktop EXE/APP Builder            ║
║                                                               ║
║  Run from the project root:  python desktop/build.py          ║
║                                                               ║
║  Builds for the current OS automatically:                     ║
║    Windows  →  dist/YouTube Downloader.exe                    ║
║    macOS    →  dist/YouTube Downloader.app                    ║
║    Linux    →  dist/YouTube Downloader  (binary)              ║
║                                                               ║
║  Output is fully self-contained — no Python, no ffmpeg        ║
║  needed on the target machine.                                ║
╚═══════════════════════════════════════════════════════════════╝
"""

import os, sys, shutil, subprocess, tarfile, zipfile, urllib.request, platform
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────
APP_NAME   = 'YouTube Downloader'
SCRIPT     = Path(__file__).parent / 'app.py'
OUT_DIR    = Path(__file__).parent.parent / 'desktop/dist'
FFMPEG_DIR = Path(__file__).parent / 'ffmpeg_bin'
ICO        = Path(__file__).parent / 'icon.ico'
ICNS       = Path(__file__).parent / 'icon.icns'

IS_WIN  = sys.platform == 'win32'
IS_MAC  = sys.platform == 'darwin'
IS_LIN  = sys.platform.startswith('linux')
ARCH    = platform.machine().lower()

# Static ffmpeg URLs
FFMPEG = {
    'win':      'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip',
    'mac_arm':  'https://evermeet.cx/ffmpeg/getrelease/arm64/zip',
    'mac_x86':  'https://evermeet.cx/ffmpeg/getrelease/zip',
    'linux':    'https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz',
}

# Static Deno URLs (for JS runtime)
DENO = {
    'win':      'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip',
    'mac_arm':  'https://github.com/denoland/deno/releases/latest/download/deno-aarch64-apple-darwin.zip',
    'mac_x86':  'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-apple-darwin.zip',
    'linux':    'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip',
}

# ── Helpers ───────────────────────────────────────────────────────────────────

def run(cmd, **kw):
    print('▶  ' + ' '.join(str(c) for c in cmd))
    subprocess.run(cmd, check=True, **kw)

def hdr(msg):
    w = 60
    print(f'\n{"═"*w}\n  {msg}\n{"═"*w}')

def dl(url, dest, label=''):
    print(f'  Downloading {label or Path(dest).name}…')
    def hook(b,bs,tot):
        if tot>0:
            p=min(b*bs/tot*100,100); bar='█'*int(p/2)+'░'*(50-int(p/2))
            print(f'\r  [{bar}] {p:5.1f}%', end='', flush=True)
    urllib.request.urlretrieve(url, dest, reporthook=hook)
    print()

# ── Step 1: Packages ──────────────────────────────────────────────────────────

def install_packages():
    hdr('Step 1 / 4  —  Installing packages')
    run([sys.executable, '-m', 'pip', 'install', '--upgrade', '--quiet',
         'yt-dlp', 'yt-dlp-ejs', 'pyinstaller'])
    print('  ✅  Done.')

# ── Step 2: ffmpeg ────────────────────────────────────────────────────────────

def download_ffmpeg():
    hdr('Step 2 / 4  —  Downloading ffmpeg')
    exe = 'ffmpeg.exe' if IS_WIN else 'ffmpeg'
    if (FFMPEG_DIR / exe).exists():
        print('  ✅  ffmpeg already downloaded, skipping.')
        return

    FFMPEG_DIR.mkdir(exist_ok=True)

    if IS_WIN:
        arch_path = Path('_ff.zip')
        dl(FFMPEG['win'], arch_path, 'ffmpeg (Windows)')
        with zipfile.ZipFile(arch_path) as z:
            for m in z.namelist():
                if Path(m).name in ('ffmpeg.exe','ffprobe.exe'):
                    with z.open(m) as src: (FFMPEG_DIR/Path(m).name).write_bytes(src.read())
                    print(f'  Extracted: {Path(m).name}')
        arch_path.unlink(missing_ok=True)

    elif IS_MAC:
        is_arm = ARCH in ('arm64','aarch64')
        url = FFMPEG['mac_arm'] if is_arm else FFMPEG['mac_x86']
        arch_path = Path('_ff.zip')
        dl(url, arch_path, f'ffmpeg (macOS {"arm64" if is_arm else "x86_64"})')
        with zipfile.ZipFile(arch_path) as z:
            for m in z.namelist():
                if Path(m).name == 'ffmpeg':
                    d = FFMPEG_DIR/'ffmpeg'; d.write_bytes(z.read(m)); d.chmod(0o755)
                    print('  Extracted: ffmpeg')
        # ffprobe symlink placeholder
        fp = FFMPEG_DIR/'ffprobe'
        if not fp.exists(): fp.symlink_to('ffmpeg')
        arch_path.unlink(missing_ok=True)

    elif IS_LIN:
        arch_path = Path('_ff.tar.xz')
        dl(FFMPEG['linux'], arch_path, 'ffmpeg (Linux)')
        with tarfile.open(arch_path, 'r:xz') as t:
            for m in t.getmembers():
                if Path(m.name).name in ('ffmpeg','ffprobe'):
                    f = t.extractfile(m)
                    if f:
                        dest = FFMPEG_DIR/Path(m.name).name
                        dest.write_bytes(f.read()); dest.chmod(0o755)
                        print(f'  Extracted: {dest.name}')
        arch_path.unlink(missing_ok=True)

    print(f'  ✅  ffmpeg ready: {FFMPEG_DIR.resolve()}')

def download_deno():
    hdr('Step 2.5 — Downloading Deno (JS Runtime)')
    exe = 'deno.exe' if IS_WIN else 'deno'
    if (FFMPEG_DIR / exe).exists():
        print('  ✅  Deno already downloaded, skipping.')
        return

    FFMPEG_DIR.mkdir(exist_ok=True)
    
    url = ''
    if IS_WIN: url = DENO['win']
    elif IS_MAC: url = DENO['mac_arm'] if ARCH in ('arm64','aarch64') else DENO['mac_x86']
    elif IS_LIN: url = DENO['linux']

    if url:
        arch_path = Path('_deno.zip')
        dl(url, arch_path, 'Deno (JS Runtime)')
        with zipfile.ZipFile(arch_path) as z:
            for m in z.namelist():
                if Path(m).name in ('deno.exe', 'deno'):
                    with z.open(m) as src: (FFMPEG_DIR/Path(m).name).write_bytes(src.read())
                    if not IS_WIN: (FFMPEG_DIR/Path(m).name).chmod(0o755)
                    print(f'  Extracted: {Path(m).name}')
        arch_path.unlink(missing_ok=True)
    
    print(f'  ✅  Deno ready: {FFMPEG_DIR.resolve()}')

# ── Step 3: Build ─────────────────────────────────────────────────────────────

def build():
    hdr('Step 3 / 4  —  Building with PyInstaller')

    sep = ';' if IS_WIN else ':'
    binaries = []
    for f in ('ffmpeg.exe','ffprobe.exe','ffmpeg','ffprobe'): # , 'deno.exe', 'deno'
        p = FFMPEG_DIR/f
        if p.exists() and not p.is_symlink():
            binaries += [f'--add-binary={p.resolve()}{sep}ffmpeg_bin']

    datas = []
    if ICO.exists():
        datas += [f'--add-data={ICO.resolve()}{sep}.']

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--onefile', '--windowed',
        f'--name={APP_NAME}',
        '--hidden-import=yt_dlp',
        '--hidden-import=yt_dlp.extractor',
        '--hidden-import=yt_dlp.downloader',
        '--hidden-import=yt_dlp.postprocessor',
        '--collect-all=yt_dlp',
        f'--distpath={OUT_DIR}',
        '--clean', '--noconfirm',
    ] + binaries + datas

    if IS_WIN and ICO.exists():   cmd += [f'--icon={ICO}']
    elif IS_MAC and ICNS.exists(): cmd += [f'--icon={ICNS}']

    cmd.append(str(SCRIPT))
    run(cmd)

# ── Step 4: Report ────────────────────────────────────────────────────────────

def report():
    hdr('Step 4 / 4  —  Build complete!')

    found = None
    for c in [OUT_DIR/f'{APP_NAME}.exe', OUT_DIR/f'{APP_NAME}.app', OUT_DIR/APP_NAME]:
        if c.exists(): found = c; break

    if not found:
        print('  ❌  Build failed — check output above for errors.'); return

    if IS_LIN and found.is_file(): found.chmod(0o755)

    sz = found.stat().st_size//1024//1024 if found.is_file() else \
         sum(f.stat().st_size for f in found.rglob('*') if f.is_file())//1024//1024

    print(f'\n  ✅  {found.name}')
    print(f'  📦  {found.resolve()}')
    print(f'  📏  ~{sz} MB')
    print()

    if IS_WIN:   print('  → Double-click on any Windows 10/11 machine. No install needed.')
    elif IS_MAC: print('  → Right-click → Open on macOS 11+. No install needed.')
    elif IS_LIN: print('  → chmod +x then run on any Linux x86_64. No install needed.')
    print()


def main():
    print()
    print('╔' + '═'*58 + '╗')
    print('║   YouTube Downloader — Desktop Builder                   ║')
    print('╚' + '═'*58 + '╝')
    print(f'\n  OS     : {platform.system()} ({ARCH})')
    print(f'  Python : {sys.version.split()[0]}')
    print(f'  Output : {OUT_DIR.resolve()}')
    print()

    if not SCRIPT.exists():
        print(f'❌  {SCRIPT} not found. Run from the project root.'); sys.exit(1)

    os.chdir(Path(__file__).parent)
    install_packages()
    download_ffmpeg()
    #download_deno()
    build()
    report()

if __name__ == '__main__':
    main()
