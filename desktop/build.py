"""
╔═══════════════════════════════════════════════════════════════╗
║       YouTube Downloader — Desktop EXE/APP Builder            ║
║             An Application by Faysal Ahmmed                   ║
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

import os, sys, shutil, subprocess, tarfile, zipfile, urllib.request, platform, struct, zlib, time
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
    'mac_arm':  'https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip',
    'mac_x86':  'https://ffmpeg.martin-riedl.de/redirect/latest/macos/amd64/release/ffmpeg.zip',
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
    def hook(b, bs, tot):
        if tot > 0:
            p = min(b * bs / tot * 100, 100); bar = '█' * int(p / 2) + '░' * (50 - int(p / 2))
            print(f'\r  [{bar}] {p:5.1f}%', end='', flush=True)
    opener = urllib.request.build_opener()
    opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                                        'AppleWebKit/537.36 (KHTML, like Gecko) '
                                        'Chrome/120.0.0.0 Safari/537.36')]
    urllib.request.install_opener(opener)
    urllib.request.urlretrieve(url, dest, reporthook=hook)
    print()

# ── Step 1: Packages ──────────────────────────────────────────────────────────

def install_packages():
    hdr('Step 1 / 4  —  Installing packages')
    run([sys.executable, '-m', 'pip', 'install', '--upgrade', '--quiet',
         'yt-dlp', 'yt-dlp-ejs', 'pyinstaller', 'pillow'])
    print('--------------------------------------------Done.')

# ── Step 2: ffmpeg ────────────────────────────────────────────────────────────

def download_ffmpeg():
    hdr('Step 2 / 4  —  Downloading ffmpeg')
    exe = 'ffmpeg.exe' if IS_WIN else 'ffmpeg'
    if (FFMPEG_DIR / exe).exists():
        print('-------------------------------------ffmpeg already downloaded, skipping.')
        return

    FFMPEG_DIR.mkdir(exist_ok=True)

    if IS_WIN:
        arch_path = Path('_ff.zip')
        dl(FFMPEG['win'], arch_path, 'ffmpeg (Windows)')
        with zipfile.ZipFile(arch_path) as z:
            for m in z.namelist():
                if Path(m).name in ('ffmpeg.exe','ffprobe.exe'):
                    with z.open(m) as src: (FFMPEG_DIR/Path(m).name).write_bytes(src.read())
                    print('-------------------------------------Extracted: {Path(m).name}')
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
                    print('-------------------------------------Extracted: ffmpeg')
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
                        print('-------------------------------------Extracted: {dest.name}')
        arch_path.unlink(missing_ok=True)

    print('-------------------------------------ffmpeg ready: {FFMPEG_DIR.resolve()}')

def download_deno():
    hdr('Step 2.5 — Downloading Deno (JS Runtime)')
    exe = 'deno.exe' if IS_WIN else 'deno'
    if (FFMPEG_DIR / exe).exists():
        print('-------------------------------------Deno already downloaded, skipping.')
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
                    print('-------------------------------------Extracted: {Path(m).name}')
        arch_path.unlink(missing_ok=True)

    print('-------------------------------------Deno ready: {FFMPEG_DIR.resolve()}')

# ── Step 3: Build ─────────────────────────────────────────────────────────────

def build():
    hdr('Step 3 / 4  —  Building with PyInstaller')

    sep = ';' if IS_WIN else ':'
    binaries = []
    for f in ('ffmpeg.exe','ffprobe.exe','ffmpeg','ffprobe'):
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

    if IS_WIN and ICO.exists():
        cmd += [f'--icon={ICO}']
    elif IS_MAC:
        if ICNS.exists():
            cmd += [f'--icon={ICNS}']
        elif ICO.exists():
            cmd += [f'--icon={ICO}']

    cmd.append(str(SCRIPT))
    run(cmd)

# ── Step 3.5: Pretty DMG (macOS only) ────────────────────────────────────────

def _make_dmg_background(path: Path, width=660, height=400):
    """
    Generates a professional, gorgeous DMG background using Pillow.
    Features:
      - Deep space gradient (dark navy → rich purple → near-black)
      - Glowing top accent bar
      - App name in large white bold text
      - Subtitle version line
      - A glowing animated-style arrow between the two icon positions
      - 'Drag to Applications' instruction label
      - Subtle circle glow behind each icon drop zone
      - Retina-ready (saved at 2x then downsampled for crisp result)
    """
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    import math

    SCALE = 2                        # render at 2x for retina sharpness
    W, H  = width * SCALE, height * SCALE

    img  = Image.new('RGB', (W, H))
    draw = ImageDraw.Draw(img)

    # ── Background gradient ───────────────────────────────────────────────────
    # Three-stop: top dark-navy → mid deep-purple → bottom near-black
    stops = [
        (0,   (12, 14, 30)),
        (0.5, (35, 18, 72)),
        (1.0, (8,  8,  20)),
    ]
    for y in range(H):
        t = y / (H - 1)
        # find which segment we're in
        for i in range(len(stops) - 1):
            t0, c0 = stops[i]
            t1, c1 = stops[i + 1]
            if t0 <= t <= t1:
                f = (t - t0) / (t1 - t0)
                r = int(c0[0] + (c1[0] - c0[0]) * f)
                g = int(c0[1] + (c1[1] - c0[1]) * f)
                b = int(c0[2] + (c1[2] - c0[2]) * f)
                draw.line([(0, y), (W, y)], fill=(r, g, b))
                break

    # ── Top accent glow bar ───────────────────────────────────────────────────
    bar_h = 6 * SCALE
    for y in range(bar_h):
        alpha = 1.0 - (y / bar_h)
        r = int(120 * alpha)
        g = int(80  * alpha)
        b = int(255 * alpha)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # ── Subtle noise/grain overlay (makes it feel premium) ───────────────────
    import random
    rng = random.Random(42)
    noise_layer = Image.new('RGB', (W, H), (0, 0, 0))
    nd = ImageDraw.Draw(noise_layer)
    for _ in range(W * H // 8):
        x = rng.randint(0, W - 1)
        y = rng.randint(0, H - 1)
        v = rng.randint(0, 18)
        nd.point((x, y), fill=(v, v, v))
    img = Image.blend(img, noise_layer, alpha=0.06)
    draw = ImageDraw.Draw(img)

    # ── Icon drop-zone glows ──────────────────────────────────────────────────
    # App icon center at (180,195) → scaled; Applications at (480,195)
    app_cx,  app_cy  = 180 * SCALE, 195 * SCALE
    appl_cx, appl_cy = 480 * SCALE, 195 * SCALE

    for cx, cy, color in [
        (app_cx,  app_cy,  (100, 60, 200)),
        (appl_cx, appl_cy, (60,  40, 160)),
    ]:
        glow = Image.new('RGB', (W, H), (0, 0, 0))
        gd   = ImageDraw.Draw(glow)
        r = 80 * SCALE
        gd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
        glow = glow.filter(ImageFilter.GaussianBlur(radius=40 * SCALE))
        img  = Image.blend(img, glow, alpha=0.35)
        draw = ImageDraw.Draw(img)

    # ── Arrow (glowing curved arrow pointing right) ───────────────────────────
    # Draw a thick right-pointing arrow between the two icon centers
    ax1 = app_cx  + 75 * SCALE
    ax2 = appl_cx - 75 * SCALE
    ay  = app_cy

    # Glow pass (thick, blurred)
    arrow_glow = Image.new('RGB', (W, H), (0, 0, 0))
    agd = ImageDraw.Draw(arrow_glow)
    agd.line([(ax1, ay), (ax2, ay)], fill=(160, 100, 255), width=8 * SCALE)
    tip = 22 * SCALE
    agd.polygon([
        (ax2,        ay),
        (ax2 - tip,  ay - tip // 2),
        (ax2 - tip,  ay + tip // 2),
    ], fill=(160, 100, 255))
    arrow_glow = arrow_glow.filter(ImageFilter.GaussianBlur(radius=12 * SCALE))
    img  = Image.blend(img, arrow_glow, alpha=0.8)
    draw = ImageDraw.Draw(img)

    # Sharp core arrow
    draw.line([(ax1, ay), (ax2, ay)], fill=(220, 190, 255), width=3 * SCALE)
    draw.polygon([
        (ax2,            ay),
        (ax2 - tip,      ay - tip // 2),
        (ax2 - tip,      ay + tip // 2),
    ], fill=(230, 210, 255))

    # ── Typography ────────────────────────────────────────────────────────────
    # Try system fonts, fall back gracefully
    def _font(size):
        for name in [
            '/System/Library/Fonts/SFNS.ttf',
            '/System/Library/Fonts/SFNSDisplay.ttf',
            '/System/Library/Fonts/Helvetica.ttc',
            '/System/Library/Fonts/Arial.ttf',
            '/Library/Fonts/Arial.ttf',
        ]:
            try:
                return ImageFont.truetype(name, size * SCALE)
            except Exception:
                pass
        return ImageFont.load_default()

    font_title    = _font(28)
    font_subtitle = _font(13)
    font_hint     = _font(11)

    # App title — centred at top
    title_text = APP_NAME
    try:
        tw = draw.textlength(title_text, font=font_title)
    except Exception:
        tw = len(title_text) * 16 * SCALE
    tx = (W - tw) // 2
    ty = 22 * SCALE

    # Shadow
    draw.text((tx + 2, ty + 2), title_text, font=font_title, fill=(0, 0, 0, 120))
    # Main text
    draw.text((tx, ty), title_text, font=font_title, fill=(240, 235, 255))

    # Subtitle
    sub = 'An Application by Faysal Ahmmed'
    try:
        sw = draw.textlength(sub, font=font_subtitle)
    except Exception:
        sw = len(sub) * 8 * SCALE
    draw.text(((W - sw) // 2, ty + 38 * SCALE), sub, font=font_subtitle, fill=(160, 140, 200))

    # Thin divider line below title
    div_y = ty + 62 * SCALE
    draw.line([(W // 4, div_y), (3 * W // 4, div_y)], fill=(80, 60, 120), width=SCALE)

    # "Drag to Applications" hint below arrow
    hint = 'Drag to Applications to install'
    try:
        hw = draw.textlength(hint, font=font_hint)
    except Exception:
        hw = len(hint) * 7 * SCALE
    draw.text(((W - hw) // 2, ay + 52 * SCALE), hint, font=font_hint, fill=(180, 160, 220))

    # ── Downscale to final size (anti-aliased) ────────────────────────────────
    final = img.resize((width, height), Image.LANCZOS)
    final.save(str(path), 'PNG', optimize=True)


def package_dmg():
    if not IS_MAC:
        return
    hdr('Step 3.5 — Creating Pretty DMG (macOS)')

    dmg_final = OUT_DIR / f'{APP_NAME}.dmg'
    if dmg_final.exists():
        dmg_final.unlink()

    app_path = OUT_DIR / f'{APP_NAME}.app'
    if not app_path.exists():
        print('-------------------------------------{app_path} not found, skipping DMG.')
        return

    # ── staging folder ────────────────────────────────────────────────────────
    stage = OUT_DIR / '_dmg_stage'
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    shutil.copytree(app_path, stage / app_path.name)
    try:
        (stage / 'Applications').symlink_to('/Applications')
    except Exception:
        pass

    # ── background image ──────────────────────────────────────────────────────
    bg_dir = stage / '.background'
    bg_dir.mkdir()
    bg_path = bg_dir / 'bg.png'
    _make_dmg_background(bg_path, width=660, height=400)
    print('-------------------------------------Background image generated.')

    # ── create writable DMG ───────────────────────────────────────────────────
    tmp_dmg = OUT_DIR / '_tmp_rw.dmg'
    if tmp_dmg.exists():
        tmp_dmg.unlink()

    print('  💿  Creating temporary writable DMG…')
    run([
        'hdiutil', 'create',
        '-volname', APP_NAME,
        '-srcfolder', str(stage),
        '-ov', '-format', 'UDRW',
        '-size', '300m',
        str(tmp_dmg),
    ])

    # ── mount it ──────────────────────────────────────────────────────────────
    print('  🔧  Mounting DMG to apply styling…')
    result = subprocess.run(
        ['hdiutil', 'attach', '-readwrite', '-noverify', '-noautoopen', str(tmp_dmg)],
        capture_output=True, text=True, check=True,
    )

    # Grab the ACTUAL mount point — "YouTube Downloader" etc.
    mount_point = None
    for line in result.stdout.splitlines():
        if '/Volumes/' in line:
            mount_point = line.split('\t')[-1].strip()
    if not mount_point:
        print('-------------------------------------Could not determine mount point. Falling back to simple DMG.')
        shutil.rmtree(stage)
        tmp_dmg.unlink(missing_ok=True)
        _simple_dmg(app_path, dmg_final)
        return

    # The volume name is just the last path component (handles "Name 2" etc.)
    vol_name = Path(mount_point).name
    bg_posix = f'{mount_point}/.background/bg.png'

    print('-------------------------------------Mounted at: {mount_point}  (volume: "{vol_name}")')

    # Give Finder a moment to register the newly mounted volume
    time.sleep(3)

    # ── AppleScript using POSIX file path for background ──────────────────────
    applescript = f'''
tell application "Finder"
    tell disk "{vol_name}"
        open
        set current view of container window to icon view
        set toolbar visible of container window to false
        set statusbar visible of container window to false
        set the bounds of container window to {{200, 120, 860, 520}}
        set viewOptions to the icon view options of container window
        set arrangement of viewOptions to not arranged
        set icon size of viewOptions to 128
        set background picture of viewOptions to POSIX file "{bg_posix}"
        set position of item "{APP_NAME}.app" of container window to {{180, 185}}
        set position of item "Applications" of container window to {{480, 185}}
        close
        open
        update without registering applications
        delay 3
        close
    end tell
end tell
'''
    print('  🖌   Styling window via Finder (this takes a moment)…')
    try:
        subprocess.run(['osascript', '-e', applescript], check=True, timeout=90)
        print('-------------------------------------Window styled successfully.')
    except Exception as e:
        print('-------------------------------------AppleScript styling failed ({e}), DMG will still work.')

    # ── unmount ───────────────────────────────────────────────────────────────
    time.sleep(2)
    try:
        subprocess.run(['hdiutil', 'detach', mount_point, '-quiet'], check=True)
    except Exception:
        subprocess.run(['hdiutil', 'detach', mount_point, '-force', '-quiet'], check=False)

    # ── convert to final compressed read-only DMG ─────────────────────────────
    print('  📦  Compressing to final DMG…')
    run([
        'hdiutil', 'convert', str(tmp_dmg),
        '-format', 'UDZO',
        '-imagekey', 'zlib-level=9',
        '-o', str(dmg_final),
    ])

    # ── cleanup ───────────────────────────────────────────────────────────────
    tmp_dmg.unlink(missing_ok=True)
    shutil.rmtree(stage)

    print('-------------------------------------DMG ready: {dmg_final.name}')
    print('-------------------------------------{dmg_final.resolve()}')


def _simple_dmg(app_path: Path, dmg_final: Path):
    """Minimal fallback DMG with no styling."""
    tmp = OUT_DIR / 'tmp_dmg_data'
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir()
    shutil.copytree(app_path, tmp / app_path.name)
    try:
        (tmp / 'Applications').symlink_to('/Applications')
    except Exception:
        pass
    run(['hdiutil', 'create', '-volname', APP_NAME,
         '-srcfolder', str(tmp), '-ov', '-format', 'UDZO', str(dmg_final)])
    shutil.rmtree(tmp)

# ── Step 4: Report ────────────────────────────────────────────────────────────

def report():
    hdr('Step 4 / 4  —  Build complete!')

    found = None
    for c in [OUT_DIR/f'{APP_NAME}.exe', OUT_DIR/f'{APP_NAME}.app', OUT_DIR/APP_NAME]:
        if c.exists(): found = c; break

    if not found:
        print('-------------------------------------Build failed — check output above for errors.'); return

    if IS_LIN and found.is_file(): found.chmod(0o755)

    sz = found.stat().st_size//1024//1024 if found.is_file() else \
         sum(f.stat().st_size for f in found.rglob('*') if f.is_file())//1024//1024

    print(f'\n  ✅  {found.name}')
    print(f'  📦  {found.resolve()}')
    print(f'  📏  ~{sz} MB')

    if IS_MAC:
        dmg = OUT_DIR / f'{APP_NAME}.dmg'
        if dmg.exists():
            dsz = dmg.stat().st_size // 1024 // 1024
            print(f'\n  💿  {dmg.name}')
            print(f'  📦  {dmg.resolve()}')
            print(f'  📏  ~{dsz} MB')

    print()

    if IS_WIN:   print('  → Double-click on any Windows 10/11 machine. No install needed.')
    elif IS_MAC: print('  → Open the DMG, drag the app to Applications. Done!')
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
        print('-------------------------------------{SCRIPT} not found. Run from the project root.'); sys.exit(1)

    os.chdir(Path(__file__).parent)
    install_packages()
    download_ffmpeg()
    #download_deno()
    build()
    if IS_MAC: package_dmg()
    report()

if __name__ == '__main__':
    main()