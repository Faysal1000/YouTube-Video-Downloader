"""
YouTube Downloader - Automated Build and Packaging System

This script orchestrates the end-to-end transformation of the raw Python source code 
into a professional, redistributable application package. 

ARCHITECTURE:
1. Environment Detection: Identifies OS and architecture for binary targeting.
2. Dependency Resolution: Pulls shared binaries (ffmpeg, deno) and Python packages.
3. PyInstaller Bundling: Compiles source and resources into an executable bundle.
4. macOS Polish: Handles ad-hoc code signing and custom DMG theme generation.
5. Final Report: Generates a summary of the produced artifacts.
"""

import os, sys, shutil, subprocess, tarfile, zipfile, urllib.request, platform, struct, zlib, time
from pathlib import Path

# --- Build Pipeline Configuration ---

# The user-facing name of the final application
APP_NAME   = 'YouTube Downloader'

# Path resolution for core files and output target
SCRIPT     = Path(__file__).parent / 'app.py'
OUT_DIR    = Path(__file__).parent.parent / 'desktop/dist'
FFMPEG_DIR = Path(__file__).parent / 'ffmpeg_bin'
ICO        = Path(__file__).parent / 'icon.ico'
ICNS       = Path(__file__).parent / 'icon.icns'

# Operating System and Architecture detection for binary selection
IS_WIN  = sys.platform == 'win32'
IS_MAC  = sys.platform == 'darwin'
IS_LIN  = sys.platform.startswith('linux')
ARCH    = platform.machine().lower()

# Static URLs for external components (ffmpeg)
# We use pre-built static binaries to ensure 'yt-dlp' has zero external runtime requirements.
FFMPEG = {
    'win':      'https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip',
    'mac_arm':  'https://ffmpeg.martin-riedl.de/redirect/latest/macos/arm64/release/ffmpeg.zip',
    'mac_x86':  'https://ffmpeg.martin-riedl.de/redirect/latest/macos/amd64/release/ffmpeg.zip',
    'linux':    'https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz',
}

# Static URLs for Deno (optional JS runtime for complex YouTube challenges)
DENO = {
    'win':      'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip',
    'mac_arm':  'https://github.com/denoland/deno/releases/latest/download/deno-aarch64-apple-darwin.zip',
    'mac_x86':  'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-apple-darwin.zip',
    'linux':    'https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip',
}

# --- Console UI and CLI Utilities ---

def run(cmd, **kw):
    """
    Executes a shell command via subprocess.
    Renders the command for logging clarity.
    """
    print(f'[EXEC] {" ".join(str(c) for c in cmd)}')
    subprocess.run(cmd, check=True, **kw)

def hdr(msg):
    """Prints a professional section header to the console."""
    w = 60
    print(f'\n{"="*w}\n  {msg}\n{"="*w}')

def dl(url, dest, label=''):
    """
    Downloads a binary artifact with a CLI-based progress bar.
    
    RATIONALE:
    Uses a custom User-Agent to bypass standard 403 blocks seen on 
    automatic GitHub/Martin-Riedl downloads.
    """
    print(f'  Downloading: {label or Path(dest).name}...')
    
    def hook(count, block_size, total_size):
        if total_size > 0:
            percentage = min(count * block_size / total_size * 100, 100)
            # Render a 50-character progress bar
            bar_len = int(percentage / 2)
            bar = '#' * bar_len + '-' * (50 - bar_len)
            print(f'\r  [{bar}] {percentage:5.1f}%', end='', flush=True)

    # Standard browser User-Agent to ensure reliable download connectivity
    opener = urllib.request.build_opener()
    opener.addheaders = [('User-Agent', 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                                         'AppleWebKit/537.36 (KHTML, like Gecko) '
                                         'Chrome/120.0.0.0 Safari/537.36')]
    urllib.request.install_opener(opener)
    
    urllib.request.urlretrieve(url, dest, reporthook=hook)
    print() # Final newline after progress completion

# --- Pipeline Step 1: Python Dependency Resolution ---

def install_packages():
    """Installs required Python modules via pip."""
    hdr('Pipeline: 1 / 4  -  Initializing Build Environment')
    run([sys.executable, '-m', 'pip', 'install', '--upgrade', '--quiet',
         'yt-dlp', 'yt-dlp-ejs', 'pyinstaller', 'pillow'])
    print('[SYSTEM] Package installation verified.')

# --- Step 2: External Binary Management ---

# --- Pipeline Step 2: Binary Artifact Management ---

def download_ffmpeg():
    """
    Downloads and extracts the correct FFmpeg binaries for the host OS.
    
    RATIONALE:
    FFmpeg is essential for 'yt-dlp' to merge audio/video tracks. 
    Packaging it inside the app removes the complexity of users having 
    to install it manually.
    """
    hdr('Pipeline: 2 / 4  -  Synchronizing Core Binaries (FFmpeg)')
    exe = 'ffmpeg.exe' if IS_WIN else 'ffmpeg'
    
    if (FFMPEG_DIR / exe).exists():
        print('[SKIP] FFmpeg is already cached.')
        return

    FFMPEG_DIR.mkdir(exist_ok=True)

    # OS-specific download and extraction logic
    if IS_WIN:
        arch_path = Path('_ff.zip')
        dl(FFMPEG['win'], arch_path, 'FFmpeg (Windows-x64)')
        with zipfile.ZipFile(arch_path) as z:
            for member in z.namelist():
                if Path(member).name in ('ffmpeg.exe','ffprobe.exe'):
                    with z.open(member) as src: 
                        (FFMPEG_DIR / Path(member).name).write_bytes(src.read())
                    print(f'[BINS] Extracted: {Path(member).name}')
        arch_path.unlink(missing_ok=True)

    elif IS_MAC:
        is_arm = ARCH in ('arm64','aarch64')
        url = FFMPEG['mac_arm'] if is_arm else FFMPEG['mac_x86']
        arch_path = Path('_ff.zip')
        dl(url, arch_path, f'FFmpeg (macOS-{"arm64" if is_arm else "x86_64"})')
        with zipfile.ZipFile(arch_path) as z:
            for member in z.namelist():
                if Path(member).name == 'ffmpeg':
                    d = FFMPEG_DIR / 'ffmpeg'
                    d.write_bytes(z.read(member))
                    d.chmod(0o755) # Ensure executable permissions
                    print('[BINS] Extracted: ffmpeg')
        # Create a symlink for ffprobe as some extractors look for it separately
        fp = FFMPEG_DIR / 'ffprobe'
        if not fp.exists(): 
            fp.symlink_to('ffmpeg')
        arch_path.unlink(missing_ok=True)

    elif IS_LIN:
        arch_path = Path('_ff.tar.xz')
        dl(FFMPEG['linux'], arch_path, 'FFmpeg (Linux-x64)')
        with tarfile.open(arch_path, 'r:xz') as t:
            for member in t.getmembers():
                if Path(member.name).name in ('ffmpeg','ffprobe'):
                    f = t.extractfile(member)
                    if f:
                        dest = FFMPEG_DIR / Path(member.name).name
                        dest.write_bytes(f.read())
                        dest.chmod(0o755)
                        print(f'[BINS] Extracted: {dest.name}')
        arch_path.unlink(missing_ok=True)

    print(f'[BINS] FFmpeg deployment complete: {FFMPEG_DIR.resolve()}')

def download_deno():
    """
    Optional: Downloads the Deno JS runtime to assist in solving 
    complex video extraction challenges.
    """
    hdr('Pipeline: 2.5  -  Synchronizing Optional Runtime (Deno)')
    exe = 'deno.exe' if IS_WIN else 'deno'
    
    if (FFMPEG_DIR / exe).exists():
        print('[SKIP] Deno is already cached.')
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
            for member in z.namelist():
                if Path(member).name in ('deno.exe', 'deno'):
                    with z.open(member) as src: 
                        (FFMPEG_DIR / Path(member).name).write_bytes(src.read())
                    if not IS_WIN: 
                        (FFMPEG_DIR / Path(member).name).chmod(0o755)
                    print(f'[BINS] Extracted: {Path(member).name}')
        arch_path.unlink(missing_ok=True)

    print(f'[BINS] Deno deployment complete: {FFMPEG_DIR.resolve()}')

# --- Step 3: Application Bundling ---

# --- Pipeline Step 3: Application Bundling (PyInstaller) ---

def build():
    """
    Orchestrates the PyInstaller bundling process.
    
    RATIONALE:
    - macOS: Uses '--onedir'. This avoids the extraction delay on startup which 
      can cause the Dock icon to bounce indefinitely or disappear.
    - Windows/Linux: Uses '--onefile' to provide a single, portable executable 
      for maximum user convenience.
    """
    hdr('Pipeline: 3 / 4  -  Executing PyInstaller Engine')

    # Path separator differences between platforms
    sep = ';' if IS_WIN else ':'
    
    # Identify and map external binaries into the bundle
    binaries = []
    for f in ('ffmpeg.exe','ffprobe.exe','ffmpeg','ffprobe'):
        p = FFMPEG_DIR / f
        if p.exists() and not p.is_symlink():
            binaries += [f'--add-binary={p.resolve()}{sep}ffmpeg_bin']

    # Map static resources (icons)
    datas = []
    if ICO.exists():
        datas += [f'--add-data={ICO.resolve()}{sep}.']

    # Platform-specific bundling mode selection
    mode_flag = '--onedir' if IS_MAC else '--onefile'

    cmd = [
        sys.executable, '-m', 'PyInstaller',
        mode_flag,
        '--windowed', # No console window on launch
        f'--name={APP_NAME}',
        # Ensure 'yt-dlp' and its dynamic extractors are fully included
        '--hidden-import=yt_dlp',
        '--hidden-import=yt_dlp.extractor',
        '--hidden-import=yt_dlp.downloader',
        '--hidden-import=yt_dlp.postprocessor',
        '--collect-all=yt_dlp',
        f'--distpath={OUT_DIR}',
        '--clean',
        '--noconfirm',
    ] + binaries + datas

    # Apply platform-specific icons
    if IS_WIN and ICO.exists():
        cmd += [f'--icon={ICO}']
    elif IS_MAC:
        if ICNS.exists():
            cmd += [f'--icon={ICNS}']
        elif ICO.exists():
            cmd += [f'--icon={ICO}']

    cmd.append(str(SCRIPT))
    run(cmd)

# --- Step 3.5: macOS DMG Packaging ---

# --- Pipeline Step 3.5: macOS Visual Identity (DMG) ---

def _make_dmg_background(path: Path, width=660, height=400):
    """
    Generates a high-fidelity, Retina-ready DMG background image using Pillow.
    
    DESIGN PHILOSOPHY:
    The background provides a professional onboarding experience for macOS users.
    It features a deep space gradient, glowing accents, and clear visual cues 
    for the 'Drag to Applications' installation workflow.
    """
    from PIL import Image, ImageDraw, ImageFilter, ImageFont
    import math

    # Render at 2x resolution for high-DPI (Retina) displays
    SCALE = 2                        
    W, H  = width * SCALE, height * SCALE

    img  = Image.new('RGB', (W, H))
    draw = ImageDraw.Draw(img)

    # 1. Background Gradient Construction
    # A premium dark-to-deep-space transition
    stops = [
        (0.0, (12, 14, 30)), # Top: Midnight Blue
        (0.5, (35, 18, 72)), # Mid: Deep Orchid
        (1.0, (8,  8,  20)), # Bottom: Void Black
    ]
    for y in range(H):
        t = y / (H - 1)
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

    # 2. Glowing Top Accent Bar
    bar_h = 6 * SCALE
    for y in range(bar_h):
        alpha = 1.0 - (y / bar_h)
        r = int(120 * alpha)
        g = int(80  * alpha)
        b = int(255 * alpha)
        draw.line([(0, y), (W, y)], fill=(r, g, b))

    # 3. Micro-texture (Film Grain)
    # Adds a premium, non-sterile feel to the gradients
    import random
    rng = random.Random(42)
    noise_layer = Image.new('RGB', (W, H), (0, 0, 0))
    nd = ImageDraw.Draw(noise_layer)
    for _ in range(W * H // 12):
        x = rng.randint(0, W - 1)
        y = rng.randint(0, H - 1)
        v = rng.randint(0, 15)
        nd.point((x, y), fill=(v, v, v))
    img = Image.blend(img, noise_layer, alpha=0.08)
    draw = ImageDraw.Draw(img)

    # 4. Icon Anchor Highlights
    # Centers for the App icon (Left) and Applications folder (Right)
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

    # 5. Instructional Glow Arrow
    # Points the user from the app to the Applications folder
    ax1 = app_cx  + 75 * SCALE
    ax2 = appl_cx - 75 * SCALE
    ay  = app_cy
    tip = 22 * SCALE

    # Background Arrow Glow (Soft diffusion)
    arrow_glow = Image.new('RGB', (W, H), (0, 0, 0))
    agd = ImageDraw.Draw(arrow_glow)
    agd.line([(ax1, ay), (ax2, ay)], fill=(160, 100, 255), width=8 * SCALE)
    agd.polygon([(ax2, ay), (ax2 - tip, ay - tip // 2), (ax2 - tip, ay + tip // 2)], 
                fill=(160, 100, 255))
    arrow_glow = arrow_glow.filter(ImageFilter.GaussianBlur(radius=12 * SCALE))
    img  = Image.blend(img, arrow_glow, alpha=0.8)
    draw = ImageDraw.Draw(img)

    # Core Sharp Arrow (Focus)
    draw.line([(ax1, ay), (ax2, ay)], fill=(220, 190, 255), width=3 * SCALE)
    draw.polygon([(ax2, ay), (ax2 - tip, ay - tip // 2), (ax2 - tip, ay + tip // 2)], 
                 fill=(230, 210, 255))

    # 6. Typography and Branding
    def _font(size):
        """Attempts to load a premium system font; falls back to default."""
        for name in [
            '/System/Library/Fonts/SFNS.ttf',
            '/System/Library/Fonts/SFNSDisplay.ttf',
            '/System/Library/Fonts/Helvetica.ttc',
            '/System/Library/Fonts/Arial.ttf',
        ]:
            try: return ImageFont.truetype(name, size * SCALE)
            except Exception: pass
        return ImageFont.load_default()

    font_title    = _font(28)
    font_subtitle = _font(13)
    font_hint     = _font(11)

    # Main Branding
    title_text = APP_NAME
    try: tw = draw.textlength(title_text, font=font_title)
    except Exception: tw = len(title_text) * 16 * SCALE
    tx, ty = (W - tw) // 2, 22 * SCALE

    # Soft Shadow for Readability
    draw.text((tx + 2, ty + 2), title_text, font=font_title, fill=(0, 0, 0, 100))
    draw.text((tx, ty), title_text, font=font_title, fill=(240, 235, 255))

    # Author Credit
    sub = 'An Application by Faysal Ahmmed'
    try: sw = draw.textlength(sub, font=font_subtitle)
    except Exception: sw = len(sub) * 8 * SCALE
    draw.text(((W - sw) // 2, ty + 38 * SCALE), sub, font=font_subtitle, fill=(160, 140, 200))

    # Design Element: Divider
    div_y = ty + 62 * SCALE
    draw.line([(W // 4, div_y), (3 * W // 4, div_y)], fill=(80, 60, 120), width=SCALE)

    # UI Hint: Drag-to-install
    hint = 'Drag to Applications to install'
    try: hw = draw.textlength(hint, font=font_hint)
    except Exception: hw = len(hint) * 7 * SCALE
    draw.text(((W - hw) // 2, ay + 52 * SCALE), hint, font=font_hint, fill=(180, 160, 220))

    # 7. Final Downsampling (Retina-to-Standard conversion)
    final = img.resize((width, height), Image.LANCZOS)
    final.save(str(path), 'PNG', optimize=True)


def package_dmg():
    """
    Assembles the final macOS Disk Image (DMG) with custom styling.
    
    RATIONALE:
    A standard .app bundle is difficult to distribute. A DMG provides a familiar, 
    branded installation interface for macOS users.
    """
    if not IS_MAC:
        return
    hdr('Pipeline: 3.5  -  Assembling Visual DMG (macOS)')

    dmg_final = OUT_DIR / f'{APP_NAME}.dmg'
    if dmg_final.exists():
        dmg_final.unlink()

    app_path = OUT_DIR / f'{APP_NAME}.app'
    if not app_path.exists():
        print(f'[WARN] {app_path} not found. Skipping DMG phase.')
        return

    # 1. Staging Environment Setup
    stage = OUT_DIR / '_dmg_stage'
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)

    # Copy the app bundle and create a symlink to Applications
    shutil.copytree(app_path, stage / app_path.name)
    try:
        (stage / 'Applications').symlink_to('/Applications')
    except Exception:
        pass

    # 2. Background Resource Injection
    bg_dir = stage / '.background'
    bg_dir.mkdir()
    bg_path = bg_dir / 'bg.png'
    _make_dmg_background(bg_path, width=660, height=400)
    print('[BINS] Custom background theme generated.')

    # 3. Writable DMG Creation
    # We first create a large, writable 'UDDR' image to apply styling
    tmp_dmg = OUT_DIR / '_tmp_rw.dmg'
    if tmp_dmg.exists():
        tmp_dmg.unlink()

    print('  Status: Initializing virtual volume...')
    run([
        'hdiutil', 'create',
        '-volname', APP_NAME,
        '-srcfolder', str(stage),
        '-ov', '-format', 'UDRW',
        '-size', '300m',
        str(tmp_dmg),
    ])

    # 4. Mounting and Finder Styling
    print('  Status: Mounting volume for UI injection...')
    result = subprocess.run(
        ['hdiutil', 'attach', '-readwrite', '-noverify', '-noautoopen', str(tmp_dmg)],
        capture_output=True, text=True, check=True,
    )

    # Dynamically resolve the mount point (handles varied system environments)
    mount_point = None
    for line in result.stdout.splitlines():
        if '/Volumes/' in line:
            mount_point = line.split('\t')[-1].strip()
            
    if not mount_point:
        print('[FAIL] Mount resolution failed. Reverting to simple DMG.')
        shutil.rmtree(stage)
        tmp_dmg.unlink(missing_ok=True)
        _simple_dmg(app_path, dmg_final)
        return

    vol_name = Path(mount_point).name
    bg_posix = f'{mount_point}/.background/bg.png'

    print(f'[INFO] Volume "{vol_name}" active at {mount_point}')
    time.sleep(3) # Allow Finder to synchronize

    # 5. AppleScript UI Automation
    # Forces Finder to set the background, icon sizes, and window positions.
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
    print('  Status: Injecting Finder styles (AppleScript)...')
    try:
        subprocess.run(['osascript', '-e', applescript], check=True, timeout=90)
        print('[INFO] UI styling applied successfully.')
    except Exception as e:
        print(f'[WARN] Styling incomplete ({e}). DMG functionality remains.')

    # 6. Finalization and Cleanup
    time.sleep(2)
    try:
        subprocess.run(['hdiutil', 'detach', mount_point, '-quiet'], check=True)
    except Exception:
        subprocess.run(['hdiutil', 'detach', mount_point, '-force', '-quiet'], check=False)

    # Convert the writable DMG into a compressed, read-only distribution format (UDZO)
    print('  Status: Finalizing compression (UDZO/zlib-9)...')
    run([
        'hdiutil', 'convert', str(tmp_dmg),
        '-format', 'UDZO',
        '-imagekey', 'zlib-level=9',
        '-o', str(dmg_final),
    ])

    # Remove temporary build artifacts
    tmp_dmg.unlink(missing_ok=True)
    shutil.rmtree(stage)

    print(f'[DONE] Disk Image finalized: {dmg_final.name}')


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

# --- Step 3.6: macOS Code Signing ---

def codesign_app():
    """
    Applies ad-hoc code signing to the .app bundle.
    
    RATIONALE:
    Modern macOS (Gatekeeper) strictly validates binaries. Without a signature, 
    the app is blocked. By applying an ad-hoc signature ('-'), we satisfy 
    basic system requirements. 
    
    NOTE: Users on other machines will still need to 'Right-click -> Open' 
    the first time to register an exception, as this isn't a paid 
    Developer ID signature.
    """
    if not IS_MAC:
        return
    hdr('Pipeline: 3.6  -  Security Integration (Code Signing)')

    app_path = OUT_DIR / f'{APP_NAME}.app'
    if not app_path.exists():
        print('[WARN] Bundle not found. Skipping security phase.')
        return

    # Security mandates signing nested binaries first (Deep signing)
    frameworks = app_path / 'Contents' / 'Frameworks'
    macos_dir  = app_path / 'Contents' / 'MacOS'
    resources  = app_path / 'Contents' / 'Resources'

    print('  Status: Signing internal binaries/libraries...')
    for search_dir in [frameworks, macos_dir, resources]:
        if search_dir.exists():
            for member in search_dir.rglob('*'):
                if member.is_file() and not member.is_symlink():
                    try:
                        # Identify Mach-O binaries or dynamic libraries
                        result = subprocess.run(['file', str(member)], 
                                                capture_output=True, text=True)
                        if 'Mach-O' in result.stdout or member.suffix in ('.dylib', '.so'):
                            run(['codesign', '--force', '--sign', '-', str(member)])
                    except Exception:
                        pass # Ignore non-binary resource files

    # Final wrap-around signature for the entire bundle
    print('  Status: Applying global bundle signature...')
    run(['codesign', '--force', '--deep', '--sign', '-', str(app_path)])

    # Verification pass
    try:
        subprocess.run(['codesign', '--verify', '--verbose', str(app_path)],
                       check=True, capture_output=True, text=True)
        print('[INFO] Code signature verified.')
    except subprocess.CalledProcessError:
        print('[WARN] Signature verification failed (system may still allow execution).')

    print('  Info: For external distribution, advise users to "Right-click -> Open" initially.')


# --- Step 4: Final Report ---

# --- Pipeline Step 4: Deployment Reporting ---

def report():
    """Generates a final summary of the build artifacts."""
    hdr('Pipeline: 4 / 4  -  Build Optimization Complete')

    artifact = None
    for candidate in [OUT_DIR / f'{APP_NAME}.exe', 
                      OUT_DIR / f'{APP_NAME}.app', 
                      OUT_DIR / APP_NAME]:
        if candidate.exists(): 
            artifact = candidate
            break

    if not artifact:
        print('[FAIL] Deployment target missing. Check engine logs above.'); return

    # Restore executable permissions if on Linux
    if IS_LIN and artifact.is_file(): 
        artifact.chmod(0o755)

    # Estimate bundle size
    if artifact.is_file():
        size_mb = artifact.stat().st_size // 1024 // 1024
    else:
        size_mb = sum(f.stat().st_size for f in artifact.rglob('*') if f.is_file()) // 1024 // 1024

    print(f'\n  Package: {artifact.name}')
    print(f'  Target:  {artifact.resolve()}')
    print(f'  Weight:  ~{size_mb} MB')

    if IS_MAC:
        dmg = OUT_DIR / f'{APP_NAME}.dmg'
        if dmg.exists():
            dmg_mb = dmg.stat().st_size // 1024 // 1024
            print(f'  Volume:  {dmg.name}')
            print(f'  Size:    ~{dmg_mb} MB')

    print('\n[SYSTEM] Distribution Readiness:')
    if IS_WIN:   
        print('  - Windows: Portable EXE generated. No runtime installers required.')
    elif IS_MAC: 
        print('  - macOS:   DMG ready. Advise users of the "Right-click -> Open" bypass.')
    elif IS_LIN: 
        print('  - Linux:   Static binary generated. Binary is chmod +x ready.')
    print()


def main():
    """Main build orchestrator."""
    print('\nYouTube Downloader :: Automated Build System')
    print('============================================')
    print(f'  Platform : {platform.system()} ({ARCH})')
    print(f'  Engine   : Python {sys.version.split()[0]}')
    print(f'  Output   : {OUT_DIR.resolve()}')
    print()

    # Pre-flight check: Ensure source exists
    if not SCRIPT.exists():
        print(f'[ERROR] Source file missing: {SCRIPT}. Please run from root.')
        sys.exit(1)

    # Change to current directory to ensure relative paths resolve correctly
    os.chdir(Path(__file__).parent)

    # Execute Pipeline
    install_packages()
    download_ffmpeg()
    # download_deno() # Optional: Uncomment to include JS runtime support
    build()
    
    if IS_MAC:
        codesign_app()
        package_dmg()
        
    report()

if __name__ == '__main__':
    main()