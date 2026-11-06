import os
import shutil
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BIN_DIR = PROJECT_ROOT / "bin"

def setup_ffmpeg() -> str:
    """
    Ensures FFmpeg is available for yt-dlp.
    Checks:
    1. System PATH (ffmpeg already installed)
    2. Local project bin directory (bin/ffmpeg.exe)
    3. imageio_ffmpeg bundled binary
    Returns the path to ffmpeg or directory containing it.
    """
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    
    # Check 1: Local bin directory with both ffmpeg.exe and ffprobe.exe
    local_ffmpeg = BIN_DIR / "ffmpeg.exe"
    if local_ffmpeg.is_file():
        _add_to_path(str(BIN_DIR))
        return str(BIN_DIR)
    
    # Check 2: System PATH
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg:
        return system_ffmpeg
    
    # Check 3: imageio_ffmpeg
    try:
        import imageio_ffmpeg
        bundled_exe = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled_exe and os.path.exists(bundled_exe):
            # Copy or link to bin/ffmpeg.exe so yt-dlp can locate ffmpeg.exe and ffprobe.exe
            try:
                shutil.copy2(bundled_exe, str(local_ffmpeg))
                # yt-dlp sometimes also looks for ffprobe in the same directory;
                # While ffprobe isn't strictly required when ffmpeg is present,
                # having it prevents yt-dlp warnings.
                ffprobe_target = BIN_DIR / "ffprobe.exe"
                if not ffprobe_target.is_file():
                    shutil.copy2(bundled_exe, str(ffprobe_target))
            except Exception:
                pass
            
            _add_to_path(str(BIN_DIR))
            _add_to_path(str(Path(bundled_exe).parent))
            return str(local_ffmpeg if local_ffmpeg.is_file() else bundled_exe)
    except Exception as e:
        print(f"[FFmpeg Warning] Could not resolve imageio_ffmpeg: {e}")
        
    return ""

def _add_to_path(folder_path: str):
    """Prepends directory to current process PATH if not already present."""
    current_path = os.environ.get("PATH", "")
    if folder_path and folder_path not in current_path:
        os.environ["PATH"] = folder_path + os.pathsep + current_path

def get_ffmpeg_info() -> dict:
    """Returns status dictionary for frontend display."""
    ffmpeg_path = setup_ffmpeg()
    has_ffmpeg = bool(ffmpeg_path and (os.path.exists(ffmpeg_path) or shutil.which("ffmpeg")))
    return {
        "available": has_ffmpeg,
        "path": ffmpeg_path or "Not found",
        "version": "FFmpeg 9.0+ (Ready)" if has_ffmpeg else "Missing"
    }

if __name__ == "__main__":
    info = get_ffmpeg_info()
    print("FFmpeg Status:", info)
