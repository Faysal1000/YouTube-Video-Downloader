"""
======================================================
  YouTube Downloader  -  Web Server Launcher
======================================================
  Run:   python start.py

  Then open in any browser (phone, tablet, PC):
    * This machine : http://localhost:8080
    * Other devices: http://<YOUR-IP>:8080

  Everything needed is downloaded automatically:
    - Python packages (fastapi, uvicorn, yt-dlp)
    - ffmpeg  (if not already present)
    - Deno    (JS runtime required by newer yt-dlp)
======================================================
"""

import os
import sys
import time
import shutil
import socket
import platform
import subprocess
import threading
import urllib.request
import zipfile
import tarfile
from pathlib import Path

BASE     = Path(__file__).parent
PORT     = 8080
HOST     = "0.0.0.0"

FFMPEG_DIR = BASE / "ffmpeg_bin"

REQUIRED_PACKAGES = [
    "fastapi",
    "uvicorn[standard]",
    "yt-dlp",
    "yt-dlp-ejs",
    "python-multipart",
]

IS_WIN  = sys.platform == "win32"
IS_MAC  = sys.platform == "darwin"
IS_LIN  = sys.platform.startswith("linux")
ARCH    = platform.machine().lower()

# Download URLs
FFMPEG_URLS = {
    "win":      "https://github.com/BtbN/FFmpeg-Builds/releases/download/latest/ffmpeg-master-latest-win64-gpl.zip",
    "mac_arm":  "https://evermeet.cx/ffmpeg/getrelease/arm64/zip",
    "mac_x86":  "https://evermeet.cx/ffmpeg/getrelease/zip",
    "linux":    "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz",
}

DENO_URLS = {
    "win":      "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-pc-windows-msvc.zip",
    "mac_arm":  "https://github.com/denoland/deno/releases/latest/download/deno-aarch64-apple-darwin.zip",
    "mac_x86":  "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-apple-darwin.zip",
    "linux":    "https://github.com/denoland/deno/releases/latest/download/deno-x86_64-unknown-linux-gnu.zip",
}

# ─────────────────────────────────────────────────────────────────────────────

def banner():
    print()
    print("=" * 56)
    print("  YouTube Downloader  -  Web Server")
    print("=" * 56)
    print()


def get_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def dl(url: str, dest: Path, label: str = ""):
    """Download a file with a progress bar."""
    print(f"    Downloading {label or dest.name} ...")
    def hook(b, bs, tot):
        if tot > 0:
            p = min(b * bs / tot * 100, 100)
            bar = "#" * int(p / 2) + "." * (50 - int(p / 2))
            print(f"\r    [{bar}] {p:5.1f}%", end="", flush=True)
    urllib.request.urlretrieve(url, dest, reporthook=hook)
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Step 1: Python packages
# ─────────────────────────────────────────────────────────────────────────────

def install_packages():
    print("📦  Checking / installing Python packages ...")
    missing = []
    for pkg in REQUIRED_PACKAGES:
        name = pkg.split("[")[0].replace("-", "_")
        try:
            __import__(name)
        except ImportError:
            missing.append(pkg)

    if missing:
        print(f"    Installing: {', '.join(missing)}")
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--quiet", "--upgrade"] + missing,
            check=True
        )
    print("    OK  All packages ready.")


# ─────────────────────────────────────────────────────────────────────────────
# Step 2: ffmpeg
# ─────────────────────────────────────────────────────────────────────────────

def ensure_ffmpeg():
    """Download bundled ffmpeg if not already present and not on PATH."""
    exe = "ffmpeg.exe" if IS_WIN else "ffmpeg"

    if (FFMPEG_DIR / exe).exists():
        print(f"    OK  ffmpeg ready (bundled in ffmpeg_bin/)")
        return

    if shutil.which("ffmpeg"):
        print(f"    OK  ffmpeg ready (system PATH)")
        return

    # Auto-download
    print("    ffmpeg not found — downloading automatically ...")
    FFMPEG_DIR.mkdir(exist_ok=True)

    try:
        if IS_WIN:
            arch_path = BASE / "_ff.zip"
            dl(FFMPEG_URLS["win"], arch_path, "ffmpeg (Windows)")
            with zipfile.ZipFile(arch_path) as z:
                for m in z.namelist():
                    if Path(m).name in ("ffmpeg.exe", "ffprobe.exe"):
                        (FFMPEG_DIR / Path(m).name).write_bytes(z.read(m))
                        print(f"    Extracted: {Path(m).name}")
            arch_path.unlink(missing_ok=True)

        elif IS_MAC:
            is_arm = ARCH in ("arm64", "aarch64")
            url = FFMPEG_URLS["mac_arm"] if is_arm else FFMPEG_URLS["mac_x86"]
            arch_path = BASE / "_ff.zip"
            dl(url, arch_path, f"ffmpeg (macOS {'arm64' if is_arm else 'x86_64'})")
            with zipfile.ZipFile(arch_path) as z:
                for m in z.namelist():
                    if Path(m).name == "ffmpeg":
                        d = FFMPEG_DIR / "ffmpeg"
                        d.write_bytes(z.read(m))
                        d.chmod(0o755)
            fp = FFMPEG_DIR / "ffprobe"
            if not fp.exists():
                fp.symlink_to("ffmpeg")
            arch_path.unlink(missing_ok=True)

        elif IS_LIN:
            arch_path = BASE / "_ff.tar.xz"
            dl(FFMPEG_URLS["linux"], arch_path, "ffmpeg (Linux)")
            with tarfile.open(arch_path, "r:xz") as t:
                for m in t.getmembers():
                    if Path(m.name).name in ("ffmpeg", "ffprobe"):
                        f = t.extractfile(m)
                        if f:
                            dest = FFMPEG_DIR / Path(m.name).name
                            dest.write_bytes(f.read())
                            dest.chmod(0o755)
            arch_path.unlink(missing_ok=True)

        print(f"    OK  ffmpeg downloaded to {FFMPEG_DIR}")

    except Exception as e:
        print(f"    WARNING: Could not auto-download ffmpeg: {e}")
        print("    Audio extraction and video merging may fail.")
        print("    Install manually: https://ffmpeg.org/download.html")


# ─────────────────────────────────────────────────────────────────────────────
# Step 3: JS runtime (Deno) — required by newer yt-dlp for YouTube
# ─────────────────────────────────────────────────────────────────────────────

def _find_js_runtime() -> str:
    """Return path to node/deno/bun if available anywhere."""
    for exe_names in [["node.exe", "node"], ["deno.exe", "deno"], ["bun.exe", "bun"]]:
        for exe in exe_names:
            bundled = FFMPEG_DIR / exe
            if bundled.exists():
                return str(bundled)
            found = shutil.which(exe)
            if found:
                return found
    return ""


def ensure_js_runtime():
    """
    Make sure a JS runtime is available for yt-dlp.
    Priority: system node > system deno > bundled deno > auto-download deno.
    """
    existing = _find_js_runtime()
    if existing:
        print(f"    OK  JS runtime ready: {existing}")
        return

    # Auto-download Deno
    print("    No JS runtime found — downloading Deno automatically ...")
    print("         (Newer yt-dlp requires this for YouTube)")
    FFMPEG_DIR.mkdir(exist_ok=True)

    exe = "deno.exe" if IS_WIN else "deno"
    if IS_WIN:
        url = DENO_URLS["win"]
    elif IS_MAC:
        url = DENO_URLS["mac_arm"] if ARCH in ("arm64", "aarch64") else DENO_URLS["mac_x86"]
    elif IS_LIN:
        url = DENO_URLS["linux"]
    else:
        print("    WARNING: Unknown OS — cannot auto-download Deno.")
        return

    try:
        arch_path = BASE / "_deno.zip"
        dl(url, arch_path, "Deno (JS runtime)")
        with zipfile.ZipFile(arch_path) as z:
            for m in z.namelist():
                if Path(m).name in ("deno.exe", "deno"):
                    dest = FFMPEG_DIR / Path(m).name
                    dest.write_bytes(z.read(m))
                    if not IS_WIN:
                        dest.chmod(0o755)
                    print(f"    Extracted: {Path(m).name}")
        arch_path.unlink(missing_ok=True)
        print(f"    OK  Deno downloaded to {FFMPEG_DIR}")
    except Exception as e:
        print(f"    WARNING: Could not auto-download Deno: {e}")
        print("    YouTube downloads may show JS runtime warnings.")
        print("    Install Node.js (recommended): https://nodejs.org")


# ─────────────────────────────────────────────────────────────────────────────
# Step 4: Start server
# ─────────────────────────────────────────────────────────────────────────────

def open_browser(url: str):
    time.sleep(1.5)
    try:
        if IS_WIN:
            os.startfile(url)
        elif IS_MAC:
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])
    except Exception:
        pass


def start_server():
    import uvicorn
    local_ip = get_local_ip()

    print()
    print("=" * 56)
    print("  Server starting ...")
    print()
    print(f"  Local  :  http://localhost:{PORT}")
    print(f"  Network:  http://{local_ip}:{PORT}")
    print()
    print("  Open the Network URL on your phone/tablet!")
    print("  (Both devices must be on the same WiFi)")
    print()
    print("  Press Ctrl+C to stop.")
    print("=" * 56)
    print()

    threading.Thread(
        target=open_browser,
        args=(f"http://localhost:{PORT}",),
        daemon=True,
    ).start()

    uvicorn.run(
        "server:app",
        host=HOST,
        port=PORT,
        reload=False,
        log_level="warning",
        app_dir=str(BASE),
    )


# ─────────────────────────────────────────────────────────────────────────────

def main():
    banner()

    print(f"  OS     : {platform.system()} {platform.machine()}")
    print(f"  Python : {sys.version.split()[0]}")
    print(f"  Dir    : {BASE}")
    print()

    print("--- Step 1/4: Python packages ---")
    install_packages()
    print()

    print("--- Step 2/4: ffmpeg ---")
    ensure_ffmpeg()
    print()

    print("--- Step 3/4: JS runtime (for YouTube) ---")
    ensure_js_runtime()
    print()

    print("--- Step 4/4: Server ---")

    if not (BASE / "server.py").exists():
        print("ERROR: server.py not found.")
        sys.exit(1)

    if not (BASE / "static" / "index.html").exists():
        print("ERROR: static/index.html not found.")
        sys.exit(1)

    start_server()


if __name__ == "__main__":
    main()
