# StreamDrop Pro 🎬🎵
> Ultra-fast, interactive YouTube Video (MP4) and Audio (MP3) Downloader for local use.

StreamDrop Pro is a local application designed to download any YouTube link (Standard videos, YouTube Shorts, Music, Playlists) with pristine quality and rich UI/UX.

---

## ✨ Features
- **🎬 Ultra HD MP4 Video**: Download in 4K, 1440p, 1080p Full HD, 720p HD, 480p, and 360p.
- **🎵 Studio MP3 Audio**: Extract crystal clear audio in 320 kbps, 256 kbps, 192 kbps, or 128 kbps with high-res album artwork and metadata embedded automatically.
- **⚡ Instant URL Inspection**: Paste any YouTube link to immediately preview the thumbnail, title, channel name, views, and duration.
- **📊 Real-time WebSocket Progress**: Watch animated download progress bars with live speed metrics (MB/s), ETA countdown, and stage indicators (*Connecting*, *Downloading streams*, *Merging / Converting*, *Ready*).
- **📁 Windows File Explorer Integration**: One-click "Show in Folder" button to instantly reveal the downloaded video/audio file on your computer.
- **▶ Built-in Media Player**: Listen to downloaded MP3s or watch MP4s right in your browser without needing external media players.
- **💾 Dual Saving Modes**: Save directly to your local `downloads/` folder OR trigger direct browser downloads.
- **🕒 Download History**: Persistent local history list to manage and replay downloaded media.
- **🛠 Self-Contained FFmpeg**: Built-in portable FFmpeg engine ensuring seamless 1080p/4K DASH stream merging and high-fidelity MP3 conversions.

---

## 🚀 How to Run

### Option 1: Double-Click Launcher (Easiest)
Simply double-click the **`start.bat`** file in this folder. It will start the server and open the web app in your browser automatically!

### Option 2: Python Command
Run in your terminal or PowerShell:
```powershell
python run.py
```
Open **`http://127.0.0.1:8000`** in your browser.

---

## 📂 Project Structure
```
youtube-downloader/
├── app/
│   ├── main.py              # FastAPI server, REST endpoints & WebSocket progress
│   ├── downloader.py        # yt-dlp download engine with progress hooks
│   ├── ffmpeg_helper.py     # Portable FFmpeg detector and manager
│   ├── history_manager.py   # Local history store (JSON)
│   ├── static/              # CSS, JavaScript, and assets
│   │   ├── css/styles.css   # Dark glassmorphic styling & glowing animations
│   │   └── js/app.js        # Reactive UI, WebSocket client, controls
│   └── templates/
│       └── index.html       # Modern single-page app interface
├── bin/                     # Portable FFmpeg engine
├── downloads/               # Your downloaded MP4 and MP3 files
├── requirements.txt         # Python dependencies
├── run.py                   # App launcher
└── start.bat                # Windows 1-click launcher
```
