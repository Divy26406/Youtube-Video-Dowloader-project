import json
import os
import threading
from pathlib import Path
from typing import List, Dict, Any, Optional

PROJECT_ROOT = Path(__file__).resolve().parent.parent
HISTORY_FILE = PROJECT_ROOT / "history.json"
_LOCK = threading.Lock()

def _load_raw() -> List[Dict[str, Any]]:
    if not HISTORY_FILE.exists():
        return []
    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []

def _save_raw(data: List[Dict[str, Any]]):
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[HistoryManager] Save error: {e}")

def get_history(limit: int = 50) -> List[Dict[str, Any]]:
    with _LOCK:
        items = _load_raw()
        return items[:limit]

def add_or_update(task_id: str, data: Dict[str, Any]):
    with _LOCK:
        items = _load_raw()
        # Find if existing
        idx = next((i for i, item in enumerate(items) if item.get("id") == task_id), None)
        if idx is not None:
            items[idx].update(data)
        else:
            data["id"] = task_id
            items.insert(0, data)
        # Cap to 100 items
        _save_raw(items[:100])

def remove_item(task_id: str) -> bool:
    with _LOCK:
        items = _load_raw()
        new_items = [i for i in items if i.get("id") != task_id]
        if len(new_items) != len(items):
            _save_raw(new_items)
            return True
        return False

def clear_all():
    with _LOCK:
        _save_raw([])
