<div align="center">

<h1 align="center">
  <img src="https://readme-typing-svg.herokuapp.com?font=Fira+Code&weight=700&size=32&pause=1000&color=00D4C8&center=true&vCenter=true&width=600&lines=Youtube+Downloader+Pro;High-Fidelity+Media+Engine;Desktop+%2B+Local+Cloud;Smart+Version+Control" alt="Typing SVG" />
</h1>

<p align="center">
  <b>The ultimate multimedia downloading ecosystem. Featuring a premium Desktop GUI and a mobile-friendly Local Server. Engineered for speed, stability, and intelligent updates.</b>
</p>

<!-- Preview Image -->
<p align="center">
  <img src="landing_page.png" alt="App Interface" width="800" style="border-radius: 10px; border: 1px solid #252530; box-shadow: 0 10px 30px rgba(0,0,0,0.5);" />
</p>

<!-- Preview Image 2 -->
<div align="center">
  <table>
    <tr>
      <td valign="middle">
        <img src="macos_installer_custom_theme.png" alt="MacOS Installer" width="400" style="border-radius: 10px; border: 1px solid #252530; box-shadow: 0 10px 30px rgba(0,0,0,0.5);" />
      </td>
      <td valign="middle">
        <img src="desktop.png" alt="DesktopApp Interface" width="400" style="border-radius: 10px; border: 1px solid #252530; box-shadow: 0 10px 30px rgba(0,0,0,0.5);" />
      </td>
    </tr>
  </table>
</div>

<!-- Badges -->
<p align="center">
  <img src="https://img.shields.io/badge/Developed%20By-Faysal%20Ahmmed-00D4C8?style=for-the-badge&logo=github" alt="Developer" />
  <img src="https://img.shields.io/badge/Python-3.11+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python" />
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/yt--dlp-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="yt-dlp" />
</p>

---

</div>

## 🌟 Executive Summary

This project is a comprehensive solution for downloading content from YouTube and other platforms. It provides two distinct modes of operation:
1.  **Desktop App**: A standalone, high-performance GUI for power users.
2.  **Local Server**: A FastAPI-based backend with a beautiful web UI accessible from any device (Phone, Tablet, PC) on your local network.

---

## 🔥 Key Features & Capabilities

### ⚡ Performance & Core
- **Multi-threaded Downloads**: High-speed downloading using parallel processing.
- **Support for 1000+ Sites**: Powered by `yt-dlp`, supporting almost every major video platform.
- **Smart Formatting**: Intelligent selection of the best available video/audio streams.
- **Automatic Merging**: Bundles high-quality video with high-bitrate audio using `ffmpeg`.

### 🖥️ Desktop Excellence
- **Premium Dark UI**: A modern, sleek interface with glassmorphism and subtle animations.
- **Progress Tracking**: Detailed real-time progress bars including speed, ETA, and file size.
- **Format Flexibility**: Switch between 4K, 1080p, 720p, or extract MP3/M4A audio with a single click.
- **Cross-Platform**: Built to work seamlessly on Windows, macOS, and Linux.

### 🌐 Server & Mobile GUI
- **Local Network Access**: Start the server and access the downloader from your iPhone or Android.
- **SSE Real-time Data**: Visual progress updates on mobile browsers without refreshing.
- **Background Jobs**: Start a download on your PC and monitor it from your phone.
- **Unified Experience**: The same powerful downloading engine, now accessible via a mobile-optimized web GUI.

---

## 📂 Deep Folder Structure Analysis

The project is architected into two main modules, each optimized for its specific environment.

```bash
ytdl-app/
├── 🖼️ landing_page.png      # App preview image
├── 🖥️ desktop/              # Desktop Application Module
│   ├── app.py               # Main GUI orchestration (Tkinter/Process Engine)
│   ├── build.py             # Automated cross-platform EXE/APP builder
│   ├── icon.ico             # Windows application icon
│   ├── icon.icns            # macOS application icon
│   └── ffmpeg_bin/          # Bundled binaries (ffmpeg, ffprobe)
│
├── 🌐 server/               # Local Server Module (Web Interface)
│   ├── server.py            # FastAPI backend (SSE, async workers)
│   ├── start.py             # Intelligent launcher & dependency checker
│   ├── static/              # Frontend assets
│   │   └── index.html       # Full-featured Web UI (Tailwind/JS)
│   ├── downloads/           # Saved media storage
│   └── ffmpeg_bin/          # Server-side binaries
│
├── 📄 .gitignore            # Environment exclusion rules
└── 📜 README.md             # This comprehensive documentation
```

---

## 🖥️ Desktop Application (Pro GUI)

The Desktop App is built for performance and deep integration with **Windows & macOS**.

- **Standalone Build**: Uses `PyInstaller` to bundle everything into a single `.exe` or `.app`.
- **Zero-Dependency**: Bundles `ffmpeg` and `yt-dlp` automatically.
- **Windows Taskbar Fix**: Uses `ctypes.windll` to set a custom `AppUserModelID` for proper icon grouping.

---

## 🔄 Smart Version Control & OTA Updates

The application features an **Intelligent Lifecycle Management** system that ensures you are always running the latest and most stable code.

> [!IMPORTANT]
> **How OTA Updates Work:**
> - **Continuous Polling**: On startup, the app performs a lightweight check against the `version.json` on the GitHub `main` branch.
> - **Release Matching**: If a newer version is detected, the app dynamically retrieves the platform-specific installer URL (macOS dmg, Windows exe) defined in the cloud.
> - **Seamless Downloads**: Users are notified via a premium modal dialog and can initiate the download with a single click.
> - **Zero-Config Changes**: The developer can change download locations or release tags in the cloud (via `version.json`) without requiring users to manually re-install.

---

---

## 🌐 Local Server & Web GUI

The Local Server turns your computer into a powerful private CDN for video downloads. This module has been **fully deployed with a high-end Web GUI**.

- **FastAPI Core**: High-concurrency async endpoints.
- **SSE (Server-Sent Events)**: The `/api/progress/{id}` endpoint provides a low-latency stream of progress JSON objects.
- **Static Assets**: Everything is packed into a single refined `index.html` for zero-friction deployment.
- **Responsive Design**: Optimized for mobile browsers (Safari, Chrome) for one-tap downloads on the go.

---

## 🚀 Getting Started

### Method 1: Running the Desktop App
1.  Navigate to the `desktop` folder.
2.  Run `python app.py`.
3.  **To Build an EXE**: Run `python build.py` and wait for the `dist` folder to be created in the `desktop/` directory.

### Method 2: Starting the Local Server
1.  Navigate to the `server` folder.
2.  Run `python start.py`.
3.  The launcher will automatically install requirements and open your browser.
4.  **Network Access**: Open the network IP shown in the console on your phone (e.g., `http://192.168.1.100:8080`).

---

## 🛠 Prerequisites & Dependencies

- **Python 3.11+**: The recommended environment for maximum performance.
- **ffmpeg**: Required for merging high-quality streams. (Auto-handled by the Desktop builder).
- **yt-dlp**: The backbone downloader engine.

---

## ☁️ Deploy to Railway (Server Mode)

Deploy your private downloader in 2 minutes:

1.  **Create a New Project**: On [Railway.app](https://railway.app/), click **New Project** → **Deploy from GitHub**.
2.  **Select Repository**: Choose your `YouTube-Video-Downloader` repo.
3.  **No Config Needed**: I've already added `Procfile` and `nixpacks.toml` to automatically install `ffmpeg` and start the server.
4.  **Add Domain**: In your Railway service settings, click **Generate Domain** to get your public URL.

---

---

## 👨‍💻 Developed By

<div align="center">
  <img src="https://img.shields.io/badge/Designed%20%26%20Built%20by-Faysal%20Ahmmed-00D4C8?style=for-the-badge&logo=github" alt="Faysal Ahmmed" />
  <p><i>Crafting high-performance, user-centric software for the modern era.</i></p>
</div>

---

<p align="center">
  <img src="https://readme-typing-svg.herokuapp.com?font=Fira+Code&size=16&pause=3000&color=7060AA&center=true&vCenter=true&width=435&lines=Fast.+Fluid.+Reliable.;The+Ultimate+Downloader+Experience." alt="Typing SVG" />
</p>
