"""
YouTube Downloader — Desktop GUI  (Redesigned UI)
Works standalone. Python + ffmpeg bundled in the EXE.
"""

import os, sys, shutil, threading, re, tkinter as tk
from tkinter import filedialog, messagebox
import subprocess, ctypes

# ── Path resolution (dev + PyInstaller) ──────────────────────────────────────
def res(rel):
    base = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, rel)

# ── Windows Taskbar Icon Fix (Global Scope) ──────────────────────────────────
try:
    import ctypes
    # Using a unique ID string to force Windows to stop using the Python icon
    myappid = u'faysal.ytdl.app.pro.v1' 
    ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
except:
    pass

def setup_ffmpeg():
    d = res('ffmpeg_bin')
    if os.path.isdir(d):
        os.environ['PATH'] = d + os.pathsep + os.environ.get('PATH', '')
    return d

FFMPEG_DIR = setup_ffmpeg()

try:
    import yt_dlp
    HAVE_YTDLP = True
except ImportError:
    HAVE_YTDLP = False

# ── Constants ─────────────────────────────────────────────────────────────────
QUALITIES  = ['best','4320p','2160p','1440p','1080p','720p','480p','360p','240p','144p']
VIDEO_FMTS = ['mp4','mkv','webm']
AUDIO_FMTS = ['mp3','m4a','opus','wav','flac']

# ── Premium Palette ───────────────────────────────────────────────────────────
BG       = '#0C0C0E'   # true near-black
PANEL    = '#111115'   # card background
CARD     = '#17171D'   # inner card
BORDER   = '#252530'   # subtle borders
BORDER2  = '#2E2E3A'   # hover borders

FG       = '#F0F0F5'   # primary text
FG2      = '#8A8A9A'   # secondary text
FG3      = '#50505F'   # muted text
FG4      = '#35353F'   # very muted

ACCENT   = '#0C0C0E'   # BLACK
ACCENT_L = '#9B80FF'   # lighter violet
ACCENT_D = '#5B3FD0'   # darker violet
CYAN     = '#00D4C8'   # teal highlight
GREEN    = '#22D47A'   # success
RED      = '#FF4466'   # error / warning
AMBER    = '#FFB340'   # warning

# Fonts — fallback-safe
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

F_DISPLAY = (_ff('Segoe UI', 'SF Pro Display', 'Helvetica Neue', 'Helvetica'), 13, 'bold')
F_BODY    = (_ff('Segoe UI', 'SF Pro Text',    'Helvetica Neue', 'Helvetica'), 9)
F_BODY_B  = (_ff('Segoe UI', 'SF Pro Text',    'Helvetica Neue', 'Helvetica'), 9,  'bold')
F_MONO    = (_ff('Cascadia Code', 'Consolas', 'Menlo', 'Courier New'), 8)
F_MONO_S  = (_ff('Cascadia Code', 'Consolas', 'Menlo', 'Courier New'), 8)
F_LABEL   = (_ff('Segoe UI', 'SF Pro Text',    'Helvetica Neue', 'Helvetica'), 7,  'bold')
F_BTN     = (_ff('Segoe UI', 'SF Pro Text',    'Helvetica Neue', 'Helvetica'), 9,  'bold')
F_BTN_LG  = (_ff('Segoe UI', 'SF Pro Text',    'Helvetica Neue', 'Helvetica'), 10, 'bold')


# ── JS runtime + EJS helper ───────────────────────────────────────────────────
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
            _, _, _, test = yt_dlp.parse_options(['--remote-components','ejs:github'])
            cli_args += ['--remote-components','ejs:github']
        except: pass
        _, _, _, parsed = yt_dlp.parse_options(cli_args)
        result = {}
        for k in ('js_runtimes','remote_components'):
            if k in parsed and parsed[k] is not None:
                result[k] = parsed[k]
        return result
    except: return {}

# ── Build yt-dlp opts ─────────────────────────────────────────────────────────
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


# ── Hover Button Helper ───────────────────────────────────────────────────────
def make_btn(parent, text, cmd, bg, fg, hover_bg=None, hover_fg=None,
             font=None, padx=14, pady=7, **kw):
    hbg = hover_bg or bg; hfg = hover_fg or fg
    b = tk.Button(parent, text=text, command=cmd, bg=bg, fg=fg,
                  relief='flat', cursor='hand2', font=font or F_BTN,
                  padx=padx, pady=pady, activebackground=hbg,
                  activeforeground=hfg, bd=0, **kw)
    b.bind('<Enter>', lambda e: b.config(bg=hbg, fg=hfg))
    b.bind('<Leave>', lambda e: b.config(bg=bg,  fg=fg))
    return b


# ── Main App ──────────────────────────────────────────────────────────────────
class App:
    def __init__(self, root):
        self.root = root
        
        root.title('YT Downloader')
        root.geometry('580x650'); root.resizable(True, True)
        root.minsize(450, 400)
        root.configure(bg=BG)
        
        # 2. Precise Absolute Path Icon Loader (Aggressive Mode)
        try:
            ic = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'icon.ico')
            if not os.path.isfile(ic):
                ic = res('icon.ico')
            
            if os.path.isfile(ic):
                # Set as DEFAULT for the entire application (crucial for taskbar)
                root.iconbitmap(default=ic)
                # Explicit window override
                root.iconbitmap(ic)
                # Deep-level system call to force taskbar update
                try: root.tk.call('wm', 'iconbitmap', root._w, ic)
                except: pass
        except Exception: pass

        # state
        self.url      = tk.StringVar()
        self.outdir   = tk.StringVar(value=os.path.expanduser('~/Downloads'))
        self.dl_type  = tk.StringVar(value='video')
        self.quality  = tk.StringVar(value='1080p')
        self.vfmt     = tk.StringVar(value='mp4')
        self.afmt     = tk.StringVar(value='mp3')
        self.pct      = tk.DoubleVar(value=0)
        self.status   = tk.StringVar(value='Ready')
        self.playlist = tk.BooleanVar(value=False)
        self._dl      = False
        self._stop    = False
        self._log_visible = False

        self.dlb = self.log = self.pc = self.p_text = None
        self.lw = self.log_toggle = self.log_sec = None
        self.qm = self.vfr = self.afr = None

        self._build_ui()
        # Remove any forced geometry, let it snap to content immediately
        self.root.geometry("")
        self.root.after(300, self._check)

    # ─────────────────────────────────────────────────────────────────────────
    def _build_ui(self):

        # ── 1. Header (TOP) ───────────────────────────────────────────────────
        hdr = tk.Frame(self.root, bg=PANEL, height=52)
        hdr.pack(fill='x', side='top')
        hdr.pack_propagate(False)

        # Accent bar on left
        accent_bar = tk.Frame(hdr, bg=ACCENT, width=3)
        accent_bar.pack(side='left', fill='y')

        # Icon badge
        icon_f = tk.Frame(hdr, bg=ACCENT, width=34, height=34)
        icon_f.pack(side='left', padx=(14, 10), pady=9)
        icon_f.pack_propagate(False)
        tk.Label(icon_f, text='▶', bg=ACCENT, fg=FG, font=(F_BODY[0], 11, 'bold')).place(relx=.5, rely=.5, anchor='center')

        # Title
        title_col = tk.Frame(hdr, bg=PANEL)
        title_col.pack(side='left', fill='y', pady=8)
        tk.Label(title_col, text='YouTube Downloader', bg=PANEL, fg=FG,
                 font=F_DISPLAY).pack(anchor='w')
        tk.Label(title_col, text='by Faysal', bg=PANEL, fg=FG3,
                 font=(F_BODY[0], 7)).pack(anchor='w')

        # PRO badge
        pro_f = tk.Frame(hdr, bg=ACCENT_D, padx=7, pady=2)
        pro_f.pack(side='right', padx=16, pady=18)
        tk.Label(pro_f, text='PRO', bg=ACCENT_D, fg=ACCENT_L,
                 font=(F_MONO[0], 7, 'bold')).pack()

        # separator
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill='x', side='top')

        # ── 2. Footer (PACK BELOW LOGS) ───────────────────────────────────────
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill='x', side='bottom')
        footer = tk.Frame(self.root, bg=PANEL, pady=10)
        footer.pack(fill='x', side='bottom')

        # ── 3. Body (CENTER CONTENT) ──────────────────────────────────────────
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill='x', side='top', padx=18, pady=(8, 0))

        # Playlist toggle (inside footer)
        pl_wrap = tk.Frame(footer, bg=PANEL)
        pl_wrap.pack(side='left', padx=(16, 8))
        tk.Checkbutton(pl_wrap, text='Playlist', variable=self.playlist,
                       bg=PANEL, fg=FG2,
                       selectcolor=ACCENT, 
                       activebackground=PANEL, activeforeground=ACCENT_L,
                       font=F_BODY, highlightthickness=0, bd=0,
                       cursor='hand2').pack()

        # Primary Download button
        self.dlb = make_btn(footer, '⬇  DOWNLOAD', self._start,
                            ACCENT, FG, hover_bg=ACCENT_L, hover_fg=BG,
                            font=F_BTN_LG, padx=20, pady=8)
        self.dlb.pack(side='left', padx=4)

        # Stop button
        make_btn(footer, '⏹ Stop', self._stop_dl,
                 CARD, FG2, hover_bg=BORDER2, hover_fg=RED,
                 font=F_BTN, padx=14, pady=8
                 ).pack(side='left', padx=2)

        # Open folder
        make_btn(footer, '📁', self._open,
                 CARD, FG2, hover_bg=BORDER2, hover_fg=FG,
                 font=F_BTN, padx=10, pady=8
                 ).pack(side='left', padx=2)

        # Clear log (right)
        make_btn(footer, '🗑 Clear', self._clear_log,
                 PANEL, FG3, hover_bg=PANEL, hover_fg=RED,
                 font=(F_BODY[0], 8), padx=8, pady=8
                 ).pack(side='right', padx=16)

        # ── 3. Body (FILLS REMAINING MIDDLE) ──────────────────────────────────
        body = tk.Frame(self.root, bg=BG)
        body.pack(fill='both', expand=True, padx=18, pady=(12, 0))

        # ── URL row
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

        make_btn(url_row, '⎘ Paste', self._paste, CARD, FG2,
                 hover_bg=BORDER, hover_fg=FG, font=F_BODY, padx=10, pady=8
                 ).pack(side='left', padx=6)

        # ── Save To row
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

        make_btn(dir_row, '📁 Browse', self._browse, CARD, FG2,
                 hover_bg=BORDER, hover_fg=FG, font=F_BODY, padx=10, pady=8
                 ).pack(side='left', padx=6)

        # ── Options row
        self._label(body, 'OPTIONS')
        opt = tk.Frame(body, bg=BG)
        opt.pack(fill='x', pady=(3, 12))

        tc = self._pill_card(opt, 'TYPE')
        tc.pack(side='left', fill='both', expand=True, padx=(0, 6))
        for v, lbl in [('video', '🎬  Video'), ('audio', '🎵  Audio')]:
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

        # ── Progress
        self._label(body, 'PROGRESS')
        status_row = tk.Frame(body, bg=BG)
        status_row.pack(fill='x', pady=(3, 4))
        tk.Label(status_row, textvariable=self.status, bg=BG, fg=FG2,
                 font=F_MONO_S, anchor='w').pack(side='left', fill='x', expand=True)
        self.p_text = tk.Label(status_row, text='0%', bg=BG, fg=ACCENT_L, font=(F_MONO[0], 9, 'bold'))
        self.p_text.pack(side='right')

        self.pc = tk.Canvas(body, height=6, bg=BG3_SAFE(), highlightthickness=0)
        self.pc.pack(fill='x', pady=0)
        self.pc.bind('<Configure>', lambda e: self._bar())

        # ── Log section
        self.log_sec = tk.Frame(body, bg=BG)
        self.log_sec.pack(fill='x', side='top')

        lhdr = tk.Frame(self.log_sec, bg=BG)
        lhdr.pack(fill='x', pady=0)
        self.log_toggle = make_btn(lhdr, '[+] Show (Logs)', self._toggle_log,
                                   BG, FG3, hover_bg=BG, hover_fg=ACCENT_L,
                                   font=(F_LABEL[0], 7, 'bold'), padx=10, pady=4)
        self.log_toggle.pack(anchor='center')

        self.lw = tk.Frame(self.log_sec, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        sb = tk.Scrollbar(self.lw, bg=BG, troughcolor=CARD, width=8, bd=0, highlightthickness=0, relief='flat')
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
        tk.Label(row, text=text, bg=BG, fg=ACCENT, font=F_LABEL).pack(side='left')
        tk.Frame(row, bg=BORDER, height=1).pack(side='left', fill='x', expand=True,
                                                 padx=(8, 0), pady=5)

    def _label_inline(self, parent, text):
        tk.Label(parent, text=text, bg=BG, fg=ACCENT, font=F_LABEL).pack(side='left')

    def _pill_card(self, parent, title):
        f = tk.Frame(parent, bg=CARD, highlightbackground=BORDER, highlightthickness=1)
        tk.Label(f, text=title, bg=CARD, fg=FG3, font=F_LABEL).pack(anchor='w', padx=12, pady=(8, 2))
        return f

    def _radio(self, parent, label, var, value, cmd=None):
        rb = tk.Radiobutton(parent, text=label, variable=var, value=value,
                            bg=CARD, fg=FG2,
                            selectcolor=ACCENT,       # filled only when selected
                            activebackground=CARD, activeforeground=ACCENT_L,
                            font=F_BODY, command=cmd,
                            indicatoron=True, bd=0, highlightthickness=0, cursor='hand2')
        rb.pack(anchor='w', padx=12, pady=(2, 4))

    def _styled_menu(self, parent, var, choices):
        m = tk.OptionMenu(parent, var, *choices)
        m.config(bg=CARD, fg=FG, relief='flat', bd=0, font=F_BODY,
                 activebackground=BORDER, highlightthickness=0, pady=3,
                 cursor='hand2', indicatoron=False)
        m['menu'].config(bg=CARD, fg=FG, relief='flat', activebackground=ACCENT_D,
                         activeforeground=FG, bd=0, font=F_BODY)
        return m

    def _bind_focus_highlight(self, frame, entry):
        def on_focus_in(e):  frame.config(highlightbackground=ACCENT)
        def on_focus_out(e): frame.config(highlightbackground=BORDER)
        entry.bind('<FocusIn>',  on_focus_in)
        entry.bind('<FocusOut>', on_focus_out)

    def _toggle_log(self):
        # Capture width BEFORE the change to prevent any jumping
        curr_w = self.root.winfo_width()
        
        if self._log_visible:
            self.lw.pack_forget()
            self.log_toggle.config(text='[+] Show (Logs)')
        else:
            self.lw.pack(fill='x', pady=0)
            self.log_toggle.config(text='[-] Hide (Logs)')
        
        self._log_visible = not self._log_visible
        
        # Apply the new height calculation but FORCE the width to stay exactly as it was
        self.root.update_idletasks()
        target_h = self.root.winfo_reqheight()
        self.root.geometry(f"{curr_w}x{target_h}")

    def _on_type(self):
        is_v = self.dl_type.get() == 'video'
        self.qm.config(state='normal' if is_v else 'disabled')

    def _paste(self):
        try: self.url.set(self.root.clipboard_get())
        except: pass

    def _browse(self):
        d = filedialog.askdirectory(initialdir=self.outdir.get())
        if d: self.outdir.set(d)

    def _open(self):
        p = self.outdir.get()
        if sys.platform == 'win32': os.startfile(p)
        elif sys.platform == 'darwin': subprocess.Popen(['open', p])
        else: subprocess.Popen(['xdg-open', p])

    def _clear_log(self):
        self.log.config(state='normal')
        self.log.delete('1.0', 'end')
        self.log.config(state='disabled')

    def _log(self, msg, tag='dim'):
        self.log.config(state='normal')
        self.log.insert('end', msg + '\n', tag)
        self.log.see('end')
        self.log.config(state='disabled')

    def _bar(self, _=None):
        c = self.pc; w = c.winfo_width(); h = c.winfo_height()
        p = self.pct.get(); fill = int(w * p / 100)
        c.delete('all')
        # Track
        c.create_rectangle(0, 0, w, h, fill=BORDER, outline='')
        # Fill with glow effect
        if fill > 0:
            c.create_rectangle(0, 0, fill, h, fill=ACCENT, outline='')
            # thin bright highlight on top
            c.create_rectangle(0, 0, fill, max(1, h // 3), fill=ACCENT_L, outline='')
        try: self.p_text.config(text=f'{p:.1f}%')
        except: pass

    def _set_p(self, p, s=''):
        self.pct.set(p)
        if s: self.status.set(s)
        self.root.after(0, self._bar)

    # ── Startup check ─────────────────────────────────────────────────────────
    def _check(self):
        if not HAVE_YTDLP:
            self._log('❌  yt-dlp not found — run: pip install yt-dlp', 'err')
            self.dlb.config(state='disabled'); return
        self._log('✓  yt-dlp ready', 'ok')

        ff = (os.path.isfile(os.path.join(FFMPEG_DIR, 'ffmpeg.exe')) or
              os.path.isfile(os.path.join(FFMPEG_DIR, 'ffmpeg')) or
              bool(shutil.which('ffmpeg')))
        self._log('✓  ffmpeg ready' if ff else '⚠  ffmpeg not found — merging may fail',
                  'ok' if ff else 'warn')

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

    # ── Download ──────────────────────────────────────────────────────────────
    def _start(self):
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
        self.dlb.config(state='disabled', bg=ACCENT_D, fg=FG3)

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
        if self._dl:
            self._stop = True; self._log('⏹  Stopping…', 'dim')

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
        self._set_p(100, '✅  Done!')
        self._log(f'🎉  Saved to: {self.outdir.get()}', 'ok')

    def _reset(self):
        self._dl = False
        self.dlb.config(state='normal', bg=ACCENT, fg=FG)


# ── Canvas progress background helper (avoids referencing undefined CARD) ────
def BG3_SAFE():
    return CARD


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()

if __name__ == '__main__':
    main()