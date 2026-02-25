"""
YouTube Downloader Desktop Application
=====================================

A high-performance, standalone GUI for downloading YouTube videos and audio.
This application wraps the 'yt-dlp' command-line utility in a modern
Tkinter-based interface.

Key Architectural Decisions:
---------------------------
1. Single Instance Policy: Uses a local TCP socket to ensure only one instance
   of the application runs at a time.
2. Responsive Initialization: Implements a background import system for large
   dependencies (yt-dlp) to ensure the UI renders instantly upon launch.
3. Cross-Platform Consistency: Custom widget drawing is used to bypass macOS
   native styling limitations, ensuring a premium look on all platforms.
4. Integrated Binary Management: Bundles platform-specific ffmpeg binaries
   for post-processing (e.g., merging video and audio).
"""

import os, sys, shutil, threading, re, socket, tkinter as tk
from tkinter import filedialog, messagebox
import subprocess, json, urllib.request, webbrowser

# --- Application Identification and Update Configuration ---
APP_VERSION = '1.0.0'

# The application checks this URL on startup for a version.json file.
# The JSON should include 'version', 'mac_url', 'win_url', and 'changelog'.
UPDATE_CHECK_URL = 'https://raw.githubusercontent.com/Faysal1000/YouTube-Video-Downloader/main/version.json'

# --- Network Identification ---
# A modern browser User-Agent ensures that requests from the application 
# are not incorrectly flagged as bot traffic/forbidden.
GLOBAL_USER_AGENT = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/122.0.0.0 Safari/537.36'
)

# --- Single Instance Lock Persistence ---
# To prevent data corruption or UI confusion, we only allow one copy of the 
# app to run. We attempt to bind a local socket to port 47216. If binding
# fails, it means another instance of this application is already active.
_LOCK_PORT = 47216
_lock_sock = None

def _acquire_single_instance():
    """
    Attempts to create a persistent lock on a local port.
    Returns:
        bool: True if this instance successfully claimed the lock, 
              False if another instance is already running.
    """
    global _lock_sock
    try:
        _lock_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # Prevent the port from staying in TIME_WAIT state
        _lock_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        _lock_sock.bind(('127.0.0.1', _LOCK_PORT))
        return True
    except OSError:
        return False

# --- Instance Check and Activation ---
if not _acquire_single_instance():
    # If we are on macOS and an instance is already running, we try to 
    # bring that existing instance to the foreground before exiting.
    if sys.platform == 'darwin':
        try:
            subprocess.run(['osascript', '-e',
                'tell application "YT Downloader" to activate'], check=False)
        except Exception:
            pass
    try:
        # Create a hidden dummy root to show the information dialog
        _r = tk.Tk(); _r.withdraw()
        messagebox.showinfo('Already Running',
            'YouTube Downloader is already open.\nPlease check your Dock or taskbar for the active window.')
        _r.destroy()
    except Exception:
        pass
    sys.exit(0)

# --- Resource Path Resolution ---
def res(rel):
    """
    Determines the absolute path to a resource file. handles both standard 
    execution (via Python) and frozen execution (via PyInstaller).
    
    Args:
        rel (str): Relative path to the resource from the package root.
    Returns:
        str: Absolute path to the resource.
    """
    # _MEIPASS is a temporary folder where PyInstaller unpacks bundled files
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)

# --- Windows Shell Optimization ---
try:
    # Set a unique AppUserModelID so Windows treats this as its own taskbar 
    # entity, allowing for correct icon grouping and pinning.
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        u'faysal.ytdl.app.pro.v1')
except Exception:
    pass

def setup_ffmpeg():
    """
    Locates the bundled ffmpeg binaries and adds them to the system PATH.
    This ensures yt-dlp can find the encoders needed for media merging.
    """
    d = res('ffmpeg_bin')
    if os.path.isdir(d):
        os.environ['PATH'] = d + os.pathsep + os.environ.get('PATH', '')
    return d

FFMPEG_DIR = setup_ffmpeg()

# Note: yt_dlp is imported lazily in a background thread later.
# This prevents the initial UI window from hanging while Python compiles
# the large yt_dlp module hierarchy.
yt_dlp     = None
HAVE_YTDLP = False

# --- Visual Design System ---
QUALITIES  = ['best','4320p','2160p','1440p','1080p','720p','480p','360p','240p','144p']
VIDEO_FMTS = ['mp4','mkv','webm']
AUDIO_FMTS = ['mp3','m4a','opus','wav','flac']

# Professional dark theme color palette
BG            = '#0C0C0E'   # Primary application background
PANEL         = '#111115'   # Sidebars and header panels
CARD          = '#17171D'   # Input fields and cards
BORDER        = '#2A2A38'   # Subtle dividers
BORDER2       = '#3A3A50'   # Focused borders or active states
FG            = '#F5F5FA'   # Primary text color
FG2           = '#C8C8D8'   # Secondary/Dimmer text
FG3           = '#9090A8'   # Disabled/Hint text
ACCENT        = '#7B5FFF'   # Brand purple
ACCENT_L      = '#B09FFF'   # Light accent for highlights
ACCENT_D      = '#5B3FD0'   # Dark accent for active buttons
ACCENT_DARK_BG= '#1A1530'   # Background for icon boxes
CYAN          = '#00E8DA'   # Information messages
GREEN         = '#30E882'   # Success messages
RED           = '#FF5577'   # Error messages
AMBER         = '#FFC040'   # Warning/Notice messages

# ── Buttons: each one has a DISTINCT solid color so you can always see it ────
BTN_PRIMARY_BG     = '#6C47FF'   # bold purple
BTN_PRIMARY_FG     = '#FFFFFF'   # white
BTN_PRIMARY_HOV    = '#8060FF'
BTN_PRIMARY_HOV_FG = '#FFFFFF'

BTN_SECONDARY_BG     = '#1A6B8A'  # teal-blue — clearly different from bg
BTN_SECONDARY_FG     = '#FFFFFF'  # white text
BTN_SECONDARY_HOV    = '#1E85AD'
BTN_SECONDARY_HOV_FG = '#FFFFFF'

BTN_STOP_BG      = '#A02040'   # solid red — unmistakable
BTN_STOP_FG      = '#FFFFFF'   # white text
BTN_STOP_HOV     = '#C0284E'
BTN_STOP_HOV_FG  = '#FFFFFF'

BTN_GHOST_BG     = '#2A2A3E'   # dark but visibly different from page bg
BTN_GHOST_FG     = '#D0D0E8'   # light text — clearly readable
BTN_GHOST_HOV    = '#363650'
BTN_GHOST_HOV_FG = '#FFFFFF'

# --- Typography Configuration ---
import tkinter.font as tkfont
_FAMILIES = []

def _ff(*names):
    """
    Selects the first available font family from a prioritized list.
    Ensures consistent looks across Windows (Segoe UI), macOS (SF Pro), and Linux.
    """
    global _FAMILIES
    if not _FAMILIES:
        try: _FAMILIES = list(tkfont.families())
        except: _FAMILIES = []
    for n in names:
        if n in _FAMILIES: return n
    return names[-1]

# Defined font styles for different UI elements
F_DISPLAY = (_ff('Segoe UI','SF Pro Display','Helvetica Neue','Helvetica'), 16, 'bold')
F_BODY    = (_ff('Segoe UI','SF Pro Text',   'Helvetica Neue','Helvetica'), 12)
F_MONO    = (_ff('Cascadia Code','Consolas','Menlo','Courier New'), 11)
F_MONO_S  = (_ff('Cascadia Code','Consolas','Menlo','Courier New'), 11)
F_LABEL   = (_ff('Segoe UI','SF Pro Text',   'Helvetica Neue','Helvetica'), 10, 'bold')
F_BTN     = (_ff('Segoe UI','SF Pro Text',   'Helvetica Neue','Helvetica'), 11, 'bold')
F_BTN_LG  = (_ff('Segoe UI','SF Pro Text',   'Helvetica Neue','Helvetica'), 13, 'bold')


# --- High-Level UI Component Factories ---

def make_btn(parent, text, cmd, bg, fg, hover_bg=None, hover_fg=None,
             font=None, padx=14, pady=8, **kw):
    """
    Creates a custom button-like widget using nested Frames and a Label.
    
    RATIONALE:
    Standard tkinter.Button widgets on macOS are heavily restricted by the 
    system's native 'Aqua' theme, preventing custom background colors.
    This composite widget bypasses those restrictions, allowing for a fully 
    branded experience while maintaining accessibility and hover effects.
    """
    hbg = hover_bg or bg
    hfg = hover_fg or fg

    # Outer frame acts as the border/hit-area
    outer = tk.Frame(parent, bg=bg, cursor='hand2', padx=2, pady=2)
    # Inner frame acts as the button body
    inner = tk.Frame(outer, bg=bg, cursor='hand2')
    inner.pack(fill='both', expand=True)
    # Label provides the text and internal padding
    lbl = tk.Label(inner, text=text, bg=bg, fg=fg,
                   font=font or F_BTN, padx=padx, pady=pady,
                   cursor='hand2')
    lbl.pack(fill='both', expand=True)

    def _on(e):
        """Applies hover states."""
        outer.config(bg=hbg); inner.config(bg=hbg); lbl.config(bg=hbg, fg=hfg)
    def _off(e):
        """Restores default states."""
        outer.config(bg=bg);  inner.config(bg=bg);  lbl.config(bg=bg,  fg=fg)
    def _click(e):
        """Handles the click event with a brief visual feedback delay."""
        _on(e)
        outer.after(80, cmd)

    # Bind interactions to all constituent parts
    for w in (outer, inner, lbl):
        w.bind('<Enter>',           _on)
        w.bind('<Leave>',           _off)
        w.bind('<ButtonRelease-1>', _click)

    # Internal reference to the original Frame.config method
    _outer_config = outer.config.__func__ 

    def _cfg(**opts):
        """
        Custom configuration wrapper to handle 'state', 'bg', and 'fg' 
        for the entire composite component.
        """
        s      = opts.pop('state', None)
        new_bg = opts.pop('bg',    None)
        new_fg = opts.pop('fg',    None)
        
        if s == 'disabled':
            for w in (outer, inner, lbl):
                w.unbind('<Enter>'); w.unbind('<Leave>'); w.unbind('<ButtonRelease-1>')
            lbl.configure(fg=FG3) # Use dim text for disabled state
        elif s == 'normal':
            for w in (outer, inner, lbl):
                w.bind('<Enter>',           _on)
                w.bind('<Leave>',           _off)
                w.bind('<ButtonRelease-1>', _click)
        
        if new_bg:
            # Configure all backgrounds to match
            outer.configure(bg=new_bg)
            inner.configure(bg=new_bg)
            lbl.configure(bg=new_bg)
        if new_fg:
            lbl.configure(fg=new_fg)

    # Override the config method of the outer frame
    outer.config = _cfg
    return outer

def BG3_SAFE(): return CARD


# --- Background Tasks ---
# --- Asynchronous Dependency Management ---

def _import_yt_dlp_async(on_done):
    """
    Imports the 'yt_dlp' module in a background thread.
    
    RATIONALE:
    yt-dlp has a massive dependency tree and complex monkeypatching logic. 
    Importing it on the main thread takes 1-3 seconds, which feels laggy.
    By importing it asynchronously, we can show a splash screen and animate 
    the UI while the engine loads.
    """
    global yt_dlp, HAVE_YTDLP
    try:
        import yt_dlp as _yd
        yt_dlp     = _yd
        HAVE_YTDLP = True
    except ImportError:
        HAVE_YTDLP = False
    
    # Notify the main thread that we are finished
    on_done()


# ══════════════════════════════════════════════════════════════════════════════
#  JS / EJS HELPERS
# ══════════════════════════════════════════════════════════════════════════════
# --- Video Extraction Challenge Helpers (JS Runtimes) ---

def _find_js_runtime():
    """
    Scans for an available JavaScript runtime (Node, Deno, or Bun).
    
    Some YouTube videos use 'signature scrambling' or extraction logic that 
    requires a JS engine to solve. We bundle Deno/Node for this purpose.
    """
    # Priority: Bundled runtime > System path
    for r in ['node.exe','node','deno.exe','deno','bun.exe','bun']:
        p = os.path.join(FFMPEG_DIR, r)
        if os.path.isfile(p):
            name = 'node' if 'node' in r else ('deno' if 'deno' in r else 'bun')
            return name, os.path.abspath(p)
        
        # Fallback to checking the user's system
        w = shutil.which(r)
        if w:
            name = 'node' if 'node' in r else ('deno' if 'deno' in r else 'bun')
            return name, os.path.abspath(w)
    return None, None

def _ensure_ejs_installed():
    """
    Auto-installs 'yt-dlp-ejs' if missing. This is a helper plugin 
    that allows yt-dlp to solve modern YouTube challenges.
    """
    try:
        import importlib; importlib.import_module('yt_dlp_ejs')
    except ImportError:
        try:
            # Silent background install
            subprocess.run([sys.executable,'-m','pip','install','--quiet','yt-dlp-ejs'],
                           check=True, capture_output=True, timeout=60)
        except Exception: 
            pass

def _get_runtime_opts():
    """
    Constructs the yt-dlp options required to enable external JS extraction.
    """
    if not HAVE_YTDLP: return {}
    
    name, path = _find_js_runtime()
    if not name or not path: return {}

    # Add the runtime's directory to PATH so subprocesses can find it
    rdir = os.path.dirname(path)
    if rdir not in os.environ.get('PATH',''):
        os.environ['PATH'] = rdir + os.pathsep + os.environ.get('PATH','')

    try:
        # Inform yt-dlp which JS engine to use
        cli_args = ['--js-runtimes', name]
        try:
            # If the remote components plugin is present, use it
            yt_dlp.parse_options(['--remote-components','ejs:github'])
            cli_args += ['--remote-components','ejs:github']
        except Exception: 
            pass
        
        _, _, _, parsed = yt_dlp.parse_options(cli_args)
        result = {}
        for k in ('js_runtimes','remote_components'):
            if k in parsed and parsed[k] is not None:
                result[k] = parsed[k]
        return result
    except Exception: 
        return {}

# --- yt-dlp Configuration Builder ---

def build_opts(dl_type, quality, afmt, vfmt, outdir, hook, playlist=False):
    """
    Translates UI settings into a dictionary of options for the yt-dlp engine.
    
    Args:
        dl_type (str): 'video' or 'audio'
        quality (str): Target vertical resolution (e.g., '1080p')
        afmt (str): Audio container format
        vfmt (str): Video container format
        outdir (str): Destination directory
        hook (callable): Progress update callback
        playlist (bool): Whether to allow multi-video downloads
    """
    # Define the file naming template
    outtmpl = os.path.join(outdir,
        '%(playlist_index)s-%(title)s.%(ext)s' if playlist else '%(title)s.%(ext)s')
    
    # Baseline options: logging setup, progress tracking, and binary locations
    opts = {
        'outtmpl': outtmpl, 
        'quiet': True, 
        'no_warnings': True,
        'progress_hooks': [hook], 
        'noplaylist': not playlist,
        'user_agent': GLOBAL_USER_AGENT,
        'http_headers': {
            'User-Agent': GLOBAL_USER_AGENT,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
        }
    }
    
    if os.path.isdir(FFMPEG_DIR): 
        opts['ffmpeg_location'] = FFMPEG_DIR

    # AUDIO ONLY PATH
    if dl_type == 'audio':
        opts.update(_get_runtime_opts())
        opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': afmt,
                'preferredquality': '0' # VBR highest quality
            }]
        })
        return opts

    # VIDEO PATH
    # We construct a format selector string that prioritizes the user's resolution choice.
    if quality == 'best':
        fmt = f'bestvideo[ext={vfmt}]+bestaudio/bestvideo+bestaudio/best'
    else:
        h = quality.replace('p','')
        # Look for best video AT or BELOW the selected resolution, 
        # falling back to best available if none found.
        fmt = (f'bestvideo[height<={h}][ext={vfmt}]+bestaudio'
               f'/bestvideo[height<={h}]+bestaudio/bestvideo+bestaudio/best')
    
    opts.update({'format': fmt, 'merge_output_format': vfmt})
    opts.update(_get_runtime_opts())
    return opts


# --- Splash Screen Overlay ---
# Displays a loading animation while dependencies like yt-dlp are imported.
# --- Startup Splash Screen Implementation ---

class Splash:
    """
    An overlay component that provides visual feedback during the 
    asynchronous loading phase. It handles an indeterminate progress 
    animation and status text.
    """
    # Animation frames for the 'bouncing dots' effect
    _FRAMES = [
        ('⬤', '◯', '◯'),
        ('◯', '⬤', '◯'),
        ('◯', '◯', '⬤'),
        ('⬤', '⬤', '◯'),
        ('◯', '⬤', '⬤'),
        ('⬤', '◯', '⬤'),
    ]

    def __init__(self, parent):
        # Create a full-window container
        self._frame = tk.Frame(parent, bg=BG)
        self._frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        # Centered branding column
        col = tk.Frame(self._frame, bg=BG)
        col.place(relx=0.5, rely=0.44, anchor='center')

        # Animated dots row
        dot_row = tk.Frame(col, bg=BG)
        dot_row.pack(pady=(0, 16))
        self._d = [
            tk.Label(dot_row, text='⬤', bg=BG, fg=ACCENT, font=(F_DISPLAY[0], 26)),
            tk.Label(dot_row, text='◯', bg=BG, fg=BORDER2, font=(F_DISPLAY[0], 26)),
            tk.Label(dot_row, text='◯', bg=BG, fg=BORDER2, font=(F_DISPLAY[0], 26)),
        ]
        for d in self._d:
            d.pack(side='left', padx=6)

        tk.Label(col, text='YouTube Downloader', bg=BG, fg=FG, font=F_DISPLAY).pack()
        tk.Label(col, text='Loading dependencies...', bg=BG, fg=FG3, font=F_BODY).pack(pady=(5, 0))

        # Horizontal progress indicator
        self._bar_canvas = tk.Canvas(col, height=3, width=220,
                                      bg=BORDER, highlightthickness=0)
        self._bar_canvas.pack(pady=(14, 0))
        self._bar_w = 0
        self._bar_growing = True

        self._fi = 0
        self._animate()

    def _animate(self):
        """Standard recursive animation loop using .after()."""
        if not self._frame.winfo_exists(): 
            return
            
        # Update bouncing dots
        dots = self._FRAMES[self._fi % len(self._FRAMES)]
        for i, d in enumerate(self._d):
            active = dots[i] == '⬤'
            d.config(text=dots[i], fg=ACCENT if active else BORDER2)
        self._fi += 1

        # Indeterminate 'breathing' progress bar animation
        W = 220
        if self._bar_growing:
            self._bar_w = min(self._bar_w + 8, W)
            if self._bar_w >= W: self._bar_growing = False
        else:
            self._bar_w = max(self._bar_w - 8, 0)
            if self._bar_w <= 0: self._bar_growing = True
            
        self._bar_canvas.delete('all')
        self._bar_canvas.create_rectangle(0, 0, W, 3, fill=BORDER, outline='')
        self._bar_canvas.create_rectangle(0, 0, self._bar_w, 3, fill=ACCENT, outline='')

        # Schedule next frame (approx 5.5 FPS for a smooth but low-resource look)
        self._aid = self._frame.after(180, self._animate)

    def dismiss(self):
        """Cleans up the overlay and cancels internal loops."""
        try: 
            self._frame.after_cancel(self._aid)
        except Exception: 
            pass
        self._frame.destroy()


# --- Main Application Controller ---

class App:
    """
    The heart of the application. Manages the main window, UI state, 
    background threads, and the download orchestration.
    """
    def __init__(self, root):
        self.root   = root
        self._ready = False

        # Basic window configuration
        root.title('YT Downloader')
        root.geometry('580x650')
        root.resizable(True, True)
        root.minsize(450, 400)
        root.configure(bg=BG)

        # macOS: Custom window styling to ensure it feels native yet professional
        if sys.platform == 'darwin':
            try:
                # Use a standard documentation window style with close/collapse buttons
                root.tk.call('::tk::unsupported::MacWindowStyle', 'style',
                             root._w, 'document', 'closeBox collapseBox')
            except Exception:
                pass
            # Integrate with the macOS system 'Quit' menu
            try:
                root.createcommand('tk::mac::Quit', root.destroy)
            except Exception:
                pass

        # Load application icon (ICO for Windows taskbar consistency)
        try:
            ic = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.ico')
            if not os.path.isfile(ic): 
                ic = res('icon.ico')
            if os.path.isfile(ic):
                root.iconbitmap(default=ic)
                root.iconbitmap(ic)
                try: 
                    root.tk.call('wm', 'iconbitmap', root._w, ic)
                except Exception: 
                    pass
        except Exception: 
            pass

        # --- Internal State Tracks ---
        self.url      = tk.StringVar()
        self.outdir   = tk.StringVar(value=os.path.expanduser('~/Downloads'))
        self.dl_type  = tk.StringVar(value='video')
        self.quality  = tk.StringVar(value='1080p')
        self.vfmt     = tk.StringVar(value='mp4')
        self.afmt     = tk.StringVar(value='mp3')
        self.pct      = tk.DoubleVar(value=0)
        self.status   = tk.StringVar(value='Initialising...')
        self.playlist = tk.BooleanVar(value=False)
        self._dl      = False # True if a download is currently active
        self._stop    = False # Set to True to signal the engine to abort
        self._log_visible = False

        # UI element references (populated in _build_ui)
        self.dlb = self.log = self.pc = self.p_text = None
        self.lw  = self.log_toggle = self.log_sec  = None
        self.qm  = self.vfr = self.afr             = None

        # Phase 1: Build the primary UI immediately.
        # This makes the window appear instantly, providing feedback to the user.
        self._build_ui()
        # Reset geometry to requested size after building widgets
        self.root.geometry("") 

        # Temporarily disable the download button until dependencies load
        self.dlb.config(state='disabled', bg=ACCENT_D, fg='#7060AA')

        # Phase 2: Show the splash screen overlay.
        # This sits on top of the 'empty' UI while yt-dlp loads in the background.
        self._splash = Splash(self.root)

        # Ensure the window is shown and focused
        self.root.update_idletasks()
        self.root.deiconify()
        if sys.platform == 'darwin':
            self.root.lift()
            self.root.focus_force()

        # Start the background import of the heavy yt-dlp engine.
        threading.Thread(
            target=_import_yt_dlp_async,
            args=(lambda: self.root.after(0, self._finish_init),),
            daemon=True
        ).start()

    # ── Called on main thread once yt_dlp import finishes ────────────────────
    def _finish_init(self):
        """
        Transition from splash screen to the main functional UI.
        Triggered once the yt-dlp engine is fully loaded in the background.
        """
        self._splash.dismiss()
        self._ready = True
        
        # Adjust UI state based on whether engine loaded successfully
        if HAVE_YTDLP:
            self.dlb.config(state='normal', bg=BTN_PRIMARY_BG, fg=BTN_PRIMARY_FG)
            self.status.set('Ready')
        else:
            self.dlb.config(state='disabled', bg='#2A1A1A', fg='#664444')
            self.status.set('Engine loading failed. Check logs.')

        # Perform initial state checks and look for application updates
        self.root.after(0, self._check)
        threading.Thread(target=self._check_for_updates, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        """
        Assembles the various sections of the application interface.
        Uses a vertically-stacked layout with a Header, Footer, and Body.
        """

        # --- Header Section (App Name and Version) ---
        hdr = tk.Frame(self.root, bg=PANEL, height=64)
        hdr.pack(fill='x', side='top')
        hdr.pack_propagate(False)

        # Decorative left accent strip
        tk.Frame(hdr, bg=ACCENT, width=3).pack(side='left', fill='y')

        # Icon box
        icon_f = tk.Frame(hdr, bg=ACCENT_DARK_BG, width=34, height=34)
        icon_f.pack(side='left', padx=(14, 10), pady=9)
        icon_f.pack_propagate(False)
        tk.Label(icon_f, text="|>", bg=ACCENT_DARK_BG, fg=ACCENT_L,
                 font=(F_BODY[0], 14, 'bold')).place(relx=.5, rely=.5, anchor='center')

        # App title and developer credit
        title_col = tk.Frame(hdr, bg=PANEL)
        title_col.pack(side='left', fill='y', pady=8)
        tk.Label(title_col, text='YouTube Downloader', bg=PANEL, fg=FG,
                 font=F_DISPLAY).pack(anchor='w')
        tk.Label(title_col, text='by Faysal', bg=PANEL, fg=FG3,
                 font=(F_BODY[0], 10)).pack(anchor='w')

        # Version display badge
        pro_f = tk.Frame(hdr, bg=ACCENT_D, padx=7, pady=2)
        pro_f.pack(side='right', padx=16, pady=18)
        tk.Label(pro_f, text=f'v{APP_VERSION}', bg=ACCENT_D, fg='#FFFFFF',
                 font=(F_MONO[0], 9, 'bold')).pack()

        # Division line
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill='x', side='top')

        # --- Footer Section (Main Action Controls) ---
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill='x', side='bottom')
        footer = tk.Frame(self.root, bg=PANEL, pady=10)
        footer.pack(fill='x', side='bottom')

        # Playlist mode toggle (Custom Canvas Checkbox)
        pl_wrap = tk.Frame(footer, bg=PANEL, cursor='hand2')
        pl_wrap.pack(side='left', padx=(16, 8))

        chk_row = tk.Frame(pl_wrap, bg=PANEL, cursor='hand2')
        chk_row.pack()
        chk_c = tk.Canvas(chk_row, width=18, height=18, bg=PANEL,
                          highlightthickness=0, cursor='hand2')
        chk_c.pack(side='left', padx=(0, 6))
        tk.Label(chk_row, text='Playlist', bg=PANEL, fg=FG,
                 font=F_BODY, cursor='hand2').pack(side='left')

        def _draw_chk():
            """Renders the custom checkbox state."""
            chk_c.delete('all')
            if self.playlist.get():
                chk_c.create_rectangle(1, 1, 17, 17, fill=ACCENT, outline=ACCENT)
                # Draw white checkmark
                chk_c.create_line(4, 9, 7, 13, fill='#FFFFFF', width=2)
                chk_c.create_line(7, 13, 14, 5, fill='#FFFFFF', width=2)
            else:
                chk_c.create_rectangle(1, 1, 17, 17, fill='', outline=FG3, width=2)

        def _toggle_chk(e=None):
            self.playlist.set(not self.playlist.get())
            _draw_chk()

        # Bind events to both the box and the label
        for w in (chk_row, chk_c):
            w.bind('<ButtonRelease-1>', _toggle_chk)
        chk_row.winfo_children()[-1].bind('<ButtonRelease-1>', _toggle_chk)
        _draw_chk()

        # Primary Action: Start Download
        self.dlb = make_btn(footer, 'DOWNLOAD', self._start,
                            BTN_PRIMARY_BG, BTN_PRIMARY_FG,
                            hover_bg=BTN_PRIMARY_HOV, hover_fg=BTN_PRIMARY_HOV_FG,
                            font=F_BTN_LG, padx=20, pady=8)
        self.dlb.pack(side='left', padx=4)

        # Control: Abort Download
        make_btn(footer, 'Stop', self._stop_dl,
                 BTN_STOP_BG, BTN_STOP_FG,
                 hover_bg=BTN_STOP_HOV, hover_fg=BTN_STOP_HOV_FG,
                 font=F_BTN, padx=14, pady=8).pack(side='left', padx=2)

        # Utility: Open Output Directory
        make_btn(footer, 'Folder', self._open,
                 BTN_SECONDARY_BG, BTN_SECONDARY_FG,
                 hover_bg=BTN_SECONDARY_HOV, hover_fg=BTN_SECONDARY_HOV_FG,
                 font=F_BTN, padx=12, pady=8).pack(side='left', padx=2)

        # Log Management: Clear Console Output
        make_btn(footer, 'Clear', self._clear_log,
                 BTN_GHOST_BG, BTN_GHOST_FG,
                 hover_bg=BTN_GHOST_HOV, hover_fg=BTN_GHOST_HOV_FG,
                 font=(F_BODY[0], 11), padx=8, pady=8).pack(side='right', padx=16)

        # --- Body Section (Configuration Inputs) ---
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill='both', expand=True, padx=18, pady=(12, 0))

        # Input: YouTube URL
        self._label(body, 'VIDEO URL')
        url_row = tk.Frame(body, bg=BG)
        url_row.pack(fill='x', pady=(3, 10))
        url_wrap = tk.Frame(url_row, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        url_wrap.pack(side='left', fill='x', expand=True)
        url_entry = tk.Entry(url_wrap, textvariable=self.url, bg=CARD, fg=FG,
                               insertbackground=ACCENT_L, relief='flat',
                               font=F_MONO, bd=8, highlightthickness=0)
        url_entry.pack(fill='x', expand=True)
        self._bind_focus_highlight(url_wrap, url_entry)
        make_btn(url_row, 'Paste', self._paste,
                 BTN_SECONDARY_BG, BTN_SECONDARY_FG,
                 hover_bg=BTN_SECONDARY_HOV, hover_fg=BTN_SECONDARY_HOV_FG,
                 font=F_BODY, padx=10, pady=8).pack(side='left', padx=6)

        # Input: Destination Directory
        self._label(body, 'SAVE TO')
        dir_row = tk.Frame(body, bg=BG)
        dir_row.pack(fill='x', pady=(3, 10))
        dir_wrap = tk.Frame(dir_row, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        dir_wrap.pack(side='left', fill='x', expand=True)
        dir_entry = tk.Entry(dir_wrap, textvariable=self.outdir, bg=CARD, fg=FG2,
                               insertbackground=ACCENT_L, relief='flat',
                               font=(F_BODY[0], 9), bd=8)
        dir_entry.pack(fill='x', expand=True)
        self._bind_focus_highlight(dir_wrap, dir_entry)
        make_btn(dir_row, 'Browse', self._browse,
                 BTN_SECONDARY_BG, BTN_SECONDARY_FG,
                 hover_bg=BTN_SECONDARY_HOV, hover_fg=BTN_SECONDARY_HOV_FG,
                 font=F_BODY, padx=10, pady=8).pack(side='left', padx=6)

        # Options: Extraction Configuration
        self._label(body, 'OPTIONS')
        opt = tk.Frame(body, bg=BG)
        opt.pack(fill='x', pady=(3, 12))

        # Option: Download Mode (Video/Audio)
        tc = self._pill_card(opt, 'TYPE')
        tc.pack(side='left', fill='both', expand=True, padx=(0, 6))
        for v, lbl in [('video','Video'),('audio','Audio')]:
            self._radio(tc, lbl, self.dl_type, v, self._on_type)

        # Option: Vertical Resolution (Video only)
        qc = self._pill_card(opt, 'QUALITY')
        qc.pack(side='left', fill='both', expand=True, padx=(0, 6))
        self.qm = self._styled_menu(qc, self.quality, QUALITIES)
        self.qm.pack(padx=10, pady=5, fill='x')

        # Option: Container Format selection
        fc = self._pill_card(opt, 'FORMAT')
        fc.pack(side='left', fill='both', expand=True)
        
        # Video format row
        self.vfr = tk.Frame(fc, bg=CARD)
        self.vfr.pack(fill='x', padx=8, pady=(2, 1))
        tk.Label(self.vfr, text='V', bg=CARD, fg=FG2, font=F_LABEL, width=2).pack(side='left')
        self._styled_menu(self.vfr, self.vfmt, VIDEO_FMTS).pack(side='left', fill='x', expand=True)
        
        # Audio format row
        self.afr = tk.Frame(fc, bg=CARD)
        self.afr.pack(fill='x', padx=8, pady=(1, 5))
        tk.Label(self.afr, text='A', bg=CARD, fg=FG2, font=F_LABEL, width=2).pack(side='left')
        self._styled_menu(self.afr, self.afmt, AUDIO_FMTS).pack(side='left', fill='x', expand=True)

        # --- Feedback: Progress and Status ---
        self._label(body, 'PROGRESS')
        status_row = tk.Frame(body, bg=BG)
        status_row.pack(fill='x', pady=(3, 4))
        tk.Label(status_row, textvariable=self.status, bg=BG, fg=FG2,
                 font=F_MONO_S, anchor='w').pack(side='left', fill='x', expand=True)
        self.p_text = tk.Label(status_row, text='0%', bg=BG, fg=ACCENT_L,
                                font=(F_MONO[0], 12, 'bold'))
        self.p_text.pack(side='right')
        
        # Graphical progress bar
        self.pc = tk.Canvas(body, height=6, bg=BG3_SAFE(), highlightthickness=0)
        self.pc.pack(fill='x', pady=0)
        self.pc.bind('<Configure>', lambda e: self._bar())

        # --- Debugging: Console Logs (Collapsible) ---
        self.log_sec = tk.Frame(body, bg=BG)
        self.log_sec.pack(fill='x', side='top')
        lhdr = tk.Frame(self.log_sec, bg=BG)
        lhdr.pack(fill='x', pady=6)
        self.log_toggle = make_btn(lhdr, '[+] Show Logs', self._toggle_log,
                                   BTN_GHOST_BG, FG3,
                                   hover_bg=BTN_GHOST_HOV, hover_fg=ACCENT_L,
                                   font=(F_LABEL[0], 10, 'bold'), padx=10, pady=2)
        self.log_toggle.pack(anchor='center')

        # Console text area inside a scrollable frame
        self.lw = tk.Frame(self.log_sec, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        sb = tk.Scrollbar(self.lw, bg=BG, troughcolor=CARD, width=8, bd=0,
                          highlightthickness=0, relief='flat')
        sb.pack(side='right', fill='y', padx=(0, 2))
        self.log = tk.Text(self.lw, bg=CARD, fg=FG2, font=F_MONO_S, relief='flat',
                           yscrollcommand=sb.set, state='disabled', height=6, width=1,
                           bd=6, selectbackground=BORDER2, insertbackground=ACCENT_L)
        self.log.pack(fill='both', expand=True)
        sb.config(command=self.log.yview)
        
        # Log coloring tags
        self.log.tag_config('ok',   foreground=GREEN)
        self.log.tag_config('err',  foreground=RED)
        self.log.tag_config('warn', foreground=AMBER)
        self.log.tag_config('info', foreground=CYAN)
        self.log.tag_config('dim',  foreground=FG3)

    # --- Low-Level Widget Helpers ---

    def _label(self, parent, text):
        """Creates a styled section label with a decorative horizontal line."""
        row = tk.Frame(parent, bg=BG)
        row.pack(fill='x', pady=(4, 0))
        tk.Label(row, text=text, bg=BG, fg=ACCENT_L, font=F_LABEL).pack(side='left')
        # Decorative line to visually separate sections
        tk.Frame(row, bg=BORDER, height=1).pack(side='left', fill='x', expand=True,
                                                 padx=(8, 0), pady=5)

    def _pill_card(self, parent, title):
        """Creates a 'card' container for options with a small header label."""
        f = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        tk.Label(f, text=title, bg=CARD, fg=ACCENT_L, font=F_LABEL).pack(anchor='w', padx=12, pady=(10, 4))
        return f

    def _radio(self, parent, label, var, value, cmd=None):
        """
        Creates a custom radio button using Canvas and Labels.
        
        RATIONALE:
        macOS native radio buttons cannot be easily styled (changed from blue). 
        This implementation uses a small Canvas to draw a custom 'dot' indicator,
        ensuring the brand's accent colors are visible on all operating systems.
        """
        row = tk.Frame(parent, bg=CARD, cursor='hand2')
        row.pack(anchor='w', padx=12, pady=(2, 4))

        # Dot indicator drawn on a small Canvas
        dot_c = tk.Canvas(row, width=16, height=16, bg=CARD,
                          highlightthickness=0, cursor='hand2')
        dot_c.pack(side='left', padx=(0, 6))

        lbl = tk.Label(row, text=label, bg=CARD, fg=FG,
                       font=F_BODY, cursor='hand2')
        lbl.pack(side='left')

        def _draw():
            """Renders the radio 'dot' based on the current selection state."""
            dot_c.delete('all')
            if var.get() == value:
                # Active state: Solid accent outer, white inner dot
                dot_c.create_oval(1, 1, 14, 14, fill=ACCENT, outline=ACCENT)
                dot_c.create_oval(4, 4, 11, 11, fill='#FFFFFF', outline='')
            else:
                # Inactive state: Subtle border outline
                dot_c.create_oval(1, 1, 14, 14, fill='', outline=FG3, width=2)

        def _select(e=None):
            """Updates the value and triggers a redraw of all sibling radios."""
            var.set(value)
            _draw()
            if cmd: 
                cmd()
            # Redraw all children of the parent to ensure only one is 'active'
            for child in parent.winfo_children():
                if hasattr(child, '_radio_redraw'):
                    child._radio_redraw()

        # Attach redraw helper to the row object for external access
        row._radio_redraw = _draw
        
        # Bind interactions
        for w in (row, dot_c, lbl):
            w.bind('<ButtonRelease-1>', _select)

        # Ensure we sync if the variable is changed externally
        var.trace_add('write', lambda *_: _draw())
        _draw()

    def _styled_menu(self, parent, var, choices):
        """
        Creates a styled dropdown menu using OptionMenu-like logic but with 
        Menubutton to allow for complete color control.
        """
        mb = tk.Menubutton(parent, textvariable=var,
                           bg='#2C3A50', fg='#FFFFFF',
                           font=F_BODY, relief='flat', bd=0,
                           activebackground=ACCENT_D, activeforeground='#FFFFFF',
                           highlightthickness=1, highlightbackground=BORDER2,
                           padx=10, pady=6, cursor='hand2', direction='below')
        menu = tk.Menu(mb, tearoff=False,
                       bg='#1E2A3A', fg='#FFFFFF', font=F_BODY,
                       activebackground=ACCENT, activeforeground='#FFFFFF',
                       relief='flat', bd=0)
        for c in choices:
            menu.add_command(label=c, command=lambda v=c: var.set(v))
        mb['menu'] = menu
        return mb

    def _bind_focus_highlight(self, frame, entry):
        """Brightens the parent frame's border when the entry gain focus."""
        entry.bind('<FocusIn>',  lambda e: frame.config(highlightbackground=ACCENT))
        entry.bind('<FocusOut>', lambda e: frame.config(highlightbackground=BORDER))

    # --- Event and Action Handlers ---

    def _toggle_log(self):
        """Shows or hides the collapsible console log area."""
        curr_w = self.root.winfo_width()
        if self._log_visible:
            self.lw.pack_forget()
            self.log_toggle.config(text='[+] Show Logs')
        else:
            self.lw.pack(fill='x', pady=0)
            self.log_toggle.config(text='[-] Hide Logs')
        self._log_visible = not self._log_visible
        
        # Ensure window resizes to accommodate the log without affecting width
        self.root.update_idletasks()
        self.root.geometry(f"{curr_w}x{self.root.winfo_reqheight()}")

    def _on_type(self):
        """Enables/disables resolution options when switching video/audio modes."""
        self.qm.config(state='normal' if self.dl_type.get() == 'video' else 'disabled')

    def _paste(self):
        """Attempts to read from system clipboard and update the URL field."""
        try: 
            self.url.set(self.root.clipboard_get())
        except Exception: 
            pass

    def _browse(self):
        """Displays a directory selection dialog."""
        d = filedialog.askdirectory(initialdir=self.outdir.get())
        if d: 
            self.outdir.set(d)

    def _open(self):
        """Opens the selected output folder in the system's file explorer."""
        p = self.outdir.get()
        if sys.platform == 'win32': 
            os.startfile(p)
        elif sys.platform == 'darwin': 
            subprocess.Popen(['open', p])
        else: 
            subprocess.Popen(['xdg-open', p])

    def _clear_log(self):
        """Wipes the console output buffer."""
        self.log.config(state='normal')
        self.log.delete('1.0', 'end')
        self.log.config(state='disabled')

    def _log(self, msg, tag='dim'):
        """
        Appends a message to the internal console log.
        Supports semantic tags: 'ok' (green), 'err' (red), 'info' (cyan), etc.
        """
        self.log.config(state='normal')
        self.log.insert('end', msg + '\n', tag)
        self.log.see('end') # Auto-scroll to bottom
        self.log.config(state='disabled')

    def _bar(self, _=None):
        """Handles the multi-layered drawing of the custom progress bar."""
        c = self.pc
        w = c.winfo_width()
        h = c.winfo_height()
        p = self.pct.get()
        fill = int(w * p / 100)
        
        c.delete('all')
        # Background track
        c.create_rectangle(0, 0, w, h, fill=BORDER, outline='')
        
        if fill > 0:
            # Secondary bar fill
            c.create_rectangle(0, 0, fill, h, fill=ACCENT, outline='')
            # Gloss highlight (upper 1/3)
            c.create_rectangle(0, 0, fill, max(1, h//3), fill=ACCENT_L, outline='')
            
        try: 
            self.p_text.config(text=f'{p:.1f}%')
        except Exception: 
            pass

    # --- Core Download Orchestration Engine ---

    def _check(self):
        """Periodically validates current input state to manage UI sensitivity."""
        if not self._dl:
            ready = bool(self.url.get().strip()) and HAVE_YTDLP
            s = 'normal' if ready else 'disabled'
            # Update button state based on readiness
            if self.dlb.config.__dict__.get('state') != s:
                self.dlb.config(state=s, 
                                bg=BTN_PRIMARY_BG if ready else ACCENT_D,
                                fg=BTN_PRIMARY_FG if ready else '#7060AA')
        self.root.after(500, self._check)

    def _start(self):
        """Validates inputs and spawns the background download thread."""
        u = self.url.get().strip()
        if not u: 
            return
            
        d = self.outdir.get()
        if not os.path.exists(d):
            try: 
                os.makedirs(d)
            except Exception:
                messagebox.showerror('Path Error', 'Cannot create target folder.')
                return

        # Prepare UI for active work
        self._dl   = True
        self._stop = False
        self.pct.set(0)
        self._bar()
        self.status.set('Preparing download...')
        self.dlb.config(state='disabled', bg=ACCENT_D, fg='#7060AA')
        
        self._log('--- Starting New Task ---', 'info')
        self._log(f'URL: {u}', 'dim')
        self._log(f'Dir: {d}', 'dim')
        
        # Ensure EJS solver is present for this session
        threading.Thread(target=_ensure_ejs_installed, daemon=True).start()
        
        # Launch engine in separate thread to keep UI responsive
        threading.Thread(target=self._run_dl, args=(u, d), daemon=True).start()

    def _run_dl(self, url, outdir):
        """
        The main worker loop. Configures yt-dlp and executes the extraction.
        Runs in a background thread.
        """
        try:
            # Build platform-optimised options
            opts = build_opts(
                self.dl_type.get(),
                self.quality.get(),
                self.afmt.get(),
                self.vfmt.get(),
                outdir,
                self._hook,
                self.playlist.get()
            )
            
            self._log('Analysing stream data...', 'dim')
            self._log('Checking extraction scripts...', 'dim')
            
            # Verify solver readiness
            _ensure_ejs_installed()
            try:
                import importlib
                importlib.import_module('yt_dlp_ejs')
                self._log('Success: Challenge solver is active.', 'ok')
            except ImportError:
                self._log('Notice: Running without extended JS support.', 'warn')

            with yt_dlp.YoutubeDL(opts) as ydl:
                # Main extraction call
                ydl.download([url])
            
            if self._stop:
                self.status.set('Stopped')
                self._log('Task stopped by user.', 'warn')
            else:
                self.status.set('Complete')
                self.pct.set(100)
                self.root.after(0, self._bar)
                self._log('Success: Task completed successfully.', 'ok')
                
        except Exception as e:
            err = str(e)
            # Standardise error messages for common issues
            if 'Incomplete YouTube ID' in err: 
                err = 'Invalid YouTube URL provided.'
            elif 'requested format not available' in err: 
                err = 'The selected resolution is not available for this video.'
            elif 'Requested' in err and 'is not available' in err: 
                err = 'Partial format missing. Try a lower quality.'
            
            self._log(f'Error: {err}', 'err')
            self.status.set('Failed')
        
        finally:
            self._dl = False
            # Return button and state to ready
            self.root.after(0, lambda: self._check())

    def _hook(self, d):
        """ yt-dlp multi-event callback. Updates the UI on the main thread."""
        if self._stop: 
            raise Exception('Stopped') # Abortion signal for yt-dlp
            
        st = d.get('status')
        if st == 'downloading':
            try:
                # Extract clean percentage from string (handle ANSI codes)
                p_str = d.get('_percent_str', '0%').replace('%','').strip()
                p_str = re.sub(r'\x1b\[[0-9;]*m', '', p_str)
                p = float(p_str)
                self.pct.set(p)
                
                speed = d.get('_speed_str', 'N/A')
                eta   = d.get('_eta_str',   'N/A')
                self.status.set(f'Downloader: {speed}  |  ETA: {eta}')
                self.root.after(0, self._bar)
            except Exception: 
                pass
        elif st == 'finished':
            self.status.set('Processing media files...')
            self._log('Extraction finished. Merging/Converting...', 'dim')

    def _stop_dl(self):
        """Signals the background thread to abort the current engine process."""
        if self._dl:
            self._stop = True
            self.status.set('Stopping...')
            self._log('Stopping engine...', 'warn')

    def _done(self):
        """Called when download and post-processing are complete."""
        self._reset()
        self._set_p(100, 'All tasks complete')
        self._log(f'Saved to directory: {self.outdir.get()}', 'ok')

    def _reset(self):
        """Resets the UI state to allow for a new download."""
        self._dl = False
        self.dlb.config(state='normal', bg=BTN_PRIMARY_BG, fg=BTN_PRIMARY_FG)

# --- Auto-Update Lifecycle ---

    def _check_for_updates(self):
        """
        Background task to verify the application version against GitHub.
        Does not interrupt the user; silently logs readiness for update.
        """
        try:
            req = urllib.request.Request(UPDATE_CHECK_URL, headers={
                'User-Agent': GLOBAL_USER_AGENT,
                'Cache-Control': 'no-cache'
            })
            resp = urllib.request.urlopen(req, timeout=8)
            data = json.loads(resp.read().decode('utf-8'))

            remote_ver = data.get('version', '0.0.0')
            if self._version_newer(remote_ver, APP_VERSION):
                # Trigger the dialog logic on the safe Main UI thread
                self.root.after(0, lambda: self._show_update_dialog(data))
        except Exception:
            # Silent fail — ensures app remains functional even without internet
            pass

    @staticmethod
    def _version_newer(remote, local):
        """Identifies if a semantic version string is prioritised over local (remote > local)."""
        try:
            r = [int(x) for x in remote.split('.')]
            l = [int(x) for x in local.split('.')]
            # Normalise list lengths to 3 parts (major.minor.patch)
            while len(r) < 3: r.append(0)
            while len(l) < 3: l.append(0)
            return r > l
        except (ValueError, AttributeError):
            return False

    def _show_update_dialog(self, data):
        """Constructs and displays a custom modal window for update notifications."""
        remote_ver = data.get('version', '?')
        changelog  = data.get('changelog', '')

        # Select the correct installer blob for the user's OS
        if sys.platform == 'win32':
            dl_url = data.get('win_url', '')
        elif sys.platform == 'darwin':
            dl_url = data.get('mac_url', '')
        else:
            dl_url = data.get('linux_url', '')

        dlg = tk.Toplevel(self.root)
        dlg.title('Update Available')
        dlg.configure(bg=PANEL)
        dlg.resizable(False, False)
        dlg.transient(self.root) # Stay on top of main window
        dlg.grab_set()

        # Center the dialog on screen
        dlg.update_idletasks()
        pw, ph = self.root.winfo_width(), self.root.winfo_height()
        px, py = self.root.winfo_x(), self.root.winfo_y()
        dw, dh = 380, 280
        dlg.geometry(f'{dw}x{dh}+{px + (pw-dw)//2}+{py + (ph-dh)//2}')

        tk.Label(dlg, text='Software Update', bg=PANEL, font=(F_DISPLAY[0], 24)).pack(pady=(18, 4))
        tk.Label(dlg, text='A new version is ready!', bg=PANEL, fg=FG, font=F_DISPLAY).pack()
        
        # Display version jump
        tk.Label(dlg, text=f'v{APP_VERSION}  ->  v{remote_ver}', bg=PANEL, fg=ACCENT_L,
                 font=F_BODY).pack(pady=(4, 2))

        if changelog:
            tk.Label(dlg, text=changelog, bg=PANEL, fg=FG3,
                     font=(F_BODY[0], 10), wraplength=320, justify='center').pack(pady=(2, 10))

        btn_row = tk.Frame(dlg, bg=PANEL)
        btn_row.pack(pady=(8, 16))

        def _download():
            if dl_url:
                webbrowser.open(dl_url)
            dlg.destroy()

        def _skip():
            dlg.destroy()

        make_btn(btn_row, 'Download Update', _download,
                 BTN_PRIMARY_BG, BTN_PRIMARY_FG,
                 hover_bg=BTN_PRIMARY_HOV, hover_fg=BTN_PRIMARY_HOV_FG,
                 font=F_BTN, padx=16, pady=8).pack(side='left', padx=6)

        make_btn(btn_row, 'Skip', _skip,
                 BTN_GHOST_BG, BTN_GHOST_FG,
                 hover_bg=BTN_GHOST_HOV, hover_fg=BTN_GHOST_HOV_FG,
                 font=F_BTN, padx=12, pady=8).pack(side='left', padx=6)

        self._log(f'Update available: Version {remote_ver}', 'info')


# ══════════════════════════════════════════════════════════════════════════════
# --- macOS Specific System Integration ---

def _apply_dock_persistence():
    """
    Sets the NSApplication activation policy to 'Regular'.
    
    RATIONALE:
    By default, an 'unbundled' Python script might not show up in the Dock 
    properly on macOS, or the icon might disappear if the main thread is 
    busy during startup. This function uses the Objective-C runtime (via ctypes) 
    to force the application to behave like a standard UI app.
    
    This MUST be called after the Tk instance is created, as Tk initializes 
    the underlying NSApplication.
    """
    if sys.platform != 'darwin':
        return
        
    try:
        # Load the Objective-C runtime library
        import ctypes, ctypes.util
        lib_objc = ctypes.cdll.LoadLibrary(ctypes.util.find_library('objc'))
        
        # Configure function return/argument types for the bridge
        lib_objc.objc_getClass.restype   = ctypes.c_void_p
        lib_objc.sel_registerName.restype = ctypes.c_void_p
        lib_objc.objc_msgSend.restype    = ctypes.c_void_p
        lib_objc.objc_msgSend.argtypes   = [ctypes.c_void_p, ctypes.c_void_p]
        
        # [NSApplication sharedApplication]
        ns_app = lib_objc.objc_msgSend(
            lib_objc.objc_getClass(b'NSApplication'),
            lib_objc.sel_registerName(b'sharedApplication'))
            
        # [ns_app setActivationPolicy:0] (0 = NSApplicationActivationPolicyRegular)
        lib_objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int64]
        lib_objc.objc_msgSend(ns_app,
            lib_objc.sel_registerName(b'setActivationPolicy:'), 0)
            
        # [ns_app activateIgnoringOtherApps:YES]
        lib_objc.objc_msgSend.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_bool]
        lib_objc.objc_msgSend(ns_app,
            lib_objc.sel_registerName(b'activateIgnoringOtherApps:'), True)
    except Exception:
        # Fail silently to avoid crashing on systems with locked-down runtimes
        pass


def main():
    """Application entry point."""
    # 1. Initialize the root UI framework
    root = tk.Tk()

    # 2. Apply macOS-specific UI fixes
    _apply_dock_persistence()

    # 3. Instantiate the App controller and start the event loop
    app_instance = App(root)
    root.mainloop()
    
    # 4. Cleanup: Release the single-instance lock on shutdown
    if _lock_sock:
        try: 
            _lock_sock.close()
        except Exception: 
            pass

if __name__ == '__main__':
    main()