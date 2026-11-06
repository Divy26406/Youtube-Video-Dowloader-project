#!/usr/bin/env python3
"""
StreamDrop Pro - YouTube Downloader Launcher
Starts FastAPI web server with Uvicorn and automatically launches the web UI.
"""
import os
import sys
import time
import threading
import webbrowser
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

# Ensure UTF-8 console output on Windows
if sys.platform == "win32" and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

from app.ffmpeg_helper import setup_ffmpeg, get_ffmpeg_info

def open_browser_delayed(url: str, delay: float = 1.2):
    def _open():
        time.sleep(delay)
        print(f"\n[StreamDrop] Opening browser at {url} ...")
        webbrowser.open(url)
    t = threading.Thread(target=_open, daemon=True)
    t.start()

def get_lan_ip() -> str:
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def main():
    host = "0.0.0.0"
    port = 8000
    lan_ip = get_lan_ip()
    local_url = f"http://127.0.0.1:{port}"
    network_url = f"http://{lan_ip}:{port}"

    print("=" * 60)
    print("   🚀 StreamDrop Pro - YouTube Video & MP3 Downloader")
    print("=" * 60)

    # 1. Setup FFmpeg
    print("[1/3] Initializing FFmpeg engine...")
    ffmpeg_path = setup_ffmpeg()
    info = get_ffmpeg_info()
    if info["available"]:
        print(f"      ✓ FFmpeg active at: {info['path']}")
    else:
        print("      ⚠️ Warning: FFmpeg not detected. Some 1080p+ merging may be limited.")

    # 2. Prepare Downloads folder
    downloads_dir = PROJECT_ROOT / "downloads"
    downloads_dir.mkdir(parents=True, exist_ok=True)
    print(f"[2/3] Downloads directory ready: {downloads_dir}")

    # 3. Print URLs and Schedule Browser Opening
    print("[3/3] Web server URLs:")
    print(f"      👉 Local PC:        {local_url}")
    print(f"      📱 Wi-Fi / Network: {network_url}")
    print("-" * 60)
    open_browser_delayed(local_url)

    # 4. Start Uvicorn Server
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=host,
        port=port,
        reload=False,
        log_level="info"
    )

if __name__ == "__main__":
    main()
