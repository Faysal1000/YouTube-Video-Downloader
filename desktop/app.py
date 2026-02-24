"""
YouTube Downloader — Desktop GUI
Works standalone. Python + ffmpeg bundled in the EXE/APP.

Fixes applied:
  - Single-instance lock via socket (port 47216)
  - Instant window + dock appearance on launch
  - yt_dlp imported in background thread (no frozen UI)
  - Animated splash overlay shown while loading
"""

import os, sys, shutil, threading, re, socket, tkinter as tk
from tkinter import filedialog, messagebox
import subprocess

# ══════════════════════════════════════════════════════════════════════════════
#  SINGLE INSTANCE LOCK  — must run before anything else
#  Binds a local socket. If already bound → another instance is running → exit.
# ══════════════════════════════════════════════════════════════════════════════
_LOCK_PORT = 47216
_lock_sock = None

def _acquire_single_instance():
    global _lock_sock
    try:
        _lock_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        _lock_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        _lock_sock.bind(('127.0.0.1', _LOCK_PORT))
        return True
    except OSError:
        return False

if not _acquire_single_instance():
    if sys.platform == 'darwin':
        try:
            subprocess.run(['osascript', '-e',
                'tell application "YT Downloader" to activate'], check=False)
        except Exception:
            pass
    try:
        _r = tk.Tk(); _r.withdraw()
        messagebox.showinfo('Already Running',
            'YouTube Downloader is already open.\nCheck your Dock or taskbar.')
        _r.destroy()
    except Exception:
        pass
    sys.exit(0)

# ══════════════════════════════════════════════════════════════════════════════
#  PATH RESOLUTION
# ══════════════════════════════════════════════════════════════════════════════
def res(rel):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)

try:
    import ctypes
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
        u'faysal.ytdl.app.pro.v1')
except Exception:
    pass

def setup_ffmpeg():
    d = res('ffmpeg_bin')
    if os.path.isdir(d):
        os.environ['PATH'] = d + os.pathsep + os.environ.get('PATH', '')
    return d

FFMPEG_DIR = setup_ffmpeg()

# yt_dlp is NOT imported here — done lazily in background to keep startup instant
yt_dlp     = None
HAVE_YTDLP = False

# ══════════════════════════════════════════════════════════════════════════════
#  CONSTANTS
# ══════════════════════════════════════════════════════════════════════════════
QUALITIES  = ['best','4320p','2160p','1440p','1080p','720p','480p','360p','240p','144p']
VIDEO_FMTS = ['mp4','mkv','webm']
AUDIO_FMTS = ['mp3','m4a','opus','wav','flac']

BG            = '#0C0C0E'
PANEL         = '#111115'
CARD          = '#17171D'
BORDER        = '#2A2A38'
BORDER2       = '#3A3A50'
FG            = '#F5F5FA'   
FG2           = '#C8C8D8'   
FG3           = '#9090A8'   
ACCENT        = '#7B5FFF'
ACCENT_L      = '#B09FFF'   
ACCENT_D      = '#5B3FD0'
ACCENT_DARK_BG= '#1A1530'
CYAN          = '#00E8DA'
GREEN         = '#30E882'
RED           = '#FF5577'
AMBER         = '#FFC040'

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

import tkinter.font as tkfont
_FAMILIES = []
def _ff(*names):
    global _FAMILIES
    if not _FAMILIES:
        try: _FAMILIES = list(tkfont.families())
        except: _FAMILIES = []
    for n in names:
        if n in _FAMILIES: return n
    return names[-1]

F_DISPLAY = (_ff('Segoe UI','SF Pro Display','Helvetica Neue','Helvetica'), 16, 'bold')
F_BODY    = (_ff('Segoe UI','SF Pro Text',   'Helvetica Neue','Helvetica'), 12)
F_MONO    = (_ff('Cascadia Code','Consolas','Menlo','Courier New'), 11)
F_MONO_S  = (_ff('Cascadia Code','Consolas','Menlo','Courier New'), 11)
F_LABEL   = (_ff('Segoe UI','SF Pro Text',   'Helvetica Neue','Helvetica'), 10, 'bold')
F_BTN     = (_ff('Segoe UI','SF Pro Text',   'Helvetica Neue','Helvetica'), 11, 'bold')
F_BTN_LG  = (_ff('Segoe UI','SF Pro Text',   'Helvetica Neue','Helvetica'), 13, 'bold')


# ══════════════════════════════════════════════════════════════════════════════
#  HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def make_btn(parent, text, cmd, bg, fg, hover_bg=None, hover_fg=None,
             font=None, padx=14, pady=8, **kw):
    """
    Frame+Label button — macOS overrides tk.Button colors with native grey,
    but cannot override Frame/Label colors. This always shows correctly.
    """
    hbg = hover_bg or bg
    hfg = hover_fg or fg

    outer = tk.Frame(parent, bg=bg, cursor='hand2', padx=2, pady=2)
    inner = tk.Frame(outer, bg=bg, cursor='hand2')
    inner.pack(fill='both', expand=True)
    lbl = tk.Label(inner, text=text, bg=bg, fg=fg,
                   font=font or F_BTN, padx=padx, pady=pady,
                   cursor='hand2')
    lbl.pack(fill='both', expand=True)

    def _on(e):
        outer.config(bg=hbg); inner.config(bg=hbg); lbl.config(bg=hbg, fg=hfg)
    def _off(e):
        outer.config(bg=bg);  inner.config(bg=bg);  lbl.config(bg=bg,  fg=fg)
    def _click(e):
        _on(e)
        outer.after(80, cmd)

    for w in (outer, inner, lbl):
        w.bind('<Enter>',           _on)
        w.bind('<Leave>',           _off)
        w.bind('<ButtonRelease-1>', _click)

    # Save the REAL tkinter config before we shadow it
    _outer_config = outer.config.__func__  # underlying method

    def _cfg(**opts):
        s      = opts.pop('state', None)
        new_bg = opts.pop('bg',    None)
        new_fg = opts.pop('fg',    None)
        if s == 'disabled':
            for w in (outer, inner, lbl):
                w.unbind('<Enter>'); w.unbind('<Leave>'); w.unbind('<ButtonRelease-1>')
            lbl.configure(fg='#555570')
        elif s == 'normal':
            for w in (outer, inner, lbl):
                w.bind('<Enter>',           _on)
                w.bind('<Leave>',           _off)
                w.bind('<ButtonRelease-1>', _click)
        if new_bg:
            # Use .configure() (alias that is NOT shadowed) to avoid recursion
            outer.configure(bg=new_bg)
            inner.configure(bg=new_bg)
            lbl.configure(bg=new_bg)
        if new_fg:
            lbl.configure(fg=new_fg)

    # Shadow only .config — .configure() stays intact and is used internally
    outer.config = _cfg
    return outer

def BG3_SAFE(): return CARD


# ══════════════════════════════════════════════════════════════════════════════
#  BACKGROUND IMPORT THREAD
# ══════════════════════════════════════════════════════════════════════════════
def _import_yt_dlp_async(on_done):
    global yt_dlp, HAVE_YTDLP
    try:
        import yt_dlp as _yd
        yt_dlp     = _yd
        HAVE_YTDLP = True
    except ImportError:
        HAVE_YTDLP = False
    on_done()


# ══════════════════════════════════════════════════════════════════════════════
#  JS / EJS HELPERS
# ══════════════════════════════════════════════════════════════════════════════
def _find_js_runtime():
    for r in ['node.exe','node','deno.exe','deno','bun.exe','bun']:
        p = os.path.join(FFMPEG_DIR, r)
        if os.path.isfile(p):
            name = 'node' if 'node' in r else ('deno' if 'deno' in r else 'bun')
            return name, os.path.abspath(p)
        w = shutil.which(r)
        if w:
            name = 'node' if 'node' in r else ('deno' if 'deno' in r else 'bun')
            return name, os.path.abspath(w)
    return None, None

def _ensure_ejs_installed():
    try:
        import importlib; importlib.import_module('yt_dlp_ejs')
    except ImportError:
        try:
            subprocess.run([sys.executable,'-m','pip','install','--quiet','yt-dlp-ejs'],
                           check=True, capture_output=True, timeout=60)
        except Exception: pass

def _get_runtime_opts():
    if not HAVE_YTDLP: return {}
    name, path = _find_js_runtime()
    if not name or not path: return {}
    rdir = os.path.dirname(path)
    if rdir not in os.environ.get('PATH',''):
        os.environ['PATH'] = rdir + os.pathsep + os.environ.get('PATH','')
    try:
        cli_args = ['--js-runtimes', name]
        try:
            yt_dlp.parse_options(['--remote-components','ejs:github'])
            cli_args += ['--remote-components','ejs:github']
        except Exception: pass
        _, _, _, parsed = yt_dlp.parse_options(cli_args)
        result = {}
        for k in ('js_runtimes','remote_components'):
            if k in parsed and parsed[k] is not None:
                result[k] = parsed[k]
        return result
    except Exception: return {}

def build_opts(dl_type, quality, afmt, vfmt, outdir, hook, playlist=False):
    outtmpl = os.path.join(outdir,
        '%(playlist_index)s-%(title)s.%(ext)s' if playlist else '%(title)s.%(ext)s')
    opts = {'outtmpl': outtmpl, 'quiet': True, 'no_warnings': True,
            'progress_hooks': [hook], 'noplaylist': not playlist}
    if os.path.isdir(FFMPEG_DIR): opts['ffmpeg_location'] = FFMPEG_DIR
    if dl_type == 'audio':
        opts.update(_get_runtime_opts())
        opts.update({'format':'bestaudio/best','postprocessors':[
            {'key':'FFmpegExtractAudio','preferredcodec':afmt,'preferredquality':'0'}]})
        return opts
    if quality == 'best':
        fmt = f'bestvideo[ext={vfmt}]+bestaudio/bestvideo+bestaudio/best'
    else:
        h = quality.replace('p','')
        fmt = (f'bestvideo[height<={h}][ext={vfmt}]+bestaudio'
               f'/bestvideo[height<={h}]+bestaudio/bestvideo+bestaudio/best')
    opts.update({'format': fmt, 'merge_output_format': vfmt})
    opts.update(_get_runtime_opts())
    return opts


# ══════════════════════════════════════════════════════════════════════════════
#  SPLASH OVERLAY — animated dots, shown while yt_dlp loads in background
# ══════════════════════════════════════════════════════════════════════════════
class Splash:
    _FRAMES = [
        ('⬤', '◯', '◯'),
        ('◯', '⬤', '◯'),
        ('◯', '◯', '⬤'),
        ('⬤', '⬤', '◯'),
        ('◯', '⬤', '⬤'),
        ('⬤', '◯', '⬤'),
    ]

    def __init__(self, parent):
        self._frame = tk.Frame(parent, bg=BG)
        self._frame.place(relx=0, rely=0, relwidth=1, relheight=1)

        col = tk.Frame(self._frame, bg=BG)
        col.place(relx=0.5, rely=0.44, anchor='center')

        # Three individually-coloured dots
        dot_row = tk.Frame(col, bg=BG)
        dot_row.pack(pady=(0, 16))
        self._d = [
            tk.Label(dot_row, text='⬤', bg=BG, fg=ACCENT,
                     font=(F_DISPLAY[0], 26)),
            tk.Label(dot_row, text='◯', bg=BG, fg=BORDER2,
                     font=(F_DISPLAY[0], 26)),
            tk.Label(dot_row, text='◯', bg=BG, fg=BORDER2,
                     font=(F_DISPLAY[0], 26)),
        ]
        for d in self._d:
            d.pack(side='left', padx=6)

        tk.Label(col, text='YouTube Downloader', bg=BG, fg=FG,
                 font=F_DISPLAY).pack()
        tk.Label(col, text='Loading dependencies…', bg=BG, fg=FG3,
                 font=F_BODY).pack(pady=(5, 0))

        # Progress bar strip
        self._bar_canvas = tk.Canvas(col, height=3, width=220,
                                      bg=BORDER, highlightthickness=0)
        self._bar_canvas.pack(pady=(14, 0))
        self._bar_w = 0
        self._bar_growing = True

        self._fi = 0
        self._animate()

    def _animate(self):
        if not self._frame.winfo_exists(): return
        dots = self._FRAMES[self._fi % len(self._FRAMES)]
        for i, d in enumerate(self._d):
            active = dots[i] == '⬤'
            d.config(text=dots[i],
                     fg=ACCENT if active else BORDER2)
        self._fi += 1

        # Indeterminate progress bar bounce
        W = 220
        seg = 60
        if self._bar_growing:
            self._bar_w = min(self._bar_w + 8, W)
            if self._bar_w >= W: self._bar_growing = False
        else:
            self._bar_w = max(self._bar_w - 8, 0)
            if self._bar_w <= 0: self._bar_growing = True
        self._bar_canvas.delete('all')
        self._bar_canvas.create_rectangle(0, 0, W, 3, fill=BORDER, outline='')
        self._bar_canvas.create_rectangle(0, 0, self._bar_w, 3,
                                           fill=ACCENT, outline='')

        self._aid = self._frame.after(180, self._animate)

    def dismiss(self):
        try: self._frame.after_cancel(self._aid)
        except Exception: pass
        self._frame.destroy()


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APP
# ══════════════════════════════════════════════════════════════════════════════
class App:
    def __init__(self, root):
        self.root   = root
        self._ready = False

        root.title('YT Downloader')
        root.geometry('580x650')
        root.resizable(True, True)
        root.minsize(450, 400)
        root.configure(bg=BG)

        # macOS: ensure the app appears in the Dock immediately on launch
        if sys.platform == 'darwin':
            try:
                # This call registers the process as a full foreground UI app
                root.tk.call('::tk::unsupported::MacWindowStyle', 'style',
                             root._w, 'document', 'closeBox collapseBox')
            except Exception:
                pass

        try:
            ic = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.ico')
            if not os.path.isfile(ic): ic = res('icon.ico')
            if os.path.isfile(ic):
                root.iconbitmap(default=ic); root.iconbitmap(ic)
                try: root.tk.call('wm', 'iconbitmap', root._w, ic)
                except Exception: pass
        except Exception: pass

        # state
        self.url      = tk.StringVar()
        self.outdir   = tk.StringVar(value=os.path.expanduser('~/Downloads'))
        self.dl_type  = tk.StringVar(value='video')
        self.quality  = tk.StringVar(value='1080p')
        self.vfmt     = tk.StringVar(value='mp4')
        self.afmt     = tk.StringVar(value='mp3')
        self.pct      = tk.DoubleVar(value=0)
        self.status   = tk.StringVar(value='Initialising…')
        self.playlist = tk.BooleanVar(value=False)
        self._dl      = False
        self._stop    = False
        self._log_visible = False

        self.dlb = self.log = self.pc = self.p_text = None
        self.lw  = self.log_toggle = self.log_sec  = None
        self.qm  = self.vfr = self.afr             = None

        # Build UI immediately → window appears right away, Dock icon visible
        self._build_ui()
        self.root.geometry("")

        # Disable download until ready
        self.dlb.config(state='disabled', bg=ACCENT_D, fg='#7060AA')

        # Show splash overlay on top of the already-visible UI
        self._splash = Splash(self.root)

        # Import yt_dlp in background — UI stays responsive and animated
        threading.Thread(
            target=_import_yt_dlp_async,
            args=(lambda: self.root.after(0, self._finish_init),),
            daemon=True
        ).start()

    # ── Called on main thread once yt_dlp import finishes ────────────────────
    def _finish_init(self):
        self._splash.dismiss()
        self._ready = True
        if HAVE_YTDLP:
            self.dlb.config(state='normal', bg=BTN_PRIMARY_BG, fg=BTN_PRIMARY_FG)
        else:
            self.dlb.config(state='disabled', bg='#2A1A1A', fg='#664444')
        self.status.set('Ready')
        self.root.after(0, self._check)

    # ─────────────────────────────────────────────────────────────────────────
    def _build_ui(self):

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=PANEL, height=64)
        hdr.pack(fill='x', side='top')
        hdr.pack_propagate(False)

        tk.Frame(hdr, bg=ACCENT, width=3).pack(side='left', fill='y')

        icon_f = tk.Frame(hdr, bg=ACCENT_DARK_BG, width=34, height=34)
        icon_f.pack(side='left', padx=(14, 10), pady=9)
        icon_f.pack_propagate(False)
        tk.Label(icon_f, text='▶', bg=ACCENT_DARK_BG, fg=ACCENT_L,
                 font=(F_BODY[0], 14, 'bold')).place(relx=.5, rely=.5, anchor='center')

        title_col = tk.Frame(hdr, bg=PANEL)
        title_col.pack(side='left', fill='y', pady=8)
        tk.Label(title_col, text='YouTube Downloader', bg=PANEL, fg=FG,
                 font=F_DISPLAY).pack(anchor='w')
        tk.Label(title_col, text='by Faysal', bg=PANEL, fg=FG3,
                 font=(F_BODY[0], 10)).pack(anchor='w')

        pro_f = tk.Frame(hdr, bg=ACCENT_D, padx=7, pady=2)
        pro_f.pack(side='right', padx=16, pady=18)
        tk.Label(pro_f, text='PRO', bg=ACCENT_D, fg='#FFFFFF',
                 font=(F_MONO[0], 9, 'bold')).pack()

        tk.Frame(self.root, bg=BORDER, height=1).pack(fill='x', side='top')

        # ── Footer ────────────────────────────────────────────────────────────
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill='x', side='bottom')
        footer = tk.Frame(self.root, bg=PANEL, pady=10)
        footer.pack(fill='x', side='bottom')

        pl_wrap = tk.Frame(footer, bg=PANEL, cursor='hand2')
        pl_wrap.pack(side='left', padx=(16, 8))

        # Custom checkbox using Canvas — macOS cannot grey out Canvas widgets
        chk_row = tk.Frame(pl_wrap, bg=PANEL, cursor='hand2')
        chk_row.pack()
        chk_c = tk.Canvas(chk_row, width=18, height=18, bg=PANEL,
                          highlightthickness=0, cursor='hand2')
        chk_c.pack(side='left', padx=(0, 6))
        tk.Label(chk_row, text='Playlist', bg=PANEL, fg=FG,
                 font=F_BODY, cursor='hand2').pack(side='left')

        def _draw_chk():
            chk_c.delete('all')
            if self.playlist.get():
                chk_c.create_rectangle(1, 1, 17, 17, fill=ACCENT, outline=ACCENT)
                chk_c.create_line(4, 9, 7, 13, fill='#FFFFFF', width=2)
                chk_c.create_line(7, 13, 14, 5, fill='#FFFFFF', width=2)
            else:
                chk_c.create_rectangle(1, 1, 17, 17, fill='', outline=FG3, width=2)

        def _toggle_chk(e=None):
            self.playlist.set(not self.playlist.get())
            _draw_chk()

        for w in (chk_row, chk_c):
            w.bind('<ButtonRelease-1>', _toggle_chk)
        chk_row.winfo_children()[-1].bind('<ButtonRelease-1>', _toggle_chk)
        _draw_chk()

        self.dlb = make_btn(footer, '⬇  DOWNLOAD', self._start,
                            BTN_PRIMARY_BG, BTN_PRIMARY_FG,
                            hover_bg=BTN_PRIMARY_HOV, hover_fg=BTN_PRIMARY_HOV_FG,
                            font=F_BTN_LG, padx=20, pady=8)
        self.dlb.pack(side='left', padx=4)

        make_btn(footer, '⏹  Stop', self._stop_dl,
                 BTN_STOP_BG, BTN_STOP_FG,
                 hover_bg=BTN_STOP_HOV, hover_fg=BTN_STOP_HOV_FG,
                 font=F_BTN, padx=14, pady=8).pack(side='left', padx=2)

        make_btn(footer, '📁  Folder', self._open,
                 BTN_SECONDARY_BG, BTN_SECONDARY_FG,
                 hover_bg=BTN_SECONDARY_HOV, hover_fg=BTN_SECONDARY_HOV_FG,
                 font=F_BTN, padx=12, pady=8).pack(side='left', padx=2)

        make_btn(footer, '🗑  Clear', self._clear_log,
                 BTN_GHOST_BG, BTN_GHOST_FG,
                 hover_bg=BTN_GHOST_HOV, hover_fg=BTN_GHOST_HOV_FG,
                 font=(F_BODY[0], 11), padx=8, pady=8).pack(side='right', padx=16)

        # ── Body ──────────────────────────────────────────────────────────────
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill='both', expand=True, padx=18, pady=(12, 0))

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
        make_btn(url_row, '⎘  Paste', self._paste,
                 BTN_SECONDARY_BG, BTN_SECONDARY_FG,
                 hover_bg=BTN_SECONDARY_HOV, hover_fg=BTN_SECONDARY_HOV_FG,
                 font=F_BODY, padx=10, pady=8).pack(side='left', padx=6)

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
        make_btn(dir_row, '📁  Browse', self._browse,
                 BTN_SECONDARY_BG, BTN_SECONDARY_FG,
                 hover_bg=BTN_SECONDARY_HOV, hover_fg=BTN_SECONDARY_HOV_FG,
                 font=F_BODY, padx=10, pady=8).pack(side='left', padx=6)

        self._label(body, 'OPTIONS')
        opt = tk.Frame(body, bg=BG)
        opt.pack(fill='x', pady=(3, 12))

        tc = self._pill_card(opt, 'TYPE')
        tc.pack(side='left', fill='both', expand=True, padx=(0, 6))
        for v, lbl in [('video','🎬  Video'),('audio','🎵  Audio')]:
            self._radio(tc, lbl, self.dl_type, v, self._on_type)

        qc = self._pill_card(opt, 'QUALITY')
        qc.pack(side='left', fill='both', expand=True, padx=(0, 6))
        self.qm = self._styled_menu(qc, self.quality, QUALITIES)
        self.qm.pack(padx=10, pady=5, fill='x')

        fc = self._pill_card(opt, 'FORMAT')
        fc.pack(side='left', fill='both', expand=True)
        self.vfr = tk.Frame(fc, bg=CARD)
        self.vfr.pack(fill='x', padx=8, pady=(2, 1))
        tk.Label(self.vfr, text='V', bg=CARD, fg=FG3, font=F_LABEL, width=2).pack(side='left')
        self._styled_menu(self.vfr, self.vfmt, VIDEO_FMTS).pack(side='left', fill='x', expand=True)
        self.afr = tk.Frame(fc, bg=CARD)
        self.afr.pack(fill='x', padx=8, pady=(1, 5))
        tk.Label(self.afr, text='A', bg=CARD, fg=FG3, font=F_LABEL, width=2).pack(side='left')
        self._styled_menu(self.afr, self.afmt, AUDIO_FMTS).pack(side='left', fill='x', expand=True)

        self._label(body, 'PROGRESS')
        status_row = tk.Frame(body, bg=BG)
        status_row.pack(fill='x', pady=(3, 4))
        tk.Label(status_row, textvariable=self.status, bg=BG, fg=FG2,
                 font=F_MONO_S, anchor='w').pack(side='left', fill='x', expand=True)
        self.p_text = tk.Label(status_row, text='0%', bg=BG, fg=ACCENT_L,
                                font=(F_MONO[0], 12, 'bold'))
        self.p_text.pack(side='right')
        self.pc = tk.Canvas(body, height=6, bg=BG3_SAFE(), highlightthickness=0)
        self.pc.pack(fill='x', pady=0)
        self.pc.bind('<Configure>', lambda e: self._bar())

        self.log_sec = tk.Frame(body, bg=BG)
        self.log_sec.pack(fill='x', side='top')
        lhdr = tk.Frame(self.log_sec, bg=BG)
        lhdr.pack(fill='x', pady=6)
        self.log_toggle = make_btn(lhdr, '[+] Show Logs', self._toggle_log,
                                   BTN_GHOST_BG, FG3,
                                   hover_bg=BTN_GHOST_HOV, hover_fg=ACCENT_L,
                                   font=(F_LABEL[0], 10, 'bold'), padx=10, pady=2)
        self.log_toggle.pack(anchor='center')

        self.lw = tk.Frame(self.log_sec, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        sb = tk.Scrollbar(self.lw, bg=BG, troughcolor=CARD, width=8, bd=0,
                          highlightthickness=0, relief='flat')
        sb.pack(side='right', fill='y', padx=(0, 2))
        self.log = tk.Text(self.lw, bg=CARD, fg=FG2, font=F_MONO_S, relief='flat',
                           yscrollcommand=sb.set, state='disabled', height=6, width=1,
                           bd=6, selectbackground=BORDER2, insertbackground=ACCENT_L)
        self.log.pack(fill='both', expand=True)
        sb.config(command=self.log.yview)
        self.log.tag_config('ok',   foreground=GREEN)
        self.log.tag_config('err',  foreground=RED)
        self.log.tag_config('warn', foreground=AMBER)
        self.log.tag_config('info', foreground=CYAN)
        self.log.tag_config('dim',  foreground=FG3)

    # ── Widget helpers ────────────────────────────────────────────────────────
    def _label(self, parent, text):
        row = tk.Frame(parent, bg=BG)
        row.pack(fill='x', pady=(4, 0))
        tk.Label(row, text=text, bg=BG, fg=ACCENT_L, font=F_LABEL).pack(side='left')
        tk.Frame(row, bg=BORDER, height=1).pack(side='left', fill='x', expand=True,
                                                 padx=(8, 0), pady=5)

    def _pill_card(self, parent, title):
        f = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        tk.Label(f, text=title, bg=CARD, fg=FG3, font=F_LABEL).pack(anchor='w', padx=12, pady=(8,2))
        return f

    def _radio(self, parent, label, var, value, cmd=None):
        """Custom radio using Frame+Label so macOS cannot grey it out."""
        row = tk.Frame(parent, bg=CARD, cursor='hand2')
        row.pack(anchor='w', padx=12, pady=(2, 4))

        # Dot indicator drawn on a Canvas — macOS can't touch this
        dot_c = tk.Canvas(row, width=16, height=16, bg=CARD,
                          highlightthickness=0, cursor='hand2')
        dot_c.pack(side='left', padx=(0, 6))

        lbl = tk.Label(row, text=label, bg=CARD, fg=FG,
                       font=F_BODY, cursor='hand2')
        lbl.pack(side='left')

        def _draw():
            dot_c.delete('all')
            if var.get() == value:
                dot_c.create_oval(1, 1, 14, 14, fill=ACCENT, outline=ACCENT)
                dot_c.create_oval(4, 4, 11, 11, fill='#FFFFFF', outline='')
            else:
                dot_c.create_oval(1, 1, 14, 14, fill='', outline=FG3, width=2)

        def _select(e=None):
            var.set(value)
            _draw()
            if cmd: cmd()
            # redraw all siblings (other radio rows in same parent)
            for child in parent.winfo_children():
                if hasattr(child, '_radio_redraw'):
                    child._radio_redraw()

        row._radio_redraw = _draw
        for w in (row, dot_c, lbl):
            w.bind('<ButtonRelease-1>', _select)

        var.trace_add('write', lambda *_: _draw())
        _draw()

    def _styled_menu(self, parent, var, choices):
        """Custom dropdown using tk.Menubutton — colours work on macOS."""
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
        entry.bind('<FocusIn>',  lambda e: frame.config(highlightbackground=ACCENT))
        entry.bind('<FocusOut>', lambda e: frame.config(highlightbackground=BORDER))

    def _toggle_log(self):
        curr_w = self.root.winfo_width()
        if self._log_visible:
            self.lw.pack_forget()
            self.log_toggle.config(text='[+] Show Logs')
        else:
            self.lw.pack(fill='x', pady=0)
            self.log_toggle.config(text='[-] Hide Logs')
        self._log_visible = not self._log_visible
        self.root.update_idletasks()
        self.root.geometry(f"{curr_w}x{self.root.winfo_reqheight()}")

    def _on_type(self):
        self.qm.config(state='normal' if self.dl_type.get() == 'video' else 'disabled')

    def _paste(self):
        try: self.url.set(self.root.clipboard_get())
        except Exception: pass

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.outdir.get())
        if d: self.outdir.set(d)

    def _open(self):
        p = self.outdir.get()
        if sys.platform == 'win32': os.startfile(p)
        elif sys.platform == 'darwin': subprocess.Popen(['open', p])
        else: subprocess.Popen(['xdg-open', p])

    def _clear_log(self):
        self.log.config(state='normal'); self.log.delete('1.0','end')
        self.log.config(state='disabled')

    def _log(self, msg, tag='dim'):
        self.log.config(state='normal')
        self.log.insert('end', msg + '\n', tag)
        self.log.see('end'); self.log.config(state='disabled')

    def _bar(self, _=None):
        c = self.pc; w = c.winfo_width(); h = c.winfo_height()
        p = self.pct.get(); fill = int(w * p / 100)
        c.delete('all')
        c.create_rectangle(0, 0, w, h, fill=BORDER, outline='')
        if fill > 0:
            c.create_rectangle(0, 0, fill, h, fill=ACCENT, outline='')
            c.create_rectangle(0, 0, fill, max(1, h//3), fill=ACCENT_L, outline='')
        try: self.p_text.config(text=f'{p:.1f}%')
        except Exception: pass

    def _set_p(self, p, s=''):
        self.pct.set(p)
        if s: self.status.set(s)
        self.root.after(0, self._bar)

    def _check(self):
        if not HAVE_YTDLP:
            self._log('❌  yt-dlp not found — run: pip install yt-dlp', 'err'); return
        self._log('✓  yt-dlp ready', 'ok')
        ff = (os.path.isfile(os.path.join(FFMPEG_DIR,'ffmpeg.exe')) or
              os.path.isfile(os.path.join(FFMPEG_DIR,'ffmpeg')) or
              bool(shutil.which('ffmpeg')))
        self._log('✓  ffmpeg ready' if ff else '⚠  ffmpeg not found', 'ok' if ff else 'warn')
        name, path = _find_js_runtime()
        if path: self._log(f'✓  JS runtime: {name}', 'ok')
        else:
            self._log('⚠  No JS runtime — YouTube may block downloads', 'warn')
            self._log('   Install Node.js → nodejs.org', 'dim')
        self._log('⟳  Checking EJS scripts…', 'dim')
        _ensure_ejs_installed()
        try:
            import importlib; importlib.import_module('yt_dlp_ejs')
            self._log('✓  EJS challenge solver ready', 'ok')
        except ImportError:
            self._log('⚠  EJS scripts missing — run: pip install yt-dlp-ejs', 'warn')
        self._log('Paste a URL above and press Download.', 'dim')

    def _start(self):
        if not self._ready:
            messagebox.showinfo('Loading', 'Still loading, please wait a moment.'); return
        if self._dl:
            messagebox.showinfo('Busy', 'A download is already in progress.'); return
        url = self.url.get().strip()
        if not url:
            messagebox.showerror('No URL', 'Please paste a YouTube URL.'); return
        if not re.match(r'https?://', url):
            messagebox.showerror('Invalid URL', 'URL must start with https://'); return

        out = self.outdir.get(); os.makedirs(out, exist_ok=True)
        self._dl = True; self._stop = False
        self._set_p(0, 'Starting…')
        self.dlb.config(state='disabled', bg=ACCENT_D, fg='#AAAACC')

        def _run():
            try:
                opts = build_opts(self.dl_type.get(), self.quality.get(),
                                  self.afmt.get(), self.vfmt.get(), out,
                                  self._hook, playlist=self.playlist.get())
                class L:
                    def debug(s, m): pass
                    def warning(s, m): self.root.after(0, self._log, f'⚠  {m}', 'warn')
                    def error(s, m):   self.root.after(0, self._log, f'✗  {m}', 'err')
                opts['logger'] = L()
                with yt_dlp.YoutubeDL(opts) as ydl:
                    self.root.after(0, self._log, '⟳  Fetching info…', 'info')
                    info = ydl.extract_info(url, download=False)
                    is_pl = info.get('_type') == 'playlist' and self.playlist.get()
                    n = len(list(info.get('entries', [info]))) if is_pl else 1
                    self.root.after(0, self._log,
                        f'{"Playlist" if is_pl else "Video"} — {n} item(s)', 'info')
                    ydl.download([url])
                self.root.after(0, self._done)
            except yt_dlp.utils.DownloadCancelled:
                self.root.after(0, self._log, '⏹  Download cancelled', 'dim')
                self.root.after(0, self._reset)
            except Exception as e:
                self.root.after(0, self._log, f'✗  {e}', 'err')
                self.root.after(0, self._reset)

        threading.Thread(target=_run, daemon=True).start()

    def _stop_dl(self):
        if self._dl: self._stop = True; self._log('⏹  Stopping…', 'dim')

    def _hook(self, d):
        if self._stop: raise yt_dlp.utils.DownloadCancelled()
        s = d.get('status')
        if s == 'downloading':
            fn  = os.path.basename(d.get('filename', ''))
            dl  = d.get('downloaded_bytes', 0)
            tot = d.get('total_bytes') or d.get('total_bytes_estimate', 0)
            spd = d.get('speed') or 0; eta = d.get('eta') or 0
            p   = dl / tot * 100 if tot else 0
            self.root.after(0, self._set_p, p,
                f'⬇  {fn[:50]}  {p:.0f}%  {spd/1024/1024:.1f} MB/s  ETA {eta}s')
        elif s == 'finished':
            fn = os.path.basename(d.get('filename', ''))
            self.root.after(0, self._log, f'✓  {fn}', 'ok')
            self.root.after(0, self._set_p, 100, 'Merging…')

    def _done(self):
        self._reset()
        self._set_p(100, '── Done! ──')
        self._log(f'Saved to: {self.outdir.get()}', 'ok')

    def _reset(self):
        self._dl = False
        self.dlb.config(state='normal', bg=BTN_PRIMARY_BG, fg=BTN_PRIMARY_FG)


# ══════════════════════════════════════════════════════════════════════════════
def main():
    root = tk.Tk()
    App(root)
    root.mainloop()
    if _lock_sock:
        try: _lock_sock.close()
        except Exception: pass

if __name__ == '__main__':
    main()