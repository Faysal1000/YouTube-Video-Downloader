"""
YouTube Downloader — FastAPI Server
====================================
Endpoints:
  GET  /                    -> serve the web UI
  POST /api/info            -> get video/playlist info
  POST /api/download        -> start a download job
  GET  /api/progress/{id}   -> SSE stream of real-time progress
  GET  /api/jobs            -> list all jobs
  GET  /api/file/{id}       -> download completed file
  DELETE /api/job/{id}      -> delete a job + its file
"""

import os
import sys
import uuid
import json
import time
import shutil
import asyncio
import threading
import subprocess
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta
from urllib.parse import quote

# ── Third-party (installed by start.py) ──────────────────────────────────────
try:
    from fastapi import FastAPI, HTTPException, BackgroundTasks
    from fastapi.responses import FileResponse, StreamingResponse, HTMLResponse
    from fastapi.staticfiles import StaticFiles
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    import yt_dlp
except ImportError:
    print("Missing packages. Run:  python start.py")
    sys.exit(1)

# ─────────────────────────────────────────────────────────────────────────────
# Setup
# ─────────────────────────────────────────────────────────────────────────────

BASE_DIR     = Path(__file__).parent
DOWNLOAD_DIR = BASE_DIR / "downloads"
STATIC_DIR   = BASE_DIR / "static"
FFMPEG_DIR   = BASE_DIR / "ffmpeg_bin"
DOWNLOAD_DIR.mkdir(exist_ok=True)

app = FastAPI(title="YouTube Downloader API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static files (the web UI)
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# ─────────────────────────────────────────────────────────────────────────────
# JS Runtime + EJS helpers
# ─────────────────────────────────────────────────────────────────────────────

def _find_js_runtime():
    """Find a JS runtime (node/deno/bun). Returns (name, abs_path) or (None, None)."""
    for r in ['node.exe', 'node', 'deno.exe', 'deno', 'bun.exe', 'bun']:
        p = str(FFMPEG_DIR / r)
        if os.path.isfile(p):
            name = 'node' if 'node' in r else ('deno' if 'deno' in r else 'bun')
            return name, os.path.abspath(p)
        w = shutil.which(r)
        if w:
            name = 'node' if 'node' in r else ('deno' if 'deno' in r else 'bun')
            return name, os.path.abspath(w)
    return None, None


def _ensure_ejs_installed():
    """Install yt-dlp-ejs package if not already installed."""
    try:
        import importlib
        importlib.import_module('yt_dlp_ejs')
    except ImportError:
        try:
            subprocess.run(
                [sys.executable, '-m', 'pip', 'install', '--quiet', 'yt-dlp-ejs'],
                check=True, capture_output=True, timeout=60
            )
        except Exception:
            pass


def _get_runtime_opts() -> dict:
    """
    Get yt-dlp options for JS runtime + EJS support.
    Uses yt_dlp.parse_options() to convert CLI flags to the correct internal format.
    """
    name, path = _find_js_runtime()
    if not name or not path:
        return {}

    # Ensure runtime dir is on PATH
    rdir = os.path.dirname(path)
    curr = os.environ.get('PATH') or ''
    if rdir and rdir not in curr:
        os.environ['PATH'] = rdir + os.pathsep + curr

    try:
        cli_args = ['--js-runtimes', name]
        # Try adding remote-components (newer yt-dlp)
        try:
            _, _, _, test = yt_dlp.parse_options(['--remote-components', 'ejs:github'])
            cli_args += ['--remote-components', 'ejs:github']
        except (SystemExit, Exception):
            pass

        _, _, _, parsed = yt_dlp.parse_options(cli_args)
        result = {}
        for k in ('js_runtimes', 'remote_components'):
            if k in parsed and parsed[k] is not None:
                result[k] = parsed[k]
        return result
    except (SystemExit, Exception):
        return {}


# Install EJS on startup
_ensure_ejs_installed()
_RUNTIME_OPTS = _get_runtime_opts()  # Cache at startup


# ─────────────────────────────────────────────────────────────────────────────
# In-memory job store
# ─────────────────────────────────────────────────────────────────────────────

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()

def new_job(url, dl_type, quality, audio_fmt, video_fmt, playlist: bool = False) -> dict:
    jid = str(uuid.uuid4())[:8]
    job = {
        "id":        jid,
        "status":    "queued",
        "progress":  0.0,
        "speed":     "",
        "eta":       "",
        "filename":  "",
        "filepath":  "",
        "title":     "",
        "url":       url,
        "type":      dl_type,
        "quality":   quality,
        "audio_fmt": audio_fmt,
        "video_fmt": video_fmt,
        "playlist":  playlist,
        "created_at": datetime.now().isoformat(),
        "finished_at": None,
        "error":     "",
        "log":       [],
        "_events":   [],
        "_done":     False,
    }
    with JOBS_LOCK:
        JOBS[jid] = job
    return job


def job_log(job: dict, msg: str, level: str = "info"):
    entry = {"time": datetime.now().strftime("%H:%M:%S"), "msg": msg, "level": level}
    job["log"].append(entry)
    _push_event(job, "log", entry)


def _push_event(job: dict, event: str, data: dict):
    job["_events"].append({"event": event, "data": data})


def _push_progress(job: dict):
    _push_event(job, "progress", {
        "status":   job["status"],
        "progress": job["progress"],
        "speed":    job["speed"],
        "eta":      job["eta"],
        "filename": job["filename"],
        "title":    job["title"],
    })


# ─────────────────────────────────────────────────────────────────────────────
# Request / Response models
# ─────────────────────────────────────────────────────────────────────────────

class InfoRequest(BaseModel):
    url: str

class DownloadRequest(BaseModel):
    url:       str
    type:      str = "video"
    quality:   str = "1080p"
    audio_fmt: str = "mp3"
    video_fmt: str = "mp4"
    playlist:  bool = False

# ─────────────────────────────────────────────────────────────────────────────
# yt-dlp helpers
# ─────────────────────────────────────────────────────────────────────────────

def _ffmpeg_location() -> Optional[str]:
    """Return bundled ffmpeg dir if present, else None."""
    if FFMPEG_DIR.is_dir():
        exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
        if (FFMPEG_DIR / exe).exists():
            return str(FFMPEG_DIR)
    return None


def _ydl_base_opts(job: Optional[dict] = None) -> dict:
    """Build base yt-dlp options shared by info and download calls."""
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "ignoreerrors": True,
        "no_color": True,
        "logger": None,
    }
    ff = _ffmpeg_location()
    if ff:
        opts["ffmpeg_location"] = ff

    # JS runtime + EJS (cached at startup)
    opts.update(_RUNTIME_OPTS)

    if job:
        opts["progress_hooks"] = [lambda d, j=job: _progress_hook(j, d)]

    return opts


def _build_opts(job: dict, out_path: Path) -> dict:
    dl_type   = job["type"]
    quality   = job["quality"]
    audio_fmt = job["audio_fmt"]
    video_fmt = job["video_fmt"]

    outtmpl = str(out_path / "%(title)s.%(ext)s")

    base = {
        **_ydl_base_opts(job),
        "outtmpl": outtmpl,
        "noplaylist": not job.get("playlist", False),
    }

    if dl_type == "audio":
        return {
            **base,
            "format": "bestaudio/best",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": audio_fmt,
                "preferredquality": "192",
            }],
        }

    if quality == "best":
        fmt = f"bestvideo[ext={video_fmt}]+bestaudio/bestvideo+bestaudio/best"
    else:
        h = quality.replace("p", "")
        fmt = (
            f"bestvideo[height<={h}][ext={video_fmt}]+bestaudio"
            f"/bestvideo[height<={h}]+bestaudio"
            f"/bestvideo+bestaudio/best"
        )

    return {**base, "format": fmt, "merge_output_format": video_fmt}


def _progress_hook(job: dict, d: dict):
    if job["status"] == "cancelled":
        raise yt_dlp.utils.DownloadCancelled()

    status = d.get("status")

    if status == "downloading":
        job["status"] = "downloading"
        dl  = d.get("downloaded_bytes", 0)
        tot = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
        spd = d.get("speed") or 0
        eta = d.get("eta") or 0
        job["progress"] = round(dl / tot * 100, 1) if tot else 0
        job["speed"]    = f"{spd/1024/1024:.1f} MB/s" if spd else ""
        job["eta"]      = f"{eta}s" if eta else ""
        job["filename"] = os.path.basename(d.get("filename", ""))
        _push_progress(job)

    elif status == "finished":
        job["status"]   = "merging"
        job["progress"] = 99.0
        fname = os.path.basename(d.get("filename", ""))
        job["filename"] = fname
        job_log(job, f"✅ Downloaded: {fname}", "ok")
        _push_progress(job)


# ─────────────────────────────────────────────────────────────────────────────
# Background download worker
# ─────────────────────────────────────────────────────────────────────────────

def _run_download(job: dict):
    """Main entry point for a download job thread."""
    try:
        # Quick check for playlist
        opts_base = _ydl_base_opts()
        opts_info = {**opts_base, "extract_flat": "in_playlist", "lazy_playlist": True}
        
        with yt_dlp.YoutubeDL(opts_info) as ydl:
            info = ydl.extract_info(job["url"], download=False)
        
        if not info:
            raise Exception("Could not extract video information. Check the URL.")

        if info.get("_type") == "playlist" and job.get("playlist"):
            # Master Playlist Mode
            job["status"] = "processing_playlist"
            job["title"] = info.get("title") or "Playlist"
            _push_progress(job)
            
            raw_entries = info.get("entries")
            if raw_entries:
                for entry in raw_entries:
                    if not entry: continue
                    # Create child job
                    video_url = entry.get("url")
                    if not video_url:
                        video_id = entry.get("id")
                        if not video_id: continue
                        video_url = f"https://www.youtube.com/watch?v={video_id}"
                    
                    child = new_job(video_url, job["type"], job["quality"], job["audio_fmt"], job["video_fmt"])
                    child["title"] = entry.get("title") or "Video"
                    
                    # Notify UI of new child
                    _push_event(job, "child_job", {"id": child["id"]})
                    
                    # Run child SEQUENTIALLY
                    _perform_individual_download(child)
            
            job["status"] = "done"
            job["progress"] = 100.0
            _push_progress(job)
        else:
            # Single Video Mode
            _perform_individual_download(job)
            
    except Exception as e:
        job["status"] = "error"
        job["error"] = str(e)
        job_log(job, f"❌ Error: {e}", "error")
        _push_progress(job)
    finally:
        job["_done"] = True
        job["finished_at"] = datetime.now().isoformat()

def _perform_individual_download(job: dict):
    """The actual downloading logic for a single video job."""
    job_id  = job["id"]
    job_dir = DOWNLOAD_DIR / job_id
    job_dir.mkdir(exist_ok=True)

    try:
        if not job.get("title"):
            job["status"] = "fetching"
            _push_progress(job)

        opts = _build_opts(job, job_dir)

        class _Logger:
            def debug(self, m):   pass
            def warning(self, m): job_log(job, f"⚠ {m}", "warn")
            def error(self, m):   job_log(job, f"❌ {m}", "error")
        opts["logger"] = _Logger()

        with yt_dlp.YoutubeDL(opts) as ydl:
            # Final metadata fetch if needed
            if not job.get("title"):
                info = ydl.extract_info(job["url"], download=False)
                job["title"] = info.get("title") or "Video"
                _push_progress(job)
            
            # Start actual download
            ydl.download([job["url"]])

        # Find file
        files = sorted(job_dir.glob("**/*"), key=lambda p: p.stat().st_mtime, reverse=True)
        files = [f for f in files if f.is_file()]
        
        if files:
            job["filepath"] = str(files[0].absolute())
            job["filename"] = files[0].name
            job["status"]   = "done"
            job["progress"] = 100.0
            job_log(job, "🎉 Ready!", "ok")
        else:
            raise RuntimeError("No file found after download")

    except yt_dlp.utils.DownloadCancelled:
        job["status"] = "cancelled"
    except Exception as e:
        job["status"] = "error"
        job["error"]  = str(e)
    finally:
        job["_done"] = True
        job["finished_at"] = datetime.now().isoformat()
        _push_progress(job)


# ─────────────────────────────────────────────────────────────────────────────
# API Routes
# ─────────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    html = (STATIC_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(content=html)


@app.post("/api/info")
async def get_info(req: InfoRequest):
    """Fetch basic info about a URL without downloading."""
    try:
        opts = {
            **_ydl_base_opts(), 
            "skip_download": True, 
            "extract_flat": "in_playlist",
            "lazy_playlist": True,
            "playlist_items": "1-50" # Limit preview fetch
        }

        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(req.url, download=False)

        is_pl = info.get("_type") == "playlist"
        raw_entries = info.get("entries")
        if is_pl and raw_entries:
            entries = list(raw_entries)
        else:
            entries = [info]
            
        entries = [e for e in entries if e]

        items = []
        for e in entries[:50]:
            items.append({
                "title":     e.get("title") or e.get("id"),
                "duration":  e.get("duration"),
                "thumbnail": e.get("thumbnail"),
                "uploader":  e.get("uploader"),
            })

        return {
            "ok":          True,
            "is_playlist": is_pl,
            "title":       info.get("title") or info.get("id"),
            "count":       len(entries),
            "thumbnail":   info.get("thumbnail"),
            "uploader":    info.get("uploader"),
            "items":       items,
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/download")
async def start_download(req: DownloadRequest):
    """Start a download job (single or playlist) and return identity instantly."""
    try:
        job = new_job(req.url, req.type, req.quality, req.audio_fmt, req.video_fmt, playlist=req.playlist)
        t = threading.Thread(target=_run_download, args=(job,), daemon=True)
        t.start()
        return {"ok": True, "job_id": job["id"]}
    except Exception as e:
        print(f"DL Start Error: {e}")
        return {"ok": False, "error": str(e)}


@app.get("/api/progress/{job_id}")
async def stream_progress(job_id: str):
    """SSE endpoint — streams real-time progress events."""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        sent = 0
        yield f"data: {json.dumps({'event':'progress','data':{'status':job['status'],'progress':job['progress'],'speed':job['speed'],'eta':job['eta'],'filename':job['filename'],'title':job['title']}})}\n\n"

        while True:
            events = job["_events"]
            while sent < len(events):
                ev = events[sent]
                yield f"data: {json.dumps(ev)}\n\n"
                sent += 1

            if job["_done"]:
                yield f"data: {json.dumps({'event':'done','data':{'status':job['status'],'filename':job['filename']}})}\n\n"
                break

            await asyncio.sleep(0.3)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/api/jobs")
async def list_jobs():
    with JOBS_LOCK:
        jobs = [
            {k: v for k, v in j.items() if not k.startswith("_")}
            for j in JOBS.values()
        ]
    return {"jobs": sorted(jobs, key=lambda j: j["created_at"], reverse=True)}


@app.get("/api/job/{job_id}")
async def get_job(job_id: str):
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return {k: v for k, v in job.items() if not k.startswith("_")}


@app.get("/api/file/{id}")
async def download_file(id: str):
    """Serve the completed file for download."""
    job = JOBS.get(id)
    fpath = None
    fname = "download"

    if job:
        if job["status"] != "done":
            raise HTTPException(status_code=400, detail=f"Job status is '{job['status']}', not done")
        fpath = Path(job["filepath"])
        fname = job["filename"]
    else:
        # Fallback: Search the downloads directory for this ID
        # Check for zip first
        zip_path = DOWNLOAD_DIR / f"{id}.zip"
        if zip_path.exists():
            fpath = zip_path
            fname = zip_path.name
        else:
            # Check for directory
            job_dir = DOWNLOAD_DIR / id
            if job_dir.exists():
                files = sorted(job_dir.glob("**/*"), key=lambda p: p.stat().st_mtime, reverse=True)
                files = [f for f in files if f.is_file()]
                if files:
                    fpath = files[0]
                    fname = files[0].name

    if not fpath or not fpath.exists():
        raise HTTPException(status_code=404, detail="File not found on disk")

    def _iterfile():
        # fpath is guaranteed to be a Path item here
        with open(fpath, mode="rb") as f:
            while chunk := f.read(1024 * 1024): # 1MB chunks
                yield chunk

    # Proper response for large files to avoid browser timeout/no-internet errors
    # Use URL encoding for filenames with non-ASCII characters to avoid latin-1 errors
    # fname is guaranteed to be a string here
    encoded_filename = quote(str(fname))
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
        "Content-Length": str(fpath.stat().st_size),
        "Access-Control-Expose-Headers": "Content-Disposition"
    }

    return StreamingResponse(_iterfile(), media_type="application/octet-stream", headers=headers)


@app.delete("/api/job/{job_id}")
async def delete_job(job_id: str):
    """Cancel (if running) and delete a job + its files."""
    job = JOBS.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job["status"] = "cancelled"

    job_dir = DOWNLOAD_DIR / job_id
    if job_dir.exists():
        shutil.rmtree(job_dir, ignore_errors=True)
    zip_file = DOWNLOAD_DIR / f"{job_id}.zip"
    if zip_file.exists():
        zip_file.unlink(missing_ok=True)

    with JOBS_LOCK:
        JOBS.pop(job_id, None)

    return {"ok": True}


@app.get("/api/health")
async def health():
    name, path = _find_js_runtime()
    return {
        "ok":         True,
        "yt_dlp":     True,
        "ffmpeg":     bool(_ffmpeg_location() or shutil.which("ffmpeg")),
        "js_runtime": f"{name}: {path}" if name else "none",
    }


@app.get("/api/storage")
async def get_storage():
    """Return disk usage info for the downloads directory."""
    try:
        if not DOWNLOAD_DIR.exists():
             DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
             
        total, used, free = shutil.disk_usage(DOWNLOAD_DIR)
        
        # Calculate size of downloads folder safely
        dl_size = 0
        for f in DOWNLOAD_DIR.glob('**/*'):
            if f.is_file():
                try:
                    dl_size += f.stat().st_size
                except Exception: continue
        
        return {
            "total": total,
            "used": used,
            "free": free,
            "downloads_size": dl_size,
            "job_count": len(JOBS)
        }
    except Exception as e:
        print(f"Storage Error: {e}")
        return {
            "total": 0, "used": 0, "free": 0,
            "downloads_size": 0, "job_count": len(JOBS),
            "error": str(e)
        }


@app.get("/api/local-files")
async def list_local_files():
    """List all completed files currently available in the downloads folder."""
    files = []
    # Search for all files in the downloads directory
    # Standard downloads are in folders named by Job ID
    for item in DOWNLOAD_DIR.iterdir():
        if item.is_dir():
            # Check for files inside job-id directories
            for sub_item in item.glob('*'):
                if sub_item.is_file():
                    files.append({
                        "name": sub_item.name,
                        "path": str(sub_item.relative_to(DOWNLOAD_DIR)),
                        "size": sub_item.stat().st_size,
                        "mtime": sub_item.stat().st_mtime,
                        "job_id": item.name
                    })
        elif item.is_file() and item.suffix == ".zip":
            # Check for zip files (playlists)
            files.append({
                "name": item.name,
                "path": item.name,
                "size": item.stat().st_size,
                "mtime": item.stat().st_mtime,
                "job_id": item.stem
            })
            
    return {"files": sorted(files, key=lambda f: f["mtime"], reverse=True)}


@app.post("/api/clean-all")
async def clean_all():
    """Immediately delete ALL jobs and files in the downloads directory."""
    try:
        with JOBS_LOCK:
            JOBS.clear()
        
        # Remove all contents of DOWNLOAD_DIR
        for item in DOWNLOAD_DIR.iterdir():
            if item.is_dir():
                shutil.rmtree(item, ignore_errors=True)
            elif item.is_file():
                item.unlink(missing_ok=True)
                
        return {"ok": True, "message": "All jobs and files cleared."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ─────────────────────────────────────────────────────────────────────────────
# Cleanup Task
# ─────────────────────────────────────────────────────────────────────────────

async def cleanup_old_jobs():
    """Background task to delete jobs and files older than 5 minutes."""
    while True:
        try:
            now = datetime.now()
            to_delete = []
            
            with JOBS_LOCK:
                for jid, job in JOBS.items():
                    # If job is not done, check created_at (maybe it's stuck)
                    # If job is done, check finished_at
                    ref_time_str = job.get("finished_at") or job.get("created_at")
                    ref_time = datetime.fromisoformat(ref_time_str)
                    
                    if now - ref_time > timedelta(hours=6):
                        to_delete.append(jid)
            
            for jid in to_delete:
                print(f"Cleanup: Removing old job {jid}")
                job_dir = DOWNLOAD_DIR / jid
                if job_dir.exists():
                    shutil.rmtree(job_dir, ignore_errors=True)
                zip_file = DOWNLOAD_DIR / f"{jid}.zip"
                if zip_file.exists():
                    zip_file.unlink(missing_ok=True)
                
                with JOBS_LOCK:
                    JOBS.pop(jid, None)
                    
        except Exception as e:
            print(f"Cleanup Error: {e}")
            
        await asyncio.sleep(60 * 60 * 6) # Run every 6 hours


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(cleanup_old_jobs())
