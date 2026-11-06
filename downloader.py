import os
import re
import time
import asyncio
from pathlib import Path
from typing import Dict, Any, Callable, Optional
import yt_dlp

from app.ffmpeg_helper import setup_ffmpeg

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DOWNLOAD_DIR = PROJECT_ROOT / "downloads"
DEFAULT_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)

# Active tasks cancellation registry
_ACTIVE_TASKS: Dict[str, Dict[str, Any]] = {}

def get_default_download_dir() -> str:
    """Returns absolute path to download folder, creates if missing."""
    DEFAULT_DOWNLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return str(DEFAULT_DOWNLOAD_DIR)

def cancel_task(task_id: str) -> bool:
    if task_id in _ACTIVE_TASKS:
        _ACTIVE_TASKS[task_id]["cancel"] = True
        return True
    return False

def extract_video_info(url: str) -> Dict[str, Any]:
    """
    Extracts rich video metadata and available quality options without downloading.
    """
    ffmpeg_path = setup_ffmpeg()
    
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": False,
        "skip_download": True,
    }
    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = ffmpeg_path

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if not info:
            raise ValueError("Unable to extract video information for the provided URL.")
        
        # Handle playlist if returned as multiple entries
        if "entries" in info and info["entries"]:
            # Single entry preview or first entry
            entries = list(info["entries"])
            first_entry = entries[0] if entries else {}
            title = info.get("title") or first_entry.get("title", "Playlist")
            thumbnail = first_entry.get("thumbnail") or info.get("thumbnail") or ""
            uploader = info.get("uploader") or first_entry.get("uploader", "Unknown")
            duration = first_entry.get("duration", 0)
            is_playlist = True
            entry_count = len(entries)
        else:
            first_entry = info
            title = info.get("title", "Unknown Title")
            thumbnail = info.get("thumbnail") or ""
            uploader = info.get("uploader") or info.get("channel") or "Unknown Channel"
            duration = info.get("duration", 0)
            is_playlist = False
            entry_count = 1

        # Calculate duration string
        if duration:
            m, s = divmod(int(duration), 60)
            h, m = divmod(m, 60)
            duration_str = f"{h:02d}:{m:02d}:{s:02d}" if h > 0 else f"{m:02d}:{s:02d}"
        else:
            duration_str = "Live / Unknown"

        # Scan formats for available heights
        formats = first_entry.get("formats", [])
        available_heights = set()
        for f in formats:
            h = f.get("height")
            if h and isinstance(h, int) and h >= 144:
                available_heights.add(h)

        sorted_heights = sorted(list(available_heights), reverse=True)
        
        # Friendly quality labels
        quality_options = []
        for h in [2160, 1440, 1080, 720, 480, 360]:
            if any(avail >= h for avail in sorted_heights):
                label_map = {
                    2160: "4K (2160p)",
                    1440: "2K (1440p)",
                    1080: "1080p (Full HD)",
                    720: "720p (HD)",
                    480: "480p (SD)",
                    360: "360p (Data Saver)"
                }
                quality_options.append({"height": str(h), "label": label_map.get(h, f"{h}p")})

        if not quality_options:
            quality_options = [{"height": "best", "label": "Best Available"}]

        return {
            "id": first_entry.get("id"),
            "title": title,
            "thumbnail": thumbnail,
            "uploader": uploader,
            "channel_url": first_entry.get("channel_url", ""),
            "duration": duration,
            "duration_str": duration_str,
            "view_count": first_entry.get("view_count", 0),
            "upload_date": first_entry.get("upload_date", ""),
            "webpage_url": first_entry.get("webpage_url", url),
            "is_playlist": is_playlist,
            "entry_count": entry_count,
            "video_qualities": quality_options,
            "audio_qualities": [
                {"bitrate": "320", "label": "320 kbps (High Quality Ultra)"},
                {"bitrate": "256", "label": "256 kbps (High Fidelity)"},
                {"bitrate": "192", "label": "192 kbps (Standard)"},
                {"bitrate": "128", "label": "128 kbps (Compact)"}
            ]
        }

def format_bytes(num_bytes: Optional[float]) -> str:
    if not num_bytes or num_bytes <= 0:
        return "0 B"
    for unit in ["B", "KB", "MB", "GB"]:
        if num_bytes < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0
    return f"{num_bytes:.1f} TB"

def format_eta(seconds: Optional[int]) -> str:
    if seconds is None or seconds < 0:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"

class DownloadCancelledException(Exception):
    pass

def execute_download(
    task_id: str,
    url: str,
    format_type: str,
    quality: str,
    output_dir: str,
    progress_callback: Callable[[Dict[str, Any]], None]
) -> Dict[str, Any]:
    """
    Synchronously downloads and processes media with yt-dlp, invoking progress_callback.
    """
    _ACTIVE_TASKS[task_id] = {"cancel": False}
    ffmpeg_path = setup_ffmpeg()
    
    out_dir = Path(output_dir) if output_dir else DEFAULT_DOWNLOAD_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    # Sanitize title template for Windows safety
    outtmpl = str(out_dir / "%(title).120B [%(id)s].%(ext)s")

    last_update_time = [0.0]
    final_filepath = [""]

    def progress_hook(d: Dict[str, Any]):
        if _ACTIVE_TASKS.get(task_id, {}).get("cancel", False):
            raise DownloadCancelledException("Download cancelled by user.")

        now = time.time()
        status = d.get("status")

        if status == "downloading":
            # Throttle progress emits to at most 10/sec for UI smoothness
            if now - last_update_time[0] < 0.1:
                return
            last_update_time[0] = now

            downloaded = d.get("downloaded_bytes", 0)
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            
            percent = 0.0
            if total > 0:
                percent = round((downloaded / total) * 100, 1)
            elif "_percent_str" in d:
                clean_pct = re.sub(r"[^\d.]", "", d.get("_percent_str", "0"))
                try:
                    percent = float(clean_pct)
                except ValueError:
                    percent = 0.0

            speed_bps = d.get("speed") or 0
            speed_str = f"{format_bytes(speed_bps)}/s" if speed_bps else "Calculating..."
            eta_sec = d.get("eta")
            eta_str = format_eta(eta_sec)

            progress_callback({
                "taskId": task_id,
                "status": "downloading",
                "stage": "Downloading stream...",
                "progress": percent,
                "downloadedBytes": downloaded,
                "downloadedStr": format_bytes(downloaded),
                "totalBytes": total,
                "totalStr": format_bytes(total) if total > 0 else "Estimating...",
                "speed": speed_str,
                "eta": eta_str
            })

        elif status == "finished":
            final_filepath[0] = d.get("filename", "")
            progress_callback({
                "taskId": task_id,
                "status": "processing",
                "stage": "Merging & post-processing...",
                "progress": 98.0,
                "speed": "Finalizing",
                "eta": "00:01"
            })

    # Prepare yt-dlp options based on MP4 or MP3
    postprocessors = []
    
    if format_type.lower() == "mp3":
        ydl_format = "bestaudio/best"
        postprocessors.append({
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": quality if quality and quality != "best" else "320",
        })
        postprocessors.append({
            "key": "FFmpegMetadata",
            "add_metadata": True,
        })
        postprocessors.append({
            "key": "EmbedThumbnail",
            "already_have_thumbnail": False
        })
        ydl_opts = {
            "format": ydl_format,
            "outtmpl": outtmpl,
            "postprocessors": postprocessors,
            "writethumbnail": True,
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
        }
    else:
        # MP4 video mode
        if quality == "best" or not quality:
            ydl_format = "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4] / bv*+ba/b"
        else:
            h = quality.replace("p", "")
            ydl_format = f"bv*[height<={h}][ext=mp4]+ba[ext=m4a]/b[height<={h}][ext=mp4] / bv*[height<={h}]+ba/b[height<={h}] / best"
        
        ydl_opts = {
            "format": ydl_format,
            "outtmpl": outtmpl,
            "merge_output_format": "mp4",
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
        }

    if ffmpeg_path:
        ydl_opts["ffmpeg_location"] = ffmpeg_path

    try:
        progress_callback({
            "taskId": task_id,
            "status": "starting",
            "stage": "Connecting to YouTube...",
            "progress": 0.0,
            "speed": "Connecting",
            "eta": "--:--"
        })

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            meta = ydl.extract_info(url, download=True)
            
            # Resolve actual downloaded file path
            resolved_path = ""
            if "requested_downloads" in meta and meta["requested_downloads"]:
                resolved_path = meta["requested_downloads"][0].get("filepath", "")
            if not resolved_path or not os.path.exists(resolved_path):
                # Search matching file in output dir
                expected_ext = ".mp3" if format_type.lower() == "mp3" else ".mp4"
                video_id = meta.get("id", "")
                for file in out_dir.iterdir():
                    if video_id in file.name and file.suffix.lower() == expected_ext:
                        resolved_path = str(file)
                        break

            file_size = os.path.getsize(resolved_path) if resolved_path and os.path.exists(resolved_path) else 0

            result = {
                "id": task_id,
                "taskId": task_id,
                "status": "completed",
                "stage": "Download Complete!",
                "progress": 100.0,
                "title": meta.get("title", "YouTube Media"),
                "format": format_type.upper(),
                "quality": quality,
                "filePath": resolved_path,
                "fileName": os.path.basename(resolved_path) if resolved_path else "downloaded_file",
                "fileSize": format_bytes(file_size),
                "thumbnail": meta.get("thumbnail", ""),
                "duration": meta.get("duration", 0),
                "uploader": meta.get("uploader", "Unknown"),
                "timestamp": time.time()
            }
            progress_callback(result)
            return result

    except DownloadCancelledException:
        result = {
            "taskId": task_id,
            "status": "cancelled",
            "stage": "Download was cancelled.",
            "progress": 0.0
        }
        progress_callback(result)
        return result
    except Exception as e:
        err_msg = str(e)
        result = {
            "taskId": task_id,
            "status": "error",
            "stage": f"Error: {err_msg}",
            "progress": 0.0,
            "error": err_msg
        }
        progress_callback(result)
        raise e
    finally:
        _ACTIVE_TASKS.pop(task_id, None)
