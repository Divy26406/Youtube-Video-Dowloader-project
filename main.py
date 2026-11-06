import asyncio
import os
import re
import sys
import time
import uuid
import urllib.parse
from pathlib import Path
from typing import Dict, Any, List

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.downloader import (
    extract_video_info,
    execute_download,
    cancel_task,
    get_default_download_dir
)
from app.ffmpeg_helper import get_ffmpeg_info
from app.history_manager import get_history, add_or_update, remove_item, clear_all

APP_DIR = Path(__file__).resolve().parent
STATIC_DIR = APP_DIR / "static"
TEMPLATES_DIR = APP_DIR / "templates"

app = FastAPI(title="StreamDrop Pro - Commercial YouTube Downloader", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static and media directories
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
app.mount("/media", StaticFiles(directory=str(get_default_download_dir())), name="media")

# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

ws_manager = ConnectionManager()

# Request schemas
class InfoRequest(BaseModel):
    url: str

class DownloadRequest(BaseModel):
    url: str
    format: str = "mp4"      # "mp4" or "mp3"
    quality: str = "best"    # "best", "1080", "720", "320", etc.

class OpenFolderRequest(BaseModel):
    taskId: str = ""

def clean_old_files(max_age_hours: int = 24):
    """Removes temporary files older than 24 hours so disk doesn't overflow."""
    try:
        downloads_dir = Path(get_default_download_dir())
        now = time.time()
        for f in downloads_dir.iterdir():
            if f.is_file():
                if now - f.stat().st_mtime > max_age_hours * 3600:
                    try:
                        f.unlink()
                    except Exception:
                        pass
    except Exception as e:
        print(f"[Housekeeping] Error cleaning files: {e}")

def get_task_file_info(task_id: str):
    """Finds task record and validates target file existence."""
    items = get_history(limit=100)
    task = next((i for i in items if i.get("id") == task_id or i.get("taskId") == task_id), None)
    if not task:
        return None, None, None

    file_path = task.get("filePath")
    if not file_path or not os.path.exists(file_path):
        # Fallback: check if file with matching ID exists in downloads directory
        downloads_dir = Path(get_default_download_dir())
        ext = ".mp3" if task.get("format") == "MP3" else ".mp4"
        for f in downloads_dir.iterdir():
            if task_id in f.name and f.suffix.lower() == ext:
                file_path = str(f)
                break

    if not file_path or not os.path.exists(file_path):
        return None, None, None

    filename = task.get("fileName") or os.path.basename(file_path)
    return task, file_path, filename

def make_safe_content_disposition(filename: str, as_attachment: bool = True) -> str:
    """
    Creates an RFC 5987 / RFC 6266 compliant Content-Disposition header.
    Prevents Latin-1 encoding crashes with non-ASCII or full-width characters.
    """
    disposition = "attachment" if as_attachment else "inline"
    # Safe ASCII fallback for older clients
    ascii_name = re.sub(r'[^\w\s\.-]', '_', filename).strip() or "downloaded_media"
    # UTF-8 encoded name for modern browsers (Chrome, Safari, Firefox, Edge, iOS, Android)
    encoded_name = urllib.parse.quote(filename, encoding='utf-8')
    return f'{disposition}; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_name}'

@app.get("/", response_class=HTMLResponse)
async def get_index():
    index_path = TEMPLATES_DIR / "index.html"
    if not index_path.exists():
        return HTMLResponse("<h1>StreamDrop Pro templates missing</h1>", status_code=500)
    with open(index_path, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

@app.get("/api/status")
async def get_status(request: Request):
    ffmpeg = get_ffmpeg_info()
    client_host = request.client.host if request.client else ""
    is_localhost = client_host in ["127.0.0.1", "localhost", "::1", "testclient"]
    return {
        "status": "online",
        "ffmpeg": ffmpeg,
        "is_localhost": is_localhost,
        "default_dir": get_default_download_dir()
    }

@app.post("/api/info")
async def fetch_info(req: InfoRequest):
    if not req.url or not req.url.strip():
        raise HTTPException(status_code=400, detail="A valid YouTube URL is required.")
    try:
        loop = asyncio.get_running_loop()
        info = await loop.run_in_executor(None, extract_video_info, req.url.strip())
        return JSONResponse(info)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

def _run_download_job(task_id: str, url: str, format_type: str, quality: str, out_dir: str):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    def on_progress(data: Dict[str, Any]):
        asyncio.run(ws_manager.broadcast(data))
        if data.get("status") in ["completed", "error"]:
            add_or_update(task_id, data)

    try:
        execute_download(
            task_id=task_id,
            url=url,
            format_type=format_type,
            quality=quality,
            output_dir=out_dir,
            progress_callback=on_progress
        )
    except Exception as e:
        print(f"[Download Error] Task {task_id}: {e}")
    finally:
        # Prune old files periodically
        clean_old_files()

@app.post("/api/download")
async def start_download(req: DownloadRequest, background_tasks: BackgroundTasks):
    task_id = str(uuid.uuid4())[:8]
    out_dir = get_default_download_dir()

    add_or_update(task_id, {
        "taskId": task_id,
        "id": task_id,
        "url": req.url,
        "format": req.format.upper(),
        "quality": req.quality,
        "status": "starting",
        "stage": "Connecting to YouTube...",
        "progress": 0.0,
        "timestamp": time.time()
    })

    background_tasks.add_task(
        _run_download_job,
        task_id=task_id,
        url=req.url.strip(),
        format_type=req.format,
        quality=req.quality,
        out_dir=out_dir
    )

    return {"taskId": task_id, "status": "started"}

@app.get("/api/download/task/{task_id}")
async def download_task_file(task_id: str):
    """
    Downloads file directly into visitor's device/browser.
    Fully immune to Unicode / Latin-1 encoding errors.
    """
    task, file_path, filename = get_task_file_info(task_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="Requested media file is not available or has expired.")

    media_type = "audio/mpeg" if filename.lower().endswith(".mp3") else "video/mp4"
    content_disp = make_safe_content_disposition(filename, as_attachment=True)

    return FileResponse(
        path=file_path,
        media_type=media_type,
        headers={"Content-Disposition": content_disp}
    )

@app.get("/api/stream/task/{task_id}")
async def stream_task_file(task_id: str):
    """
    Streams file for in-browser media playback with pure Accept-Ranges headers.
    """
    task, file_path, filename = get_task_file_info(task_id)
    if not file_path:
        raise HTTPException(status_code=404, detail="Media file not found.")

    media_type = "audio/mpeg" if filename.lower().endswith(".mp3") else "video/mp4"
    return FileResponse(
        path=file_path,
        media_type=media_type
    )

@app.post("/api/cancel/{task_id}")
async def cancel_download(task_id: str):
    success = cancel_task(task_id)
    return {"taskId": task_id, "cancelled": success}

@app.get("/api/history")
async def fetch_history():
    return JSONResponse(get_history())

@app.delete("/api/history/{task_id}")
async def delete_history_item(task_id: str):
    task, file_path, _ = get_task_file_info(task_id)
    if file_path and os.path.exists(file_path):
        try:
            os.remove(file_path)
        except Exception:
            pass
    removed = remove_item(task_id)
    return {"success": removed}

@app.delete("/api/history")
async def clear_history():
    clear_all()
    return {"success": True}

@app.post("/api/open-folder")
async def open_folder(req: OpenFolderRequest, request: Request):
    """Only available if client is localhost."""
    client_host = request.client.host if request.client else ""
    if client_host not in ["127.0.0.1", "localhost", "::1"]:
        return {"success": False, "error": "Folder viewing is only supported on the local server host."}

    target_path = Path(get_default_download_dir())
    if req.taskId:
        _, file_path, _ = get_task_file_info(req.taskId)
        if file_path:
            target_path = Path(file_path)

    try:
        if sys.platform == "win32":
            import subprocess
            if target_path.is_file():
                subprocess.run(["explorer", f"/select,{str(target_path)}"])
            else:
                os.startfile(str(target_path))
        return {"success": True}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.websocket("/ws/progress")
async def websocket_progress(websocket: WebSocket):
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        ws_manager.disconnect(websocket)
