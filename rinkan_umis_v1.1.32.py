# =============================================================================
# RINKAN UMIS (Universal Media Ingest System)
# Version: 1.0.0
# =============================================================================

import flet as ft
import os
import shutil
import json
import time
import datetime
import threading
import subprocess
import glob
import psutil
import platform
import sys
import re
import uuid
import hashlib
import tempfile
import queue
import urllib.request
from pathlib import Path
from typing import Dict, Optional, List
from PIL import Image, UnidentifiedImageError, ImageOps

# --- Constants ---
APP_NAME = "RINKAN UMIS"
VERSION = "1.1.32"
UPDATE_DATE = datetime.date.today().strftime("%Y-%m-%d")
DAY_COUNT_FIXED = 4  # v7: 撮影日数は4日固定
PB_WIDTH = 260       # v1.1.24: プログレスバーの固定幅

APP_DATA_DIR = Path.home() / ".rinkan_umis"
THUMB_CACHE_DIR = APP_DATA_DIR / "thumbnails"
PREVIEW_CACHE_DIR = APP_DATA_DIR / "previews" # v8.0.4: プレビュー用キャッシュ
THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)
PREVIEW_CACHE_DIR.mkdir(parents=True, exist_ok=True)
# v10.6.0: 再生時間キャッシュ（ffprobe 呼び出しを最小化）
DURATION_CACHE_PATH = APP_DATA_DIR / "duration_cache.json"
_duration_cache: dict = {}
_duration_cache_dirty = False
_duration_cache_lock = threading.Lock()  # スレッドセーフアクセス用
_duration_save_timer: Optional[threading.Timer] = None  # 書き込みデバウンス用

def _load_duration_cache():
    global _duration_cache
    try:
        if DURATION_CACHE_PATH.exists():
            with open(DURATION_CACHE_PATH, "r", encoding="utf-8") as fp:
                _duration_cache = json.load(fp)
    except: pass

def _save_duration_cache():
    global _duration_cache_dirty, _duration_save_timer
    _duration_save_timer = None
    with _duration_cache_lock:
        if not _duration_cache_dirty: return
        try:
            with open(DURATION_CACHE_PATH, "w", encoding="utf-8") as fp:
                json.dump(_duration_cache, fp, ensure_ascii=False)
            _duration_cache_dirty = False
        except: pass

def _schedule_duration_cache_save():
    """デバウンスによる書き込み: 最後の更新から2秒後に1回だけ保存"""
    global _duration_save_timer
    if _duration_save_timer is not None:
        _duration_save_timer.cancel()
    _duration_save_timer = threading.Timer(2.0, _save_duration_cache)
    _duration_save_timer.daemon = True
    _duration_save_timer.start()

_load_duration_cache()

# v7.6.4: UIの安定性を保証する最小サイズとパネル比率の定義
MIN_WINDOW_WIDTH = 1100
MIN_WINDOW_HEIGHT = 800
MAX_SCENE_PANEL_RATIO = 0.25 # 3:1 (Source:Scene) -> Scene is max 25% of total width

# --- 共通ディレクトリの定義 ---
if getattr(sys, 'frozen', False):
    if platform.system() == "Windows":
        base_dir = Path(os.getenv("APPDATA")) / "Rinkan_UMIS"
    else:
        base_dir = Path.home() / "Library" / "Application Support" / "Rinkan_UMIS"
else:
    base_dir = Path(__file__).parent

PROJECTS_DIR = base_dir / "projects"
HISTORY_FILE = PROJECTS_DIR / "history.json"
TEMP_DIR_FIXED = Path.home() / "Rinkan_UMIS_temp"
TEMP_DIR_FIXED.mkdir(parents=True, exist_ok=True)

THUMB_CACHE_DIR = base_dir / "thumb_cache"
THUMB_CACHE_DIR.mkdir(parents=True, exist_ok=True)

# --- 1. Constants & Styles ---
class UIStyles:
    COLOR_PRIMARY = "#4285F4"       # Google Blue / Active State
    COLOR_BG_DARK = "#000000"       # Pure Black for Main
    COLOR_BG_SIDEBAR = "#111111"    # Sidebar and Panels
    COLOR_BG_HOVER = "#2A2A2A"      # Hover state
    COLOR_TEXT_MAIN = "#FFFFFF"     # High Emphasis
    COLOR_TEXT_SEC = "#909090"      # Low Emphasis
    COLOR_DIVIDER = "#222222"       # Subtle Dividers
    COLOR_ACCENT_PURPLE = "#8B5CF6" # Tag / Category Accent
    COLOR_ACCENT_GREEN = "#10B981"  # Success / Selected Accent

# UI Constants
SIDEBAR_WIDTH = 220
INSPECTOR_WIDTH_DEFAULT = 320
HEADER_HEIGHT = 80

# Backward compatibility and global style constants
COLOR_PRIMARY = UIStyles.COLOR_PRIMARY
COLOR_BG_DARK = UIStyles.COLOR_BG_DARK
COLOR_BG_SIDEBAR = UIStyles.COLOR_BG_SIDEBAR
COLOR_BG_HOVER = UIStyles.COLOR_BG_HOVER
COLOR_TEXT_MAIN = UIStyles.COLOR_TEXT_MAIN
COLOR_TEXT_SEC = UIStyles.COLOR_TEXT_SEC
COLOR_DIVIDER = UIStyles.COLOR_DIVIDER
COLOR_ACCENT_PURPLE = UIStyles.COLOR_ACCENT_PURPLE
COLOR_ACCENT_GREEN = UIStyles.COLOR_ACCENT_GREEN

COLOR_ACCENT = COLOR_PRIMARY
COLOR_SUCCESS = COLOR_ACCENT_GREEN
COLOR_ERROR = "#FF5252"
COLOR_BG_MAIN = COLOR_BG_DARK
COLOR_BG_CARD = COLOR_BG_HOVER
COLOR_BADGE = "#E91E63"
COLOR_DISABLED_BTN_BG = "#333333"
COLOR_DISABLED_BTN_TEXT = "#666666"
COLOR_PROGRESS_PHASE1 = COLOR_PRIMARY
COLOR_PROGRESS_PHASE2 = COLOR_ACCENT_GREEN  # フェーズ2: リネーム整理
COLOR_SELECT_MODE = COLOR_ACCENT_GREEN
COLOR_WARNING = "#FFB300"

# --- Default Scenes ---
DEFAULT_SCENES_RAW = {
    0: ["全体写真", "班別写真", "裏方", "インサート", "自然"],
    1: ["会場到着", "開校式", "ふれあいタイム", "昼食", "班別1", "全体企画", "ふれあいテント村", "自然散策", "班別写真", "創作活動", "夕食", "班別2", "閉め勤行_就寝"],
    2: ["起床_勤行", "朝食", "ダンス練習", "全体写真", "カレー作り", "班別3", "創作活動2", "夕食", "CF", "班別4", "閉め勤行_就寝"],
    3: ["起床_勤行", "朝食", "班別5", "昼食", "閉校式_お別れ"],
    4: ["予備日_全体", "予備日_班別"]
}

HELP_TEXTS = {
    "rename_date": "ファイルのメタデータ（EXIF）または更新日時から取得した日付をファイル名に付与します。",
    "rename_venue": "選択した会場名をファイル名に付与します。",
    "rename_scene": "選択したシーン名をファイル名に付与します。",
    "rename_pg": "選択したカメラマンの名前をファイル名に付与します。",
    "rename_id": "ドライブ名などから取得したカード識別番号をファイル名に付与します。",
    "date_format": "ファイル名に使用する日付の形式（YYMMDD等）を選択します。",
    "show_file_log": "ファイルごとのコピー・検証結果をログエリアに表示します。オフにすると処理速度がわずかに向上します。",
    "scene_numbering": "シーン名に「Day番号+連番」を付与します（例: 101_会場到着）。",
    "use_sequential": "元のファイル名を破棄し、0001から始まる連番でリネームします。",
    "emergency_fmt": "取り込み未完了でも強制的に初期化ボタンを有効にします。誤操作に注意してください。",
    "create_sub_folder": "各シーンフォルダの中に、選別用のサブフォルダを自動的に作成します。",
    "sub_folder_name": "自動作成するサブフォルダの名前（例: 選別, select）を指定します。",
    "category_Photo": "静止画（JPG, PNG等）を「写真」などのフォルダに自動で振り分けます。",
    "category_Movie": "動画（MP4, MOV等）を「動画」などのフォルダに自動で振り分けます。",
    "category_Raw": "Rawデータ（ARW, CR2等）を「Raw」などのフォルダに自動で振り分けます。",
    "category_Audio": "音声データ（WAV, MP3等）を「音声」などのフォルダに自動で振り分けます。",
}

CAT_ICONS = {
    "Photo": (ft.Icons.IMAGE, "#4CAF50"),
    "Movie": (ft.Icons.VIDEOCAM, "#2196F3"),
    "Raw": (ft.Icons.RAW_ON, "#FF9800"),
    "Audio": (ft.Icons.AUDIOTRACK, "#9C27B0"),
}

# --- 1. History Logger ---
class HistoryLogger:
    def __init__(self):
        self.history_dir = base_dir / "history"
        self.history_dir.mkdir(parents=True, exist_ok=True)

    def _get_current_file(self):
        return self.history_dir / f"history_{datetime.datetime.now().strftime('%Y%m')}.json"

    def add_entry(self, entry: Dict):
        path = self._get_current_file()
        data = []
        if path.exists():
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
            except: pass
        data.insert(0, entry)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

    def get_history(self) -> List[Dict]:
        all_data = []
        files = sorted(self.history_dir.glob("history_*.json"), reverse=True)
        for f in files:
            try:
                with open(f, 'r', encoding='utf-8') as fh:
                    all_data.extend(json.load(fh))
            except: pass
        return all_data

    def update_formatted_status(self, execution_id: str, formatted: bool):
        files = sorted(self.history_dir.glob("history_*.json"), reverse=True)
        for f in files:
            try:
                with open(f, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                updated = False
                for entry in data:
                    if entry.get("id") == execution_id:
                        entry["formatted"] = formatted
                        updated = True; break
                if updated:
                    with open(f, 'w', encoding='utf-8') as fh:
                        json.dump(data, fh, indent=4, ensure_ascii=False)
                    return True
            except: pass
        return False

    def clear_history(self):
        for f in self.history_dir.glob("history_*.json"):
            try: os.remove(f)
            except: pass

# --- 2. Config Manager ---
class ConfigManager:
    def __init__(self, project_name="初期プロジェクト"):
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        self.project_name = project_name
        self.config_path = PROJECTS_DIR / f"{project_name}.json"
        self.data = self._load_config()
        if "is_first_run" not in self.data:
            self.data["is_first_run"] = True

    def _load_config(self) -> Dict:
        default_scenes = []
        for day, names in DEFAULT_SCENES_RAW.items():
            for idx, name in enumerate(names, 1):
                default_scenes.append({"day": day, "num": idx, "name": name})

        default_exclusions = [
            "System Volume Information", "$RECYCLE.BIN", "THMBNL", "TAKE", "DATABASE", "AVF_INFO",
            ".Trashes", ".Spotlight-V100", ".fseventsd"
        ]

        home = Path.home()
        default_config = {
            "settings": {"day_count": DAY_COUNT_FIXED},
            "paths": {
                "temp_dir": str(TEMP_DIR_FIXED),
                "dest_root": str(home / "Rinkan_UMIS_Archive"),
            },
            "current_location": "第1",
            "locations": ["第1", "第2", "第3", "第4", "第5", "第6", "第7", "第8", "高校"],
            "card_ids": [f"{i:02d}" for i in range(1, 6)],
            "photographers": ["田中", "山田", "高橋"],
            "scenes": default_scenes,
            "exclusions": {
                "ext": [".thm", ".lrv", ".cpi", ".xml", ".bin", ".ind", ".db", ".ppn", ".bup", ".ds_store"],
                "folders": default_exclusions
            },
            "category_settings": {
                "Movie": {"exts": [".mp4", ".mov", ".mxf", ".avi", ".mkv"], "folder": "動画", "disabled": False},
                "Photo": {"exts": [".jpg", ".jpeg", ".png", ".heic", ".heif", ".tiff"], "folder": "写真", "disabled": False},
                "Raw":   {"exts": [".arw", ".cr2", ".cr3", ".nef", ".raf", ".orf", ".dng", ".rw2"], "folder": "Raw", "disabled": False},
                "Audio": {"exts": [".wav", ".mp3", ".aac", ".m4a"], "folder": "音声", "disabled": False}
            },
            "options": {
                "create_scene_folder": True,
                "create_category_folder": True,
                "create_photographer_folder": True,
                "create_sub_folder": True,
                "sub_folder_name": "選別",
                "verify_checksum": True,
                "use_location_name": False,
                "use_scene_name": True,
                "use_date": True,
                "date_format": "%m%d",
                "use_card_id": True,
                "use_photographer_name": True,
                "use_sequential_numbering": False,
                "show_file_log": True,
                "scene_numbering": True,
                "scene_num_digits": 3,
                "emergency_fmt": False,
                "excluded_source_drives": [],
            },
            "last_state": {},
            "rename_order": ["location", "scene", "date", "card_id", "photographer"],
            "folder_order": ["category", "scene", "photographer"]
        }

        if self.config_path.exists():
            try:
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    merged = default_config.copy()
                    if "venues" in loaded and "locations" not in loaded: loaded["locations"] = loaded["venues"]
                    if "current_venue" in loaded and "current_location" not in loaded: loaded["current_location"] = loaded["current_venue"]
                    for k, v in loaded.items():
                        if isinstance(v, dict) and k in merged: merged[k].update(v)
                        else: merged[k] = v
                    if "rename_order" in merged:
                        merged["rename_order"] = [x.replace("venue", "location") for x in merged["rename_order"]]
                        if "date" not in merged["rename_order"]: merged["rename_order"].insert(0, "date")
                    merged["settings"]["day_count"] = DAY_COUNT_FIXED
                    merged["folder_order"] = ["category", "scene", "photographer"]
                    return merged
            except: return default_config
        self.data = default_config
        self.save()
        return default_config

    def save(self):
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    def save_as(self, new_name: str):
        new_path = PROJECTS_DIR / f"{new_name}.json"
        with open(new_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=4, ensure_ascii=False)

    def delete_project(self):
        if self.config_path.exists(): os.remove(self.config_path)

    def _get_list_ref(self, list_key: str) -> list:
        if list_key == "excluded_folders": return self.data["exclusions"]["folders"]
        if list_key in self.data: return self.data[list_key]
        return []

    def add_item(self, list_key: str, item):
        target = self._get_list_ref(list_key)
        if item not in target: target.append(item)
        self.save()

    def remove_item(self, list_key: str, item_value):
        target = self._get_list_ref(list_key)
        # 辞書型リスト（photographers等）と文字列型リスト（card_ids等）の両方に対応
        if not target: return
        
        found = False
        if isinstance(target[0], dict):
            for i, itm in enumerate(target):
                if itm.get('name') == item_value:
                    target.pop(i)
                    found = True; break
        else:
            if item_value in target:
                target.remove(item_value)
                found = True
        
        if found: self.save()

    def update_item_by_index(self, list_key: str, index: int, new_value):
        target = self._get_list_ref(list_key)
        if 0 <= index < len(target):
            if list_key == "photographers" and isinstance(target[index], dict):
                target[index].update(new_value)
            else: target[index] = new_value
            self.save()

    def _reorder_list(self, target: list, old_index: int, new_index: int):
        if 0 <= old_index < len(target) and 0 <= new_index <= len(target):
            item = target.pop(old_index)
            if old_index < new_index: new_index -= 1
            target.insert(new_index, item)
            self.save()

    def move_item_step(self, list_key: str, index: int, direction: str):
        if list_key == "rename_order": target = self.data["rename_order"]
        elif list_key == "folder_order": target = self.data["folder_order"]
        else: target = self._get_list_ref(list_key)
        if not target: return
        if direction == "up" and index > 0:
            target[index], target[index-1] = target[index-1], target[index]; self.save()
        elif direction == "down" and index < len(target) - 1:
            target[index], target[index+1] = target[index+1], target[index]; self.save()

    def reorder_item(self, list_key: str, old_index: int, new_index: int):
        self._reorder_list(self._get_list_ref(list_key), old_index, new_index)

    def reorder_rename_rules(self, old_index: int, new_index: int):
        self._reorder_list(self.data["rename_order"], old_index, new_index)

    def get_next_scene_num(self, day: int) -> int:
        max_num = 0
        for s in self.data["scenes"]:
            if s["day"] == int(day) and s["num"] > max_num: max_num = s["num"]
        return max_num + 1

    def add_scene(self, day, num, name):
        self.data["scenes"].append({"day": int(day), "num": int(num), "name": name})
        self.save()

    def remove_scene(self, day, num):
        self.data["scenes"] = [s for s in self.data["scenes"] if not (s["day"] == day and s["num"] == num)]
        day_scenes = sorted([s for s in self.data["scenes"] if s["day"] == day], key=lambda x: x["num"])
        for i, s in enumerate(day_scenes, 1): s["num"] = i
        self.save()

    def swap_scene(self, day: int, num: int, delta: int):
        day_scenes = sorted([s for s in self.data["scenes"] if s["day"] == day], key=lambda x: x["num"])
        idx = next((i for i, s in enumerate(day_scenes) if s["num"] == num), -1)
        if idx == -1: return
        t_idx = idx + delta
        if 0 <= t_idx < len(day_scenes):
            day_scenes[idx]["num"], day_scenes[t_idx]["num"] = day_scenes[t_idx]["num"], day_scenes[idx]["num"]
            self.save()

    def generate_filename(self, scene_info, photographer, card_id, original_filename, date_str=None):
        parts = []
        opts = self.data["options"]
        order = self.data.get("rename_order", ["date", "location", "scene", "photographer", "card_id"])
        use_numbering = opts.get("scene_numbering", True)
        for k in order:
            if k == "date" and opts.get("use_date", False) and date_str:
                parts.append(date_str)
            elif k == "location" and opts.get("use_location_name", True) and scene_info.get('venue'):
                parts.append(scene_info.get('venue'))
            elif k == "scene" and opts.get("use_scene_name", True):
                parts.append(f"{scene_info['day']}{scene_info['num']:02d}_{scene_info['name']}" if use_numbering else f"{scene_info['name']}")
            elif k == "photographer" and opts.get("use_photographer_name", True) and photographer:
                parts.append(photographer)
            elif k == "card_id" and opts.get("use_card_id", True) and card_id:
                parts.append(card_id)
        parts.append(original_filename)
        return "_".join(filter(None, parts))

# --- 3. Copy Worker ---
class CopyWorker(threading.Thread):
    def __init__(self, config_mgr: ConfigManager, source_files: list,
                 scene_assignments: dict, photographer: str, card_id: str,
                 on_log, on_progress, on_finished):
        super().__init__()
        self.cfg_mgr = config_mgr
        self.config = config_mgr.data
        self.source_files = source_files
        self.scene_assignments = scene_assignments
        self.photographer = photographer
        self.card_id = card_id
        self.on_log = on_log
        self.on_progress = on_progress
        self.on_finished = on_finished
        self.is_cancelled = False
        self.daemon = True
        self.start_time = 0
        self.sequence_counter = 1
        self.stats = {
            "total_count": 0, "errors": [],
            "verify_results": {"success": 0, "fail": 0, "skipped": 0},
            "size_details": {}, "count_details": {},
            "scene_details": {}
        }
        self.cat_settings = self.config.get("category_settings", {})
        self.ext_to_cat = {}
        for cat, conf in self.cat_settings.items():
            if not conf.get("disabled", False):
                for e in conf["exts"]:
                    self.ext_to_cat[e.lower()] = cat

    def _get_file_date(self, file_path: Path) -> str:
        fmt = self.config["options"].get("date_format", "%y%m%d")
        dt = None
        if file_path.suffix.lower() in ['.jpg', '.jpeg', '.tiff', '.heic']:
            try:
                with Image.open(file_path) as img:
                    exif = img._getexif()
                    if exif:
                        date_str = exif.get(36867)
                        if date_str:
                            dt = datetime.datetime.strptime(date_str, "%Y:%m:%d %H:%M:%S")
            except: pass
        if dt is None:
            try:
                timestamp = os.path.getmtime(file_path)
                dt = datetime.datetime.fromtimestamp(timestamp)
            except: dt = datetime.datetime.now()
        try: return dt.strftime(fmt)
        except: return dt.strftime("%y%m%d")

    def run(self):
        try:
            self.on_log("=== 処理開始 ===")
            self.start_time = time.time()

            all_tasks = []
            scene_details = {}
            for scene_key, file_indices in self.scene_assignments.items():
                parts = scene_key.split("_", 2)
                day = int(parts[0]) if len(parts) > 0 else 0
                num = int(parts[1]) if len(parts) > 1 else 1
                name = parts[2] if len(parts) > 2 else "Unknown"
                scene_info = {"day": day, "num": num, "name": name}
                
                for fi in file_indices:
                    if 0 <= fi < len(self.source_files):
                        fi_info = self.source_files[fi]
                        all_tasks.append((fi_info, scene_info))
                        
                        s_key = scene_info['name']
                        if s_key not in scene_details:
                            scene_details[s_key] = {"count": 0, "size": 0}
                        scene_details[s_key]["count"] += 1
                        scene_details[s_key]["size"] += fi_info['size']

            total_size = sum(t[0]['size'] for t in all_tasks)
            self.stats["total_size"] = total_size
            self.stats["total_count"] = len(all_tasks)
            self.stats["scene_details"] = scene_details

            if len(all_tasks) == 0:
                self.on_log("コピー対象ファイルがありません。")
                self.on_finished(True, "対象なし"); return

            self.on_log(f"対象: {len(all_tasks)} ファイル ({total_size / (1024**3):.2f} GB)")

            timestamp_str = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_id = re.sub(r'[^a-zA-Z0-9_\-]', '', str(self.card_id or 'unknown'))
            session_folder = TEMP_DIR_FIXED / f"ingest_{timestamp_str}_{safe_id}"
            try:
                session_folder.mkdir(parents=True, exist_ok=True)
                self.on_log(f"一時作業フォルダ: {session_folder.name}")
            except Exception as e:
                self.on_log(f"[致命的エラー] 一時フォルダ作成失敗: {e}")
                self.on_finished(False, "一時フォルダ作成失敗"); return

            self.on_log("フェーズ 1/2: 一時フォルダへ転送中...")
            processed_size = 0
            temp_task_map = []
            show_detail = self.config["options"].get("show_file_log", True)

            for file_info, scene_info in all_tasks:
                if self.is_cancelled: break
                src = Path(file_info['path'])
                dst_temp = session_folder / src.name
                counter = 1
                while dst_temp.exists():
                    dst_temp = session_folder / f"{src.stem}_{counter}{src.suffix}"
                    counter += 1
                try:
                    shutil.copy2(src, dst_temp)
                    if show_detail: self.on_log(f"転送完了: {src.name}")
                except (PermissionError, OSError) as e:
                    self.on_log(f"[スキップ] {src.name}: {e}"); continue
                processed_size += file_info['size']
                self._report_progress(processed_size, total_size, "転送中", COLOR_PROGRESS_PHASE1, "転送中...")
                cat = file_info.get('cat', 'Photo')
                temp_task_map.append((dst_temp, src.name, src.suffix.lower(), cat, scene_info))
                self.stats["size_details"][cat] = self.stats["size_details"].get(cat, 0) + file_info['size']
                self.stats["count_details"][cat] = self.stats["count_details"].get(cat, 0) + 1

            if self.is_cancelled: self.on_finished(False, "中断"); return

            self.on_log("フェーズ 2/2: リネーム・整理中...")
            dest_root = Path(self.config["paths"]["dest_root"])
            total_p2 = len(temp_task_map)
            use_numbering = self.config["options"].get("scene_numbering", True)
            use_seq = self.config["options"].get("use_sequential_numbering", False)
            create_sub = self.config["options"].get("create_sub_folder", False)
            sub_name = self.config["options"].get("sub_folder_name", "選別")
            sub_cache = set()

            for idx, (tmp_path, orig_name, ext, cat, scene_info) in enumerate(temp_task_map):
                if self.is_cancelled: break
                
                cat_folder = self.cat_settings.get(cat, {}).get("folder", cat)
                if use_numbering:
                    scene_folder = f"{scene_info['day']}{scene_info['num']:02d}_{scene_info['name']}"
                else:
                    scene_folder = scene_info['name']
                pg_folder = self.photographer or "未指定"

                current_path = dest_root / scene_folder / cat_folder / pg_folder
                current_path.mkdir(parents=True, exist_ok=True)

                scene_dir = dest_root / scene_folder

                if create_sub and sub_name and str(scene_dir) not in sub_cache:
                    try:
                        sub_dir = scene_dir / sub_name
                        if not sub_dir.exists(): sub_dir.mkdir(parents=True, exist_ok=True)
                        sub_cache.add(str(scene_dir))
                    except: pass

                if use_seq:
                    file_body = f"{self.sequence_counter:04d}{ext}"
                    self.sequence_counter += 1
                else:
                    file_body = orig_name

                date_str = self._get_file_date(tmp_path)
                si_with_venue = scene_info.copy()
                new_name = self.cfg_mgr.generate_filename(si_with_venue, self.photographer, self.card_id, file_body, date_str)
                final_path = current_path / new_name

                if final_path.exists():
                    if show_detail: self.on_log(f"スキップ(重複): {new_name}")
                    self.stats["verify_results"]["skipped"] += 1
                else:
                    try:
                        shutil.copy2(tmp_path, final_path)
                        if tmp_path.stat().st_size != final_path.stat().st_size:
                            self.on_log(f"[エラー] サイズ不一致: {new_name}")
                            self.stats["verify_results"]["fail"] += 1
                            self.stats["errors"].append(f"検証失敗: {new_name}")
                        else:
                            if show_detail: self.on_log(f"検証成功: {new_name}")
                            self.stats["verify_results"]["success"] += 1
                    except Exception as e:
                        self.on_log(f"[エラー] 保存失敗: {e}")
                        self.stats["verify_results"]["fail"] += 1
                        self.stats["errors"].append(str(e))

                r = (idx + 1) / total_p2 if total_p2 > 0 else 1.0
                self.on_progress(r, "整理中", "仕上げ処理中...", COLOR_PROGRESS_PHASE2, "整理中...")

            if not self.is_cancelled:
                self.on_log("一時データのクリーンアップ中...")
                try:
                    for p in session_folder.rglob("*"):
                        if p.is_file(): p.unlink()
                    self.on_log("一時データ削除完了")
                except Exception as e:
                    self.on_log(f"[警告] クリーンアップエラー: {e}")

                v_res = self.stats["verify_results"]
                self.on_log(f"=== 検証結果: 成功 {v_res['success']} / 失敗 {v_res['fail']} / スキップ {v_res['skipped']} ===")
                self.on_log("=== 完了 ===")
                final_ok = (v_res["fail"] == 0)
                self.on_finished(final_ok, "成功" if final_ok else f"一部失敗 ({v_res['fail']}件)")
            else:
                self.on_finished(False, "中断")
        except Exception as e:
            self.on_log(f"システムエラー: {e}")
            self.on_finished(False, "失敗")

    def _report_progress(self, current, total, status, color, btn_text):
        if total == 0: return
        ratio = current / total
        elapsed = time.time() - self.start_time
        eta_str = "計算中..."
        if ratio > 0:
            eta = (elapsed / ratio) - elapsed
            eta_str = f"残り約{int(eta // 60)}分{int(eta % 60)}秒"
        self.on_progress(ratio, status, eta_str, color, btn_text)

# --- 3.5. Select Worker (v9.0.0) ---
class SelectWorker(threading.Thread):
    def __init__(self, source_files: list, dest_root: Path, sub_folder_name: str, on_log, on_progress, on_finished):
        super().__init__()
        self.source_files = source_files
        self.dest_root = dest_root
        self.sub_folder_name = sub_folder_name
        self.on_log = on_log
        self.on_progress = on_progress
        self.on_finished = on_finished
        self.is_cancelled = False
        self.daemon = True

    def run(self):
        try:
            flagged_files = [f for f in self.source_files if f.get("is_selected_for_edit")]
            if not flagged_files:
                self.on_log("選別されたファイルがありません。")
                self.on_finished(True, "対象なし"); return

            self.on_log(f"選別コピー開始: {len(flagged_files)} ファイル")
            
            # v9.0.1: 各シーンフォルダ内に選別フォルダを作成してコピー
            for i, f in enumerate(flagged_files):
                if self.is_cancelled: break
                src = Path(f["path"])
                
                # シーンフォルダの特定
                scene_name = f.get("assigned_scene")
                if not scene_name:
                    self.on_log(f"警告: {f['name']} のシーン情報が見つかりません。スキップします。")
                    continue
                
                scene_dir = self.dest_root / scene_name
                target_dir = scene_dir / self.sub_folder_name
                target_dir.mkdir(parents=True, exist_ok=True)
                
                dst = target_dir / src.name
                
                # v9.5.0: 重複コピーを防止。既に存在する場合はスキップ。
                if dst.exists():
                    self.on_log(f"スキップ: {dst.name} は既に存在します")
                    continue
                
                shutil.copy2(src, dst)
                self.on_log(f"コピー完了: {scene_name}/{self.sub_folder_name}/{dst.name}")
                
                ratio = (i + 1) / len(flagged_files)
                self.on_progress(ratio, "選別コピー中", f"{i+1}/{len(flagged_files)}", COLOR_SELECT_MODE, "処理中...")

            if self.is_cancelled:
                self.on_finished(False, "キャンセルされました")
            else:
                self.on_log("=== 選別出力完了 ===")
                self.on_finished(True, "成功")
        except Exception as e:
            self.on_log(f"エラー: {e}")
            self.on_finished(False, str(e))

# --- 4. Format Worker ---
class FormatWorker(threading.Thread):
    def __init__(self, mount_point, label, on_progress, on_finished):
        super().__init__()
        self.mount_point = mount_point
        self.label = label
        self.on_progress = on_progress
        self.on_finished = on_finished
        self.is_cancelled = False
        self.daemon = True

    def run(self):
        try:
            self.on_progress(0.1, "初期化準備中", "デバイスを確立中...", COLOR_ERROR, "初期化中...")
            time.sleep(1)
            if self.is_cancelled: self.on_finished(False, "中止"); return
            self.on_progress(0.3, "初期化中", "メディアを消去中...", COLOR_ERROR, "初期化中...")
            system = platform.system()
            if system == "Darwin":
                device = None
                for part in psutil.disk_partitions(all=False):
                    if part.mountpoint == self.mount_point:
                        device = part.device; break
                if not device: raise Exception("デバイスが見つかりません")
                subprocess.run(["diskutil", "eraseVolume", "ExFAT", self.label, device], check=True, capture_output=True, text=True)
            elif system == "Windows":
                d_letter = self.mount_point.split(":")[0] + ":"
                subprocess.run(f'format {d_letter} /FS:EXFAT /V:{self.label} /Q /Y', shell=True, check=True, capture_output=True, text=True)
            if self.is_cancelled: self.on_finished(False, "中止"); return
            self.on_progress(0.8, "完了処理中", "情報更新中...", COLOR_ERROR, "完了処理中...")
            time.sleep(1)
            self.on_progress(1.0, "初期化完了", "正常終了", COLOR_SUCCESS, "完了")
            self.on_finished(True, "初期化成功")
        except Exception as e:
            self.on_finished(False, f"初期化失敗: {e}")

# --- 5. UI Helper Functions ---
def create_settings_header(text, on_edit_click=None, is_editing=False, edit_btn_text="編集"):
    content_row = [ft.Text(text, size=16, color=COLOR_TEXT_MAIN, weight=ft.FontWeight.BOLD, expand=True)]
    if on_edit_click:
        btn_text = "完了" if is_editing else edit_btn_text
        btn_color = COLOR_PRIMARY if is_editing else COLOR_TEXT_SEC
        content_row.append(ft.GestureDetector(content=ft.Text(btn_text, size=13, color=btn_color, weight="bold"), on_tap=on_edit_click))
    return ft.Container(content=ft.Row(content_row), padding=ft.padding.only(left=15, right=15, bottom=8, top=20))

def create_settings_group(controls):
    content_col = ft.Column(spacing=0)
    for i, ctrl in enumerate(controls):
        content_col.controls.append(ctrl)
        if i < len(controls) - 1:
            content_col.controls.append(ft.Divider(height=1, color=COLOR_DIVIDER, leading_indent=15))
    return ft.Container(content=content_col, bgcolor=COLOR_BG_CARD, border_radius=12)

INFO_TITLES = {
    "rename_date": "撮影日 (date)",
    "rename_venue": "会場名 (location)",
    "rename_location": "会場名 (location)",
    "rename_scene": "シーン名 (scene)",
    "rename_pg": "カメラマン (photographer)",
    "rename_photographer": "カメラマン (photographer)",
    "rename_id": "カードID (card_id)",
    "rename_card_id": "カードID (card_id)",
    "date_format": "日付フォーマット",
    "show_file_log": "詳細ログ表示",
    "scene_numbering": "シーン番号付与",
    "use_sequential": "連番リネーム",
    "emergency_fmt": "緊急フォーマット",
    "create_sub_folder": "選別フォルダ作成",
    "sub_folder_name": "選別フォルダ名",
    "category_Photo": "カテゴリ: 写真 (Photo)",
    "category_Movie": "カテゴリ: 動画 (Movie)",
    "category_Raw": "カテゴリ: Raw",
    "category_Audio": "カテゴリ: 音声 (Audio)",
}

def create_info_btn(help_key, page):
    title = INFO_TITLES.get(help_key, "ヘルプ")
    text = HELP_TEXTS.get(help_key, "説明がありません。")

    def _on_click(e):
        def _close(ev):
            try: page.close(dlg)
            except: pass
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(title, size=15, weight="bold", color=COLOR_TEXT_MAIN),
            content=ft.Container(
                content=ft.Text(text, size=13, color=COLOR_TEXT_MAIN, selectable=True),
                width=360,
                padding=5,
            ),
            actions=[ft.TextButton("閉じる", on_click=_close)],
            bgcolor=COLOR_BG_CARD,
        )
        try:
            page.open(dlg)
        except Exception:
            try:
                page.dialog = dlg
                dlg.open = True
                page.update()
            except: pass

    return ft.Container(
        content=ft.IconButton(
            icon=ft.Icons.INFO_OUTLINED,
            icon_color=COLOR_TEXT_SEC,
            icon_size=18,
            tooltip=text,
            on_click=_on_click,
            padding=0,
        ),
        width=28,
        height=28,
        alignment=ft.alignment.center,
    )

def create_switch_tile_ctrl(label, switch_ctrl, help_key=None, page=None):
    row_content = [ft.Text(label, size=15, color=COLOR_TEXT_MAIN)]
    if help_key and page: row_content.append(create_info_btn(help_key, page))
    return ft.Container(content=ft.Row([ft.Row(row_content, vertical_alignment="center"), switch_ctrl], alignment="spaceBetween"), padding=ft.padding.symmetric(horizontal=15, vertical=10), height=48)

def create_input_tile(label, control, icon=None, on_click_icon=None, help_key=None, page=None):
    label_row = [ft.Text(label, size=15, color=COLOR_TEXT_MAIN, no_wrap=True)]
    if help_key and page: label_row.append(create_info_btn(help_key, page))
    row_content = [ft.Row(label_row, vertical_alignment="center", width=180, wrap=False), ft.Container(content=control, expand=True, padding=ft.padding.only(left=10), clip_behavior=ft.ClipBehavior.ANTI_ALIAS)]
    if icon: row_content.append(ft.IconButton(icon, on_click=on_click_icon, icon_color=COLOR_TEXT_SEC, icon_size=20))
    return ft.Container(content=ft.Row(row_content, alignment="spaceBetween"), padding=ft.padding.symmetric(horizontal=15, vertical=10), height=48)

def create_action_tile(label, icon, on_click, font_color=COLOR_TEXT_MAIN, icon_color=COLOR_PRIMARY):
    return ft.Container(content=ft.Row([ft.Row([ft.Icon(icon, size=20, color=icon_color), ft.Text(label, size=15, color=font_color)], spacing=12, vertical_alignment="center"), ft.Icon(ft.Icons.CHEVRON_RIGHT, size=16, color=COLOR_TEXT_SEC)], alignment="spaceBetween"), padding=ft.padding.symmetric(horizontal=15, vertical=10), height=48, on_click=on_click, ink=True)

# --- 6. Main Application Class ---
class RinkanUMISApp:
    def __init__(self, page: ft.Page):
        self.page = page
        self.page.title = f"{APP_NAME} v{VERSION}"
        self.page.theme_mode = ft.ThemeMode.DARK
        self.page.padding = 0
        self.page.bgcolor = COLOR_BG_MAIN
        self.page.on_resize = self.on_page_resize
        # v7.6.4: UI崩れ防止のため計算された最小サイズを設定
        self.page.window_min_width = MIN_WINDOW_WIDTH
        self.page.window_min_height = MIN_WINDOW_HEIGHT

        self.file_picker = ft.FilePicker(on_result=self.on_dialog_result)
        self.page.overlay.append(self.file_picker)
        self.picker_target = None

        self.cfg_mgr = ConfigManager("初期プロジェクト")
        self.scene_panel_width = 320
        self.history_logger = HistoryLogger()
        self.current_copy_worker = None
        self.selected_scene_info = None
        self.current_photographer = None
        self.current_filter_char = None
        self.is_scene_editing = False
        self.is_complete_state = False
        self.format_allowed = False
        self.drive_map = {}
        self.last_execution_id = None
        self.current_card_id = None
        self._cancel_scan = False
        self._active_modal_dlg = None  # v1.1.25: アクティブなダイアログの状態を追跡
        self._identity_modal_back_flag = False # v7.5.1: 戻るボタン挙動用
        self.current_sort = "name" # v7.6.7: デフォルトのソート順
        self.app_mode = "ingest" # v9.0.0: "ingest" or "select"
        self.focused_file_index = -1 # v8.0.0: クイックプレビュー・フォーカス用
        self._preview_visible = False
        
        # v9.3.0: セレクトモード専用ステート
        self.show_guide = True
        self.select_mode_scene_index = 0
        self.selection_tray_controls = {}
        # v10.1.0: 現在選択中のシーンフォルダ名
        self._current_select_scene = None
        # v10.7.3: セレクトモードの一括選択状態
        self.is_select_bulk_mode = False
        self.select_cat_filters = {"Movie": True, "Photo": True, "Raw": True, "Audio": True}
        self.ingest_cat_filters = {"Movie": True, "Photo": True, "Raw": True, "Audio": True}
        
        # v9.5.0: UI刷新に伴う状態変数
        self.select_inspector_width = INSPECTOR_WIDTH_DEFAULT
        self.sidebar_width = SIDEBAR_WIDTH
        
        # コンポーネント
        self.modern_sidebar = None
        self.modern_top_bar = None
        
        # v9.3.0/v9.4.2/v9.5.0: セレクトモード専用インスペクター
        self.select_inspector_preview = ft.Container(height=260, bgcolor=ft.Colors.BLACK, border_radius=8, alignment=ft.alignment.center)
        # v10.3.0: グリッドヘッダーとサイドバーを動的更新するための参照
        self._select_title_text = ft.Text("シーン未選択", size=24, weight="bold")
        self._select_count_text = ft.Text("0個の項目", size=12, color=COLOR_TEXT_SEC)
        # v10.7.0: シーン移動ボタン
        self.btn_move_scene = ft.ElevatedButton(
            "別のシーンへ移動",
            icon=ft.Icons.DRIVE_FILE_MOVE_OUTLINED,
            on_click=self._show_move_scene_dialog,
            disabled=True,
            style=ft.ButtonStyle(
                bgcolor=COLOR_BG_CARD,
                color=COLOR_TEXT_MAIN,
                padding=10
            )
        )
        self._select_library_tile = None  # ExpansionTile への参照
        self.select_inspector_meta = ft.Column(spacing=5, scroll=ft.ScrollMode.AUTO)

        # v10.7.3: 一括選択モード用
        self.is_select_bulk_mode = False
        self.btn_bulk_select_mode = ft.IconButton(
            icon=ft.Icons.CHECK_BOX_OUTLINE_BLANK,
            icon_color=COLOR_TEXT_SEC,
            on_click=self.toggle_bulk_select_mode,
            tooltip="一括選択モード切替",
        )

        # v8.0.11: 動画プレビュー操作用 (ショートカット用のみ維持)
        self.video_ctrl = None
        self.audio_ctrl = None # v8.0.22: 音声再生管理用

        # v8.0.13: 固定幅250px・カスタムRow(カメラマン名省略+カードID固定)
        self._identity_pg_text = ft.Text(
            "撮影者", size=12, color=COLOR_TEXT_MAIN,
            overflow=ft.TextOverflow.ELLIPSIS, no_wrap=True, expand=True
        )
        self._identity_cid_text = ft.Text(
            "---", size=11, color=COLOR_TEXT_SEC, no_wrap=True, width=50, text_align="right"
        )
        self.btn_select_identity = ft.ElevatedButton(
            style=ft.ButtonStyle(
                bgcolor=COLOR_BG_CARD,
                color=COLOR_TEXT_MAIN,
                shape=ft.RoundedRectangleBorder(radius=8),
                side={"": ft.BorderSide(1, COLOR_DIVIDER)},
                padding=ft.padding.symmetric(horizontal=10, vertical=8),
                elevation=0,
            ),
            content=ft.Row([
                ft.Icon(ft.Icons.PERSON_SEARCH, size=16, color=COLOR_TEXT_SEC),
                self._identity_pg_text,
                ft.Container(width=1, height=16, bgcolor=COLOR_DIVIDER),
                self._identity_cid_text,
            ], spacing=6, vertical_alignment="center", tight=True),
            on_click=self.show_identity_modal
        )

        self.current_view = "main"
        self.history_expanded = {}
        self._content_area = ft.Container(expand=True)
        self.lv_history_list = ft.ListView(expand=True, spacing=10, padding=15)

        self.source_files = []
        self.scene_assignments = {}
        self.all_selected = False
        self.view_mode = "grid"
        self.last_selected_idx = None
        self.is_dragging = False
        self.thumb_size = 120
        self.font_size = 12  # v8.0.13: フォントサイズ独立制御
        self._thumb_gen_id = 0
        # v8.0.13: 履歴フィルタ（ORフィルタ用リスト）
        self.hist_filter_pg: list = []
        self.hist_filter_cid: list = []
        self.hist_filter_scene: list = []
        self._scan_id = 0
        self._is_scanning = False
        self._thumb_controls = {}
        self._thumb_img_controls = {}
        self._slider_timer = None
        self._scanning_row = ft.Row([
            ft.ProgressRing(width=18, height=18, stroke_width=2, color=COLOR_PRIMARY),
            ft.Text("スキャン中...", size=12, color=COLOR_TEXT_SEC, italic=True),
            ft.IconButton(ft.Icons.CANCEL, icon_color=COLOR_ERROR, icon_size=18, tooltip="スキャンを中止", on_click=self.cancel_scan_action)
        ], spacing=8, visible=False, alignment=ft.MainAxisAlignment.CENTER)

        # v8.0.21: カラム内プレビューの状態管理
        self._is_col_preview_mode = False
        self.video_ctrl_col = None
        
        self.col_preview_content = ft.Container(
            content=ft.Text("ファイルを選択してプレビュー", color=COLOR_TEXT_SEC, size=12),
            alignment=ft.alignment.center, expand=True
        )
        self.btn_col_fullscreen = ft.IconButton(
            ft.Icons.FULLSCREEN, icon_color=COLOR_PRIMARY, icon_size=24,
            tooltip="全画面表示", on_click=lambda e: self.show_quick_preview(), visible=False
        )
        self.btn_col_back = ft.IconButton(
            ft.Icons.ARROW_BACK, icon_color=COLOR_TEXT_SEC, icon_size=20,
            tooltip="リストに戻る", on_click=lambda e: self.hide_col_preview()
        )
        self.col_preview_area = ft.Container(
            content=ft.Stack([
                ft.Column([
                    ft.Container(
                        content=ft.Row([self.btn_col_back, ft.Text("プレビュー", size=12, color=COLOR_TEXT_SEC, expand=True)], spacing=5),
                        padding=ft.padding.only(left=5, top=5)
                    ),
                    self.col_preview_content,
                ], expand=True, spacing=0),
                ft.Container(content=self.btn_col_fullscreen, bottom=10, right=10)
            ]),
            bgcolor=COLOR_BG_MAIN, border_radius=8,
            border=ft.border.all(1, COLOR_DIVIDER),
            expand=True, visible=False
        )
        self.thumb_main_slot = ft.Container(expand=True) # v8.0.21: リストとプレビューの切り替え用スロット

        self.dd_project = ft.Dropdown(width=180, text_size=12, border_color=COLOR_DIVIDER, on_change=self.on_project_change)
        self.dd_drive = ft.Dropdown(options=[], text_size=12, border_color=COLOR_DIVIDER, width=170, on_change=self.on_source_change, hint_text="メディア接続待機...")
        self.dd_venue = ft.Dropdown(options=[], width=180, border_color=COLOR_DIVIDER, on_change=self.on_venue_change)
        self.row_days = ft.Row(spacing=0)
        self.radio_day = ft.RadioGroup(content=ft.Row([self.row_days], scroll=ft.ScrollMode.AUTO), value="0", on_change=self.on_day_change)
        
        self.scene_content_area = ft.Container(expand=True)
        self.grid_scenes = ft.GridView(runs_count=2, child_aspect_ratio=1.6, spacing=6, run_spacing=6, expand=True)
        self.lv_scenes_edit = ft.ListView(spacing=5, expand=True)
        
        self.grid_thumbnails = ft.GridView(max_extent=120, child_aspect_ratio=0.9, spacing=5, run_spacing=5, expand=True)
        self.list_thumbnails = ft.ListView(spacing=2, expand=True, padding=5)
        
        self.thumb_container = ft.Container(expand=True)
        self.btn_view_toggle = ft.IconButton(ft.Icons.VIEW_LIST, icon_color=COLOR_TEXT_SEC, tooltip="表示切替", on_click=self.toggle_view_mode, icon_size=20)
        self.btn_scene_edit = ft.IconButton(ft.Icons.EDIT, icon_color=COLOR_TEXT_SEC, tooltip="シーン編集", on_click=self.toggle_scene_edit_mode)
        self.lv_log = ft.ListView(expand=True, spacing=2, padding=5, auto_scroll=True)
        self.lbl_percent = ft.Text("0%", size=12, weight=ft.FontWeight.BOLD, color=COLOR_PRIMARY)
        self.lbl_status = ft.Text("待機中...", size=11, color=COLOR_TEXT_SEC)
        self.lbl_rename_preview = ft.Text("リネーム例: ---", size=10, color=COLOR_ACCENT, italic=True)
        
        # v7.5.1: 実行履歴ボタン (ヘッダーから移動)
        self.btn_history = ft.ElevatedButton(
            text="実行履歴",
            icon=ft.Icons.HISTORY,
            height=50,
            style=ft.ButtonStyle(
                bgcolor=COLOR_BG_CARD,
                color=COLOR_TEXT_SEC,
                shape=ft.RoundedRectangleBorder(radius=8),
                padding=15
            ),
            on_click=self.show_history_dialog
        )
        
        # v7.5.1: カテゴリインポート状態表示用
        self.row_cat_status = ft.Row(spacing=10)

        self.pb_fill = ft.Container(bgcolor=COLOR_PRIMARY, border_radius=6, width=0, animate=ft.Animation(300, "easeOut"))
        self.pb_track = ft.Container(bgcolor=COLOR_DISABLED_BTN_BG, border_radius=6, height=12)
        self.tf_dest_dir = ft.TextField(read_only=False, border=ft.InputBorder.NONE, text_size=12, color=COLOR_TEXT_SEC, expand=True, on_change=lambda e: self._save_path("dest", e.control.value))
        
        # v7.6.2: ボタンサイズを大きくし、視認性を向上
        self.btn_start = ft.ElevatedButton(
            height=36,
            disabled=True,
            style=ft.ButtonStyle(
                bgcolor=COLOR_DISABLED_BTN_BG,
                color=COLOR_DISABLED_BTN_TEXT,
                padding=ft.padding.symmetric(horizontal=20, vertical=0),
                overlay_color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
            on_click=self.start_copy,
            content=ft.Text("START INGEST", text_align=ft.TextAlign.CENTER, size=13, weight="bold"),
        )
        self.btn_cancel = ft.ElevatedButton("キャンセル", height=50, disabled=True, bgcolor=COLOR_ERROR, color="white", on_click=self.cancel_copy, style=ft.ButtonStyle(overlay_color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE), padding=10))
        self.btn_format = ft.ElevatedButton(
            height=44,
            disabled=True,
            expand=True,
            style=ft.ButtonStyle(
                bgcolor=COLOR_DISABLED_BTN_BG,
                color=COLOR_DISABLED_BTN_TEXT,
                padding=ft.padding.symmetric(horizontal=12, vertical=8),
                overlay_color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
                shape=ft.RoundedRectangleBorder(radius=6),
            ),
            on_click=self.format_card,
            content=ft.Row([
                ft.Icon(ft.Icons.DELETE_FOREVER_OUTLINED, size=16),
                ft.Text("FORMAT CARD", size=12, weight="bold"),
            ], spacing=8, tight=True, alignment=ft.MainAxisAlignment.CENTER),
        )
        self.btn_open_folder = ft.ElevatedButton(height=50, style=ft.ButtonStyle(bgcolor=COLOR_PRIMARY, color=COLOR_TEXT_MAIN, padding=10, overlay_color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE)), on_click=self.open_dest_folder, content=ft.Text("保存先を開く", size=13, weight="bold", no_wrap=True))
        
        self.lbl_file_count = ft.Text("ファイル: 0", size=11, color=COLOR_TEXT_SEC)
        self.lbl_assigned_count = ft.Text("割当済: 0", size=11, color=COLOR_TEXT_SEC)
        self.rename_labels = {"date": "撮影日", "location": "会場名", "scene": "シーン名", "photographer": "カメラマン", "card_id": "カードID"}
        self.range_selection_start_idx = None
        self.last_ingested_drive = None
        # v8.0.13: 全選択/全解除を独立した2ボタンに分割
        self.btn_select_all_btn = ft.TextButton(
            "全選択",
            on_click=self.select_all_files,
            style=ft.ButtonStyle(color=COLOR_PRIMARY)
        )
        self.btn_deselect_all_btn = ft.TextButton(
            "全解除",
            on_click=self.deselect_all_files,
            style=ft.ButtonStyle(color=COLOR_TEXT_SEC)
        )

        self.eject_icon_widget = ft.Icon(ft.Icons.EJECT, color=COLOR_ERROR, size=18)
        self.eject_ring_widget = ft.ProgressRing(width=16, height=16, stroke_width=2, color=COLOR_ERROR, visible=False)

        self._thumb_queue = queue.Queue()
        threading.Thread(target=self._thumb_worker, daemon=True).start()

        self.sw_rename_venue = ft.Switch(active_color=COLOR_PRIMARY, on_change=self.save_opts)
        self.sw_rename_scene = ft.Switch(active_color=COLOR_PRIMARY, on_change=self.save_opts)
        self.sw_rename_pg = ft.Switch(active_color=COLOR_PRIMARY, on_change=self.save_opts)
        self.sw_rename_id = ft.Switch(active_color=COLOR_PRIMARY, on_change=self.save_opts)
        self.sw_rename_date = ft.Switch(active_color=COLOR_PRIMARY, on_change=self.save_opts)
        self.sw_rename_seq = ft.Switch(active_color=COLOR_ERROR, on_change=self.on_rename_seq_change)  # v8.0.13: 警告色+警告ダイアログ
        self.dd_date_format = ft.Dropdown(width=200, text_size=13, border_color=COLOR_DIVIDER, content_padding=5, options=[
            ft.dropdown.Option("%y%m%d", "260324 (YYMMDD)"), ft.dropdown.Option("%Y%m%d", "20260324 (YYYYMMDD)"),
            ft.dropdown.Option("%m%d", "0324 (MMDD)"), ft.dropdown.Option("%m-%d", "03-24 (MM-DD)")
        ], on_change=self.save_opts)
        self.switches_rename = {"date": self.sw_rename_date, "location": self.sw_rename_venue, "scene": self.sw_rename_scene, "photographer": self.sw_rename_pg, "card_id": self.sw_rename_id}
        self.sw_show_file_log = ft.Switch(active_color=COLOR_PRIMARY, on_change=self.save_opts)
        self.sw_scene_numbering = ft.Switch(active_color=COLOR_PRIMARY, on_change=self.save_opts)
        self.sw_emergency_fmt = ft.Switch(active_color=COLOR_ERROR, on_change=self.save_opts)
        self.sw_create_sub_folder = ft.Switch(active_color=COLOR_PRIMARY, on_change=self.save_opts)
        self.tf_sub_folder_name = ft.TextField(width=150, text_size=13, height=35, content_padding=5, border_color=COLOR_DIVIDER, on_blur=self.save_opts)
        self.col_rename_rules = ft.Column()
        self.col_category_settings = ft.Column()
        self.lv_editors = ft.Column()

        # v9.3.0: セレクトモード専用UIコンポーネント
        self.select_scene_carousel = ft.Row(spacing=10, scroll=ft.ScrollMode.AUTO)
        self.select_gallery_grid = ft.GridView(max_extent=200, child_aspect_ratio=0.9, spacing=10, run_spacing=10, expand=True)
        self.select_tray_list = ft.Row(spacing=5, scroll=ft.ScrollMode.AUTO)
        self.btn_execute_select = ft.ElevatedButton(
            "選別を実行", bgcolor=COLOR_SELECT_MODE, color="black", 
            icon=ft.Icons.PLAY_ARROW, on_click=self._start_select_copy,
            height=45, style=ft.ButtonStyle(shape=ft.RoundedRectangleBorder(radius=8))
        )
        self.sl_thumb_size = ft.Slider(min=80, max=300, value=120, width=100, on_change=self.on_thumb_size_change)
        self.guide_overlay = self._build_shortcut_guide()

        # v10.7.4: グローバルステータスバー
        self.status_spinner = ft.ProgressRing(width=14, height=14, stroke_width=2, color=COLOR_PRIMARY, visible=False)
        self.lbl_global_status = ft.Text("システム待機中", size=11, color=COLOR_TEXT_SEC)
        self.status_bar = ft.Container(
            content=ft.Row([
                ft.Row([
                    self.status_spinner,
                    self.lbl_global_status,
                ], spacing=10, vertical_alignment="center"),
                ft.Container(expand=True),
                ft.Text("Developed by Keizo Ando", size=10, color=COLOR_TEXT_SEC, italic=True),
            ], vertical_alignment="center"),
            bgcolor=COLOR_BG_SIDEBAR,
            padding=ft.padding.symmetric(horizontal=15, vertical=5),
            height=30,
            border=ft.border.only(top=ft.border.BorderSide(1, COLOR_DIVIDER)),
        )

        self.build_ui()
        
        # v1.1.32: 起動時にアップデートを確認
        threading.Thread(target=self.check_for_updates, daemon=True).start()

        threading.Thread(target=self.drive_monitor, daemon=True).start()
        self.load_config_to_ui()

    def sanitize_text(self, text):
        if not text: return ""
        return re.sub(r'[^a-zA-Z0-9\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF\s_\-\.\(\)\[\]%]', "", text)

    def set_status(self, text, spinning=False):
        """v10.7.4: ステータスバーのテキストとスピナーを更新"""
        self.lbl_global_status.value = text
        self.status_spinner.visible = spinning
        try:
            self.lbl_global_status.update()
            self.status_spinner.update()
        except: pass

    def log(self, msg):
        t = datetime.datetime.now().strftime('%H:%M:%S')
        self.lv_log.controls.append(ft.Text(f"[{t}] {msg}", size=11, selectable=True, color=COLOR_TEXT_MAIN))
        if len(self.lv_log.controls) > 500:
            self.lv_log.controls.pop(0)
        try: self.lv_log.update()
        except: pass

    def show_snack(self, msg, color=None):
        self.page.snack_bar = ft.SnackBar(ft.Text(msg), bgcolor=color or COLOR_TEXT_SEC)
        self.page.snack_bar.open = True
        try: self.page.update()
        except: pass

    def apply_start_button_state(self, text, bgcolor, color, disabled):
        self.btn_start.content.value = text
        self.btn_start.bgcolor = bgcolor
        self.btn_start.color = color
        self.btn_start.disabled = disabled
        try: self.btn_start.update()
        except: pass

    def check_format_button_state(self):
        is_emergency = self.cfg_mgr.data["options"].get("emergency_fmt", False)
        is_same_drive = (self.dd_drive.value == self.last_ingested_drive) if self.last_ingested_drive else False
        is_enabled = is_emergency or (self.format_allowed and is_same_drive)
        
        self.btn_format.disabled = not is_enabled
        self.btn_format.bgcolor = COLOR_ERROR if is_enabled else COLOR_DISABLED_BTN_BG
        self.btn_format.color = "white" if is_enabled else COLOR_DISABLED_BTN_TEXT
        try: self.btn_format.update()
        except: pass

    def reset_progress_ui(self):
        self.lbl_percent.value = "0%"
        self.pb_fill.width = 0
        self.pb_fill.bgcolor = COLOR_PRIMARY
        self.lbl_status.value = "待機中..."
        self.is_complete_state = False
        self.format_allowed = False
        self.update_preview()
        self.btn_cancel.disabled = True
        self.check_format_button_state()
        try: self.page.update()
        except: pass

    def _save_path(self, t, v):
        if t == "dest":
            self.cfg_mgr.data["paths"]["dest_root"] = v
            self._refresh_library_sidebar()
        self.cfg_mgr.save()

    def _refresh_library_sidebar(self):
        """v1.1.23: 保存先変更に伴いライブラリ（シーン一覧）を更新"""
        if self.app_mode == "select":
            if hasattr(self, "_select_library_tile") and self._select_library_tile and self._sidebar_item_func:
                self._select_library_tile.controls = self._get_dynamic_library_items(self._sidebar_item_func)
                try: self._select_library_tile.update()
                except: pass

    def _scene_key(self, s):
        return f"{s['day']}_{s['num']}_{s['name']}"

    def build_ui(self):
        # v7.6.4で定義したシステム定数を使用するように修正
        self.page.window_min_width = MIN_WINDOW_WIDTH
        self.page.window_min_height = MIN_WINDOW_HEIGHT
        self.page.on_keyboard_event = self.on_keyboard_event # v8.0.0: ショートカット設定

        # v9.5.0: レイアウト構築
        # v1.0.3: ヘッダーを全モード共通化し、座標の完全一致を図る
        # v1.1.0: UI構造の抜本的統一
        header = self._build_header()
        sidebar = self._build_modern_sidebar()
        
        # モードに応じたメインコンテンツとインスペクタの構築
        if self.app_mode == "ingest":
            content_main = self._build_thumb_panel()
            inspector = self._build_scene_panel()
            bottom_bar = self._build_bottom_bar()
            
            # 分割バー（インジェスト用）
            splitter = ft.GestureDetector(
                content=ft.Container(
                    width=10, bgcolor="transparent", 
                    content=ft.VerticalDivider(width=1, color=COLOR_DIVIDER, thickness=1, leading_indent=4, trailing_indent=4),
                    on_hover=lambda e: (setattr(e.control, 'bgcolor', ft.Colors.with_opacity(0.1, COLOR_PRIMARY) if e.data == "true" else "transparent"), e.control.update())
                ),
                drag_interval=10,
                on_pan_update=self.on_splitter_drag,
            )
            
            # メイン右カラム（コンテンツ + インスペクタ + フッター）
            right_col = ft.Column([
                ft.Row([
                    content_main,
                    splitter,
                    inspector
                ], expand=True, spacing=0, vertical_alignment=ft.CrossAxisAlignment.START),
                bottom_bar
            ], expand=True, spacing=0)
        else:
            # セレクトモード
            content_main, inspector, bottom_bar = self._build_select_content_blocks()
            
            # 分割バー（セレクト用）
            splitter = ft.GestureDetector(
                content=ft.Container(
                    width=10, bgcolor="transparent",
                    content=ft.VerticalDivider(width=1, color=COLOR_DIVIDER, thickness=1, leading_indent=4, trailing_indent=4),
                    on_hover=lambda e: (setattr(e.control, 'bgcolor', ft.Colors.with_opacity(0.1, COLOR_PRIMARY) if e.data == "true" else "transparent"), e.control.update())
                ),
                drag_interval=10,
                on_pan_update=self.on_select_splitter_drag,
            )
            
            right_col = ft.Column([
                ft.Row([
                    content_main,
                    splitter,
                    inspector
                ], expand=True, spacing=0, vertical_alignment=ft.CrossAxisAlignment.START),
                bottom_bar
            ], expand=True, spacing=0)

        # v1.1.27: サイドバースプリッター
        sidebar_splitter = ft.GestureDetector(
            content=ft.Container(
                width=10, bgcolor="transparent",
                content=ft.VerticalDivider(width=1, color=COLOR_DIVIDER, thickness=1, leading_indent=4, trailing_indent=4),
                on_hover=lambda e: (setattr(e.control, 'bgcolor', ft.Colors.with_opacity(0.1, COLOR_PRIMARY) if e.data == "true" else "transparent"), e.control.update())
            ),
            drag_interval=10,
            on_pan_update=self.on_sidebar_drag,
        )

        # 最終レイアウト
        main_layout = ft.Row([
            sidebar,
            sidebar_splitter,
            right_col
        ], expand=True, spacing=0)

        layout = ft.Column([
            header,
            ft.Divider(height=1, color=COLOR_DIVIDER),
            main_layout,
            self.status_bar
        ], spacing=0, expand=True)

        self.tutorial_overlay = ft.Container(
            visible=False,
            bgcolor="#00000000",
            expand=True,
            on_click=lambda e: None,
            content=ft.Stack([])
        )

        # settings_overlay: _build_adobe_preferences_view() で content を動的構築するため
        # ここはシンプルなプレースホルダーのみ定義する
        self.settings_overlay = ft.Container(
            visible=False,
            expand=True,
            bgcolor="#AA000000",
            on_click=lambda e: self.close_settings_modal(),
            content=ft.Container(expand=True),  # _build_adobe_preferences_view で差し替え
        )

        self.preview_content_slot = ft.Container(alignment=ft.alignment.center, expand=True)
        self.preview_filename_text = ft.Text(size=16, weight="bold", color="white")
        # v8.0.18: 操作ガイドの更新
        self.preview_op_guide = ft.Text(
            "[J/L]: 10s戻る/進む  [K]: 再生/停止  [←/→]: 移動  [Space/Esc]: 閉じる",
            color="#AAAAAA", size=11
        )
        
        # v8.0.19: 音声抑制用ダミー。実体を持たせるためサイズを1にし、透明度を極限まで下げる
        self.dummy_focus = ft.TextField(width=1, height=1, opacity=0.01, on_change=self._on_dummy_change, on_submit=self._on_dummy_change)
        self.global_dummy_focus = ft.TextField(width=1, height=1, opacity=0.01, on_change=self._on_dummy_change, on_submit=self._on_dummy_change)

        self.preview_overlay = ft.Container(
            visible=False,
            bgcolor="#F2000000",
            expand=True,
            on_click=lambda e: self.close_quick_preview(),
            content=ft.Stack([
                ft.Column([
                    ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.PREVIEW, color=COLOR_PRIMARY, size=20),
                            self.preview_filename_text,
                            ft.Container(expand=True),
                            ft.IconButton(ft.Icons.CLOSE, icon_color="white", on_click=lambda e: self.close_quick_preview()),
                        ], alignment="spaceBetween"),
                        padding=ft.padding.symmetric(horizontal=20, vertical=10),
                        bgcolor="#33000000",
                    ),
                    self.preview_content_slot,
                    ft.Container(
                        content=self.preview_op_guide,
                        padding=15,
                        alignment=ft.alignment.center,
                        bgcolor="#33000000",
                    ),
                ], expand=True, spacing=0),
                self.dummy_focus
            ])
        )
        # v8.0.19: グローバルフォーカスをメイン画面外（スタック最下層）に配置
        self.global_focus_container = ft.Container(content=self.global_dummy_focus, width=1, height=1, left=-10, top=-10)

        self.page.controls.clear()
        self.page.add(ft.Stack([
            self.global_focus_container,
            layout,
            self.settings_overlay,
            self.tutorial_overlay,
            self.preview_overlay,
            self.guide_overlay
        ], expand=True))
        
        # 起動時にフォーカスを当てて音を抑制
        self.page.on_connect = lambda e: self._reset_focus()
        threading.Timer(0.5, self._reset_focus).start()

    def _build_shortcut_guide(self):
        # v9.3.0: 操作ガイドオーバーレイ
        guide_content = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.KEYBOARD, color=COLOR_PRIMARY),
                    ft.Text("ショートカット操作ガイド", size=18, weight="bold"),
                    ft.Container(expand=True),
                    ft.IconButton(ft.Icons.CLOSE, on_click=lambda e: self.toggle_guide(False))
                ]),
                ft.Divider(color=COLOR_DIVIDER),
                ft.Row([
                    ft.Column([
                        ft.Text("【基本操作】", weight="bold", color=COLOR_PRIMARY),
                        ft.Text("Space : プレビューの切替"),
                        ft.Text("Arrowキー : 前後のファイルへ移動"),
                        ft.Text("S : 選定/解除 (星マーク)"),
                    ], expand=True),
                    ft.Column([
                        ft.Text("【動画・音声】", weight="bold", color=COLOR_PRIMARY),
                        ft.Text("K : 再生 / 一時停止"),
                        ft.Text("J / L : 10秒 戻る / 進む"),
                    ], expand=True),
                ]),
                ft.Container(height=10),
                ft.Text("※ このガイドは右上の「？」ボタンでいつでも再表示できます。", size=12, color=COLOR_TEXT_SEC, italic=True),
            ], spacing=10, tight=True),
            bgcolor="#EE1A1A1A",
            border=ft.border.all(1, COLOR_PRIMARY),
            border_radius=12,
            padding=25,
            width=500,
            shadow=ft.BoxShadow(spread_radius=5, blur_radius=30, color=ft.Colors.BLACK),
        )
        return ft.Container(
            content=guide_content,
            alignment=ft.alignment.center,
            bgcolor="#66000000",
            visible=False,
            expand=True
        )

    def toggle_guide(self, visible):
        self.show_guide = visible
        self.guide_overlay.visible = visible
        try: self.page.update()
        except: pass

    def on_select_splitter_drag(self, e: ft.DragUpdateEvent):
        """v10.4.0: インスペクタ幅をリアルタイム更新（16:9プレビュー維持）"""
        # v10.7.10: ウィンドウ幅の50%まで拡張可能に
        max_w = self.page.width * 0.5 if self.page.width else 600
        self.select_inspector_width = max(250, min(max_w, self.select_inspector_width - e.delta_x))
        if hasattr(self, '_inspector_container') and self._inspector_container:
            self._inspector_container.width = self.select_inspector_width
            inner_w = self.select_inspector_width - 30
            self.select_inspector_preview.width = inner_w
            self.select_inspector_preview.height = int(inner_w * 9 / 16)
            try:
                self._inspector_container.update()
                # v1.1.6: インスペクタ幅に合わせてグリッドを確実に再描画
                if hasattr(self, "select_gallery_grid") and self.select_gallery_grid:
                    self.select_gallery_grid.update()
                if hasattr(self, "thumb_container") and self.thumb_container:
                    self.thumb_container.update()
            except: pass

    def _build_logo_group(self):
        """v1.0.2: 統一されたロゴとモード切替ボタンのグループ"""
        logo = ft.Row([
            ft.Icon(ft.Icons.CAMERA_ALT, size=22, color=COLOR_PRIMARY),
            ft.Text("RINKAN UMIS", size=16, weight="bold", color=COLOR_PRIMARY),
            ft.Text(f"v{VERSION}", size=9, color=COLOR_TEXT_SEC),
        ], spacing=8, vertical_alignment="center")

        switcher = ft.SegmentedButton(
            segments=[
                ft.Segment("ingest", label=ft.Text("取り込み", size=10), icon=ft.Icon(ft.Icons.DOWNLOAD, size=14)),
                ft.Segment("select", label=ft.Text("セレクト", size=10), icon=ft.Icon(ft.Icons.STAR, size=14)),
            ],
            selected={self.app_mode},
            on_change=self.on_mode_change,
            style=ft.ButtonStyle(padding=ft.padding.all(2)),
        )

        return ft.Column([
            logo,
            ft.Container(content=switcher, padding=ft.padding.only(top=8))
        ], spacing=0)

    def _build_modern_sidebar(self):
        """v9.5.0: スクリーンショットに基づいたモダンなサイドバーを構築"""
        # v1.1.0: インジェストモードにも対応
        def sidebar_item(icon, text, count=None, active=False, on_click=None):
            return ft.Container(
                content=ft.Row([
                    ft.Icon(icon, size=18, color=COLOR_PRIMARY if active else COLOR_TEXT_SEC),
                    ft.Text(text, size=13, weight=ft.FontWeight.W_500 if active else ft.FontWeight.W_400, color=COLOR_TEXT_MAIN if active else COLOR_TEXT_SEC),
                    ft.Container(expand=True),
                    ft.Text(str(count), size=11, color=COLOR_TEXT_SEC) if count is not None else ft.Container()
                ], spacing=10),
                padding=ft.padding.symmetric(7, 12),
                border_radius=6,
                bgcolor=COLOR_BG_HOVER if active else "transparent",
                on_click=on_click,
                on_hover=lambda e: (setattr(e.control, "bgcolor", COLOR_BG_HOVER if e.data == "true" else ("transparent" if not active else COLOR_BG_HOVER)), e.control.update())
            )

        section_label = lambda text: ft.Container(
            content=ft.Text(text.upper(), size=10, weight="bold", color=COLOR_TEXT_SEC),
            padding=ft.padding.only(left=12, top=20, bottom=8)
        )

        sidebar_controls = []
        
        if self.app_mode == "select":
            # セレクトモード: ライブラリとメディア
            library_items = self._get_dynamic_library_items(sidebar_item)
            media_items = self._get_dynamic_media_items(sidebar_item)
            self._select_library_tile = ft.ExpansionTile(
                title=ft.Text("ライブラリ", size=11, weight="bold", color=COLOR_TEXT_SEC),
                initially_expanded=True,
                controls=library_items,
                tile_padding=ft.padding.symmetric(horizontal=6, vertical=0),
                controls_padding=ft.padding.only(left=0),
                min_tile_height=32,
            )
            sidebar_controls = [
                self._select_library_tile,
                ft.ExpansionTile(
                    title=ft.Text("メディア", size=11, weight="bold", color=COLOR_TEXT_SEC),
                    initially_expanded=True,
                    controls=media_items,
                    tile_padding=ft.padding.symmetric(horizontal=6, vertical=0),
                    controls_padding=ft.padding.only(left=0),
                    min_tile_height=32,
                ),
                ft.Divider(height=1, color=COLOR_DIVIDER),
                sidebar_item(ft.Icons.FOLDER_OUTLINED, "全て", len(self.source_files),
                             active=False, on_click=lambda _: self._on_sidebar_collection_click()),
            ]
        else:
            # インジェストモード: メディアとセットアップ
            media_items = self._get_dynamic_media_items(sidebar_item)
            
            # インジェスト専用のセットアップUI
            setup_controls = ft.Column([
                ft.Container(
                    content=ft.Column([
                        ft.Text("プロジェクト", size=10, color=COLOR_TEXT_SEC, weight="bold"),
                        self.dd_project,
                    ], spacing=4),
                    padding=ft.padding.symmetric(horizontal=12, vertical=10)
                ),
                ft.Container(
                    content=ft.Column([
                        ft.Text("会場", size=10, color=COLOR_TEXT_SEC, weight="bold"),
                        self.dd_venue,
                    ], spacing=4),
                    padding=ft.padding.symmetric(horizontal=12, vertical=10)
                ),
                ft.Container(
                    content=ft.Column([
                        ft.Text("カメラマン / カードID", size=10, color=COLOR_TEXT_SEC, weight="bold"),
                        self.btn_select_identity,
                    ], spacing=4),
                    padding=ft.padding.symmetric(horizontal=12, vertical=10)
                ),
                ft.Container(
                    content=ft.Column([
                        ft.Row([
                            ft.Icon(ft.Icons.STORAGE, size=14, color=COLOR_TEXT_SEC),
                            ft.Text("ソースメディア", size=11, weight="bold", color=COLOR_TEXT_SEC),
                        ], spacing=6),
                        ft.Row([
                            self.dd_drive,
                        ], spacing=0),
                        ft.Row([
                            # 取り出しボタン
                            ft.Container(
                                content=ft.Row([
                                    ft.Stack([
                                        self.eject_icon_widget,
                                        self.eject_ring_widget
                                    ], width=18, height=18, alignment=ft.alignment.center),
                                    ft.Text("取り出し", size=11, color=COLOR_TEXT_MAIN),
                                ], spacing=4, tight=True),
                                on_click=self.eject_current_drive,
                                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                                border=ft.border.all(1, COLOR_DIVIDER),
                                border_radius=6,
                                bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
                                tooltip="メディアを取り出す",
                            ),
                            # 非表示ボタン
                            ft.Container(
                                content=ft.Row([
                                    ft.Icon(ft.Icons.VISIBILITY_OFF_OUTLINED, size=18, color=COLOR_TEXT_SEC),
                                    ft.Text("非表示", size=11, color=COLOR_TEXT_MAIN)
                                ], spacing=4, tight=True),
                                on_click=self.hide_current_drive,
                                padding=ft.padding.symmetric(horizontal=10, vertical=6),
                                border=ft.border.all(1, COLOR_DIVIDER),
                                border_radius=6,
                                bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
                                tooltip="このメディアをリストから隠す",
                            ),
                        ], spacing=8),
                        self.btn_format,
                    ], spacing=8),
                    padding=ft.padding.symmetric(horizontal=12, vertical=12),
                    bgcolor=ft.Colors.with_opacity(0.05, ft.Colors.BLACK),
                    border_radius=8,
                    margin=ft.margin.symmetric(horizontal=4, vertical=8)
                )
            ], spacing=0)

            sidebar_controls = [
                ft.ExpansionTile(
                    title=ft.Text("メディア", size=11, weight="bold", color=COLOR_TEXT_SEC),
                    initially_expanded=True,
                    controls=media_items,
                    tile_padding=ft.padding.symmetric(horizontal=6, vertical=0),
                    controls_padding=ft.padding.only(left=0),
                    min_tile_height=32,
                ),
                ft.Divider(height=1, color=COLOR_DIVIDER),
                section_label("セットアップ"),
                setup_controls,
            ]

        self._sidebar_item_func = sidebar_item  # 再構築用に保持
        self.modern_sidebar = ft.Container(
            width=self.sidebar_width,
            bgcolor=COLOR_BG_SIDEBAR,
            padding=ft.padding.symmetric(horizontal=6, vertical=10),
            content=ft.Column([
                ft.Column(sidebar_controls, spacing=0, scroll=ft.ScrollMode.AUTO, expand=True)
            ])
        )
        return self.modern_sidebar

    def _get_dynamic_library_items(self, sidebar_item_func):
        items = []
        try:
            dest_root = self.cfg_mgr.data["paths"].get("dest_root")
            if dest_root and os.path.exists(dest_root):
                for entry in sorted(os.scandir(dest_root), key=lambda e: e.name):
                    if entry.is_dir() and not entry.name.startswith(".") and entry.name != "thumbnails":
                        is_active = (entry.name == self._current_select_scene)
                        items.append(sidebar_item_func(
                            ft.Icons.SUBTITLES_OUTLINED,
                            entry.name,
                            active=is_active,
                            on_click=lambda e, name=entry.name: self._on_sidebar_library_click(name)
                        ))
        except: pass
        if not items:
            items.append(sidebar_item_func(ft.Icons.SUBTITLES_OUTLINED, "No Scenes"))
        return items

    def _get_dynamic_media_items(self, sidebar_item_func):
        items = []
        try:
            for mount, info in self.drive_map.items():
                # v9.6.0: クリックでそのドライブを選択
                items.append(sidebar_item_func(
                    ft.Icons.CAMERA_ALT_OUTLINED, 
                    info['name'],
                    on_click=lambda e, m=mount: self._on_sidebar_media_click(m)
                ))
        except: pass
        if not items:
            items.append(sidebar_item_func(ft.Icons.CAMERA_ALT_OUTLINED, "No Media"))
        return items

    def _build_modern_top_bar(self):
        scene_label = self._current_select_scene or "シーン未選択"
        # v1.1.22: 動的な更新のために参照を保持
        self._top_bar_scene_label = ft.Text(scene_label, size=14, weight="bold")
        return ft.Container(
            height=HEADER_HEIGHT,
            padding=ft.padding.symmetric(0, 20),
            border=ft.border.only(bottom=ft.border.BorderSide(1, COLOR_DIVIDER)),
            content=ft.Row([
                ft.Row([
                    ft.Icon(ft.Icons.FOLDER_OPEN, size=16, color=COLOR_TEXT_SEC),
                    self._top_bar_scene_label,
                ], spacing=8),
                ft.Container(expand=True),
            ])
        )

    def _build_modern_filter_bar(self):
        # v1.1.2: カテゴリチップはヘッダーに一本化するため、ここでは表示を削除
        return ft.Container(
            padding=ft.padding.only(bottom=12),
            content=ft.Row([
                self.btn_bulk_select_mode,
                ft.VerticalDivider(width=1, color=COLOR_DIVIDER, thickness=1),
                # self._cat_chips_row はヘッダーで使用するため、ここでは削除
                ft.Container(expand=True),
                ft.IconButton(
                    ft.Icons.GRID_VIEW if self.view_mode == "list" else ft.Icons.VIEW_LIST,
                    icon_size=18,
                    tooltip="表示切替",
                    on_click=self.toggle_view_mode
                ),
            ], spacing=10, vertical_alignment="center")
        )

    def _get_display_count(self):
        """現在のフィルタ条件で実際に表示されるファイル数を返す"""
        count = 0
        for f in self.source_files:
            if f.get('_select_locked'): continue
            if not self.select_cat_filters.get(f['cat'], True): continue
            count += 1
        return count

    def _toggle_select_cat(self, cat):
        filters = self.select_cat_filters if self.app_mode == "select" else self.ingest_cat_filters
        filters[cat] = not filters.get(cat, True)
        self.refresh_thumbnail_grid()
        # v1.1.2: チップの見た目を更新（ヘッダー内）
        self._update_cat_chips_row()
        try: self.page.update()
        except: pass

    def _update_cat_chips_row(self):
        """v1.1.2: カテゴリチップの見た目を最新の状態にする"""
        CAT_LABELS = [("Movie", "動画"), ("Photo", "写真"), ("Raw", "RAW"), ("Audio", "Audio")]
        CAT_COLORS = {cat: color for cat, (_, color) in CAT_ICONS.items()}

        def make_cat_chip(cat, label):
            filters = self.select_cat_filters if self.app_mode == "select" else self.ingest_cat_filters
            active = filters.get(cat, True)
            cat_color = CAT_COLORS.get(cat, COLOR_PRIMARY)
            return ft.Container(
                content=ft.Row([
                    ft.Icon(CAT_ICONS[cat][0], size=13, color="white" if active else "#777777"),
                    ft.Text(label, size=11, color="white" if active else "#777777", weight="bold" if active else "normal"),
                ], spacing=5, tight=True),
                # v1.1.2: オフ時はより明確にグレーアウト
                bgcolor=cat_color if active else "#222222",
                padding=ft.padding.symmetric(horizontal=12, vertical=6),
                border_radius=15,
                border=ft.border.all(1.5 if active else 1, cat_color if active else "#444444"),
                on_click=lambda e, c=cat: self._toggle_select_cat(c),
                on_hover=lambda e: self._on_chip_hover(e),
                opacity=1.0 if active else 0.7,
            )

        if not hasattr(self, "_cat_chips_row") or self._cat_chips_row is None:
            self._cat_chips_row = ft.Row(spacing=8, alignment="center")
            
        self._cat_chips_row.controls = [make_cat_chip(c, l) for c, l in CAT_LABELS]
        if self._cat_chips_row.page:
            try: self._cat_chips_row.update()
            except: pass

    def _on_chip_hover(self, e):
        # ホバー時の視覚効果
        filters = self.select_cat_filters if self.app_mode == "select" else self.ingest_cat_filters
        active = filters.get(e.control.content.controls[1].value, True) # ちょっと強引だが
        # ... 代わりにタグやデータを持たせるのが綺麗だが、ここでは簡易的に
        if e.data == "true":
            e.control.opacity = 0.8
        else:
            e.control.opacity = 1.0
        if e.control.page:
            e.control.update()

    def _update_cat_chips(self):
        self._update_cat_chips_row()

    def _build_modern_inspector(self):
        # v10.1.0: モック要素（メモ・タグ・情報タブ）を削除。プレビュー＋ファイル情報のみ。
        # v10.4.0: 幅変更に対応するためインスタンス変数に保持
        inner_w = self.select_inspector_width - 30  # padding 15*2
        self.select_inspector_preview.width = inner_w
        self.select_inspector_preview.height = int(inner_w * 9 / 16)
        self._inspector_container = ft.Container(
            width=self.select_inspector_width,
            bgcolor=COLOR_BG_SIDEBAR,
            padding=15,
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.INFO_OUTLINE, size=16, color=COLOR_TEXT_SEC),
                    ft.Text("インスペクタ", size=13, weight="bold", expand=True),
                ], spacing=8),
                ft.Divider(height=1, color=COLOR_DIVIDER),
                self.select_inspector_preview,
                self.select_inspector_meta,
                ft.Container(height=10),
                self.btn_move_scene,
            ], spacing=10, scroll=ft.ScrollMode.AUTO, tight=True,
               alignment=ft.MainAxisAlignment.START,
               horizontal_alignment=ft.CrossAxisAlignment.START)
        )
        return self._inspector_container

    def _build_modern_bottom_bar(self):
        # v10.1.0: 再生コントロール（モック）を削除。サイズスライダーのみ。
        selected_count = sum(1 for f in self.source_files if f.get('is_selected_for_edit') and not f.get('_select_locked'))
        return ft.Container(
            height=50,
            bgcolor=COLOR_BG_SIDEBAR,
            padding=ft.padding.symmetric(0, 20),
            border=ft.border.only(top=ft.border.BorderSide(1, COLOR_DIVIDER)),
            content=ft.Row([
                ft.Row([
                    ft.Icon(ft.Icons.STAR, size=14, color=COLOR_SELECT_MODE),
                    ft.Text(f"選別中: {selected_count}件", size=12, color=COLOR_TEXT_SEC),
                ], spacing=6),
                ft.Container(expand=True),
                ft.Row([
                    ft.Icon(ft.Icons.IMAGE_OUTLINED, size=16, color=COLOR_TEXT_SEC),
                    self.sl_thumb_size,
                    ft.Icon(ft.Icons.IMAGE, size=20, color=COLOR_TEXT_SEC),
                ], spacing=10)
            ], vertical_alignment="center")
        )

    def _build_select_content_blocks(self):
        """v1.1.0: セレクトモードの構成要素を個別に返す（統合レイアウト用）"""
        filter_bar = self._build_modern_filter_bar()
        inspector = self._build_modern_inspector()
        bottom_controls = self._build_modern_bottom_bar()

        # メインコンテンツエリア (Toolbar + Grid)
        content_main = ft.Container(
            content=ft.Column([
                filter_bar,
                ft.Container(
                    content=ft.Row([
                        ft.Column([
                            self._select_title_text,
                            self._select_count_text,
                        ], spacing=2),
                        ft.Container(expand=True),
                        self.btn_bulk_select_mode, # v1.1.0: 位置調整
                        self.btn_execute_select
                    ]),
                    padding=ft.padding.only(bottom=20)
                ),
                ft.Container(
                    content=self.thumb_container,
                    expand=True
                )
            ], spacing=0),
            expand=True,
            padding=20
        )
        return content_main, inspector, bottom_controls

    def _build_select_layout(self):
        # v1.1.0: build_ui で統合されたため、このメソッドは直接は使用されませんが互換性のために保持
        content_main, inspector, bottom_bar = self._build_select_content_blocks()
        sidebar = self._build_modern_sidebar()
        return ft.Row([sidebar, content_main, inspector], expand=True)
    def on_search_change(self, value):
        """v9.5.0: 検索文字列の変更に対応"""
        self.log(f"検索フィルタ: {value}")

    def on_view_mode_toggle(self, e):
        """v9.5.0: グリッド/リスト表示の切り替え"""
        e.control.selected = not e.control.selected
        e.control.update()
        self.log(f"表示モード切替: {'リスト' if e.control.selected else 'グリッド'}")

    def on_page_resize(self, e):
        self.update_header()

    def update_header(self):
        if hasattr(self, '_header_slot'):
            self._header_slot.content = self._build_header_inner()
            try: self._header_slot.update()
            except: pass

    def on_mode_change_manual(self, mode):
        """v9.5.0: 手動モード切替（トグル以外からの呼び出し用）"""
        self.app_mode = mode
        self.reset_progress_ui()
        self.source_files.clear()
        self.scene_assignments.clear()
        self.selected_scene_info = None
        self.build_ui()
        self.refresh_scene_buttons()
        self.refresh_thumbnail_grid()
        self.update_preview()
        if self.app_mode == "ingest":
            self.log("取り込みモードに切り替えました。")
            self._start_scan()
        else:
            self.log("セレクトモードに切り替えました。")
        try: self.page.update()
        except: pass

    def on_mode_change(self, e):
        # v9.0.0: モード切り替え
        self.on_mode_change_manual(e.control.selected.copy().pop())

    def _on_sidebar_library_click(self, folder_name):
        """v9.6.0: ライブラリ内のフォルダをクリックした際の処理"""
        dest_root = Path(self.cfg_mgr.data["paths"]["dest_root"])
        scene_dir = dest_root / folder_name
        if scene_dir.exists():
            self._current_select_scene = folder_name  # v10.1.0: 現在のシーンを記録
            if self.app_mode != "select":
                self.on_mode_change_manual("select")
            
            self.source_files.clear()
            self._is_scanning = True
            self._scanning_row.visible = True
            self.lbl_file_count.value = "ライブラリ読込中..."
            
            # v1.1.22: タイトルとサイドバーを即座に更新
            self._select_title_text.value = folder_name
            if hasattr(self, "_top_bar_scene_label"):
                self._top_bar_scene_label.value = folder_name
            if self._select_library_tile and self._sidebar_item_func:
                self._select_library_tile.controls = self._get_dynamic_library_items(self._sidebar_item_func)
            
            self.refresh_thumbnail_grid()
            try: self.page.update()
            except: pass

            def run_scan():
                try:
                    self.set_status(f"'{folder_name}' をスキャン中...", spinning=True)
                    self._scan_target_directory(scene_dir, recursive=True)
                finally:
                    self.set_status("システム待機中", spinning=False)
                    self._is_scanning = False
                    self._scanning_row.visible = False
                    self.lbl_file_count.value = f"ファイル: {len(self.source_files)}"
                    self.refresh_thumbnail_grid()
                    self.log(f"ライブラリから '{folder_name}' を読み込みました。")
                    # カウントを動的に更新
                    self._select_count_text.value = f"{self._get_display_count()}個の項目"
                    try:
                        self._select_title_text.update()
                        self._select_count_text.update()
                        if hasattr(self, "_top_bar_scene_label"):
                            self._top_bar_scene_label.update()
                    except: pass
                    # サイドバーの状態を再確認（完了時）
                    if self._select_library_tile and self._sidebar_item_func:
                        self._select_library_tile.controls = self._get_dynamic_library_items(self._sidebar_item_func)
                        try: self._select_library_tile.update()
                        except: pass
                    try: self.page.update()
                    except: pass

            threading.Thread(target=run_scan, daemon=True).start()
    
    def _show_move_scene_dialog(self, e):
        # v10.7.0: 選択中のファイルを別のシーンへ移動させるダイアログを表示
        selected_files = [f for f in self.source_files if f.get('selected')]
        if not selected_files:
            self.show_snack("ファイルを選択してください", COLOR_ERROR)
            return

        def on_scene_select(target_scene):
            self._close_active_modal()
            # 確認ダイアログ
            self._open_modal_dialog(
                "シーン移動の確認",
                ft.Column([
                    ft.Text(f"{len(selected_files)} 件のファイルを以下のシーンへ移動します：", size=14),
                    ft.Text(f"【{target_scene['name']}】", size=16, weight="bold", color=COLOR_PRIMARY),
                    ft.Text("※ファイル名中のシーン名も自動的に置換されます。", size=12, color=COLOR_TEXT_SEC),
                ], tight=True, spacing=10),
                [
                    ft.TextButton("実行", on_click=lambda _: self._execute_move_files(selected_files, target_scene), style=ft.ButtonStyle(color=COLOR_SUCCESS)),
                    ft.TextButton("キャンセル", on_click=self._close_active_modal)
                ]
            )

        # シーンリストを作成
        day_count = DAY_COUNT_FIXED
        scene_tabs = []
        for d in range(1, day_count + 1):
            scenes = sorted([s for s in self.cfg_mgr.data["scenes"] if s["day"] == d], key=lambda x: x["num"])
            if not scenes: continue
            
            grid = ft.GridView(
                expand=True, runs_count=2, max_extent=180, child_aspect_ratio=3.0, spacing=5, run_spacing=5
            )
            for s in scenes:
                grid.controls.append(
                    ft.Container(
                        content=ft.Text(f"{s['num']:02d}: {s['name']}", size=12),
                        padding=10, border=ft.border.all(1, COLOR_DIVIDER), border_radius=6,
                        on_click=lambda e, sc=s: on_scene_select(sc),
                        bgcolor=COLOR_BG_SIDEBAR, ink=True
                    )
                )
            scene_tabs.append(ft.Tab(text=f"{d}日目", content=grid))

        self._open_modal_dialog(
            "移動先のシーンを選択",
            ft.Container(
                content=ft.Tabs(tabs=scene_tabs, expand=True, height=400),
                width=400, height=400
            ),
            [ft.TextButton("キャンセル", on_click=self._close_active_modal)]
        )

    def _execute_move_files(self, files_to_move, target_scene):
        self._close_active_modal()
        self._is_scanning = True
        self._scanning_row.visible = True
        self.lbl_file_count.value = "シーン移動中..."
        self.set_status("ファイルを別のシーンへ移動中...", spinning=True)
        self.page.update()

        def move_worker():
            try:
                dest_root = Path(self.cfg_mgr.data["paths"]["dest_root"])
                use_numbering = self.cfg_mgr.data["options"].get("scene_numbering", True)
                sub_name = self.cfg_mgr.data["options"].get("sub_folder_name", "選別")
                cat_settings = self.cfg_mgr.data.get("category_settings", {})
                
                new_scene_folder = f"{target_scene['day']}{target_scene['num']:02d}_{target_scene['name']}" if use_numbering else target_scene['name']
                
                moved_count = 0
                error_count = 0
                
                for f in files_to_move:
                    old_path = Path(f['path'])
                    if not old_path.exists(): continue
                    old_name = old_path.name

                    try:
                        # 旧シーンフォルダの特定
                        old_scene_folder = f.get('assigned_scene')
                        if not old_scene_folder:
                            # assigned_scene が None の場合はパスから推測 (dest_root 直下のフォルダ)
                            try:
                                rel = old_path.relative_to(dest_root)
                                old_scene_folder = rel.parts[0]
                            except:
                                # 推測不能な場合は空文字列にするが、リネームに影響
                                old_scene_folder = ""

                        if old_scene_folder == new_scene_folder: continue 
                        
                        # カテゴリフォルダとカメラマンフォルダの特定
                        cat = f.get('cat', 'Other')
                        cat_folder_name = cat_settings.get(cat, {}).get("folder", cat)
                        
                        # 元のパス構造からカメラマンフォルダを特定 (Scene/Category/Photographer/File)
                        pg_folder_name = ""
                        try:
                            if old_scene_folder:
                                rel_parts = old_path.relative_to(dest_root / old_scene_folder).parts
                                # rel_parts: (Category, Photographer, File) または (Category, File)
                                if len(rel_parts) >= 3:
                                    pg_folder_name = rel_parts[1]
                        except: pass

                        # 新しいファイル名 (旧シーン名を新シーン名に置換)
                        if old_scene_folder:
                            new_name = old_name.replace(old_scene_folder, new_scene_folder)
                        else:
                            new_name = old_name
                        
                        # 新しい親ディレクトリを構築 (設定に基づき自動生成)
                        new_parent = dest_root / new_scene_folder / cat_folder_name
                        if pg_folder_name:
                            new_parent = new_parent / pg_folder_name
                        
                        new_parent.mkdir(parents=True, exist_ok=True)
                        new_path = new_parent / new_name
                        
                        # 物理移動
                        shutil.move(str(old_path), str(new_path))
                        
                        # 選別済みフォルダ内も同期移動
                        if sub_name and old_scene_folder:
                            sorted_old = dest_root / old_scene_folder / sub_name / old_name
                            if sorted_old.exists():
                                sorted_new_parent = dest_root / new_scene_folder / sub_name
                                sorted_new_parent.mkdir(parents=True, exist_ok=True)
                                sorted_new_path = sorted_new_parent / new_name
                                shutil.move(str(sorted_old), str(sorted_new_path))

                        moved_count += 1
                    except Exception as ex:
                        self.log(f"移動失敗: {old_name} -> {ex}")
                        error_count += 1

                self.log(f"シーン移動完了: {moved_count}件成功, {error_count}件失敗")
                self.show_snack(f"{moved_count}件のファイルを移動しました", COLOR_SUCCESS)
                
            except Exception as outer_ex:
                self.log(f"致命的なエラー: {outer_ex}")
            finally:
                self.set_status("システム待機中", spinning=False)
                self._is_scanning = False
                # 表示をリフレッシュ
                self._on_sidebar_library_click(self._current_select_scene)

        threading.Thread(target=move_worker, daemon=True).start()

    def _on_sidebar_media_click(self, mount_path):
        """v9.6.0: メディア（ドライブ）をクリックした際の処理"""
        if self.app_mode != "ingest":
            self.on_mode_change_manual("ingest")
        
        self.dd_drive.value = mount_path
        self.on_source_change(None)

    def _on_sidebar_collection_click(self):
        """v9.6.0: '全ての動画' をクリックした際の処理"""
        if self.app_mode == "ingest":
            self._start_scan()
        else:
            # セレクトモード時は全シーンを横断的に表示
            dest_root = Path(self.cfg_mgr.data["paths"]["dest_root"])
            if dest_root.exists():
                self.source_files.clear()
                self._is_scanning = True
                self._scanning_row.visible = True
                self.lbl_file_count.value = "全アーカイブ読込中..."
                self.refresh_thumbnail_grid()
                try: self.page.update()
                except: pass

                def run_scan_all():
                    try:
                        self._scan_target_directory(dest_root, recursive=True)
                    finally:
                        self._is_scanning = False
                        self._scanning_row.visible = False
                        self.lbl_file_count.value = f"ファイル: {len(self.source_files)}"
                        self.refresh_thumbnail_grid()
                        self.log("全てのアーカイブ動画を読み込みました。")
                        try: self.page.update()
                        except: pass

                threading.Thread(target=run_scan_all, daemon=True).start()

    def _scan_target_directory(self, target_dir: Path, recursive=False):
        """v9.6.0: 指定フォルダからメディアファイルを検索してsource_filesに追加"""
        cat_settings = self.cfg_mgr.data.get("category_settings", {})
        ext_to_cat = {}
        for cat, conf in cat_settings.items():
            # v10.6.2: セレクトモード時はインジェスト設定（disabled）を無視して全件読込対象とする
            if self.app_mode != "select" and conf.get("disabled", False):
                continue
            for e in conf.get("exts", []):
                ext_to_cat[e.lower()] = cat
        
        pattern = f"**/*" if recursive else "*"
        try:
            # v9.6.0: 大量のファイルを扱うためソートしてバッチ追加
            found_paths = list(target_dir.glob(pattern))
            for p in sorted(found_paths):
                if p.is_file() and not p.name.startswith(".") and p.suffix.lower() in ext_to_cat:
                    # 重複チェック
                    if any(f['path'] == str(p) for f in self.source_files): continue
                    
                    cat = ext_to_cat[p.suffix.lower()]
                    
                    try: st = p.stat()
                    except: continue

                    self.source_files.append({
                        "name": p.name,
                        "path": str(p),
                        "ext": p.suffix.lower(), # v9.6.0: 欠落していたキーを追加
                        "size": st.st_size,
                        "cat": cat,
                        "date": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y%m%d"),
                        "selected": (self.app_mode != "select"), # v10.7.3: セレクトモード時はデフォルト未選択
                        "assigned_scene": None,
                        "is_selected_for_edit": False
                    })
        except Exception as e:
            self.log(f"スキャンエラー: {str(e)}")

    def _build_header(self):
        # v7.6.1: リサイズで中身を再構築できるようスロット化
        self._header_slot = ft.Container(
            content=self._build_header_inner(),
            bgcolor=COLOR_BG_SIDEBAR,
            padding=ft.padding.symmetric(horizontal=15, vertical=8),
        )
        return self._header_slot

    def _build_header_inner(self):
        # v1.1.2: カテゴリチップと保存先をヘッダーに統合
        logo_group = self._build_logo_group()

        # カテゴリチップ
        self._update_cat_chips_row()
        
        # 保存先コンパクト表示
        dest_compact = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.LOCATION_ON, size=16, color=COLOR_PRIMARY),
                ft.Text(self.tf_dest_dir.value or "保存先未設定", size=11, color=COLOR_TEXT_MAIN, max_lines=1, overflow="ellipsis", width=180),
                ft.IconButton(ft.Icons.FOLDER_OPEN, icon_size=16, on_click=self.pick_dest, tooltip="保存先フォルダを選択")
            ], spacing=5, tight=True),
            padding=ft.padding.symmetric(horizontal=12, vertical=4),
            bgcolor=ft.Colors.with_opacity(0.1, ft.Colors.BLACK),
            border_radius=8,
            on_click=self.open_dest_folder,
            tooltip="保存先フォルダを開く (ダブルクリック推奨)",
            ink=True
        )

        settings_btn = ft.IconButton(
            ft.Icons.SETTINGS, icon_color=COLOR_TEXT_SEC,
            tooltip="設定", on_click=self.open_settings_modal, icon_size=20,
        )
        
        divider = lambda: ft.Container(width=1, height=24, bgcolor=COLOR_DIVIDER)

        # セレクトモード時のシーン名表示
        scene_info = ft.Container()
        if self.app_mode == "select":
            scene_label = self._current_select_scene or "シーン未選択"
            scene_info = ft.Row([
                divider(),
                ft.Icon(ft.Icons.FOLDER_OPEN, size=16, color=COLOR_TEXT_SEC),
                ft.Text(scene_label, size=14, weight="bold", color=COLOR_TEXT_MAIN),
            ], spacing=8, tight=True)

        return ft.Row([
            logo_group,
            ft.Row([
                self._cat_chips_row,
                ft.Container(width=15),
                dest_compact,
                scene_info
            ], alignment="center", expand=True),
            ft.Row([
                divider(),
                settings_btn
            ], spacing=10, vertical_alignment="center", tight=True)
        ], alignment="spaceBetween", vertical_alignment="center")


    def _show_project_picker_modal(self, e=None):
        # v7.6.1: コンパクトモード用プロジェクト切替
        project_names = [o.key for o in (self.dd_project.options or [])]
        current = self.cfg_mgr.project_name

        def _pick(name):
            self._close_active_modal()
            if name != current:
                self.dd_project.value = name
                self.on_project_change(None)
            self.update_header()

        rows = []
        for name in project_names:
            is_sel = (name == current)
            rows.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.CHECK if is_sel else ft.Icons.FOLDER_OPEN,
                            color=COLOR_PRIMARY if is_sel else COLOR_TEXT_SEC, size=18),
                    ft.Text(name, size=13, weight="bold" if is_sel else "normal",
                            color=COLOR_TEXT_MAIN, expand=True),
                ], spacing=8, vertical_alignment="center"),
                padding=10,
                bgcolor=COLOR_BG_SIDEBAR,
                border_radius=8,
                on_click=lambda ev, n=name: _pick(n),
                ink=True,
            ))
        if not rows:
            rows.append(ft.Text("プロジェクトがありません", color=COLOR_TEXT_SEC))
        self._open_modal_dialog(
            "プロジェクトを選択",
            ft.Column(rows, spacing=6, tight=True, scroll=ft.ScrollMode.AUTO),
            [ft.TextButton("閉じる", on_click=self._close_active_modal)],
        )

    def _show_venue_picker_modal(self, e=None):
        # v7.6.1: コンパクトモード用会場切替
        venues = self.cfg_mgr.data.get("locations", []) or []
        current = self.dd_venue.value

        def _pick(name):
            self._close_active_modal()
            self.dd_venue.value = name
            try: self.dd_venue.update()
            except: pass
            self.on_venue_change(None)
            self.update_header()

        rows = []
        for name in venues:
            is_sel = (name == current)
            rows.append(ft.Container(
                content=ft.Row([
                    ft.Icon(ft.Icons.CHECK if is_sel else ft.Icons.LOCATION_ON,
                            color=COLOR_PRIMARY if is_sel else COLOR_TEXT_SEC, size=18),
                    ft.Text(name, size=13, weight="bold" if is_sel else "normal",
                            color=COLOR_TEXT_MAIN, expand=True),
                ], spacing=8, vertical_alignment="center"),
                padding=10,
                bgcolor=COLOR_BG_SIDEBAR,
                border_radius=8,
                on_click=lambda ev, n=name: _pick(n),
                ink=True,
            ))
        if not rows:
            rows.append(ft.Text("会場が登録されていません。設定から追加してください。", color=COLOR_TEXT_SEC))
        self._open_modal_dialog(
            "会場を選択",
            ft.Column(rows, spacing=6, tight=True, scroll=ft.ScrollMode.AUTO),
            [ft.TextButton("閉じる", on_click=self._close_active_modal)],
        )

    def _build_scene_panel(self):
        """v1.1.0: インジェストモードのシーンパネル。セレクトモードのインスペクタとスタイルを統一"""
        self.scene_panel = ft.Container(
            width=self.scene_panel_width,
            bgcolor=COLOR_BG_SIDEBAR,
            padding=15,
            content=ft.Column([
                ft.Row([
                    ft.Icon(ft.Icons.SUBTITLES_OUTLINED, size=16, color=COLOR_TEXT_SEC),
                    ft.Text("シーン割当", size=13, weight="bold", expand=True),
                ], spacing=8),
                ft.Divider(height=1, color=COLOR_DIVIDER),
                ft.Container(content=self.radio_day, padding=2, border=ft.border.all(1, COLOR_DIVIDER), border_radius=6),
                ft.Row([
                    ft.Text("シーンリスト", size=11, color=COLOR_TEXT_SEC, weight="bold"),
                    ft.Container(expand=True),
                    self.btn_scene_edit,
                    ft.IconButton(ft.Icons.ADD_CIRCLE, icon_color=COLOR_SUCCESS, on_click=self.add_scene_manual, icon_size=18),
                ], spacing=0),
                ft.Container(
                    content=self.scene_content_area,
                    border=ft.border.all(1, COLOR_DIVIDER),
                    border_radius=6,
                    padding=5,
                    bgcolor=COLOR_BG_MAIN, # グリッド内は少し暗く
                    expand=True,
                )
            ], spacing=10, tight=True)
        )
        return self.scene_panel

    def _build_thumb_panel(self):
        self.sl_thumb_size = ft.Slider(min=80, max=300, value=120, divisions=22, label="{value}", width=120, active_color=COLOR_PRIMARY, on_change=self.on_thumb_size_change)
        # v7.6.7: 並び替え用ドロップダウン
        self.dd_sort = ft.Dropdown(
            options=[
                ft.dropdown.Option("name", "名前順"),
                ft.dropdown.Option("date", "日付順"),
                ft.dropdown.Option("cat", "カテゴリ順"),
                ft.dropdown.Option("size", "サイズ順"),
            ],
            value=self.current_sort,
            width=100,
            text_size=12,
            content_padding=ft.padding.only(left=8, right=4, top=0, bottom=0),
            border_color=COLOR_DIVIDER,
            on_change=self.on_sort_change,
        )
        # v8.0.13: フォントサイズ独立スライダー追加
        self.sl_font_size = ft.Slider(
            min=9, max=20, value=12, divisions=11, label="{value}",
            width=100, active_color=COLOR_PRIMARY,
            on_change=self.on_font_size_change
        )
        # v8.0.13: 全選択/全解除の2ボタンをColumnでグループ化
        select_btn_group = ft.Column([
            self.btn_select_all_btn,
            self.btn_deselect_all_btn,
        ], spacing=0, tight=True)

        # v8.0.13: スライダーアイコンを変更し、フォントサイズスライダーを追加
        thumb_toolbar = ft.Row([
            select_btn_group,
            ft.TextButton("未割当を選択", on_click=self.select_unassigned, style=ft.ButtonStyle(color=COLOR_ACCENT)),
            self.lbl_file_count, 
            self.lbl_assigned_count,
            ft.TextButton("シーン割当を取消", on_click=self.clear_assignments, style=ft.ButtonStyle(color=COLOR_ERROR)),
            ft.VerticalDivider(width=1, color=COLOR_DIVIDER, thickness=1),
            ft.Row([
                ft.Icon(ft.Icons.SORT, size=16, color=COLOR_TEXT_SEC),
                self.dd_sort,
                ft.VerticalDivider(width=1, color=COLOR_DIVIDER, thickness=1),
                ft.Icon(ft.Icons.PHOTO_SIZE_SELECT_LARGE, size=16, color=COLOR_TEXT_SEC),
                self.sl_thumb_size,
                ft.VerticalDivider(width=1, color=COLOR_DIVIDER, thickness=1),
                ft.Icon(ft.Icons.FORMAT_SIZE, size=16, color=COLOR_TEXT_SEC),
                self.sl_font_size,
                self.btn_view_toggle,
            ], spacing=5, vertical_alignment="center", tight=True)
        ], spacing=10, wrap=True, alignment=ft.MainAxisAlignment.START)
        
        self.thumb_container.content = self.grid_thumbnails
        self.thumb_main_slot.content = self.thumb_container # 初期状態はリスト

        thumb_panel = ft.Container(
            content=ft.Column([
                ft.Text("ソースファイル", weight="bold", size=13, color=COLOR_TEXT_MAIN),
                thumb_toolbar,
                ft.Container(
                    content=ft.Stack([
                        self.thumb_main_slot,
                        self.col_preview_area
                    ], expand=True),
                    expand=True,
                ),
                self._scanning_row,
            ], spacing=5, expand=True),
            expand=True, padding=10
        )
        return thumb_panel


    def _build_bottom_bar(self):
        """v1.1.12: スクリーンショット準拠のスリムなステータスバー型ボトムバー"""

        # 保存先参照ボタン（小型）
        self.btn_pick_dest = ft.Container(
            content=ft.Row([
                ft.Icon(ft.Icons.FOLDER_OPEN, size=13, color=COLOR_TEXT_SEC),
                ft.Text("参照", size=11),
            ], spacing=4, tight=True),
            padding=ft.padding.symmetric(horizontal=8, vertical=4),
            border_radius=4,
            bgcolor=COLOR_BG_CARD,
            on_click=self.pick_dest,
            on_hover=lambda e: (setattr(e.control, 'bgcolor', COLOR_BG_HOVER if e.data == "true" else COLOR_BG_CARD), e.control.update())
        )

        # ステータス左エリア：ログテキスト + 保存先
        status_left = ft.Row([
            ft.Icon(ft.Icons.CIRCLE, size=8, color=COLOR_PRIMARY),
            self.lbl_status,
            ft.Text("Destination:", size=11, color=COLOR_TEXT_SEC),
            ft.Container(content=self.tf_dest_dir, expand=True),
            self.btn_pick_dest,
        ], spacing=8, vertical_alignment="center", expand=True)

        # 細いプログレスバー（中央）
        progress_bar = ft.Row([
            self.lbl_percent,
            ft.Stack([
                ft.Container(bgcolor="#2A2A2A", border_radius=3, height=4, width=PB_WIDTH),
                ft.Container(content=self.pb_fill, height=4, border_radius=3, width=PB_WIDTH, alignment=ft.alignment.center_left),
            ], width=PB_WIDTH),
        ], spacing=8, vertical_alignment="center")
        # pb_fill の高さを上書き
        self.pb_fill.height = 4
        self.pb_fill.border_radius = 3

        # サブボタン（履歴・フォルダ）
        self.btn_history.height = 30
        self.btn_open_folder.height = 30
        self.btn_history.style = ft.ButtonStyle(
            bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_SEC,
            padding=ft.padding.symmetric(horizontal=10),
            shape=ft.RoundedRectangleBorder(radius=4),
        )
        self.btn_open_folder.style = ft.ButtonStyle(
            bgcolor=COLOR_BG_CARD, color=COLOR_TEXT_SEC,
            padding=ft.padding.symmetric(horizontal=10),
            shape=ft.RoundedRectangleBorder(radius=4),
        )
        self.btn_cancel.height = 30
        self.btn_cancel.style = ft.ButtonStyle(
            bgcolor=COLOR_BG_CARD, color=COLOR_ERROR,
            padding=ft.padding.symmetric(horizontal=10),
            shape=ft.RoundedRectangleBorder(radius=4),
            overlay_color=ft.Colors.with_opacity(0.1, ft.Colors.WHITE),
        )

        sub_row = ft.Row([
            self.btn_history,
            self.btn_open_folder,
            self.btn_cancel,
        ], spacing=6, vertical_alignment="center")

        # START INGEST ボタン（右端、目立つ大型ボタン）
        self.btn_start.height = 36
        self.btn_start.style = ft.ButtonStyle(
            bgcolor={
                ft.ControlState.DISABLED: COLOR_DISABLED_BTN_BG,
                ft.ControlState.DEFAULT: COLOR_PRIMARY,
            },
            color={
                ft.ControlState.DISABLED: COLOR_DISABLED_BTN_TEXT,
                ft.ControlState.DEFAULT: ft.Colors.WHITE,
            },
            padding=ft.padding.symmetric(horizontal=20, vertical=0),
            shape=ft.RoundedRectangleBorder(radius=6),
            overlay_color=ft.Colors.with_opacity(0.15, ft.Colors.WHITE),
        )

        right_actions = ft.Row([
            sub_row,
            ft.Container(width=12),
            self.btn_start,
        ], spacing=0, vertical_alignment="center")

        # コンソールログ折りたたみパネル
        self._log_panel_visible = False
        log_panel_container = ft.Container(
            content=ft.Column([
                ft.Container(
                    content=self.lv_log,
                    expand=True,
                    padding=ft.padding.symmetric(horizontal=8, vertical=4),
                    bgcolor=COLOR_BG_MAIN,
                    border_radius=6,
                )
            ], spacing=0),
            visible=False,
            height=120,
            bgcolor=COLOR_BG_SIDEBAR,
            border=ft.border.only(top=ft.border.BorderSide(1, COLOR_DIVIDER)),
            padding=ft.padding.symmetric(horizontal=20, vertical=8),
        )
        self._log_panel_container = log_panel_container

        def toggle_log_panel(e):
            self._log_panel_visible = not self._log_panel_visible
            log_panel_container.visible = self._log_panel_visible
            try: log_panel_container.update()
            except: pass

        console_btn = ft.TextButton(
            "Console",
            on_click=toggle_log_panel,
            style=ft.ButtonStyle(color=COLOR_TEXT_SEC, padding=ft.padding.symmetric(horizontal=6, vertical=0)),
        )

        status_bar_row = ft.Row([
            status_left,
            ft.Container(width=20),
            progress_bar,
            ft.Container(width=20),
            console_btn,
            ft.Container(width=8),
            right_actions,
        ], spacing=0, vertical_alignment="center")

        return ft.Column([
            log_panel_container,
            ft.Container(
                content=status_bar_row,
                bgcolor=COLOR_BG_SIDEBAR,
                padding=ft.padding.symmetric(horizontal=20, vertical=8),
                height=52,
                border=ft.border.only(top=ft.border.BorderSide(1, COLOR_DIVIDER)),
            ),
        ], spacing=0)

    def start_walkthrough(self, e=None):
        if hasattr(self, "settings_overlay") and self.settings_overlay.visible:
            self.settings_overlay.visible = False
        if self.current_view != "main":
            self.switch_view("main")
        self.cfg_mgr.data["is_first_run"] = False
        self.cfg_mgr.save()
        self.tutorial_step = 0
        self.tutorial_overlay.visible = True
        self.page.update()
        self.next_walkthrough_step()
    
    def end_walkthrough(self, e=None):
        self.tutorial_overlay.visible = False
        self.tutorial_overlay.content = None
        if hasattr(self, "settings_overlay") and self.settings_overlay.visible:
            self.settings_overlay.visible = False
        if self.current_view != "main":
            self.switch_view("main")
        try: self.page.update()
        except: pass

    def next_walkthrough_step(self, e=None):
        steps = [
            {
                "title": "1. 撮影者 / カード設定",
                "text": "サイドバー上部のボタンから、撮影者名とカードIDを設定します。これらは取り込み時のファイル名に反映される重要な情報です。",
                "action": lambda: self.switch_view("main") if self.current_view != "main" else None
            },
            {
                "title": "2. ファイルブラウザ",
                "text": "左側のエリアにドライブ内のファイルが表示されます。クリックで個別選択（丸印）でき、複数選択して一括でシーン割り当てが可能です。",
            },
            {
                "title": "3. 範囲選択（高速操作）",
                "text": "起点を左クリックした後、終点を**右クリック（Macは2本指タップ）**すると、その間を瞬時に一括選択できます。最速の選択方法です。",
            },
            {
                "title": "4. シーン割り当て",
                "text": "右側のシーンボタンを押すと、選択中のファイルがそのシーンに割り当てられます。タブで日程（撮影日）を切り替えられます。",
            },
            {
                "title": "5. カテゴリフィルター",
                "text": "ヘッダーのアイコンで表示を「動画のみ」「写真のみ」等に絞り込めます。インジェストとセレクトで独立して状態が保持されます。",
            },
            {
                "title": "6. セレクトモード",
                "text": "ヘッダー右上の切替スイッチで「セレクト」にすると、アーカイブ済みファイルの選別や詳細確認、書き出しが行えます。",
            }
        ]

        if self.tutorial_step >= len(steps):
            self.end_walkthrough()
            return

        step = steps[self.tutorial_step]
        self.tutorial_step += 1

        if "action" in step:
            try: step["action"]()
            except: pass

        # v8.0.12: 環境によるズレを防ぐため、中央配置のダイアログ形式に変更
        balloon = ft.Container(
            content=ft.Column([
                ft.Row([
                    ft.Container(
                        content=ft.Text(f"Step {self.tutorial_step} / {len(steps)}", size=11, color=COLOR_PRIMARY, weight="bold"),
                        padding=ft.padding.symmetric(horizontal=8, vertical=2),
                        border=ft.border.all(1, COLOR_PRIMARY),
                        border_radius=4
                    ),
                    ft.Text(step["title"], weight="bold", color=COLOR_TEXT_MAIN, size=18, expand=True),
                ], alignment="center", spacing=12),
                ft.Divider(color=COLOR_DIVIDER, height=20),
                ft.Text(step["text"], color=COLOR_TEXT_MAIN, size=14),
                ft.Container(height=20),
                ft.Row([
                    ft.TextButton("ツアーを終了", on_click=self.end_walkthrough, style=ft.ButtonStyle(color=COLOR_TEXT_SEC)),
                    ft.ElevatedButton(
                        "次へ" if self.tutorial_step < len(steps) else "完了",
                        on_click=self.next_walkthrough_step,
                        bgcolor=COLOR_PRIMARY,
                        color=COLOR_TEXT_MAIN,
                        width=100,
                        height=40
                    )
                ], alignment="end", spacing=10)
            ], spacing=10, tight=True),
            bgcolor=COLOR_BG_CARD,
            border=ft.border.all(1, COLOR_PRIMARY),
            border_radius=16,
            padding=25,
            width=420,
            shadow=ft.BoxShadow(spread_radius=5, blur_radius=30, color=ft.Colors.BLACK),
            animate_opacity=300
        )

        self.tutorial_overlay.content = ft.Container(
            content=balloon,
            alignment=ft.alignment.center,
            bgcolor="#AA000000",
            expand=True,
            on_click=lambda e: None # 背景クリック無効
        )
        self.tutorial_overlay.visible = True
        try: self.page.update()
        except: pass

    def on_sidebar_drag(self, e: ft.DragUpdateEvent):
        """v1.1.27: サイドバー幅をマウスドラッグで調整。最大20%制限"""
        # アプリ幅の20%を上限とする
        max_w = (self.page.width * 0.2) if self.page.width else 400
        min_w = 160
        self.sidebar_width = max(min_w, min(max_w, self.sidebar_width + e.delta_x))
        if hasattr(self, 'modern_sidebar') and self.modern_sidebar:
            self.modern_sidebar.width = self.sidebar_width
            try: self.modern_sidebar.update()
            except: pass

    def on_splitter_drag(self, e: ft.DragUpdateEvent):
        # v7.6.0: ウィンドウ幅から上限を動的算出し、左ペイン(サムネイル)を最低300px担保
        MIN_SCENE_WIDTH = 200
        MIN_THUMB_WIDTH = 300
        SPLITTER_WIDTH = 6
        try:
            page_w = float(self.page.width or 0)
        except Exception:
            page_w = 0.0
            
        # v7.6.4: シーンパネルの最大幅を全体の25%（3:1比率）に制限
        ratio_max = page_w * MAX_SCENE_PANEL_RATIO
        dyn_max = min(ratio_max, page_w - MIN_THUMB_WIDTH - SPLITTER_WIDTH)
        dyn_max = max(MIN_SCENE_WIDTH + 1, dyn_max)
        
        new_width = self.scene_panel.width - e.delta_x
        if MIN_SCENE_WIDTH < new_width < dyn_max:
            self.scene_panel.width = new_width
            if new_width < 250:
                self.grid_scenes.runs_count = 1
            else:
                self.grid_scenes.runs_count = 2
            self.scene_panel.update()
            try: self.grid_scenes.update()
            except: pass

    def on_sort_change(self, e):
        self.current_sort = self.dd_sort.value
        self.sort_files()
        self.focused_file_index = -1 # ソート後はフォーカスをリセット
        self.refresh_thumbnail_grid()

    def sort_files(self):
        if not self.source_files: return
        if self.current_sort == "name":
            self.source_files.sort(key=lambda x: x['name'].lower())
        elif self.current_sort == "date":
            self.source_files.sort(key=lambda x: x.get('mtime', 0))
        elif self.current_sort == "cat":
            self.source_files.sort(key=lambda x: (x['cat'], x['name'].lower()))
        elif self.current_sort == "size":
            self.source_files.sort(key=lambda x: x['size'], reverse=True)

    def on_keyboard_event(self, e: ft.KeyboardEvent):
        # v1.1.25: 自前の _active_modal_dlg フラグで確実に判定
        is_dialog_active = (self._active_modal_dlg is not None)
        if self.settings_overlay.visible or self.tutorial_overlay.visible or is_dialog_active:
            if e.key == "Escape": self._close_active_modal()
            return

        if e.key == " ":
            # v8.0.23: v8.0.18の操作性を継承。スペースはトグル。
            if self._preview_visible:
                # 全画面表示中なら閉じる
                self.close_quick_preview()
            elif self.app_mode == "select":
                # v9.3.2: セレクトモード時はスペースで即全画面プレビュー（インスペクターがあるため）
                self.show_quick_preview()
            elif self._is_col_preview_mode:
                # カラムプレビュー表示中ならリストに戻る
                self.hide_col_preview()
            else:
                # リスト表示中ならプレビューを開く
                self.update_col_preview(switch_to_preview=True)
        elif e.key == "k" or e.key == "K":
            if self._preview_visible and self.video_ctrl: self._toggle_video_play()
        elif e.key == "j" or e.key == "J":
            if self._preview_visible and self.video_ctrl: self._seek_relative(-10000)
        elif e.key == "l" or e.key == "L":
            if self._preview_visible and self.video_ctrl: self._seek_relative(10000)
        elif e.key == "Escape":
            if self._preview_visible: self.close_quick_preview()
        elif e.key == "Arrow Right" or e.key == "Arrow Down":
            self.navigate_preview(1)
        elif e.key == "Arrow Left" or e.key == "Arrow Up":
            self.navigate_preview(-1)
        elif e.key == "s" or e.key == "S":
            # v9.5.0: インジェストモードでは無効化。セレクトモードのみ実行。
            if self.app_mode == "select":
                if 0 <= self.focused_file_index < len(self.source_files):
                    self.toggle_selection_flag(self.focused_file_index)
            else:
                self.log("選別（S）はセレクトモードでのみ有効です。")
            # v10.6.0: macOS警告音防止
            self._reset_focus()

    def _is_file_visible(self, f):
        """v10.7.11/v1.1.19: 現在の表示設定でファイルが可視状態か判定"""
        # カテゴリフィルターをチェック
        filters = self.select_cat_filters if self.app_mode == "select" else self.ingest_cat_filters
        if not filters.get(f['cat'], True): return False
        
        # 設定の無効化をチェック
        cat_conf = self.cfg_mgr.data["category_settings"].get(f['cat'], {})
        if cat_conf.get("disabled", False): return False

        if self.app_mode == "select":
            if f.get('_select_locked'): return False
            
        return True

    def navigate_preview(self, delta):
        # v10.7.11: フィルタ状態を尊重してナビゲート
        if not self.source_files: return
        
        curr = self.focused_file_index
        step = 1 if delta > 0 else -1
        
        # 次の可視アイテムを探索
        new_idx = curr + step
        while 0 <= new_idx < len(self.source_files):
            if self._is_file_visible(self.source_files[new_idx]):
                break
            new_idx += step
        
        # 見つかった場合のみ移動
        if 0 <= new_idx < len(self.source_files):
            old_idx = self.focused_file_index
            self.focused_file_index = new_idx
            if old_idx != -1: self._update_item_visual(old_idx)
            self._update_item_visual(new_idx)
            
            if self.app_mode == "select" or self._is_col_preview_mode:
                self.update_col_preview(switch_to_preview=False)
            
            if self._preview_visible:
                if platform.system() == "Darwin":
                    time.sleep(0.1)
                self.show_quick_preview()

    def show_quick_preview(self, e=None):
        if self.focused_file_index == -1 and self.source_files:
            self.focused_file_index = 0
            self._update_item_visual(0)
        
        if 0 <= self.focused_file_index < len(self.source_files):
            f = self.source_files[self.focused_file_index]
            self._preview_visible = True
            
            self._stop_audio() # v8.0.22: 音声を停止
            
            # v8.0.20: 全画面表示時はインライン側の動画を停止
            if self.video_ctrl_col:
                try: self.video_ctrl_col.pause()
                except: pass

            # コンテンツの構築
            self.preview_filename_text.value = f['name']
            self.preview_content_slot.content = self._build_preview_widget(f, is_fullscreen=True)
            
            try: 
                self.page.update()
                self.dummy_focus.focus() # v8.0.2: スペース音対策
            except: pass

    def _on_dummy_change(self, e):
        # v8.0.2: スペース入力を即座にクリア
        self.dummy_focus.value = ""
        self.global_dummy_focus.value = ""
        try:
            self.dummy_focus.update()
            self.global_dummy_focus.update()
        except: pass

    def _reset_focus(self, e=None):
        # v8.0.19: 警告音抑制のため、常にTextFieldにフォーカスを戻す
        try:
            self.global_dummy_focus.focus()
            self.page.update()
        except: pass

    def close_quick_preview(self, e=None):
        self._preview_visible = False
        self.preview_overlay.visible = False
        self.video_ctrl = None
        self._stop_audio() # v8.0.22: 音声を停止
        # ビデオ再生中なら停止させるためにコンテンツをクリア
        self.preview_content_slot.content = None
        self._reset_focus() # フォーカスを戻す
        try: self.page.update()
        except: pass

    def toggle_selection_flag(self, idx):
        if 0 <= idx < len(self.source_files):
            f = self.source_files[idx]
            f['is_selected_for_edit'] = not f.get('is_selected_for_edit', False)
            self._update_item_visual(idx)
            
            if f['is_selected_for_edit']:
                self.show_selection_animation()
            
            # v9.3.0: セレクショントレイの更新
            self.update_selection_tray()
            
            # プレビュー中ならプレビュー側も更新
            if self.app_mode == "select":
                self.update_col_preview(switch_to_preview=False)
            elif self._is_col_preview_mode:
                self.update_col_preview(switch_to_preview=False)

    def update_selection_tray(self):
        # v9.3.0: 選別トレイの動的更新
        if not hasattr(self, "select_tray_list"): return
        self.select_tray_list.controls.clear()
        selected_files = [f for f in self.source_files if f.get('is_selected_for_edit')]
        
        for f in selected_files:
            thumb = self._get_cached_thumbnail(f['path'])
            item = ft.Container(
                content=ft.Stack([
                    ft.Image(src=thumb, width=60, height=45, fit=ft.ImageFit.COVER, border_radius=4) if thumb else ft.Container(width=60, height=45, bgcolor="#333333", border_radius=4, content=ft.Icon(ft.Icons.IMAGE, size=16)),
                    ft.Container(ft.Icon(ft.Icons.STAR, color=COLOR_SELECT_MODE, size=10), top=1, right=1)
                ]),
                on_click=lambda e, path=f['path']: self._focus_by_path(path),
                tooltip=f['name']
            )
            self.select_tray_list.controls.append(item)
            
        self.btn_execute_select.disabled = (len(selected_files) == 0)
        self.btn_execute_select.text = f"選別を実行 ({len(selected_files)}件)"
        try:
            self.select_tray_list.update()
            self.btn_execute_select.update()
        except: pass

    def _focus_by_path(self, path):
        # v9.3.0: パス指定でフォーカスを移動
        for i, f in enumerate(self.source_files):
            if f['path'] == path:
                old_idx = self.focused_file_index
                self.focused_file_index = i
                if old_idx != -1: self._update_item_visual(old_idx)
                self._update_item_visual(i)
                self.update_col_preview(switch_to_preview=True)
                break

    def _start_select_copy(self, e=None):
        # v10.1.0: 現在のシーンフォルダ配下の選別フォルダにコピー。完了後ロック＆非表示。
        selected_files = [f for f in self.source_files if f.get('is_selected_for_edit') and not f.get('_select_locked')]
        if not selected_files:
            self.show_snack("選別されたファイルがありません", COLOR_ERROR)
            return

        scene_name = self._current_select_scene
        if not scene_name:
            self.show_snack("シーンフォルダが選択されていません", COLOR_ERROR)
            return

        dest_root = Path(self.cfg_mgr.data["paths"]["dest_root"])
        sub_folder_name = self.cfg_mgr.data["options"].get("sub_folder_name", "選別")
        target_dir = dest_root / scene_name / sub_folder_name

        self.btn_execute_select.disabled = True
        try: self.btn_execute_select.update()
        except: pass

        def run_copy():
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                copied_count = 0
                for f in selected_files:
                    src = Path(f['path'])
                    dst = target_dir / src.name
                    if not dst.exists():
                        shutil.copy2(src, dst)
                        self.log(f"コピー完了: {scene_name}/{sub_folder_name}/{dst.name}")
                    else:
                        self.log(f"スキップ（既存）: {dst.name}")
                    copied_count += 1

                self.show_snack(f"選別コピー完了（{copied_count}件）", COLOR_SUCCESS)
                # v10.6.0: コピー後はシーン全体を再スキャンして選別フォルダも含めて表示
                scene_dir = dest_root / scene_name
                self._is_scanning = True
                self._scanning_row.visible = True
                try: self.page.update()
                except: pass
                self.source_files.clear()
                self._scan_target_directory(scene_dir, recursive=True)
                self._is_scanning = False
                self._scanning_row.visible = False
                self.refresh_thumbnail_grid()
                self.update_selection_tray()
                self._select_title_text.value = scene_name
                self._select_count_text.value = f"{self._get_display_count()}個の項目"
                try:
                    self._select_title_text.update()
                    self._select_count_text.update()
                except: pass
                if self._select_library_tile and self._sidebar_item_func:
                    self._select_library_tile.controls = self._get_dynamic_library_items(self._sidebar_item_func)
                    try: self._select_library_tile.update()
                    except: pass
                try: self.page.update()
                except: pass
            except Exception as ex:
                self.show_snack(f"選別コピーエラー: {ex}", COLOR_ERROR)
                self._is_scanning = False
            finally:
                self.btn_execute_select.disabled = False
                try: self.btn_execute_select.update()
                except: pass

        threading.Thread(target=run_copy, daemon=True).start()

    def update_col_preview(self, switch_to_preview=True):
        # v8.0.21: カラム内プレビューの更新
        if 0 <= self.focused_file_index < len(self.source_files):
            f = self.source_files[self.focused_file_index]
            
            if self.app_mode == "select":
                # v9.5.0: 詳細メタデータの抽出と表示
                self._update_inspector_details(f)
                return

            if switch_to_preview:
                self._is_col_preview_mode = True
                self.col_preview_area.visible = True
                self.thumb_main_slot.visible = False
            
            self._stop_audio() # v8.0.22: 音声を停止

            # v1.1.19: 既存コンテンツをクリアせず直接書き換えることでチカつき（黒画面）を防止
            self.col_preview_content.content = self._build_preview_widget(f, is_fullscreen=False)
            self.btn_col_fullscreen.visible = True
            try: 
                self.col_preview_area.update()
            except: pass

    def _check_if_selected(self, f):
        """v9.5.0: すでに選別フォルダにコピー済みかチェック"""
        try:
            src = Path(f['path'])
            sub_name = self.cfg_mgr.data["options"].get("sub_folder_name", "選別")
            target = src.parent / sub_name / src.name
            return target.exists()
        except: return False

    def _update_inspector_details(self, f):
        """v9.5.0: インスペクターに詳細なメタデータを表示"""
        self.select_inspector_preview.content = self._build_preview_widget(f, is_fullscreen=False)
        
        # 基本情報
        path = Path(f['path'])
        stat = path.stat()
        
        def _fmt_size_precise(s):
            for u in ['B','KB','MB','GB','TB']:
                if s < 1000: return f"{s:.2f} {u}"
                s /= 1000 # 1000単位との指定
            return f"{s:.2f} PB"

        size_str = _fmt_size_precise(stat.st_size)
        m_time = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        c_time = datetime.datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M:%S")
        
        info_list = [
            ("ファイル名", f['name']),
            ("サイズ", size_str),
            ("カテゴリ", f['cat']),
            ("作成日", c_time),
            ("撮影日", f.get('date', '不明')),
            ("更新日", m_time),
        ]
        
        # 動画詳細情報 (ffprobe)
        if f['cat'] == 'Movie':
            try:
                res = subprocess.run([
                    "ffprobe", "-v", "error", "-select_streams", "v:0",
                    "-show_entries", "stream=width,height,codec_name,r_frame_rate",
                    "-of", "json", f['path']
                ], capture_output=True, text=True, timeout=2)
                if res.returncode == 0:
                    data = json.loads(res.stdout)
                    if 'streams' in data and data['streams']:
                        s = data['streams'][0]
                        info_list.append(("解像度", f"{s.get('width')} x {s.get('height')}"))
                        info_list.append(("コーデック", s.get('codec_name', '').upper()))
                        fps_raw = s.get('r_frame_rate', '0/0')
                        if '/' in fps_raw:
                            n, d = map(float, fps_raw.split('/'))
                            fps = f"{n/d:.2f}" if d != 0 else "0.00"
                            info_list.append(("フレームレート", f"{fps} fps"))
            except: pass
            
        if 'duration' in f:
            info_list.insert(2, ("再生時間", f['duration']))

        meta_rows = []
        for label, val in info_list:
            meta_rows.append(ft.Row([
                ft.Text(label, size=11, color=COLOR_TEXT_SEC, width=80),
                ft.Text(val, size=11, color=COLOR_TEXT_MAIN, weight="bold", expand=True, selectable=True)
            ], spacing=10))
        
        meta_rows.append(ft.Divider(color=COLOR_DIVIDER, height=10))
        sub_name = self.cfg_mgr.data["options"].get("sub_folder_name", "選別")
        is_already_copied = Path(f['path']).parent.name == sub_name
        
        status_color = COLOR_ACCENT_GREEN if is_already_copied else (COLOR_SELECT_MODE if f.get('is_selected_for_edit') else COLOR_TEXT_SEC)
        status_text = "選別済み" if is_already_copied else ("選別待ち" if f.get('is_selected_for_edit') else "未選別")
        status_icon = ft.Icons.LOCK if is_already_copied else (ft.Icons.STAR if f.get('is_selected_for_edit') else ft.Icons.STAR_BORDER)

        meta_rows.append(ft.Row([
            ft.Icon(status_icon, color=status_color, size=20),
            ft.Text(status_text, color=status_color, weight="bold", size=12)
        ], spacing=5))
        
        self.select_inspector_meta.controls = meta_rows
        try:
            self.select_inspector_preview.update()
            self.select_inspector_meta.update()
        except: pass

    def show_selection_animation(self):
        # v9.1.0: 選別時のアニメーション演出
        if not hasattr(self, "_selection_star"): return
        
        self._selection_star.opacity = 1.0
        self._selection_star.scale = 1.5
        try: self._selection_star.update()
        except: pass
        
        def reset_star():
            time.sleep(0.5)
            self._selection_star.opacity = 0.0
            self._selection_star.scale = 1.0
            try: self._selection_star.update()
            except: pass
            
        threading.Thread(target=reset_star, daemon=True).start()

    def hide_col_preview(self):
        # v8.0.21: リスト表示に戻る
        self._is_col_preview_mode = False
        self.col_preview_area.visible = False
        self.thumb_main_slot.visible = True
        self._stop_audio() # v8.0.22: 音声を停止
        self.video_ctrl_col = None
        try:
            self.col_preview_area.update()
            self.thumb_main_slot.update()
        except: pass

    def _stop_audio(self):
        # v8.0.22: 再生中の音声を確実に停止・破棄する
        if self.audio_ctrl:
            try:
                self.audio_ctrl.pause()
                self.page.overlay.remove(self.audio_ctrl)
            except: pass
            self.audio_ctrl = None
            try: self.page.update()
            except: pass

    def _build_preview_widget(self, f, is_fullscreen=True):
        # v8.0.20: プレビューウィジェット生成の共通化
        path = f['path']
        cat = f['cat']
        
        main_widget = None
        if cat == 'Photo' or cat == 'Raw':
            preview_path = self._get_or_generate_preview(f)
            if preview_path:
                main_widget = ft.Image(src=preview_path, fit=ft.ImageFit.CONTAIN, expand=True)
            else:
                main_widget = ft.Column([
                    ft.ProgressRing(color=COLOR_PRIMARY, width=20, height=20),
                    ft.Text("生成中...", color="white", size=10)
                ], alignment="center", horizontal_alignment="center")

        elif cat == 'Movie':
            try:
                v = ft.Video(
                    expand=True,
                    playlist=[ft.VideoMedia(path)],
                    autoplay=True, # v1.1.16: 自動再生を有効化
                    volume=100,
                    show_controls=True,
                )
                if is_fullscreen: self.video_ctrl = v
                else: self.video_ctrl_col = v
                
                main_widget = ft.GestureDetector(
                    content=v,
                    on_tap=lambda e: self._toggle_video_play(is_fullscreen),
                    expand=True,
                )
            except:
                main_widget = ft.Text("動画エラー", color="white", size=12)
        elif cat == 'Audio':
            # v8.0.22: 音声はOverlayで管理し確実に停止できるようにする
            self.audio_ctrl = ft.Audio(src=path, autoplay=True)
            self.page.overlay.append(self.audio_ctrl)
            try: self.page.update()
            except: pass
            main_widget = ft.Column([
                ft.Icon(ft.Icons.AUDIO_FILE, size=50, color=COLOR_PRIMARY),
                ft.Text("音声再生中...", color="white", size=12)
            ], alignment="center", horizontal_alignment="center")
        
        if not main_widget:
            main_widget = ft.Icon(ft.Icons.INSERT_DRIVE_FILE, size=50, color=COLOR_TEXT_SEC)

        # v9.1.0: 選別アニメーション用のレイヤーをスタックに追加
        star_overlay = ft.Icon(
            ft.Icons.STAR, color=COLOR_SELECT_MODE, size=120, 
            opacity=0, scale=1.0,
            animate_opacity=300, animate_scale=ft.Animation(300, ft.AnimationCurve.BOUNCE_OUT)
        )
        self._selection_star = star_overlay # 参照保持
        
        return ft.Stack([
            ft.Container(content=main_widget, alignment=ft.alignment.center, expand=True),
            ft.Container(content=star_overlay, alignment=ft.alignment.center, expand=True)
        ], expand=True)

    def _toggle_video_play(self, is_fullscreen=True):
        v = self.video_ctrl if is_fullscreen else self.video_ctrl_col
        if v:
            try: v.play_or_pause()
            except: pass

    def _seek_relative(self, ms_delta):
        if self.video_ctrl:
            try:
                curr = self.video_ctrl.get_position()
                self.video_ctrl.seek_to(max(0, curr + ms_delta))
            except: pass

    def _get_or_generate_preview(self, f):
        # v8.0.4: プレビュー用の1080p回転補正済み画像を生成
        file_path = f['path']
        preview_path = PREVIEW_CACHE_DIR / f"{hashlib.md5(file_path.encode()).hexdigest()}_p1080.jpg"
        if preview_path.exists(): return str(preview_path)
        
        try:
            with Image.open(file_path) as img:
                img = ImageOps.exif_transpose(img) # 回転補正
                img.thumbnail((1920, 1080)) # プレビューサイズ
                img.convert('RGB').save(str(preview_path), "JPEG", quality=80)
            return str(preview_path)
        except:
            # RAWなどでPILが失敗した場合は、既存のサムネイルをフォールバック
            return self._get_cached_thumbnail(file_path)

    def on_venue_change(self, e):
        self.cfg_mgr.data["current_location"] = self.dd_venue.value
        self.cfg_mgr.save()
        self.update_header() # ヘッダーの会場表示を更新
        self.update_preview()

    def select_unassigned(self, e):
        count = 0
        for i, f in enumerate(self.source_files):
            if f['assigned_scene'] is None:
                f['selected'] = True
                self._update_item_visual(i)
                count += 1
        self._update_counts()
        self.all_selected = all(f['selected'] for f in self.source_files) if self.source_files else False
        self.show_snack(f"未割当のファイル {count}件 を選択しました", COLOR_SUCCESS)
        try: self.page.update()
        except: pass

    def switch_view(self, view_name):
        self.current_view = view_name
        if view_name == "main":
            self._content_area.content = self._main_view_ctrl
        else:
            self.refresh_history_view()
            self._content_area.content = self._history_view_ctrl
        try: self.page.update()
        except: pass

    def refresh_project_list(self):
        opts = []
        if PROJECTS_DIR.exists():
            for f in PROJECTS_DIR.glob("*.json"):
                if f.name == "history.json": continue
                opts.append(ft.dropdown.Option(f.stem))
        self.dd_project.options = opts
        if self.cfg_mgr.project_name in [o.key for o in opts]:
            self.dd_project.value = self.cfg_mgr.project_name
        try: self.dd_project.update()
        except: pass

    def on_project_change(self, e):
        if self.dd_project.value and self.dd_project.value != self.cfg_mgr.project_name:
            self.cfg_mgr = ConfigManager(self.dd_project.value)
            self.load_config_to_ui()
            self.refresh_project_list()

    def on_source_change(self, e):
        if self.dd_drive.value and self.dd_drive.value != "ドライブを接続":
            self._confirm_scan_if_large(self.dd_drive.value)

    def _start_scan(self):
        if self.dd_drive.value and self.dd_drive.value != "ドライブを接続":
            self._confirm_scan_if_large(self.dd_drive.value)

    def _confirm_scan_if_large(self, drive_display):
        drive_path = self.drive_map.get(drive_display)
        if not drive_path: return
        
        try:
            usage = shutil.disk_usage(drive_path)
            total_gb = usage.total / (1024**3)
        except:
            total_gb = 0
            
        if total_gb >= 128:
            def on_confirm(ev):
                self._close_active_modal()
                self._start_scan_execution()
                
            def on_cancel(ev):
                self._close_active_modal()
                self.dd_drive.value = "ドライブを接続"
                self.source_files.clear()
                self.scene_assignments.clear()
                self.refresh_thumbnail_grid()
                self.update_preview()
                try: self.page.update()
                except: pass
                
            self._open_modal_dialog(
                "大容量ドライブの確認",
                ft.Column([
                    ft.Text(f"選択されたドライブは {total_gb:.1f}GB の大容量ドライブです。", weight="bold"),
                    ft.Text("意図しないドライブ（SSD等）を選択していないか確認してください。"),
                    ft.Text("このままスキャンを開始しますか？"),
                ], tight=True, spacing=10),
                [
                    ft.TextButton("はい", on_click=on_confirm, style=ft.ButtonStyle(color=COLOR_SUCCESS)),
                    ft.TextButton("いいえ", on_click=on_cancel, style=ft.ButtonStyle(color=COLOR_TEXT_SEC)),
                ]
            )
        else:
            self._start_scan_execution()

    def _start_scan_execution(self):
        self._scan_id += 1
        self._thumb_gen_id += 1
        self._cancel_scan = False
        scan_id = self._scan_id
        self.source_files.clear()
        self.scene_assignments.clear()
        self.range_selection_start_idx = None
        self.selected_scene_info = None
        self.radio_day.value = "0"
        self.refresh_scene_buttons()
        self._is_scanning = True
        self._scanning_row.visible = True
        self._clear_thumb_queue()
        self.lbl_file_count.value = "スキャン中..."
        self.lbl_assigned_count.value = "割当済: 0"
        self.refresh_thumbnail_grid()
        self.update_preview()
        try: self.page.update()
        except: pass
        threading.Thread(target=self._scan_worker, args=(scan_id,), daemon=True).start()

    def _start_archive_scan(self, scene_info):
        # v9.0.0: アーカイブから指定シーンのファイルを読込
        self._scan_id += 1
        self._thumb_gen_id += 1
        scan_id = self._scan_id
        self.source_files.clear()
        self.refresh_thumbnail_grid()
        
        dest_root = Path(self.cfg_mgr.data["paths"]["dest_root"])
        scene_folder_name = f"{scene_info['day']}{scene_info['num']:02d}_{scene_info['name']}" if self.cfg_mgr.data["options"].get("scene_numbering", True) else scene_info['name']
        scene_path = dest_root / scene_folder_name
        
        if not scene_path.exists():
            self.log(f"フォルダが見つかりません: {scene_folder_name}")
            self.update_preview()
            return

        self._is_scanning = True
        self._scanning_row.visible = True
        self.lbl_file_count.value = "アーカイブ読込中..."
        self.page.update()

        def archive_worker():
            batch = []
            excludes = self.cfg_mgr.data["exclusions"]
            cat_settings = self.cfg_mgr.data.get("category_settings", {})
            ext_to_cat = {}
            for cat, conf in cat_settings.items():
                for ext in conf["exts"]: ext_to_cat[ext.lower()] = cat

            # v9.3.7/v9.4.1: 選別済みファイルの検知 (複数のフォルダ名候補をチェック)
            sub_folder_name = self.cfg_mgr.data["options"].get("sub_folder_name", "選別")
            select_candidates = [sub_folder_name, "選別"]
            selected_names = set()
            
            # v9.4.1: 検知した全ての選別フォルダからファイル名を収集
            detected_select_dirs = []
            for cand in select_candidates:
                cand_dir = scene_path / cand
                if cand_dir.exists() and cand_dir.is_dir():
                    detected_select_dirs.append(cand_dir)
                    for f in cand_dir.iterdir():
                        if f.is_file() and not f.name.startswith("."):
                            selected_names.add(f.name)

            for root, dirs, filenames in os.walk(scene_path):
                if self._scan_id != scan_id: break
                
                # v9.3.7/v9.4.1: 選別フォルダ自体の中身はスキャンしない
                is_select_dir = False
                for d in detected_select_dirs:
                    if Path(root).resolve() == d.resolve() or str(Path(root).resolve()).startswith(str(d.resolve()) + os.sep):
                        is_select_dir = True
                        break
                if is_select_dir:
                    continue

                for name in sorted(filenames):
                    if name.startswith("."): continue
                    path = Path(root) / name
                    ext = path.suffix.lower()
                    if ext in ext_to_cat:
                        st = path.stat()
                        is_flagged = name in selected_names # v9.3.7: 選別済みなら自動チェック
                        batch.append({
                            "path": str(path), "name": name, "ext": ext, 
                            "cat": ext_to_cat[ext], "size": st.st_size, 
                            "mtime": st.st_mtime, "date": datetime.datetime.fromtimestamp(st.st_mtime).strftime("%Y/%m/%d %H:%M:%S"),
                            "selected": False, "assigned_scene": scene_folder_name,
                            "is_selected_for_edit": is_flagged
                        })
            
            if self._scan_id == scan_id:
                self.source_files.extend(batch)
                self.sort_files()
                self._finish_scan(scan_id)
                self.log(f"アーカイブから {len(self.source_files)} 件読み込みました。")

        threading.Thread(target=archive_worker, daemon=True).start()

    def _clear_thumb_queue(self):
        while not self._thumb_queue.empty():
            try:
                self._thumb_queue.get_nowait()
                self._thumb_queue.task_done()
            except: break

    def cancel_scan_action(self, e):
        self._cancel_scan = True
        self._is_scanning = False
        self._scanning_row.visible = False
        self._clear_thumb_queue()
        self.show_snack("スキャンを中止しました", COLOR_ACCENT)
        self.lbl_file_count.value = f"ファイル: {len(self.source_files)} (中止)"
        try: self.page.update()
        except: pass

    def _scan_worker(self, scan_id):
        drive_display = self.dd_drive.value
        if not drive_display or drive_display == "ドライブを接続":
            self._finish_scan(scan_id); return
        drive_path = self.drive_map.get(drive_display, "")
        if not drive_path or not os.path.exists(drive_path):
            self._finish_scan(scan_id); return

        excludes = self.cfg_mgr.data["exclusions"]
        cat_settings = self.cfg_mgr.data.get("category_settings", {})
        ext_to_cat = {}
        for cat, conf in cat_settings.items():
            if not conf.get("disabled", False):
                for ext in conf["exts"]: ext_to_cat[ext.lower()] = cat

        batch = []
        last_flush = time.time()

        for root, dirs, filenames in os.walk(drive_path):
            if self._scan_id != scan_id or self._cancel_scan: break
            dirs[:] = sorted([d for d in dirs if d not in excludes["folders"] and not d.startswith(".")])
            for name in sorted(filenames):
                if self._scan_id != scan_id or self._cancel_scan: break
                if name.startswith("."): continue
                time.sleep(0.01)
                path = Path(root) / name
                ext = path.suffix.lower()
                if ext in excludes["ext"]: continue
                if ext in ext_to_cat:
                    cat = ext_to_cat[ext]
                    try: 
                        st = path.stat()
                        size = st.st_size
                        mtime = st.st_mtime
                        date_str = datetime.datetime.fromtimestamp(mtime).strftime("%Y/%m/%d %H:%M:%S")
                    except: continue
                    batch.append({"path": str(path), "name": name, "ext": ext, "cat": cat, "size": size, "mtime": mtime, "date": date_str, "selected": False, "assigned_scene": None})
                    now = time.time()
                    if now - last_flush >= 1.5 and batch: # v8.0.8: UI更新間隔を少し広げて負荷軽減
                        added_batch = list(batch)
                        self.source_files.extend(added_batch)
                        batch.clear()
                        last_flush = now
                        if self._scan_id == scan_id:
                            self.lbl_file_count.value = f"ファイル: {len(self.source_files)} (スキャン中...)"
                            self._append_thumbnails_to_ui(added_batch)
                            # v8.0.8: UI更新直後に長めのスリープを入れ、ボタン入力を処理する隙間を作る
                            time.sleep(0.15)

        if self._scan_id == scan_id:
            if batch and not self._cancel_scan:
                added_batch = list(batch)
                self.source_files.extend(added_batch)
                self._append_thumbnails_to_ui(added_batch)
            self.sort_files() # v7.6.7: スキャン完了後に指定の順序でソート
            self._finish_scan(scan_id)

    def _finish_scan(self, scan_id):
        if self._scan_id != scan_id: return
        self._is_scanning = False
        self._scanning_row.visible = False
        status_suffix = " (中断)" if self._cancel_scan else ""
        self.lbl_file_count.value = f"ファイル: {len(self.source_files)}{status_suffix}"
        if self._cancel_scan:
            self._clear_thumb_queue()
        self.refresh_thumbnail_grid()
        self.update_selection_tray()
        self.update_preview()
        try: self.page.update()
        except: pass

    def _append_thumbnails_to_ui(self, new_files):
        if not new_files: return
        sz = int(self.thumb_size)
        img_w = int(sz * 0.85)
        img_h = int(sz * 0.6)
        start_idx = len(self.source_files) - len(new_files)
        grid_new_controls = []
        list_new_controls = []
        for i_offset, f in enumerate(new_files):
            # v10.6.2: セレクトモード時はモード独自のフィルタのみ、インジェストモード時は設定に従う
            if self.app_mode == "select":
                if not self.select_cat_filters.get(f['cat'], True): continue
            else:
                cat_conf = self.cfg_mgr.data["category_settings"].get(f['cat'], {})
                if cat_conf.get("disabled", False): continue
            
            i = start_idx + i_offset
            icon_data = CAT_ICONS.get(f['cat'], (ft.Icons.INSERT_DRIVE_FILE, COLOR_TEXT_SEC))
            tp = self._get_cached_thumbnail(f['path'])
            if tp:
                thumb_content = ft.Image(src=tp, width=img_w, height=img_h, fit=ft.ImageFit.COVER, border_radius=4)
            else:
                thumb_content = ft.Icon(icon_data[0], color=icon_data[1], size=max(24, sz // 3))
            thumb_img_container = ft.Container(content=thumb_content, width=img_w, height=img_h, alignment=ft.alignment.center)
            self._thumb_img_controls[i] = thumb_img_container
            
            # v9.0.0: star_btn
            star_btn_grid = ft.IconButton(
                icon=ft.Icons.STAR_BORDER, icon_color=COLOR_TEXT_SEC,
                icon_size=max(16, sz // 6), on_click=lambda e, idx=i: self.toggle_selection_flag(idx)
            )
            # v9.3.7: 再生時間バッジ (インジェスト時)
            dur_val = f.get('duration', '')
            dur_text_grid = ft.Text(dur_val, size=max(8, sz // 15), color="white", weight="bold")
            dur_badge_grid = ft.Container(
                content=dur_text_grid,
                bgcolor="#AA000000", padding=ft.padding.symmetric(horizontal=4, vertical=1),
                border_radius=3, bottom=2, right=2,
                visible=bool(dur_val)
            )
            thumb_img_container.content = ft.Stack([thumb_content, ft.Container(content=star_btn_grid, top=-5, right=-5), dur_badge_grid])

            inner_grid = ft.Container(
                content=ft.Column([
                    thumb_img_container,
                    ft.Text(f['name'], size=max(9, sz // 12), no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, color=COLOR_TEXT_MAIN, text_align="center"),
                ], horizontal_alignment="center", spacing=2, alignment="start"),
                bgcolor=COLOR_BG_SIDEBAR, border=ft.border.all(2, "transparent"), border_radius=6, padding=4,
                width=sz + 6, height=int(sz * 1.2),
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            )
            grid_card = ft.GestureDetector(
                content=inner_grid,
                on_tap=lambda e, idx=i: self.on_file_click(e, idx),
                on_secondary_tap=lambda e, idx=i: self.on_file_right_click(e, idx),
                on_double_tap=lambda e, p=f['path']: self.open_file_external(p),
                on_enter=lambda e, idx=i: self._on_drag_enter(idx),
            )
            grid_new_controls.append(grid_card)
            row_h = max(36, int(sz * 0.35))
            thumb_w = max(30, int(sz * 0.4))
            thumb_h = max(22, int(sz * 0.3))
            font_sz = max(10, int(sz * 0.1))
            sel_icon = ft.Icon(ft.Icons.RADIO_BUTTON_UNCHECKED, color=COLOR_TEXT_SEC, size=16)
            list_thumb_widget = ft.Icon(icon_data[0], color=icon_data[1], size=max(16, thumb_h // 2))
            if tp:
                list_thumb_widget = ft.Image(src=tp, width=thumb_w, height=thumb_h, fit=ft.ImageFit.COVER, border_radius=3)
            
            # v9.0.0: star_btn_list
            star_btn_list = ft.IconButton(
                icon=ft.Icons.STAR_BORDER, icon_color=COLOR_TEXT_SEC,
                icon_size=16, on_click=lambda e, idx=i: self.toggle_selection_flag(idx)
            )

            # v9.3.7: 再生時間テキスト (リスト用)
            dur_text_list = ft.Text(dur_val, size=8, color="white", weight="bold")
            dur_badge_list = ft.Container(
                content=dur_text_list,
                bgcolor="#88000000", bottom=1, right=1, padding=1, border_radius=2,
                visible=bool(dur_val)
            )
            list_thumb_stack = ft.Stack([
                list_thumb_widget,
                dur_badge_list
            ])

            inner_list = ft.Container(
                content=ft.Row([
                    sel_icon,
                    list_thumb_stack,
                    ft.Text(f['name'], size=font_sz, expand=True, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, color=COLOR_TEXT_MAIN),
                    ft.Text(f.get('date', ''), size=font_sz - 1, color=COLOR_TEXT_SEC, width=150, no_wrap=True),
                    ft.Text(f['cat'], size=font_sz - 1, color=icon_data[1], width=50, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS),
                    ft.Text("", size=font_sz - 1, color=COLOR_TEXT_SEC, width=70, text_align="right"), # Size placeholder
                    ft.Text("", size=font_sz - 1, color=COLOR_TEXT_SEC, width=90), # Scene placeholder
                    star_btn_list,
                ], spacing=5, vertical_alignment="center"),
                bgcolor=COLOR_BG_SIDEBAR, border_radius=4,
                border=ft.border.all(2, "transparent"),
                padding=ft.padding.symmetric(horizontal=5, vertical=2), height=row_h
            )
            list_row = ft.GestureDetector(
                content=inner_list,
                on_tap=lambda e, idx=i: self.on_file_click(e, idx),
                on_secondary_tap=lambda e, idx=i: self.on_file_right_click(e, idx),
                on_double_tap=lambda e, p=f['path']: self.open_file_external(p),
                on_enter=lambda e, idx=i: self._on_drag_enter(idx),
            )
            list_new_controls.append(list_row)
            if self.view_mode == "grid":
                self._thumb_controls[i] = (inner_grid, None, star_btn_grid, dur_badge_grid)
            else:
                self._thumb_controls[i] = (inner_list, sel_icon, star_btn_list, dur_badge_list)
        self.grid_thumbnails.controls.extend(grid_new_controls)
        self.list_thumbnails.controls.extend(list_new_controls)
        try:
            self.lbl_file_count.update()
            if self.view_mode == "grid":
                self.grid_thumbnails.update()
            else:
                self.list_thumbnails.update()
        except: pass
        for i_offset, f in enumerate(new_files):
            self._thumb_queue.put((self._thumb_gen_id, start_idx + i_offset, f))

    def _thumb_worker(self):
        while True:
            try:
                gen_id, idx, f = self._thumb_queue.get()
                if gen_id != self._thumb_gen_id or self._cancel_scan:
                    self._thumb_queue.task_done()
                    continue
                sz = int(self.thumb_size)
                is_select = (self.app_mode == "select")
                img_w = sz if is_select else int(sz * 0.85)
                img_h = int(sz * 9 / 16) if is_select else int(sz * 0.6)
                border_r = 0 if is_select else 4
                self.set_status(f"サムネイル生成中: {f['name']}", spinning=True)
                cached = self._generate_thumbnail(f)

                if cached and gen_id == self._thumb_gen_id and not self._cancel_scan:
                    if idx in self._thumb_img_controls and self.view_mode == "grid":
                        ctrl = self._thumb_img_controls[idx]
                        if is_select:
                            new_img = ft.Image(src=cached, width=img_w, height=img_h, fit=ft.ImageFit.COVER, border_radius=border_r)
                            if idx in self._thumb_controls:
                                _, sel_icon, star_btn, dur_badge = self._thumb_controls[idx]
                                ctrl.content = ft.Stack([new_img, dur_badge, sel_icon])
                            else:
                                ctrl.content = new_img
                        else:
                            # v1.1.12: インジェストモードは Stack そのもの
                            card_w = int(self.thumb_size) + 20
                            img_h_ingest = int(self.thumb_size * 0.72)
                            new_img = ft.Image(src=cached, width=card_w, height=img_h_ingest, fit=ft.ImageFit.COVER)
                            if idx in self._thumb_controls:
                                _, _sel, star_icon, dur_badge = self._thumb_controls[idx]
                                # ctrl は Stack — controls[0] を差し替え
                                if ctrl.controls:
                                    ctrl.controls[0] = new_img
                                else:
                                    ctrl.controls = [new_img]
                                # star_icon と dur_badge を再追加
                                assigned_items = [c for c in ctrl.controls[1:] if c is not star_icon and c is not dur_badge]
                                ctrl.controls = [new_img] + assigned_items + [star_icon, dur_badge]
                            else:
                                ctrl.controls = [new_img]
                        try: ctrl.update()
                        except: pass

                # サムネイル更新後にバッジも即時反映
                if gen_id == self._thumb_gen_id:
                    try: self._update_item_visual(idx)
                    except: pass

                self._thumb_queue.task_done()
                if self._thumb_queue.empty():
                    self.set_status("システム待機中", spinning=False)
                time.sleep(0.02)
            except Exception:
                time.sleep(0.5)

    def _get_cached_thumbnail(self, file_path):
        # v8.0.4: 回転補正済みであることを保証するため _v2 を付与して強制更新
        thumb_path = THUMB_CACHE_DIR / f"{hashlib.md5(file_path.encode()).hexdigest()}_v2.jpg"
        return str(thumb_path) if thumb_path.exists() else None

    def _bg_generate_thumbs(self, gen_id, files_snapshot):
        # v10.0.0: キャッシュ済みでも _generate_thumbnail を常に呼ぶ（duration取得のため）
        sz = int(self.thumb_size)
        is_select = (self.app_mode == "select")
        img_w = sz if is_select else int(sz * 0.85)
        img_h = int(sz * 9 / 16) if is_select else int(sz * 0.6)
        border_r = 0 if is_select else 4
        for idx, f in enumerate(files_snapshot):
            if self._thumb_gen_id != gen_id: return
            # v1.1.17: SDカード等へのI/O負荷を抑えるため、各ループに僅かな待機を入れる（スロットリング）
            time.sleep(0.05)
            # _generate_thumbnail はサムネイルキャッシュ済みでも duration を取得してから早期リターンする
            cached = self._generate_thumbnail(f)
            if cached and self._thumb_gen_id == gen_id:
                if idx in self._thumb_img_controls and self.view_mode == "grid":
                    ctrl = self._thumb_img_controls[idx]
                    new_img = ft.Image(src=cached, width=img_w, height=img_h, fit=ft.ImageFit.COVER, border_radius=border_r)
                    # dur_badge / sel_check の参照を保持してStackを再構築
                    if idx in self._thumb_controls:
                        _, sel_icon, star_btn, dur_badge = self._thumb_controls[idx]
                        if is_select:
                            ctrl.content = ft.Stack([new_img, dur_badge, sel_icon])
                        else:
                            ctrl.content = ft.Stack([
                                new_img,
                                ft.Container(content=star_btn, top=-5, right=-5),
                                dur_badge
                            ])
                    else:
                        ctrl.content = new_img
                    try: ctrl.update()
                    except: pass
            # duration バッジを即時更新（_generate_thumbnail でdurationが設定される）
            if self._thumb_gen_id == gen_id:
                try: self._update_item_visual(idx)
                except: pass

    def _generate_thumbnail(self, f):
        file_path = f['path']
        ext = f['ext']
        cat = f['cat']
        # v8.0.4: _v2 を付与
        thumb_path = THUMB_CACHE_DIR / f"{hashlib.md5(file_path.encode()).hexdigest()}_v2.jpg"
        
        # v10.6.0: 動画・音声の再生時間取得（永続キャッシュ優先）
        if cat in ['Movie', 'Audio'] and not f.get('duration'):
            global _duration_cache, _duration_cache_dirty
            with _duration_cache_lock:
                cached_dur = _duration_cache.get(file_path)
            if cached_dur:
                f['duration'] = cached_dur
            else:
                try:
                    res = subprocess.run([
                        "ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", file_path
                    ], capture_output=True, text=True, timeout=3)
                    if res.returncode == 0 and res.stdout.strip():
                        dur_sec = float(res.stdout.strip())
                        mins = int(dur_sec // 60)
                        secs = int(dur_sec % 60)
                        f['duration'] = f"{mins}:{secs:02d}"
                        with _duration_cache_lock:
                            _duration_cache[file_path] = f['duration']
                            _duration_cache_dirty = True
                        _schedule_duration_cache_save()  # デバウンス保存
                except: pass

        if thumb_path.exists(): return str(thumb_path)
        try:
            if cat == 'Photo' and ext in ['.jpg', '.jpeg', '.png', '.heic', '.heif', '.tiff']:
                with Image.open(file_path) as img:
                    img = ImageOps.exif_transpose(img) # v8.0.3: 回転情報を補正
                    img.thumbnail((120, 120))
                    img.convert('RGB').save(str(thumb_path), "JPEG", quality=65)
                return str(thumb_path)
            elif cat == 'Raw' and ext in ['.arw', '.cr2', '.cr3', '.nef', '.raf', '.orf', '.dng', '.rw2']:
                try:
                    with Image.open(file_path) as img:
                        img = ImageOps.exif_transpose(img) # v8.0.3: 回転情報を補正
                        img.thumbnail((120, 120))
                        img.convert('RGB').save(str(thumb_path), "JPEG", quality=65)
                    return str(thumb_path)
                except:
                    if platform.system() == "Darwin":
                        try:
                            subprocess.run(["sips", "-s", "format", "jpeg", "-z", "120", "120", file_path, "--out", str(thumb_path)], capture_output=True, timeout=10)
                            if thumb_path.exists(): return str(thumb_path)
                        except: pass
                return None
            elif cat == 'Movie' and ext in ['.mp4', '.mov', '.mxf', '.avi', '.mkv']:
                try:
                    subprocess.run([
                        "ffmpeg", "-y", "-i", file_path,
                        "-frames:v", "1", "-vf", "scale=160:-1",
                        "-q:v", "8", str(thumb_path)
                    ], capture_output=True, timeout=5)
                    if thumb_path.exists(): return str(thumb_path)
                except: pass
                if platform.system() == "Darwin":
                    try:
                        subprocess.run(["qlmanage", "-t", "-s", "160", "-o", str(THUMB_CACHE_DIR), file_path], capture_output=True, timeout=5)
                        candidates = list(THUMB_CACHE_DIR.glob(f"{Path(file_path).name}*"))
                        for c in candidates:
                            if c.suffix == '.png':
                                with Image.open(c) as img:
                                    img.convert('RGB').save(str(thumb_path), "JPEG", quality=65)
                                c.unlink()
                                return str(thumb_path)
                    except: pass
                return None
        except: pass
        return None

    def refresh_thumbnail_grid(self):
        if self.view_mode == "grid":
            self._refresh_grid_view()
        else:
            self._refresh_list_view()

    def _refresh_grid_view(self):
        self._thumb_gen_id += 1
        gen_id = self._thumb_gen_id
        self._thumb_controls = {}
        self._thumb_img_controls.clear()
        self.grid_thumbnails.controls.clear()
        sz = int(self.thumb_size)

        if self.app_mode == "select":
            # v10.6.0: セレクトモード — 未選別/選別済みを2グループ（ft.Wrapで折り返し）
            img_w = sz
            img_h = int(sz * 9 / 16)
            sub_folder = self.cfg_mgr.data["options"].get("sub_folder_name", "選別")

            def _is_sorted(f):
                return Path(f['path']).parent.name == sub_folder

            sorted_names = {f['name'] for f in self.source_files if _is_sorted(f)}

            def _make_select_card(i, f):
                icon_data = CAT_ICONS.get(f['cat'], (ft.Icons.INSERT_DRIVE_FILE, COLOR_TEXT_SEC))
                is_flagged = f.get('is_selected_for_edit', False)
                border_color, bg, border_w = self._get_item_style(f, i)
                tp = self._get_cached_thumbnail(f['path'])
                thumb_content = ft.Image(src=tp, width=img_w, height=img_h, fit=ft.ImageFit.COVER, border_radius=0) if tp \
                    else ft.Icon(icon_data[0], color=icon_data[1], size=max(24, sz // 3))
                dur_val = f.get('duration', '')
                dur_badge = ft.Container(
                    content=ft.Text(dur_val, size=max(8, sz // 15), color="white", weight="bold"),
                    bgcolor="#AA000000", padding=ft.padding.symmetric(horizontal=4, vertical=1),
                    border_radius=3, bottom=2, right=2, visible=bool(dur_val)
                )
                sel_check = ft.Container(
                    content=ft.Icon(ft.Icons.STAR, color="white", size=min(sz // 5, 18)),
                    bgcolor=COLOR_SELECT_MODE, border_radius=min(sz // 8, 14),
                    padding=ft.padding.all(3), top=4, right=4, visible=is_flagged
                )
                sel_badge = ft.Container(
                    content=ft.Icon(ft.Icons.CHECK_BOX, color="white", size=min(sz // 6, 16)),
                    bgcolor=COLOR_PRIMARY, border_radius=3, # v10.7.3: 四角いチェックマーク
                    padding=ft.padding.all(1), top=4, left=4, visible=f.get('selected', False)
                )
                thumb_img_container = ft.Container(
                    content=ft.Stack([thumb_content, dur_badge, sel_check, sel_badge]),
                    width=img_w, height=img_h, alignment=ft.alignment.center
                )
                self._thumb_img_controls[i] = thumb_img_container
                inner = ft.Container(
                    content=thumb_img_container,
                    bgcolor=bg, border=ft.border.all(border_w, border_color),
                    border_radius=4, clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                    width=img_w, height=img_h,
                )
                self._thumb_controls[i] = (inner, sel_badge, sel_check, dur_badge)
                return ft.GestureDetector(
                    content=inner,
                    on_tap=lambda e, idx=i: self.on_file_click(e, idx),
                    on_secondary_tap=lambda e, idx=i: self.on_file_right_click(e, idx),
                    on_double_tap=lambda e, p=f['path']: self.open_file_external(p),
                )

            unsorted_cards = []
            sorted_cards = []
            for i, f in enumerate(self.source_files):
                # v1.1.20: モード独立のフィルタを適用
                if not self._is_file_visible(f): continue
                card = _make_select_card(i, f)
                if _is_sorted(f):
                    sorted_cards.append(card)
                elif f['name'] not in sorted_names:
                    unsorted_cards.append(card)

            # v10.7.8: グリッド全体の幅を計算して中央寄せ（中身は左詰め）
            spacing = 5
            padding_w = 40  # content_main padding 20*2
            # サイドバー(260) + スプリッター(10) + インスペクタ(可変) + 分割線(1)
            available_w = self.page.width - self.sidebar_width - self.select_inspector_width - 11 - padding_w
            cols = max(1, int(available_w // (sz + spacing)))
            grid_w = cols * (sz + spacing) - spacing

            unsorted_wrap = ft.Row(controls=unsorted_cards, spacing=spacing, run_spacing=spacing, wrap=True, alignment=ft.MainAxisAlignment.START, width=grid_w)

            if sorted_cards:
                divider_row = ft.Container(
                    content=ft.Row([
                        ft.Icon(ft.Icons.STAR, color=COLOR_SELECT_MODE, size=14),
                        ft.Text("選別済み", size=12, color=COLOR_SELECT_MODE, weight="bold"),
                        ft.Container(
                            expand=True,
                            content=ft.Divider(height=1, color=COLOR_SELECT_MODE),
                        ),
                    ], vertical_alignment="center", spacing=8),
                    padding=ft.padding.only(top=16, bottom=8),
                    width=grid_w
                )
                sorted_wrap = ft.Row(controls=sorted_cards, spacing=spacing, run_spacing=spacing, wrap=True, alignment=ft.MainAxisAlignment.START, width=grid_w)
                scroll_col = ft.Column(
                    [unsorted_wrap, divider_row, sorted_wrap],
                    scroll=ft.ScrollMode.AUTO, spacing=0,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                )
            else:
                scroll_col = ft.Column(
                    [unsorted_wrap], scroll=ft.ScrollMode.AUTO, spacing=0,
                    horizontal_alignment=ft.CrossAxisAlignment.CENTER
                )

            self.thumb_container.content = scroll_col
            self._update_counts()
            try: self.page.update()
            except: pass
            files_snapshot = list(self.source_files)
            threading.Thread(target=self._bg_generate_thumbs, args=(gen_id, files_snapshot), daemon=True).start()
            return

        # ─── インジェストモード ───
        card_w = sz + 20
        img_h = int(sz * 0.72)
        self.grid_thumbnails.spacing = 12
        self.grid_thumbnails.run_spacing = 12
        self.grid_thumbnails.max_extent = card_w + 4
        self.grid_thumbnails.child_aspect_ratio = card_w / (img_h + 52)

        for i, f in enumerate(self.source_files):
            # v1.1.19: カテゴリフィルターおよび設定状態を尊重
            if not self._is_file_visible(f):
                continue

            icon_data = CAT_ICONS.get(f['cat'], (ft.Icons.INSERT_DRIVE_FILE, COLOR_TEXT_SEC))
            is_flagged = f.get('is_selected_for_edit', False)
            is_selected = f.get('selected', False)
            is_assigned = f['assigned_scene'] is not None
            border_color, bg, border_w = self._get_item_style(f, i)
            tp = self._get_cached_thumbnail(f['path'])

            # サムネイル画像またはアイコン
            if tp:
                thumb_content = ft.Image(src=tp, width=card_w, height=img_h, fit=ft.ImageFit.COVER)
            else:
                thumb_content = ft.Container(
                    content=ft.Icon(icon_data[0], color=icon_data[1], size=max(28, sz // 3)),
                    width=card_w, height=img_h, alignment=ft.alignment.center,
                    bgcolor="#1A1A1A",
                )

            # デュレーションバッジ（右下）
            dur_val = f.get('duration', '')
            dur_badge = ft.Container(
                content=ft.Text(dur_val, size=max(8, sz // 16), color="white", weight="bold"),
                bgcolor="#CC000000",
                padding=ft.padding.symmetric(horizontal=5, vertical=2),
                border_radius=3, bottom=4, right=4,
                visible=bool(dur_val)
            )

            # スターアイコン（右上）
            star_icon = ft.Container(
                content=ft.Icon(
                    ft.Icons.STAR if is_flagged else ft.Icons.STAR_BORDER,
                    color=COLOR_SELECT_MODE if is_flagged else ft.Colors.with_opacity(0.7, ft.Colors.WHITE),
                    size=max(14, sz // 8),
                ),
                top=4, right=4,
                on_click=lambda e, idx=i: self.toggle_selection_flag(idx),
            )

            # シーン割当オーバーレイ（左上）
            scene_overlay_items = []
            if is_assigned:
                parts = f['assigned_scene'].split('_', 2)
                sn = parts[2] if len(parts) > 2 else f['assigned_scene']
                scene_overlay_items.append(ft.Container(
                    content=ft.Text(sn, size=max(8, sz // 14), color="white", no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS),
                    bgcolor="#BB0050C8",
                    padding=ft.padding.symmetric(horizontal=5, vertical=2),
                    border_radius=3, top=4, left=4,
                    width=card_w - 40,
                ))

            thumb_stack = ft.Stack(
                [thumb_content, *scene_overlay_items, star_icon, dur_badge],
                width=card_w, height=img_h,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            )
            self._thumb_img_controls[i] = thumb_stack

            # ファイル名テキスト
            name_text = ft.Text(
                f['name'], size=max(9, sz // 13),
                no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS,
                color=COLOR_TEXT_MAIN, weight="w500",
            )

            # カテゴリ/コーデックサブテキスト（ProRes 4444 スタイル）
            cat_label = f.get('codec_label') or f['cat']
            sub_text = ft.Text(
                cat_label, size=max(8, sz // 16),
                color=COLOR_TEXT_SEC,
                no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS,
            )

            # 選択インジケータ（右下の小丸）
            sel_indicator = ft.Container(
                width=10, height=10, border_radius=5,
                bgcolor=COLOR_PRIMARY if is_selected else "#333333",
                border=ft.border.all(1, COLOR_PRIMARY if is_selected else "#555555"),
            )

            info_row = ft.Row([
                ft.Column([name_text, sub_text], spacing=1, expand=True),
                sel_indicator,
            ], vertical_alignment="center", spacing=6)

            inner = ft.Container(
                content=ft.Column([
                    thumb_stack,
                    ft.Container(
                        content=info_row,
                        padding=ft.padding.symmetric(horizontal=6, vertical=6),
                    ),
                ], spacing=0, alignment="start"),
                bgcolor="#181818",
                border=ft.border.all(2 if is_selected else 1, border_color),
                border_radius=8,
                width=card_w,
                clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            )
            self._thumb_controls[i] = (inner, sel_indicator, star_icon, dur_badge)
            card = ft.GestureDetector(
                content=inner,
                on_tap=lambda e, idx=i: self.on_file_click(e, idx),
                on_secondary_tap=lambda e, idx=i: self.on_file_right_click(e, idx),
                on_double_tap=lambda e, p=f['path']: self.open_file_external(p),
                on_enter=lambda e, idx=i: self._on_drag_enter(idx),
            )
            self.grid_thumbnails.controls.append(card)

        self.thumb_container.content = self.grid_thumbnails
        self._update_counts()
        try: self.page.update()
        except: pass
        files_snapshot = list(self.source_files)
        threading.Thread(target=self._bg_generate_thumbs, args=(gen_id, files_snapshot), daemon=True).start()

    def _refresh_list_view(self):
        self._thumb_controls = {}
        self.list_thumbnails.controls.clear()
        sz = int(self.thumb_size)
        row_h = max(36, int(sz * 0.35))
        thumb_w = max(30, int(sz * 0.4))
        thumb_h = max(22, int(sz * 0.3))
        # v8.0.13: フォントサイズはthumb_sizeに連動せず独立変数で管理
        font_sz = int(self.font_size)
        def _fmt_size(s):
            for u in ['B','KB','MB','GB']:
                if s < 1024: return f"{s:.1f}{u}"
                s /= 1024
            return f"{s:.1f}TB"
        # v10.6.0: セレクトモードで選別済みグループを区別して表示
        is_select = (self.app_mode == "select")
        sub_folder_lv = self.cfg_mgr.data["options"].get("sub_folder_name", "選別") if is_select else None
        sorted_names_lv = {f['name'] for f in self.source_files
                           if sub_folder_lv and Path(f['path']).parent.name == sub_folder_lv} if sub_folder_lv else set()

        def _iter_list(include_sorted):
            for i, f in enumerate(self.source_files):
                # v1.1.19: 常に可視性をチェック
                if not self._is_file_visible(f): continue
                in_sorted = sub_folder_lv and Path(f['path']).parent.name == sub_folder_lv
                if include_sorted:
                    if in_sorted: yield i, f
                else:
                    if not in_sorted and f['name'] not in sorted_names_lv: yield i, f

        sorted_divider_shown = False
        for pass_sorted in [False, True]:
            for i, f in _iter_list(pass_sorted):
                if pass_sorted and not sorted_divider_shown:
                    sorted_divider_shown = True
                    self.list_thumbnails.controls.append(ft.Container(
                        content=ft.Row([
                            ft.Icon(ft.Icons.STAR, color=COLOR_SELECT_MODE, size=14),
                            ft.Text("選別済み", size=12, color=COLOR_SELECT_MODE, weight="bold"),
                            ft.Container(expand=True, content=ft.Divider(height=1, color=COLOR_SELECT_MODE)),
                        ], vertical_alignment="center", spacing=8),
                        padding=ft.padding.only(top=12, bottom=6),
                    ))

                icon_data = CAT_ICONS.get(f['cat'], (ft.Icons.INSERT_DRIVE_FILE, COLOR_TEXT_SEC))
                is_sel = f['selected']
                is_flagged = f.get('is_selected_for_edit', False)
                is_assigned = f['assigned_scene'] is not None
                border_color, bg, border_w = self._get_item_style(f, i)
                thumb_widget = ft.Icon(icon_data[0], color=icon_data[1], size=max(16, thumb_h // 2))
                tp = self._get_cached_thumbnail(f['path'])
                if tp:
                    thumb_widget = ft.Image(src=tp, width=thumb_w, height=thumb_h, fit=ft.ImageFit.COVER, border_radius=3)
                scene_label = ""
                if is_assigned:
                    parts = f['assigned_scene'].split('_', 2)
                    scene_label = parts[2] if len(parts) > 2 else f['assigned_scene']
                sel_icon = ft.Icon(ft.Icons.CHECK_CIRCLE, color=COLOR_PRIMARY, size=16) if is_sel else ft.Icon(ft.Icons.RADIO_BUTTON_UNCHECKED, color=COLOR_TEXT_SEC, size=16)
                
                # v9.0.0: セレクトボタン
                star_btn = ft.IconButton(
                    icon=ft.Icons.STAR if is_flagged else ft.Icons.STAR_BORDER,
                    icon_color=COLOR_SELECT_MODE if is_flagged else COLOR_TEXT_SEC,
                    icon_size=16,
                    on_click=lambda e, idx=i: self.toggle_selection_flag(idx),
                    padding=0
                )

                # v9.3.7: 再生時間テキストを個別に管理
                dur_val = f.get('duration', '')
                dur_text_ctrl = ft.Text(dur_val, size=8, color="white", weight="bold")
                # v9.9.0: Container を変数に取り出して _thumb_controls に保存（visible 更新に対応）
                dur_badge_list = ft.Container(
                    content=dur_text_ctrl,
                    bgcolor="#88000000", bottom=1, right=1, padding=1, border_radius=2,
                    visible=bool(dur_val)
                )

                is_select_mode = (self.app_mode == "select")
                display_name = f['name']
                if is_select_mode and len(display_name) > 25:
                    display_name = display_name[:22] + ".."

                list_inner = ft.Container(
                    content=ft.Row([
                        sel_icon,
                        ft.Icon(icon_data[0], color=icon_data[1], size=14) if not is_select_mode else ft.Container(),
                        ft.Text(f['cat'], size=max(9, font_sz - 2), color=icon_data[1], width=50) if not is_select_mode else ft.Container(),
                        ft.Stack([thumb_widget, dur_badge_list]),
                        ft.Text(display_name, size=font_sz if not is_select_mode else font_sz - 1, expand=True, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, color=COLOR_TEXT_MAIN if not is_select_mode else COLOR_TEXT_SEC),
                        ft.Text(f.get('date', ''), size=max(9, font_sz - 1), color=COLOR_TEXT_SEC, width=150, no_wrap=True) if not is_select_mode else ft.Container(),
                        ft.Text(_fmt_size(f['size']), size=max(9, font_sz - 1), color=COLOR_TEXT_SEC, width=70, text_align="right", no_wrap=True) if not is_select_mode else ft.Container(),
                        ft.Text(scene_label, size=max(9, font_sz - 1), color=COLOR_SUCCESS if is_assigned else COLOR_TEXT_SEC, width=90, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS) if not is_select_mode else ft.Container(),
                        star_btn,
                    ], spacing=5, vertical_alignment="center"),
                    bgcolor=bg, border_radius=4,
                    border=ft.border.all(2, border_color),
                    padding=ft.padding.symmetric(horizontal=5, vertical=2), height=row_h
                )
                self._thumb_controls[i] = (list_inner, sel_icon, star_btn, dur_badge_list)
                row = ft.GestureDetector(
                    content=list_inner,
                    on_tap_down=lambda e, idx=i: self.on_file_click(e, idx), # v8.0.17: on_tap -> on_tap_down
                    on_secondary_tap_down=lambda e, idx=i: self.on_file_right_click(e, idx), # v8.0.17: secondaryもdownに変更
                    on_double_tap=lambda e, p=f['path']: self.open_file_external(p),
                    on_enter=lambda e, idx=i: self._on_drag_enter(idx),
                )
                self.list_thumbnails.controls.append(row)
        self.thumb_container.content = self.list_thumbnails
        self._update_counts()
        try: self.page.update()
        except: pass
        files_snapshot = list(self.source_files)
        threading.Thread(target=self._bg_generate_thumbs, args=(self._thumb_gen_id, files_snapshot), daemon=True).start()

    def toggle_selection_flag(self, idx):
        # v9.0.0: 選別（星）の状態をトグル
        if 0 <= idx < len(self.source_files):
            f = self.source_files[idx]
            f['is_selected_for_edit'] = not f.get('is_selected_for_edit', False)
            self._update_item_visual(idx)
            self.update_selection_tray() # v9.4.1: トレイを更新
            self.update_preview()
            
            # v9.1.0: プレビュー表示中ならアニメーションを実行
            if f['is_selected_for_edit'] and (self._is_col_preview_mode or self._preview_visible) and self.focused_file_index == idx:
                self.show_selection_animation()

            # 選別されたことがわかるようにスナックバー（任意）
            if f['is_selected_for_edit']:
                self.show_snack(f"「{f['name']}」を選別リストに追加しました", COLOR_SELECT_MODE)

    def toggle_bulk_select_mode(self, e):
        # v10.7.3: 一括選択モードの切り替え
        self.is_select_bulk_mode = not self.is_select_bulk_mode
        self.btn_bulk_select_mode.icon = ft.Icons.CHECK_BOX if self.is_select_bulk_mode else ft.Icons.CHECK_BOX_OUTLINE_BLANK
        self.btn_bulk_select_mode.icon_color = COLOR_PRIMARY if self.is_select_bulk_mode else COLOR_TEXT_SEC
        
        if self.is_select_bulk_mode:
            self.show_snack("一括選択モード: ON (クリックで選択/解除)", COLOR_PRIMARY)
        else:
            # モードOFF時は選択を解除
            for i, f in enumerate(self.source_files):
                if f.get('selected'):
                    f['selected'] = False
                    self._update_item_visual(i)
            self.show_snack("一括選択モード: OFF", COLOR_TEXT_SEC)
            
        try:
            self.btn_bulk_select_mode.update()
            self._update_counts()
        except: pass

    def _get_item_style(self, f, idx):
        # v10.7.9: 表示スタイルの計算を再定義（セレクトモードのフォーカス管理を厳格化）
        is_sel = f.get('selected', False)
        is_flagged = f.get('is_selected_for_edit', False)
        is_assigned = f.get('assigned_scene') is not None
        is_focused = (idx == self.focused_file_index)
        
        if self.app_mode == "select":
            # セレクトモード: チェック状態（is_sel）はアイコンのみで表現し、枠線は出さない
            if is_flagged:
                # 選別済み（星）: オレンジ枠 + 特殊背景
                return COLOR_SELECT_MODE, "#2D2610", 2
            elif is_focused:
                # フォーカス中: 青枠（1つだけ）
                return COLOR_PRIMARY, COLOR_BG_SIDEBAR, 2
            else:
                # その他: 透明枠
                return "transparent", COLOR_BG_SIDEBAR, 2
        else:
            # インジェストモード
            if is_flagged:
                return COLOR_SELECT_MODE, "#2D2610", 2
            elif is_assigned and is_sel:
                return "#FFD700", "#1a3a1a", 3
            elif is_assigned:
                return COLOR_SUCCESS, "#1a3a1a", 2
            elif is_sel:
                return COLOR_PRIMARY, COLOR_BG_CARD, 3
            elif is_focused:
                return COLOR_PRIMARY, "transparent", 3
            else:
                return "transparent", COLOR_BG_SIDEBAR, 2

    def _update_item_visual(self, idx):
        if idx not in self._thumb_controls or idx >= len(self.source_files): return
        container, sel_badge, sel_icon_or_star, dur_badge = self._thumb_controls[idx]
        f = self.source_files[idx]
        is_sel = f.get('selected', False)
        is_flagged = f.get('is_selected_for_edit', False)

        border_color, bg, border_w = self._get_item_style(f, idx)
        container.bgcolor = bg
        container.border = ft.border.all(border_w, border_color)

        # 一括選択バッジ (Googleフォト風チェック または インジェストの丸チョボ/アイコン)
        if sel_badge:
            if isinstance(sel_badge, ft.Container) and not getattr(sel_badge, "content", None):
                # インジェストモードの丸チョボ (Grid)
                sel_badge.bgcolor = COLOR_PRIMARY if is_sel else "#333333"
                sel_badge.border = ft.border.all(1, COLOR_PRIMARY if is_sel else "#555555")
            elif isinstance(sel_badge, ft.Icon):
                # リストビューの選択アイコン
                sel_badge.name = ft.Icons.CHECK_CIRCLE if is_sel else ft.Icons.RADIO_BUTTON_UNCHECKED
                sel_badge.color = COLOR_PRIMARY if is_sel else COLOR_TEXT_SEC
            else:
                sel_badge.visible = is_sel

        # 編集用選択 (星マークまたはモード切替アイコン)
        if sel_icon_or_star:
            if isinstance(sel_icon_or_star, ft.Container) and isinstance(getattr(sel_icon_or_star, 'content', None), ft.Icon):
                # インジェストモードv1.1.12: Container(Icon) スター
                sel_icon_or_star.content.name = ft.Icons.STAR if is_flagged else ft.Icons.STAR_BORDER
                sel_icon_or_star.content.color = COLOR_SELECT_MODE if is_flagged else ft.Colors.with_opacity(0.7, ft.Colors.WHITE)
            elif isinstance(sel_icon_or_star, ft.Container):
                # グリッドビューの sel_check (Container内の星)
                sel_icon_or_star.visible = is_flagged
            elif isinstance(sel_icon_or_star, ft.IconButton):
                # リストビューの star_btn
                sel_icon_or_star.icon = ft.Icons.STAR if is_flagged else ft.Icons.STAR_BORDER
            else:
                # インジェストモードのラジオボタン等
                sel_icon_or_star.name = ft.Icons.CHECK_BOX if is_sel else ft.Icons.CHECK_BOX_OUTLINE_BLANK
                sel_icon_or_star.color = COLOR_PRIMARY if is_sel else COLOR_TEXT_SEC

        # v9.8.0: dur_badge は常に Container — visible と内容を直接更新
        if dur_badge:
            dur_val = f.get('duration', '')
            if isinstance(dur_badge, ft.Container):
                if dur_badge.content: dur_badge.content.value = dur_val
                dur_badge.visible = bool(dur_val)
            else:
                dur_badge.value = dur_val

        try: container.update()
        except: pass

    def on_thumb_size_change(self, e):
        self.thumb_size = int(e.control.value)
        if self._slider_timer:
            self._slider_timer.cancel()
            self._slider_timer = None
        self._slider_timer = threading.Timer(0.25, self._do_thumb_resize)
        self._slider_timer.start()

    def _do_thumb_resize(self):
        self._slider_timer = None
        self.refresh_thumbnail_grid()

    def toggle_view_mode(self, e):
        self.view_mode = "list" if self.view_mode == "grid" else "grid"
        self.btn_view_toggle.icon = ft.Icons.GRID_VIEW if self.view_mode == "list" else ft.Icons.VIEW_LIST
        self.btn_view_toggle.tooltip = "グリッド表示" if self.view_mode == "list" else "リスト表示"
        self.refresh_thumbnail_grid()

    def open_file_external(self, path):
        try:
            if platform.system() == "Darwin": subprocess.Popen(["open", path])
            elif platform.system() == "Windows": os.startfile(path)
            else: subprocess.Popen(["xdg-open", path])
        except Exception as ex:
            self.show_snack(f"ファイルを開けませんでした: {ex}", COLOR_ERROR)

    def on_file_click(self, e, idx):
        old_focus = self.focused_file_index
        self.focused_file_index = idx
        self.last_selected_idx = idx
        self.range_selection_start_idx = idx

        # v10.7.3: 一括選択モード時はトグル、通常時は単一フォーカス
        if self.app_mode == "select":
            if self.is_select_bulk_mode:
                self.source_files[idx]['selected'] = not self.source_files[idx].get('selected', False)
            else:
                # 通常時は他を解除してこれだけ選択（または選択なしでも良いがわかりやすくするため単一選択）
                for i, f in enumerate(self.source_files):
                    if f.get('selected'):
                        f['selected'] = False
                        self._update_item_visual(i)
                self.source_files[idx]['selected'] = True
        else:
            # インジェストモード: v1.1.14: クリックで選択をトグル（追加選択・解除を可能にする）
            self.source_files[idx]['selected'] = not self.source_files[idx].get('selected', False)
        
        if old_focus != -1 and old_focus != idx:
            self._update_item_visual(old_focus)
        self._update_item_visual(idx)
        
        if old_focus != idx:
            self.update_col_preview(switch_to_preview=False)
        self._update_counts()

    def on_file_right_click(self, e, idx):
        # v10.7.1: 範囲選択（右クリック）
        if self.range_selection_start_idx is not None:
            # インスペクターの表示も右クリックしたファイルに合わせる
            self.focused_file_index = idx
            self.update_col_preview(switch_to_preview=False)
            
            start = min(self.range_selection_start_idx, idx)
            end = max(self.range_selection_start_idx, idx)
            for j in range(start, end + 1):
                if not self.source_files[j]['selected']:
                    self.source_files[j]['selected'] = True
                    self._update_item_visual(j)
            self.last_selected_idx = idx
            self._update_counts()
            self.show_snack(f"{end - start + 1}件のファイルを一括選択しました", COLOR_SUCCESS)

    def _on_drag_enter(self, idx):
        if self.is_dragging and 0 <= idx < len(self.source_files):
            if not self.source_files[idx]['selected']:
                self.source_files[idx]['selected'] = True
                self._update_item_visual(idx) # v8.0.16: 全体再描画を避けてラグを解消
                self._update_counts()

    def toggle_select_all(self, e):
        # v8.0.13: 後方互換のため残す（内部から呼ぶ場合用）
        self.all_selected = not self.all_selected
        for f in self.source_files: f['selected'] = self.all_selected
        for i in range(len(self.source_files)):
            self._update_item_visual(i)
        self._update_counts()
        try: self.page.update()
        except: pass

    def select_all_files(self, e):
        # v8.0.13: 全選択ボタン
        self.all_selected = True
        for f in self.source_files: f['selected'] = True
        for i in range(len(self.source_files)):
            self._update_item_visual(i)
        self._update_counts()
        try: self.page.update()
        except: pass

    def deselect_all_files(self, e):
        # v8.0.13: 全解除ボタン
        self.all_selected = False
        for f in self.source_files: f['selected'] = False
        for i in range(len(self.source_files)):
            self._update_item_visual(i)
        self._update_counts()
        try: self.page.update()
        except: pass

    def on_font_size_change(self, e):
        # v8.0.15: デバウンスを導入してUIフリーズを防止
        self.font_size = int(e.control.value)
        if self._slider_timer:
            self._slider_timer.cancel()
        self._slider_timer = threading.Timer(0.25, self._do_font_resize)
        self._slider_timer.start()

    def _do_font_resize(self):
        self._slider_timer = None
        if self.view_mode == "list":
            self.refresh_thumbnail_grid()

    def on_rename_seq_change(self, e):
        # v8.0.16: 先に設定を保存し、その後に必要ならダイアログを表示
        self.save_opts(e)
        if self.sw_rename_seq.value:
            def _dismiss(ev):
                self._close_active_modal()
            # Fletのダイアログ表示を確実にするため、明示的に再生成
            self._open_modal_dialog(
                "⚠ 連番リネームの注意",
                ft.Column([
                    ft.Text("連番リネームをオンにするとファイル名が重複する可能性があります。", weight="bold", color=COLOR_ERROR),
                    ft.Text("適切にカメラマン名、カードID等を設定してファイル名が重複しないようにしてください。", size=13, color=COLOR_TEXT_MAIN),
                ], tight=True, spacing=10),
                [ft.TextButton("了解", on_click=_dismiss, style=ft.ButtonStyle(color=COLOR_WARNING))],
            )



    def _update_counts(self):
        total = len(self.source_files)
        assigned = sum(1 for f in self.source_files if f['assigned_scene'] is not None)
        # v10.7.0: 移動ボタンの更新
        sel_count = sum(1 for f in self.source_files if f.get('selected'))
        self.btn_move_scene.disabled = (sel_count == 0)
        try:
            self.lbl_file_count.update()
            self.lbl_assigned_count.update()
            self.btn_move_scene.update()
        except: pass

    def assign_selected_to_scene(self, scene_info):
        key = self._scene_key(scene_info)
        if key not in self.scene_assignments: self.scene_assignments[key] = []
        count = 0
        for i, f in enumerate(self.source_files):
            if f['selected']:
                old_key = f['assigned_scene']
                if old_key and old_key != key and old_key in self.scene_assignments:
                    if i in self.scene_assignments[old_key]:
                        self.scene_assignments[old_key].remove(i)
                f['assigned_scene'] = key
                if i not in self.scene_assignments[key]:
                    self.scene_assignments[key].append(i)
                f['selected'] = False
                count += 1
        if count > 0:
            self.show_snack(f"{count}ファイルを「{scene_info['name']}」に割り当てました", COLOR_SUCCESS)
        else:
            self.show_snack("選択されたファイルがありません", COLOR_ACCENT)
        self.refresh_thumbnail_grid()
        self.refresh_scene_buttons()
        self.update_preview()

    def clear_assignments(self, e):
        for f in self.source_files: f['assigned_scene'] = None; f['selected'] = False
        self.scene_assignments.clear()
        self.all_selected = False
        self.refresh_thumbnail_grid()
        self.refresh_scene_buttons()
        self.update_preview()
        self.show_snack("全ての割り当てを解除しました")

    def on_day_change(self, e):
        self.selected_scene_info = None
        self.refresh_scene_buttons()

    def refresh_day_radio(self):
        self.row_days.controls.clear()
        self.row_days.controls.append(ft.Radio(value="0", label="その他"))
        for i in range(1, DAY_COUNT_FIXED + 1):
            self.row_days.controls.append(ft.Container(width=10))
            self.row_days.controls.append(ft.Radio(value=str(i), label=f"{i}日目"))
        try: self.page.update()
        except: pass

    def _get_scene_category_counts(self, scene_info):
        # v9.2.0: シーンフォルダ内のカテゴリ別ファイル数を取得
        dest_root = Path(self.cfg_mgr.data["paths"]["dest_root"])
        is_numbering = self.cfg_mgr.data["options"].get("scene_numbering", True)
        scene_folder_name = f"{scene_info['day']}{scene_info['num']:02d}_{scene_info['name']}" if is_numbering else scene_info['name']
        scene_path = dest_root / scene_folder_name
        
        counts = {"Photo": 0, "Movie": 0, "Audio": 0, "Raw": 0, "Other": 0}
        if not scene_path.exists(): return counts
        
        cat_settings = self.cfg_mgr.data.get("category_settings", {})
        ext_to_cat = {}
        for cat, conf in cat_settings.items():
            for ext in conf.get("exts", []):
                ext_to_cat[ext.lower()] = cat

        for root, dirs, filenames in os.walk(scene_path):
            for name in filenames:
                if name.startswith("."): continue
                ext = Path(name).suffix.lower()
                cat = ext_to_cat.get(ext, "Other")
                if cat in counts: counts[cat] += 1
                else: counts["Other"] += 1
        return counts

    def toggle_bulk_select_mode(self, e):
        # v10.7.3: 一括選択モードの切り替え
        self.is_select_bulk_mode = not self.is_select_bulk_mode
        self.btn_bulk_select_mode.icon = ft.Icons.CHECK_BOX if self.is_select_bulk_mode else ft.Icons.CHECK_BOX_OUTLINE_BLANK
        self.btn_bulk_select_mode.icon_color = COLOR_PRIMARY if self.is_select_bulk_mode else COLOR_TEXT_SEC
        
        if self.is_select_bulk_mode:
            self.show_snack("一括選択モード: ON (クリックで選択/解除)", COLOR_PRIMARY)
        else:
            # モードOFF時は選択を解除
            for i, f in enumerate(self.source_files):
                if f.get('selected'):
                    f['selected'] = False
                    self._update_item_visual(i)
            self.show_snack("一括選択モード: OFF", COLOR_TEXT_SEC)
            
        try:
            self.btn_bulk_select_mode.update()
            self._update_counts()
        except: pass

    def refresh_scene_buttons(self):
        target_day = int(self.radio_day.value)
        scenes = sorted([s for s in self.cfg_mgr.data["scenes"] if s["day"] == target_day], key=lambda x: x["num"])
        is_numbering = self.cfg_mgr.data["options"].get("scene_numbering", True)

        if self.is_scene_editing:
            self.lv_scenes_edit.controls.clear()
            for i, s in enumerate(scenes):
                key = self._scene_key(s)
                count = len(self.scene_assignments.get(key, []))
                
                row_items = [
                    ft.Icon(ft.Icons.DRAG_HANDLE, color=COLOR_TEXT_SEC, size=20),
                    ft.Text(f"{s['day']}{s['num']:02d} {s['name']}" if is_numbering else s['name'], size=13, expand=True, color=COLOR_TEXT_MAIN),
                ]
                
                if self.app_mode == "select":
                    cat_counts = self._get_scene_category_counts(s)
                    for cat in ["Photo", "Movie", "Audio", "Raw"]:
                        c = cat_counts[cat]
                        if c > 0:
                            icon_data = CAT_ICONS.get(cat)
                            row_items.append(
                                ft.Row([
                                    ft.Icon(icon_data[0], color=icon_data[1], size=12),
                                    ft.Text(str(c), size=10, color=icon_data[1], weight="bold")
                                ], spacing=2)
                            )
                else:
                    row_items.append(ft.Container(content=ft.Text(f"{count}件", size=11, color="white", weight="bold"), bgcolor=COLOR_BADGE, border_radius=10, padding=ft.padding.symmetric(horizontal=8, vertical=2), visible=(count>0)))
                
                row_items.extend([
                    ft.IconButton(ft.Icons.EDIT, icon_size=16, icon_color=COLOR_PRIMARY, on_click=lambda e, d=s['day'], n=s['num'], nm=s['name']: self.rename_scene(d, n, nm), tooltip="名前変更"),
                    ft.IconButton(ft.Icons.DELETE, icon_size=16, icon_color=COLOR_ERROR, on_click=lambda e, d=s['day'], n=s['num']: self.delete_scene(d, n), tooltip="削除"),
                ])

                drag_content = ft.Container(
                    content=ft.Row(row_items),
                    bgcolor="#2C2C2E", border_radius=8, padding=10
                )
                drag_item = ft.Draggable(group="scenes", content=drag_content, data=str(i))
                drag_target = ft.DragTarget(group="scenes", content=drag_item, on_accept=lambda e, tgt=i: self._on_scene_drag_drop(e.src_id, tgt))
                self.lv_scenes_edit.controls.append(drag_target)
            self.scene_content_area.content = self.lv_scenes_edit
        else:
            self.grid_scenes.controls.clear()
            for s in scenes:
                is_sel = (self.selected_scene_info and self.selected_scene_info["day"] == s["day"] and self.selected_scene_info["num"] == s["num"])
                key = self._scene_key(s)
                count = len(self.scene_assignments.get(key, []))
                main_col = ft.Column(spacing=2, alignment="center", horizontal_alignment="center")
                if is_numbering:
                    main_col.controls.append(ft.Text(f"{s['day']}{s['num']:02d}", weight="bold", size=13, color="white" if is_sel else COLOR_TEXT_MAIN))
                main_col.controls.append(ft.Text(s['name'], size=11, no_wrap=True, overflow=ft.TextOverflow.ELLIPSIS, color="white" if is_sel else "#DDDDDD", weight="w500", max_lines=1))
                
                if self.app_mode == "select":
                    cat_counts = self._get_scene_category_counts(s)
                    badge_row = ft.Row(spacing=4, vertical_alignment="center", alignment="center")
                    for cat in ["Photo", "Movie", "Audio", "Raw"]:
                        c = cat_counts[cat]
                        if c > 0:
                            icon_data = CAT_ICONS.get(cat)
                            badge_row.controls.append(
                                ft.Row([
                                    ft.Icon(icon_data[0], color=icon_data[1], size=10),
                                    ft.Text(str(c), size=9, color=icon_data[1], weight="bold")
                                ], spacing=1)
                            )
                    if badge_row.controls:
                        main_col.controls.append(badge_row)
                
                stack_items = [ft.Container(content=main_col, alignment=ft.alignment.center)]
                if count > 0 and self.app_mode != "select":
                    badge = ft.Container(
                        content=ft.Text(f"{count}件", size=9, color="white", weight="bold"),
                        bgcolor=COLOR_BADGE, border_radius=8,
                        padding=ft.padding.symmetric(horizontal=5, vertical=1),
                        right=0, top=0
                    )
                    stack_items.append(badge)

                scene_btn = ft.Container(
                    content=ft.Stack(stack_items),
                    bgcolor=COLOR_PRIMARY if is_sel else "#252525",
                    border_radius=8,
                    on_click=lambda e, sc=s: self.on_scene_click(sc),
                    ink=True,
                    padding=8,
                )
                self.grid_scenes.controls.append(scene_btn)
            self.scene_content_area.content = self.grid_scenes

        # v9.3.0: セレクトモード専用カルーセルの更新
        if self.app_mode == "select" and hasattr(self, "select_scene_carousel"):
            self.select_scene_carousel.controls.clear()
            for s in scenes:
                is_sel = (self.selected_scene_info and self.selected_scene_info["day"] == s["day"] and self.selected_scene_info["num"] == s["num"])
                cat_counts = self._get_scene_category_counts(s)
                total = sum(cat_counts.values())
                btn = ft.Container(
                    content=ft.Column([
                        ft.Text(f"{s['day']}{s['num']:02d}" if is_numbering else "", size=9, weight="bold", color=COLOR_TEXT_SEC),
                        ft.Text(s['name'], size=12, weight="bold", no_wrap=True, color="black" if is_sel else "white"),
                        ft.Text(f"{total} files", size=10, color="black" if is_sel else COLOR_TEXT_SEC)
                    ], spacing=1, alignment="center"),
                    padding=ft.padding.symmetric(horizontal=15, vertical=8),
                    bgcolor=COLOR_PRIMARY if is_sel else "#2C2C2E",
                    border_radius=8,
                    border=ft.border.all(1, COLOR_PRIMARY if is_sel else COLOR_DIVIDER),
                    on_click=lambda e, sc=s: self.on_scene_click(sc),
                    ink=True,
                    width=120
                )
                self.select_scene_carousel.controls.append(btn)
            try: self.select_scene_carousel.update()
            except: pass

        try: self.scene_content_area.update()
        except: pass

    def _on_scene_drag_drop(self, src_id, target_idx):
        src_data = self.page.get_control(src_id).data
        if src_data is None: return
        src_idx = int(src_data)
        if src_idx == target_idx: return
        target_day = int(self.radio_day.value)
        day_scenes = sorted([s for s in self.cfg_mgr.data["scenes"] if s["day"] == target_day], key=lambda x: x["num"])
        item = day_scenes.pop(src_idx)
        day_scenes.insert(target_idx, item)
        for i, s in enumerate(day_scenes):
            old_key = self._scene_key(s)
            s['num'] = i + 1
            new_key = self._scene_key(s)
            if old_key != new_key and old_key in self.scene_assignments:
                self.scene_assignments[new_key] = self.scene_assignments.pop(old_key)
                for fi in self.scene_assignments[new_key]:
                    if fi < len(self.source_files):
                        self.source_files[fi]['assigned_scene'] = new_key
        self.cfg_mgr.save()
        self.refresh_scene_buttons()
        self.refresh_thumbnail_grid()

    def on_scene_click(self, scene_info):
        # v8.0.24: プレビュー表示中は、表示中のファイルも選択状態に含めて即時割り当て可能にする
        if (self._is_col_preview_mode or self._preview_visible) and self.focused_file_index != -1:
            idx = self.focused_file_index
            if not self.source_files[idx]['selected']:
                self.source_files[idx]['selected'] = True
                self._update_item_visual(idx)

        if self.app_mode == "select":
            # v9.0.0: セレクトモード時はアーカイブからファイルを読込
            self.selected_scene_info = scene_info
            self.refresh_scene_buttons()
            self._start_archive_scan(scene_info)
            return

        selected_count = sum(1 for f in self.source_files if f['selected'])
        if selected_count > 0:
            self.assign_selected_to_scene(scene_info)
        else:
            # v8.0.12: 即時フィードバックのためハイライトを先に更新
            self.selected_scene_info = scene_info
            self.refresh_scene_buttons()
            self.update_preview()

    def select_scene(self, info):
        self.selected_scene_info = info
        self.refresh_scene_buttons()
        self.update_preview()

    def add_scene_manual(self, e):
        tf = ft.TextField(label="シーン名", autofocus=True)
        def save_sc(ev):
            val = self.sanitize_text(tf.value)
            if val:
                self.cfg_mgr.add_scene(int(self.radio_day.value), self.cfg_mgr.get_next_scene_num(int(self.radio_day.value)), val)
                self._close_active_modal()
                self.refresh_scene_buttons()
        self._open_modal_dialog(
            "シーン追加",
            tf,
            [
                ft.TextButton("追加", on_click=save_sc),
                ft.TextButton("キャンセル", on_click=self._close_active_modal),
            ],
        )

    def rename_scene(self, day, num, current_name):
        tf = ft.TextField(label="新しいシーン名", value=current_name, autofocus=True)
        def save_rename(ev):
            new_name = self.sanitize_text(tf.value)
            if new_name:
                old_key = f"{day}_{num}_{current_name}"
                new_key = f"{day}_{num}_{new_name}"
                if old_key in self.scene_assignments:
                    idxs = self.scene_assignments.pop(old_key)
                    self.scene_assignments[new_key] = idxs
                    for fi in idxs:
                        if fi < len(self.source_files):
                            self.source_files[fi]['assigned_scene'] = new_key
                for s in self.cfg_mgr.data["scenes"]:
                    if s["day"] == day and s["num"] == num:
                        s["name"] = new_name; break
                self.cfg_mgr.save()
                self._close_active_modal()
                self.refresh_scene_buttons()
                self.refresh_thumbnail_grid()
        self._open_modal_dialog(
            "シーン名変更",
            tf,
            [
                ft.TextButton("変更", on_click=save_rename),
                ft.TextButton("キャンセル", on_click=self._close_active_modal),
            ],
        )

    def toggle_scene_edit_mode(self, e):
        self.is_scene_editing = not self.is_scene_editing
        self.btn_scene_edit.icon_color = COLOR_PRIMARY if self.is_scene_editing else COLOR_TEXT_SEC
        self.refresh_scene_buttons()

    def delete_scene(self, day, num):
        def confirm(ev):
            self.cfg_mgr.remove_scene(day, num)
            self._close_active_modal()
            self.refresh_scene_buttons()
        self._open_modal_dialog(
            "削除確認",
            ft.Text(f"Day{day}-{num} を削除しますか？", color=COLOR_TEXT_MAIN),
            [
                ft.TextButton("削除", on_click=confirm, style=ft.ButtonStyle(color=COLOR_ERROR)),
                ft.TextButton("キャンセル", on_click=self._close_active_modal),
            ],
        )

    def show_identity_modal(self, e):
        # v1.1.11: キャンセル時に戻せるようバックアップをとる
        old_pg = self.current_photographer
        old_cid = self.current_card_id

        # v8.0.16: 開いた時に一旦選択をクリアし、再選択を促す
        self.current_photographer = None
        self.current_card_id = None
        self._update_identity_button() # UI上の表示も一旦リセット
        
        # v8.0.12: ウィンドウ高さに応じてモーダルサイズを制限し、スクロール可能にする
        # v8.0.15: window_height -> height (Flet 0.27.x対応)
        modal_height = min(600, (self.page.height or 800) * 0.7)
        list_area_height = (modal_height - 180) # ラベルやボタンを除いた高さ
        
        pg_list_area = ft.GridView(runs_count=2, child_aspect_ratio=2.2, spacing=10, run_spacing=10, expand=True)
        cid_list_area = ft.GridView(runs_count=1, child_aspect_ratio=4.5, spacing=10, run_spacing=10, expand=True)

        def select_pg(name):
            self.current_photographer = name
            refresh_pg_list()
            check_auto_close()

        def select_cid(cid):
            self.current_card_id = cid
            refresh_cid_list()
            check_auto_close()

        def check_auto_close():
            if self.current_photographer and self.current_card_id:
                self._close_active_modal()
                self._update_identity_button()
                self.update_preview()

        def refresh_pg_list():
            pgs = self.cfg_mgr.data.get("photographers", [])
            pg_names = [p if isinstance(p, str) else p.get('name', '') for p in pgs]
            pg_list_area.controls.clear()
            for name in pg_names:
                is_sel = (name == self.current_photographer)
                pg_list_area.controls.append(ft.Container(
                    content=ft.Text(name, size=14, weight="bold" if is_sel else "normal", color=COLOR_TEXT_MAIN if is_sel else COLOR_TEXT_SEC, text_align="center"),
                    alignment=ft.alignment.center,
                    bgcolor=COLOR_PRIMARY if is_sel else "#2C2C2E",
                    border_radius=8,
                    padding=ft.padding.symmetric(vertical=8),
                    border=ft.border.all(2 if is_sel else 1, ft.Colors.WHITE if is_sel else COLOR_DIVIDER),
                    on_click=lambda e, n=name: select_pg(n),
                    ink=True
                ))
            try: pg_list_area.update()
            except: pass

        def refresh_cid_list():
            cids = self.cfg_mgr.data.get("card_ids", [f"{i:02d}" for i in range(1, 11)])
            cid_list_area.controls.clear()
            for cid in cids:
                is_sel = (cid == self.current_card_id)
                cid_list_area.controls.append(ft.Container(
                    content=ft.Text(cid, size=14, weight="bold" if is_sel else "normal", color=COLOR_TEXT_MAIN if is_sel else COLOR_TEXT_SEC, text_align="center"),
                    alignment=ft.alignment.center,
                    bgcolor=COLOR_ACCENT if is_sel else "#2C2C2E",
                    border_radius=8,
                    padding=ft.padding.symmetric(vertical=8),
                    border=ft.border.all(2 if is_sel else 1, ft.Colors.WHITE if is_sel else COLOR_DIVIDER),
                    on_click=lambda e, c=cid: select_cid(c),
                    ink=True
                ))
            try: cid_list_area.update()
            except: pass

        def add_pg(e):
            self._close_active_modal()
            self._identity_modal_back_flag = True # フラグ設定
            self.open_settings_modal(None)
            self._open_list_editor("photographers", callback=refresh_pg_list)

        def add_cid(e):
            self._close_active_modal()
            self._identity_modal_back_flag = True # フラグ設定
            self.open_settings_modal(None)
            self._open_list_editor("card_ids", callback=refresh_cid_list)

        refresh_pg_list()
        refresh_cid_list()

        pg_column = ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.PERSON, size=18, color=COLOR_TEXT_MAIN),
                ft.Text("カメラマン", weight="bold", color=COLOR_TEXT_MAIN, size=15),
                ft.IconButton(ft.Icons.ADD_CIRCLE_OUTLINE, icon_color=COLOR_SUCCESS, icon_size=20, tooltip="追加/編集", on_click=add_pg)
            ], spacing=5, vertical_alignment="center"),
            ft.Container(content=pg_list_area, padding=8, bgcolor=COLOR_BG_SIDEBAR, border_radius=8, height=list_area_height)
        ], spacing=5, alignment=ft.MainAxisAlignment.START, col={"xs": 12, "sm": 7})

        cid_column = ft.Column([
            ft.Row([
                ft.Icon(ft.Icons.CREDIT_CARD, size=18, color=COLOR_TEXT_MAIN),
                ft.Text("カードID", weight="bold", color=COLOR_TEXT_MAIN, size=15),
                ft.IconButton(ft.Icons.ADD_CIRCLE_OUTLINE, icon_color=COLOR_SUCCESS, icon_size=20, tooltip="追加/編集", on_click=add_cid)
            ], spacing=5, vertical_alignment="center"),
            ft.Container(content=cid_list_area, padding=8, bgcolor=COLOR_BG_SIDEBAR, border_radius=8, height=list_area_height)
        ], spacing=5, alignment=ft.MainAxisAlignment.START, col={"xs": 12, "sm": 5})

        content = ft.ResponsiveRow(
            [pg_column, cid_column],
            spacing=20,
            run_spacing=10,
            alignment=ft.MainAxisAlignment.CENTER,
            vertical_alignment=ft.CrossAxisAlignment.START,
        )

        def cancel_identity(e):
            self.current_photographer = old_pg
            self.current_card_id = old_cid
            self._update_identity_button()
            self._close_active_modal()

        self._open_modal_dialog(
            "撮影者 / カードの選択",
            ft.Container(content=content, padding=10, width=650, height=modal_height),
            [ft.TextButton("キャンセル", on_click=cancel_identity)],
        )

    def _update_identity_button(self):
        pg = self.current_photographer or "撮影者未設定"
        cid = self.current_card_id or "---"
        self._identity_pg_text.value = pg
        self._identity_cid_text.value = cid
        
        # v8.0.16: スタイル更新方法をButtonStyle再生成に統一 (エラー防止)
        has_both = bool(self.current_photographer and self.current_card_id)
        border_side = ft.BorderSide(2, COLOR_SUCCESS) if has_both else ft.BorderSide(1, "transparent")
        self.btn_select_identity.style = ft.ButtonStyle(
            bgcolor=COLOR_BG_CARD,
            color=COLOR_TEXT_MAIN,
            shape=ft.RoundedRectangleBorder(radius=8),
            side={"": border_side},
            padding=ft.padding.symmetric(horizontal=10, vertical=8),
            elevation=0,
        )
        try: self.btn_select_identity.update()
        except: pass

    # v7.5.2: カテゴリ設定モーダルを単独で開く機能
    def show_category_config_modal(self, e):
        cat_rows = []
        for cat, conf in self.cfg_mgr.data["category_settings"].items():
            icon_data = CAT_ICONS.get(cat)
            sw_cat = ft.Switch(
                value=not conf["disabled"], 
                active_color=icon_data[1], 
                on_change=lambda e, c=cat: self._on_cat_change(e, c, "disabled")
            )
            cat_rows.append(ft.Container(
                content=ft.Row([
                    ft.Icon(icon_data[0], color=icon_data[1]),
                    ft.Text(cat, weight="bold", expand=True),
                    sw_cat
                ], alignment="spaceBetween"),
                padding=10,
                bgcolor=COLOR_BG_SIDEBAR,
                border_radius=8
            ))
        
        self._open_modal_dialog(
            "インポート設定",
            ft.Column(cat_rows, tight=True, spacing=10, width=300),
            [ft.TextButton("閉じる", on_click=self._close_active_modal)]
        )

    def _clear_thumb_cache(self, e=None):
        def do_clear():
            try:
                files = list(THUMB_CACHE_DIR.glob("*.jpg")) + list(THUMB_CACHE_DIR.glob("*.png"))
                count = len(files)
                for f in files:
                    try: f.unlink()
                    except: pass
                self.show_snack(f"サムネイルキャッシュを削除しました（{count}件）", COLOR_SUCCESS)
                self.refresh_thumbnail_grid()
            except Exception as ex:
                self.show_snack(f"キャッシュ削除エラー: {ex}", COLOR_ERROR)
        self._show_confirm_dialog(
            "サムネイルキャッシュをクリア",
            f"サムネイルキャッシュ（{THUMB_CACHE_DIR}）を全て削除します。\n次回表示時に再生成されます。",
            do_clear
        )

    def _clear_preview_cache(self, e=None):
        def do_clear():
            try:
                files = list(PREVIEW_CACHE_DIR.glob("*"))
                count = len(files)
                for f in files:
                    try: f.unlink()
                    except: pass
                self.show_snack(f"プレビューキャッシュを削除しました（{count}件）", COLOR_SUCCESS)
            except Exception as ex:
                self.show_snack(f"キャッシュ削除エラー: {ex}", COLOR_ERROR)
        self._show_confirm_dialog(
            "プレビューキャッシュをクリア",
            f"プレビューキャッシュ（{PREVIEW_CACHE_DIR}）を全て削除します。",
            do_clear
        )

    def _clear_all_cache(self, e=None):
        def do_clear():
            total = 0
            for cache_dir in [THUMB_CACHE_DIR, PREVIEW_CACHE_DIR]:
                for f in cache_dir.glob("*"):
                    try: f.unlink(); total += 1
                    except: pass
            self.show_snack(f"全キャッシュを削除しました（{total}件）", COLOR_SUCCESS)
            self.refresh_thumbnail_grid()
        self._show_confirm_dialog(
            "全キャッシュをクリア",
            "サムネイル・プレビューの全キャッシュを削除します。\n次回表示時に再生成されます。",
            do_clear
        )

    def _show_confirm_dialog(self, title, message, on_confirm):
        def on_yes(e):
            self.page.close(dlg)
            threading.Thread(target=on_confirm, daemon=True).start()
        def on_no(e):
            self.page.close(dlg)
        dlg = ft.AlertDialog(
            title=ft.Text(title),
            content=ft.Text(message),
            actions=[
                ft.TextButton("キャンセル", on_click=on_no),
                ft.FilledButton("削除する", on_click=on_yes,
                    style=ft.ButtonStyle(bgcolor=COLOR_ERROR, color="white")),
            ],
            actions_alignment=ft.MainAxisAlignment.END,
        )
        self.page.open(dlg)

    def open_settings_modal(self, e):
        # v1.1.11: Adobe Photoshop 環境設定の完全再現 (2ペイン・コンテンツスワップ方式)
        self._settings_selected_cat = "一般"
        self._build_adobe_preferences_view()

    # ── Adobe-like Preferences UI ────────────────────────────────────────────

    # カラーパレット（Adobe Bridge / Lightroom 準拠）
    _PREFS_SIDEBAR_BG  = "#252525"
    _PREFS_CONTENT_BG  = "#2E2E2E"
    _PREFS_TITLEBAR_BG = "#1E1E1E"
    _PREFS_FOOTER_BG   = "#1E1E1E"
    _PREFS_HIGHLIGHT   = "#0078D4"   # Fluent / Adobe アクセントブルー
    _PREFS_ROW_HOVER   = "#383838"
    _PREFS_BORDER      = "#161616"
    _PREFS_TEXT        = "#D4D4D4"
    _PREFS_TEXT_DIM    = "#808080"
    _PREFS_SECTION_TXT = "#60AAFF"   # セクションタイトル

    # カテゴリ定義: (表示名, アイコン)
    _PREFS_CATEGORIES = [
        ("一般",         ft.Icons.TUNE),
        ("リネーム規則", ft.Icons.DRIVE_FILE_RENAME_OUTLINE),
        ("カテゴリ設定", ft.Icons.CATEGORY),
        ("リスト管理",   ft.Icons.LIST_ALT),
        ("キャッシュ",   ft.Icons.STORAGE),
        ("プロジェクト", ft.Icons.FOLDER_SPECIAL),
    ]

    def _build_adobe_preferences_view(self):
        """設定ダイアログを初回構築する。カテゴリ切替は _switch_settings_cat で行う。"""

        # ── サイドバー ────────────────────────────────────────────────────
        self._prefs_sidebar_items = {}
        sidebar_col = ft.Column(spacing=0, scroll=ft.ScrollMode.AUTO)

        for cat_name, cat_icon in self._PREFS_CATEGORIES:
            item = self._build_prefs_sidebar_item(cat_name, cat_icon,
                                                   active=(cat_name == self._settings_selected_cat))
            self._prefs_sidebar_items[cat_name] = item
            sidebar_col.controls.append(item)

        sidebar = ft.Container(
            width=200,
            bgcolor=self._PREFS_SIDEBAR_BG,
            border=ft.border.only(right=ft.BorderSide(1, self._PREFS_BORDER)),
            content=ft.Column([
                ft.Container(
                    content=ft.Text("設定カテゴリ", size=10, color=self._PREFS_TEXT_DIM,
                                    weight="bold"),
                    padding=ft.padding.only(left=16, top=14, bottom=8),
                ),
                sidebar_col,
            ], spacing=0),
        )

        # ── コンテンツエリア ───────────────────────────────────────────────
        self._settings_content_area = ft.Container(
            expand=True,
            bgcolor=self._PREFS_CONTENT_BG,
            padding=ft.padding.only(left=32, right=32, top=24, bottom=24),
            content=self._get_adobe_pref_content(self._settings_selected_cat),
        )

        # ── ダイアログ全体のサイズ ─────────────────────────────────────────
        modal_w = min(1050, (self.page.width or 1200) * 0.88)
        modal_h = min(800,  (self.page.height or 850) * 0.88)

        inner_panel = ft.Container(
            width=modal_w,
            height=modal_h,
            bgcolor=self._PREFS_CONTENT_BG,
            border_radius=8,
            clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
            shadow=ft.BoxShadow(spread_radius=0, blur_radius=40,
                                color=ft.Colors.with_opacity(0.6, ft.Colors.BLACK),
                                offset=ft.Offset(0, 8)),
            content=ft.Column([
                # タイトルバー
                ft.Container(
                    content=ft.Row([
                        ft.Row([
                            ft.Icon(ft.Icons.SETTINGS, size=14, color=self._PREFS_TEXT_DIM),
                            ft.Text("環境設定", size=12, color=self._PREFS_TEXT,
                                    weight=ft.FontWeight.W_500),
                        ], spacing=8),
                        ft.Row([
                            ft.IconButton(
                                ft.Icons.CLOSE, icon_size=14, icon_color=self._PREFS_TEXT_DIM,
                                style=ft.ButtonStyle(
                                    padding=4,
                                    overlay_color=ft.Colors.with_opacity(0.15, ft.Colors.WHITE),
                                    shape=ft.RoundedRectangleBorder(radius=4),
                                ),
                                tooltip="閉じる",
                                on_click=lambda e: self.close_settings_modal(),
                            ),
                        ], spacing=0),
                    ], alignment="spaceBetween"),
                    padding=ft.padding.symmetric(horizontal=14, vertical=8),
                    bgcolor=self._PREFS_TITLEBAR_BG,
                    border=ft.border.only(bottom=ft.BorderSide(1, self._PREFS_BORDER)),
                ),
                # 2ペインレイアウト
                ft.Row([
                    sidebar,
                    self._settings_content_area,
                ], expand=True, spacing=0),
                # フッター
                ft.Container(
                    content=ft.Row([
                        ft.Text(f"RINKAN UMIS  v{VERSION}", size=10, color=self._PREFS_TEXT_DIM),
                        ft.Row([
                            ft.OutlinedButton(
                                "キャンセル",
                                on_click=lambda e: self.close_settings_modal(),
                                style=ft.ButtonStyle(
                                    color=self._PREFS_TEXT,
                                    side=ft.BorderSide(1, "#555555"),
                                    shape=ft.RoundedRectangleBorder(radius=4),
                                    padding=ft.padding.symmetric(horizontal=20, vertical=8),
                                ),
                            ),
                            ft.ElevatedButton(
                                "OK",
                                on_click=lambda e: self.close_settings_modal(),
                                style=ft.ButtonStyle(
                                    bgcolor=self._PREFS_HIGHLIGHT,
                                    color="white",
                                    shape=ft.RoundedRectangleBorder(radius=4),
                                    padding=ft.padding.symmetric(horizontal=28, vertical=8),
                                    elevation=0,
                                ),
                            ),
                        ], spacing=8),
                    ], alignment="spaceBetween"),
                    padding=ft.padding.symmetric(horizontal=16, vertical=10),
                    bgcolor=self._PREFS_FOOTER_BG,
                    border=ft.border.only(top=ft.BorderSide(1, self._PREFS_BORDER)),
                ),
            ], spacing=0, expand=True),
        )

        # settings_overlay の中身を差し替え
        self.settings_overlay.content = ft.Container(
            alignment=ft.alignment.center,
            on_click=lambda e: None,  # バブルアップ防止
            expand=True,
            content=inner_panel,
        )
        self.settings_overlay.visible = True
        try: self.page.update()
        except: pass

    def _build_prefs_sidebar_item(self, cat_name: str, cat_icon, active: bool) -> ft.Container:
        """サイドバーの1行アイテムを生成する。"""
        def _on_click(e, c=cat_name):
            self._switch_settings_cat(c)

        def _on_hover(e):
            if not (self._settings_selected_cat == cat_name):
                e.control.bgcolor = (self._PREFS_ROW_HOVER if e.data == "true"
                                     else "transparent")
                try: e.control.update()
                except: pass

        return ft.Container(
            content=ft.Row([
                ft.Container(
                    width=3, height=20,
                    bgcolor=(self._PREFS_HIGHLIGHT if active else "transparent"),
                    border_radius=2,
                ),
                ft.Icon(cat_icon, size=15,
                        color=("white" if active else self._PREFS_TEXT_DIM)),
                ft.Text(cat_name, size=12,
                        color=("white" if active else self._PREFS_TEXT),
                        weight=(ft.FontWeight.W_600 if active else ft.FontWeight.W_400)),
            ], spacing=10, vertical_alignment="center"),
            padding=ft.padding.symmetric(horizontal=10, vertical=8),
            bgcolor=(self._PREFS_HIGHLIGHT if active else "transparent"),
            border_radius=0,
            on_click=_on_click,
            on_hover=_on_hover,
            animate=ft.Animation(120, "easeOut"),
        )

    def _switch_settings_cat(self, cat: str):
        """カテゴリ切替: コンテンツエリアのみ差し替える（ダイアログ再構築なし）"""
        prev = self._settings_selected_cat
        self._settings_selected_cat = cat

        # 旧アイテムを非アクティブに
        if prev in self._prefs_sidebar_items:
            old = self._prefs_sidebar_items[prev]
            old.bgcolor = "transparent"
            row = old.content
            row.controls[0].bgcolor = "transparent"          # バー
            row.controls[1].color = self._PREFS_TEXT_DIM     # アイコン
            row.controls[2].color = self._PREFS_TEXT         # テキスト
            row.controls[2].weight = ft.FontWeight.W_400
            try: old.update()
            except: pass

        # 新アイテムをアクティブに
        if cat in self._prefs_sidebar_items:
            new = self._prefs_sidebar_items[cat]
            new.bgcolor = self._PREFS_HIGHLIGHT
            row = new.content
            row.controls[0].bgcolor = self._PREFS_HIGHLIGHT
            row.controls[1].color = "white"
            row.controls[2].color = "white"
            row.controls[2].weight = ft.FontWeight.W_600
            try: new.update()
            except: pass

        # コンテンツだけ差し替え
        self._settings_content_area.content = self._get_adobe_pref_content(cat)
        try: self._settings_content_area.update()
        except: pass

    def _get_adobe_pref_content(self, cat: str) -> ft.Column:
        """各カテゴリの設定コンテンツを生成する。"""
        TXT = self._PREFS_TEXT
        TXT_DIM = self._PREFS_TEXT_DIM
        SECTION = self._PREFS_SECTION_TXT
        BORDER = "#404040"
        ROW_BG = "#363636"

        def section_header(title: str, icon=None) -> ft.Container:
            row_items = []
            if icon:
                row_items.append(ft.Icon(icon, size=13, color=SECTION))
            row_items.append(ft.Text(title, size=11, weight="bold", color=SECTION,
                                     ))
            return ft.Container(
                content=ft.Column([
                    ft.Row(row_items, spacing=6, vertical_alignment="center"),
                    ft.Container(height=1, bgcolor=BORDER,
                                 margin=ft.margin.only(top=4, bottom=2)),
                ], spacing=0),
                margin=ft.margin.only(top=18, bottom=8),
            )

        def pref_row(label: str, control, help_key: str = None,
                     description: str = None) -> ft.Container:
            """ラベル + コントロール + 説明文の標準行"""
            left = ft.Column([
                ft.Text(label, size=12, color=TXT),
                *([] if not description else
                  [ft.Text(description, size=10, color=TXT_DIM,
                           italic=True, no_wrap=False, max_lines=2)]),
            ], spacing=2, expand=True)
            right_items = [control]
            if help_key:
                right_items.append(create_info_btn(help_key, self.page))
            return ft.Container(
                content=ft.Row([left, ft.Row(right_items, spacing=4,
                                             vertical_alignment="center")],
                               alignment="spaceBetween",
                               vertical_alignment="center"),
                padding=ft.padding.symmetric(horizontal=12, vertical=10),
                bgcolor=ROW_BG,
                border_radius=6,
                margin=ft.margin.only(bottom=4),
            )

        def pref_switch(label: str, sw: ft.Switch, help_key: str = None,
                        description: str = None) -> ft.Container:
            return pref_row(label, sw, help_key, description)

        def pref_action(label: str, icon, callback,
                        destructive: bool = False) -> ft.Container:
            color = "#FF6060" if destructive else TXT
            ic_color = "#FF6060" if destructive else "#60AAFF"
            return ft.Container(
                content=ft.Row([
                    ft.Row([
                        ft.Icon(icon, size=16, color=ic_color),
                        ft.Text(label, size=12, color=color),
                    ], spacing=10),
                    ft.Icon(ft.Icons.CHEVRON_RIGHT, size=14, color=TXT_DIM),
                ], alignment="spaceBetween"),
                padding=ft.padding.symmetric(horizontal=12, vertical=11),
                bgcolor=ROW_BG,
                border_radius=6,
                margin=ft.margin.only(bottom=4),
                on_click=callback,
                ink=True,
                animate=ft.Animation(100, "easeOut"),
            )

        controls = []

        # ── 一般 ─────────────────────────────────────────────────────────
        if cat == "一般":
            controls = [
                section_header("アプリケーション", ft.Icons.APPS),
                ft.Container(
                    content=ft.ElevatedButton(
                        "操作ガイドを再開", icon=ft.Icons.PLAY_CIRCLE_OUTLINE,
                        on_click=self.start_walkthrough,
                        style=ft.ButtonStyle(
                            bgcolor="#3A3A3A", color="white",
                            shape=ft.RoundedRectangleBorder(radius=4),
                            padding=ft.padding.symmetric(horizontal=16, vertical=10),
                            elevation=0,
                        ),
                    ),
                    margin=ft.margin.only(bottom=8),
                ),
                section_header("表示オプション", ft.Icons.VISIBILITY),
                pref_switch(
                    "詳細なファイル処理ログを表示", self.sw_show_file_log,
                    "show_file_log",
                    "コピー・検証の進捗をファイル単位でログに記録します"
                ),
                pref_switch(
                    "シーンリストに番号を付与", self.sw_scene_numbering,
                    "scene_numbering",
                    "例: 101_会場到着 のようにDay+連番を付けます"
                ),
                section_header("安全設定", ft.Icons.WARNING_AMBER),
                pref_switch(
                    "緊急フォーマット（カード初期化）を常に有効化",
                    self.sw_emergency_fmt, "emergency_fmt",
                    "⚠️ 誤操作防止のため、通常は無効を推奨します"
                ),
            ]

        # ── リネーム規則 ─────────────────────────────────────────────────
        elif cat == "リネーム規則":
            rename_rows = []
            for key in self.cfg_mgr.data.get("rename_order", []):
                label = self.rename_labels.get(key, key)
                sw = self.switches_rename.get(key)
                if not sw:
                    continue
                if key == "date":
                    ctrl = ft.Row([self.dd_date_format, sw], spacing=8,
                                   vertical_alignment="center")
                    rename_rows.append(pref_row(f"▸ {label}", ctrl, "rename_date"))
                else:
                    hk = {"location": "rename_venue", "scene": "rename_scene",
                          "photographer": "rename_pg", "card_id": "rename_id"}.get(key)
                    rename_rows.append(pref_row(f"▸ {label}", sw, hk))

            controls = [
                section_header("ファイル名の構成要素", ft.Icons.SORT),
                ft.Text("有効にした項目が下記の順でファイル名に連結されます。",
                        size=11, color=TXT_DIM, italic=True),
                ft.Container(
                    content=ft.Column(rename_rows, spacing=0),
                    margin=ft.margin.only(top=8),
                ),
                section_header("自動整理オプション", ft.Icons.AUTO_FIX_HIGH),
                pref_switch(
                    "連番リネーム（元のファイル名を破棄）", self.sw_rename_seq,
                    "use_sequential",
                    "⚠️ 0001, 0002 … の連番に置き換えます。元のファイル名は失われます"
                ),
                pref_switch(
                    "取り込み時に選別用サブフォルダを自動生成",
                    self.sw_create_sub_folder, "create_sub_folder",
                ),
                pref_row(
                    "選別フォルダ名", self.tf_sub_folder_name, "sub_folder_name",
                ),
            ]

        # ── カテゴリ設定 ─────────────────────────────────────────────────
        elif cat == "カテゴリ設定":
            header_row = ft.Container(
                content=ft.Row([
                    ft.Text("有効", width=44, size=10, color=TXT_DIM,
                             text_align="center"),
                    ft.Text("種別", width=64, size=10, color=TXT_DIM),
                    ft.Text("フォルダ名", width=110, size=10, color=TXT_DIM),
                    ft.Text("対象拡張子 (カンマ区切り)", expand=True,
                             size=10, color=TXT_DIM),
                ]),
                padding=ft.padding.symmetric(horizontal=12, vertical=6),
                bgcolor="#2A2A2A",
                border_radius=ft.border_radius.only(top_left=6, top_right=6),
            )
            cat_data_rows = []
            for c_name, conf in self.cfg_mgr.data["category_settings"].items():
                icon_info = CAT_ICONS.get(c_name, (ft.Icons.FILE_PRESENT, TXT_DIM))
                cb = ft.Checkbox(
                    value=not conf["disabled"],
                    fill_color=self._PREFS_HIGHLIGHT,
                    check_color="white",
                    on_change=lambda e, n=c_name: self._on_cat_change(e, n, "disabled"),
                )
                tf_folder = ft.TextField(
                    value=conf["folder"], width=110, height=28, text_size=11,
                    content_padding=ft.padding.symmetric(horizontal=6),
                    border_color="#555555", focused_border_color=self._PREFS_HIGHLIGHT,
                    bgcolor="#1E1E1E", color=TXT,
                    on_blur=lambda e, n=c_name: self._on_cat_change(e, n, "folder"),
                )
                tf_exts = ft.TextField(
                    value=", ".join(conf["exts"]), expand=True, height=28,
                    text_size=10,
                    content_padding=ft.padding.symmetric(horizontal=6),
                    border_color="#555555", focused_border_color=self._PREFS_HIGHLIGHT,
                    bgcolor="#1E1E1E", color=TXT_DIM,
                    on_blur=lambda e, n=c_name: self._on_cat_change(e, n, "exts"),
                )
                cat_data_rows.append(
                    ft.Container(
                        content=ft.Row([
                            ft.Container(cb, width=44, alignment=ft.alignment.center),
                            ft.Row([
                                ft.Icon(icon_info[0], size=14, color=icon_info[1]),
                                ft.Text(c_name, size=12, color=TXT, weight="bold"),
                            ], width=64, spacing=4),
                            tf_folder,
                            tf_exts,
                        ], spacing=8, vertical_alignment="center"),
                        padding=ft.padding.symmetric(horizontal=8, vertical=6),
                        bgcolor=ROW_BG,
                        border=ft.border.only(
                            top=ft.BorderSide(1, "#2A2A2A"),
                        ),
                    )
                )
            controls = [
                section_header("ファイル分類と自動振り分け", ft.Icons.CATEGORY),
                ft.Text("各メディア種別のフォルダ名と対象拡張子を設定します。",
                        size=11, color=TXT_DIM, italic=True),
                ft.Container(height=8),
                ft.Container(
                    content=ft.Column([header_row] + cat_data_rows, spacing=0),
                    border=ft.border.all(1, BORDER),
                    border_radius=6,
                    clip_behavior=ft.ClipBehavior.ANTI_ALIAS,
                ),
            ]

        # ── リスト管理 ───────────────────────────────────────────────────
        elif cat == "リスト管理":
            controls = [
                section_header("マスターデータ", ft.Icons.MANAGE_ACCOUNTS),
                pref_action("カメラマン データベース...", ft.Icons.PEOPLE,
                             lambda e: self._open_list_editor("photographers")),
                pref_action("カード識別 ID リスト...", ft.Icons.CREDIT_CARD,
                             lambda e: self._open_list_editor("card_ids")),
                pref_action("会場 / ロケーション リスト...", ft.Icons.LOCATION_ON,
                             lambda e: self._open_list_editor("locations")),
                pref_action("除外対象フォルダ設定...", ft.Icons.FOLDER_OFF,
                             lambda e: self._open_list_editor("excluded_folders")),
                section_header("デバイス表示", ft.Icons.DEVICES),
                pref_action("非表示に設定したドライブを管理...", ft.Icons.VISIBILITY,
                             self.open_hidden_drives_editor),
            ]

        # ── キャッシュ ───────────────────────────────────────────────────
        elif cat == "キャッシュ":
            controls = [
                section_header("キャッシュの管理", ft.Icons.STORAGE),
                ft.Container(
                    content=ft.Text(
                        "パフォーマンス向上のために作成された一時データです。"
                        "削除後は次回表示時に再生成されます。",
                        size=11, color=TXT_DIM, italic=True
                    ),
                    margin=ft.margin.only(bottom=12),
                ),
                pref_action("サムネイルキャッシュをクリア",
                             ft.Icons.DELETE_SWEEP, self._clear_thumb_cache),
                pref_action("プレビュー用ビデオキャッシュをクリア",
                             ft.Icons.DELETE_SWEEP, self._clear_preview_cache),
                ft.Container(
                    content=ft.Divider(height=1, color=BORDER),
                    margin=ft.margin.symmetric(vertical=8),
                ),
                pref_action("すべてのローカルキャッシュを完全消去",
                             ft.Icons.DELETE_FOREVER, self._clear_all_cache,
                             destructive=True),
            ]

        # ── プロジェクト ─────────────────────────────────────────────────
        elif cat == "プロジェクト":
            proj_badge = ft.Container(
                content=ft.Text(self.cfg_mgr.project_name, size=13,
                                color="white", weight="bold"),
                bgcolor="#0078D4",
                padding=ft.padding.symmetric(horizontal=10, vertical=4),
                border_radius=4,
                margin=ft.margin.only(bottom=12),
            )
            controls = [
                section_header("現在のプロジェクト", ft.Icons.FOLDER_SPECIAL),
                proj_badge,
                pref_action("新規プロジェクトを定義...", ft.Icons.ADD,
                             self.manual_create_new_project),
                pref_action("プロジェクト設定を保存", ft.Icons.SAVE,
                             self.manual_save_project),
                pref_action("名前を付けて保存...", ft.Icons.SAVE_AS,
                             self.save_project_as),
                section_header("メンテナンス", ft.Icons.BUILD),
                pref_action("プロジェクト保存先フォルダを表示",
                             ft.Icons.FOLDER_OPEN, self.open_projects_folder),
                pref_action("プロジェクトを完全に削除してリセット",
                             ft.Icons.DELETE_FOREVER, self.delete_project,
                             destructive=True),
            ]

        return ft.Column(controls, scroll=ft.ScrollMode.AUTO, spacing=0,
                         tight=True)

    def close_settings_modal(self, e=None):
        self.settings_overlay.visible = False
        self._identity_modal_back_flag = False # フラグリセット
        try: self.page.update()
        except: pass

    def _open_modal_dialog(self, title_text, content_ctrl, actions):
        dlg = ft.AlertDialog(
            modal=True,
            title=ft.Text(title_text, size=16, weight="bold", color=COLOR_TEXT_MAIN),
            content=content_ctrl,
            actions=actions,
            bgcolor=COLOR_BG_CARD,
        )
        self._active_modal_dlg = dlg
        try:
            self.page.open(dlg)
        except Exception:
            try:
                self.page.dialog = dlg
                dlg.open = True
                self.page.update()
            except: pass
        return dlg

    def _close_active_modal(self, e=None):
        dlg = getattr(self, "_active_modal_dlg", None)
        if dlg is None: return
        try: self.page.close(dlg)
        except:
            try:
                dlg.open = False
                self.page.update()
            except: pass
        self._active_modal_dlg = None

    def _back_to_settings_main(self, e=None):
        if self._identity_modal_back_flag:
            self.close_settings_modal()
            self.show_identity_modal(None)
            return
        # 現在のカテゴリのコンテンツを再描画して戻る
        if hasattr(self, "_settings_content_area") and self._settings_content_area:
            self._settings_content_area.content = self._get_adobe_pref_content(
                self._settings_selected_cat
            )
            try: self._settings_content_area.update()
            except: pass

    def open_hidden_drives_editor(self, e):
        excluded = self.cfg_mgr.data["options"].setdefault("excluded_source_drives", [])
        list_col = ft.Column(spacing=2, scroll="auto", height=200)
        def refresh():
            list_col.controls.clear()
            if not excluded:
                list_col.controls.append(ft.Text("非表示中のドライブはありません", size=12, color=COLOR_TEXT_SEC, italic=True))
            for drv in list(excluded):
                row = ft.Row([
                    ft.Icon(ft.Icons.STORAGE, size=16, color=COLOR_TEXT_SEC),
                    ft.Text(drv, size=12, expand=True, color=COLOR_TEXT_MAIN),
                    ft.TextButton("解除", style=ft.ButtonStyle(color=COLOR_SUCCESS), on_click=lambda e, d=drv: do_restore(d))
                ], spacing=5)
                list_col.controls.append(ft.Container(content=row, padding=5, bgcolor=COLOR_BG_CARD, border_radius=4))
            try: list_col.update()
            except: pass
        def do_restore(drv):
            if drv in excluded: excluded.remove(drv)
            self.cfg_mgr.save()
            refresh()
        refresh()
        editor_view = ft.Column([
            ft.Row([
                ft.IconButton(ft.Icons.ARROW_BACK, on_click=self._back_to_settings_main,
                              tooltip="戻る"),
                ft.Text("非表示ドライブの解除", size=16, weight="bold", color=COLOR_TEXT_MAIN)
            ], alignment="start"),
            ft.Text("解除するとドライブが再びドロップダウンに表示されます。",
                    size=12, color=COLOR_TEXT_SEC),
            ft.Divider(color=COLOR_DIVIDER),
            list_col,
        ], tight=True, scroll=ft.ScrollMode.AUTO)
        if hasattr(self, "_settings_content_area") and self._settings_content_area:
            self._settings_content_area.content = editor_view
            try: self._settings_content_area.update()
            except: pass

    def _on_cat_change(self, e, cat, field):
        if field == "disabled": self.cfg_mgr.data["category_settings"][cat]["disabled"] = not e.control.value
        elif field == "folder": self.cfg_mgr.data["category_settings"][cat]["folder"] = self.sanitize_text(e.control.value)
        elif field == "exts": self.cfg_mgr.data["category_settings"][cat]["exts"] = [x.strip().lower() for x in e.control.value.split(",") if x.strip()]
        self.cfg_mgr.save()
        self.update_cat_status_icons()
        # v7.6.3: カテゴリ設定変更時にソーススキャンを再実行してリストを更新
        if field == "disabled":
            self._start_scan_execution()

    def _open_list_editor(self, key, callback=None):
        # v7.5.1: 並び替えボタン追加と削除バグ修正
        items = self.cfg_mgr._get_list_ref(key)
        list_col = ft.Column(spacing=2, scroll="auto", height=300)

        def refresh():
            list_col.controls.clear()
            current_items = self.cfg_mgr._get_list_ref(key)
            for i, item in enumerate(current_items):
                val = item if isinstance(item, str) else item.get('name', str(item))
                row = ft.Row([
                    ft.Text(val, size=13, expand=True),
                    ft.IconButton(ft.Icons.ARROW_UPWARD, icon_size=16, icon_color=COLOR_TEXT_SEC, on_click=lambda e, idx=i: do_move(idx, "up"), tooltip="上へ"),
                    ft.IconButton(ft.Icons.ARROW_DOWNWARD, icon_size=16, icon_color=COLOR_TEXT_SEC, on_click=lambda e, idx=i: do_move(idx, "down"), tooltip="下へ"),
                    ft.IconButton(ft.Icons.REMOVE_CIRCLE, icon_color=COLOR_ERROR, icon_size=18, on_click=lambda e, v=val: do_del(v))
                ], spacing=5)
                list_col.controls.append(ft.Container(content=row, padding=5, bgcolor=COLOR_BG_CARD, border_radius=4))
            try: list_col.update()
            except: pass

        def do_del(val):
            self.cfg_mgr.remove_item(key, val)
            refresh()
            if callback: callback()
            self._update_identity_button()

        def do_add(e):
            v = self.sanitize_text(tf_add.value)
            if not v: return
            self.cfg_mgr.add_item(key, v)
            tf_add.value = ""
            tf_add.focus() # v7.5.1: 連続入力をサポート
            refresh()
            if callback: callback()
            self._update_identity_button()

        def do_move(idx, direction):
            self.cfg_mgr.move_item_step(key, idx, direction)
            refresh()
            if callback: callback()

        tf_add = ft.TextField(hint_text="新規追加", expand=True, height=35, text_size=13, on_submit=do_add) # Enter対応
        add_row = ft.Row([tf_add, ft.IconButton(ft.Icons.ADD_CIRCLE, icon_color=COLOR_SUCCESS, on_click=do_add)], spacing=5)
        refresh()

        titles = {"photographers": "カメラマン管理", "card_ids": "カードID管理", "locations": "会場管理", "excluded_folders": "除外フォルダ管理"}
        editor_view = ft.Column([
            ft.Row([
                ft.IconButton(ft.Icons.ARROW_BACK, on_click=self._back_to_settings_main,
                              tooltip="戻る"),
                ft.Text(titles.get(key, key), size=16, weight="bold",
                        color=COLOR_TEXT_MAIN)
            ], alignment="start"),
            ft.Divider(color=COLOR_DIVIDER),
            list_col,
            ft.Divider(color=COLOR_DIVIDER),
            add_row
        ], tight=True, scroll=ft.ScrollMode.AUTO)
        if hasattr(self, "_settings_content_area") and self._settings_content_area:
            self._settings_content_area.content = editor_view
            try: self._settings_content_area.update()
            except: pass

    def reset_history_filters(self, e):
        # v8.0.13: リストプロパティをクリアし、ボタンラベルもリセット
        self.hist_filter_pg = []
        self.hist_filter_cid = []
        self.hist_filter_scene = []
        self.lbl_hist_pg.value = "カメラマン: すべて"
        self.lbl_hist_cid.value = "カードID: すべて"
        self.lbl_hist_scene.value = "シーン: すべて"
        self.refresh_history_view()

    def _open_history_filter_modal(self, kind):
        # v8.0.13: 履歴フィルタのモーダル選択UI
        history_data = self.history_logger.get_history()
        if kind == "pg":
            all_vals = sorted(set(str(e.get("photographer", "")) for e in history_data if e.get("photographer")))
            current = list(self.hist_filter_pg)
            title = "カメラマンで絞り込む"
        elif kind == "cid":
            all_vals = sorted(set(str(e.get("card_id", "")) for e in history_data if e.get("card_id")))
            current = list(self.hist_filter_cid)
            title = "カードIDで絞り込む"
        else:  # scene
            scene_set = set()
            for e in history_data:
                for s in e.get("scene_details", {}).keys():
                    scene_set.add(s)
            all_vals = sorted(scene_set)
            current = list(self.hist_filter_scene)
            title = "シーン名で絞り込む"

        selected = list(current)
        cbs = []
        for val in all_vals:
            cb = ft.Checkbox(label=val, value=(val in selected))
            cbs.append((val, cb))

        def apply(ev):
            result = [val for val, cb in cbs if cb.value]
            if kind == "pg":
                self.hist_filter_pg = result
                self.lbl_hist_pg.value = f"カメラマン: {', '.join(result) if result else 'すべて'}"
            elif kind == "cid":
                self.hist_filter_cid = result
                self.lbl_hist_cid.value = f"カードID: {', '.join(result) if result else 'すべて'}"
            else:
                self.hist_filter_scene = result
                self.lbl_hist_scene.value = f"シーン: {', '.join(result) if result else 'すべて'}"
            self._close_active_modal()
            self.refresh_history_view()

        if not all_vals:
            self._open_modal_dialog(
                title,
                ft.Text("該当する履歴データがありません。", color=COLOR_TEXT_SEC),
                [ft.TextButton("閉じる", on_click=self._close_active_modal)]
            )
            return

        cb_list = ft.Column([cb for _, cb in cbs], spacing=6, scroll=ft.ScrollMode.AUTO)
        self._open_modal_dialog(
            title,
            ft.Container(content=cb_list, height=min(300, len(cbs) * 40 + 20), width=300, padding=10),
            [
                ft.TextButton("適用", on_click=apply, style=ft.ButtonStyle(color=COLOR_PRIMARY)),
                ft.TextButton("キャンセル", on_click=self._close_active_modal),
            ]
        )

    def show_history_dialog(self, e):
        """v1.1.28: 実行履歴をモーダルダイアログで表示"""
        self.refresh_history_view()
        self._open_modal_dialog(
            "実行履歴",
            ft.Container(
                content=self.lv_history_list,
                width=850, height=600,
                padding=10,
            ),
            [ft.TextButton("閉じる", on_click=self._close_active_modal)]
        )

    def refresh_history_view(self):
        self.lv_history_list.controls.clear()
        history_data = self.history_logger.get_history()
        if not history_data:
            self.lv_history_list.controls.append(ft.Text("履歴がありません。", color=COLOR_TEXT_SEC))
        else:
            # v8.0.13: ORフィルタリング（選択なし=すべて表示）
            f_pgs = self.hist_filter_pg
            f_cids = self.hist_filter_cid
            f_scenes = self.hist_filter_scene

            for entry in history_data:
                pg = str(entry.get("photographer") or "")
                cid = str(entry.get("card_id") or "")
                # ORフィルタ: リストが空=全表示、選択あり=いずれかに一致するもののみ
                pg_match = (not f_pgs) or any(pg_f == pg for pg_f in f_pgs)
                cid_match = (not f_cids) or any(cid_f == cid for cid_f in f_cids)

                scene_details = entry.get('scene_details', {})
                if not f_scenes:
                    scene_match = True
                else:
                    scene_match = any(s in scene_details for s in f_scenes)

                if pg_match and cid_match and scene_match:
                    entry_id = entry.get("id")
                    is_expanded = self.history_expanded.get(entry_id, False)
                    self.lv_history_list.controls.append(self._build_history_entry_widget(entry, is_expanded))

            if not self.lv_history_list.controls:
                self.lv_history_list.controls.append(ft.Text("条件に一致する履歴はありません。", color=COLOR_TEXT_SEC))

        try: self.lv_history_list.update()
        except: pass

    def _toggle_history_entry(self, entry_id):
        self.history_expanded[entry_id] = not self.history_expanded.get(entry_id, False)
        self.refresh_history_view()

    def _build_history_entry_widget(self, entry, is_expanded):
        try:
            dt = datetime.datetime.fromisoformat(entry.get("date", ""))
            date_str = dt.strftime("%Y/%m/%d %H:%M")
        except: date_str = "Unknown Date"
        success = "成功" in entry.get("status", "")
        status_color = COLOR_SUCCESS if success else COLOR_ERROR
        # v8.0.13: サイズ単位を動的に切り替える
        def _fmt_bytes(b):
            for u in ['B','KB','MB','GB']:
                if b < 1024: return f"{b:.1f}{u}"
                b /= 1024
            return f"{b:.1f}TB"
        total_size_str = _fmt_bytes(entry.get('total_size', 0))
        is_formatted = entry.get("formatted", False)
        fmt_label = "初期化済" if is_formatted else "未初期化"
        fmt_bg = COLOR_SUCCESS if is_formatted else (COLOR_TEXT_SEC if success else COLOR_ERROR)
        fmt_badge = ft.Container(
            content=ft.Text(fmt_label, size=10, weight="bold", color="white"),
            bgcolor=fmt_bg, padding=ft.padding.symmetric(horizontal=6, vertical=2),
            border_radius=4
        )
        header_row = ft.Row([
            ft.Icon(ft.Icons.CHECK_CIRCLE if success else ft.Icons.ERROR, color=status_color, size=20),
            ft.Text(date_str, size=14, weight="bold", color=COLOR_TEXT_MAIN, width=130),
            fmt_badge,
            ft.Text(entry.get("photographer", "-"), size=14, color=COLOR_PRIMARY, width=80),
            ft.Text(f"ID: {entry.get('card_id', '-')}", size=13, color=COLOR_TEXT_SEC, width=60),
            ft.Text(f"{entry.get('total_count', 0)}件 / {total_size_str}", size=13, color=COLOR_TEXT_SEC, expand=True),
            ft.IconButton(ft.Icons.KEYBOARD_ARROW_UP if is_expanded else ft.Icons.KEYBOARD_ARROW_DOWN, icon_color=COLOR_TEXT_SEC, on_click=lambda e, id_val=entry.get("id"): self._toggle_history_entry(id_val))
        ], alignment="spaceBetween", vertical_alignment="center")
        content_controls = [ft.Container(content=header_row, padding=10, on_click=lambda e, id_val=entry.get("id"): self._toggle_history_entry(id_val))]
        if is_expanded:
            details_col = ft.Column(spacing=5)
            details_col.controls.append(ft.Text(f"保存先: {entry.get('save_dest', '不明')}", size=12, color=COLOR_TEXT_SEC))
            cat_details = entry.get('size_details', {})
            cat_counts = entry.get('count_details', {})
            if cat_details:
                cat_strs = [f"{c}: {cat_counts.get(c,0)}件 ({s/(1024**3):.2f}GB)" for c, s in cat_details.items()]
                details_col.controls.append(ft.Text(f"カテゴリ別: {' / '.join(cat_strs)}", size=12, color=COLOR_TEXT_SEC))
            scene_details = entry.get('scene_details', {})
            if scene_details:
                scene_strs = [f"{s_name} {d['count']}件" for s_name, d in scene_details.items()]
                details_col.controls.append(ft.Text(f"シーン別: {' / '.join(scene_strs)}", size=12, color=COLOR_TEXT_SEC))
            if entry.get("has_errors"):
                err_list = "\n".join(entry.get("error_list", [])[:5])
                details_col.controls.append(ft.Container(content=ft.Text(f"エラーログ:\n{err_list}", size=11, color=COLOR_ERROR), bgcolor="#331111", padding=8, border_radius=4))
            content_controls.append(ft.Divider(height=1, color=COLOR_DIVIDER))
            content_controls.append(ft.Container(content=details_col, padding=ft.padding.only(left=30, right=10, top=10, bottom=15)))
        return ft.Card(
            content=ft.Container(
                content=ft.Column(content_controls, spacing=0),
                bgcolor=COLOR_BG_CARD, border_radius=8,
            ),
            elevation=2, margin=ft.margin.only(bottom=5)
        )

    def clear_history(self, e):
        def confirm(ev):
            self.history_logger.clear_history()
            self._close_active_modal()
            self.refresh_history_view()
            self.show_snack("履歴をクリアしました", COLOR_SUCCESS)
        self._open_modal_dialog(
            "履歴クリア",
            ft.Text("全ての取り込み履歴を削除しますか？", color=COLOR_TEXT_MAIN),
            [
                ft.TextButton("削除", on_click=confirm, style=ft.ButtonStyle(color=COLOR_ERROR)),
                ft.TextButton("キャンセル", on_click=self._close_active_modal),
            ],
        )

    def start_copy(self, e):
        if self.is_complete_state:
            self.reset_progress_ui(); return
        
        if self.app_mode == "select":
            # v9.0.0: セレクトモードのコピー実行
            self._start_select_copy()
            return

        assigned_count = sum(1 for f in self.source_files if f['assigned_scene'] is not None)
        if assigned_count == 0:
            self.show_snack("シーンに割り当てられたファイルがありません", COLOR_ERROR); return
        if not self.current_card_id:
            self.show_snack("カードIDを選択してください", COLOR_ERROR); return
        self.btn_start.disabled = True; self.btn_cancel.disabled = False
        self.lv_log.controls.clear()
        def on_log(msg): self.log(msg)
        def on_progress(r, status, eta, color, btn_text):
            self.pb_fill.width = PB_WIDTH * r; self.pb_fill.bgcolor = color
            self.lbl_percent.value = f"{int(r*100)}%"; self.lbl_status.value = f"{status} - {eta}"
            try: self.page.update()
            except: pass
        def on_finished(success, msg):
            self.worker = None
            if success:
                self.log("取り込み完了"); self.show_snack("取り込みが完了しました", COLOR_SUCCESS)
                self.last_ingested_drive = self.dd_drive.value
                self.format_allowed = True
                self.is_complete_state = True
                self.apply_start_button_state("完了（リセット）", COLOR_SUCCESS, "white", False)
                
                # v8.0.12: 履歴を保存
                if self.current_copy_worker:
                    exec_id = str(uuid.uuid4())
                    self.last_execution_id = exec_id
                    entry = {
                        "id": exec_id,
                        "date": datetime.datetime.now().isoformat(),
                        "photographer": self.current_photographer or "未指定",
                        "card_id": self.current_card_id or "不明",
                        "status": "成功",
                        "total_count": self.current_copy_worker.stats.get("total_count", 0),
                        "total_size": self.current_copy_worker.stats.get("total_size", 0),
                        "size_details": self.current_copy_worker.stats.get("size_details", {}),
                        "count_details": self.current_copy_worker.stats.get("count_details", {}),
                        "scene_details": self.current_copy_worker.stats.get("scene_details", {}),
                        "save_dest": self.cfg_mgr.data["paths"]["dest_root"],
                        "formatted": False
                    }
                    self.history_logger.add_entry(entry)
            else:
                self.log(f"エラー: {msg}"); self.show_snack(f"処理結果: {msg}", COLOR_ERROR)
                self.apply_start_button_state("取り込み開始", COLOR_SUCCESS, "white", False)
            self.btn_cancel.disabled = True
            self.check_format_button_state()
            try: self.page.update()
            except: pass
        self.current_copy_worker = CopyWorker(self.cfg_mgr, self.source_files, self.scene_assignments,
                                               self.current_photographer, self.current_card_id, on_log, on_progress, on_finished)
        self.current_copy_worker.start()

    def cancel_copy(self, e):
        if self.current_copy_worker: self.current_copy_worker.is_cancelled = True
        self.btn_cancel.disabled = True; self.show_snack("キャンセルを要求しました", COLOR_ACCENT)

    def format_card(self, e):
        drive_display = self.dd_drive.value
        if not drive_display or drive_display == "ドライブを接続": self.show_snack("ドライブを選択してください", COLOR_ERROR); return
        drive_path = self.drive_map.get(drive_display)
        if not drive_path: return
        target_label = drive_display.split("(")[0].strip() or "UMIS_CARD"
        try:
            usage = shutil.disk_usage(drive_path)
            total_gb = usage.total / (1024**3)
        except:
            total_gb = 0
        def run_fmt(e):
            if hasattr(self, '_fmt_dlg') and self._fmt_dlg:
                self.page.close(self._fmt_dlg)
            self.btn_format.disabled = True; self.btn_start.disabled = True
            def on_prog(r, s, eta, c, bt):
                self.pb_fill.width = PB_WIDTH * r; self.pb_fill.bgcolor = c; self.lbl_percent.value = f"{int(r*100)}%"
                self.lbl_status.value = f"{s} - {eta}"
                try: self.page.update()
                except: pass
            def on_fin(ok, msg):
                if ok:
                    self.log("初期化完了"); self.show_snack(f"初期化完了 (ラベル: {target_label})", COLOR_SUCCESS)
                    if self.last_execution_id: self.history_logger.update_formatted_status(self.last_execution_id, True)
                else: self.log(f"エラー: {msg}"); self.show_snack(msg, COLOR_ERROR)
                if self.sw_emergency_fmt.value:
                    self.sw_emergency_fmt.value = False
                    self.cfg_mgr.data["options"]["emergency_fmt"] = False
                    self.cfg_mgr.save()
                self.format_allowed = False
                self.btn_start.disabled = False
                self.reset_progress_ui()
                try: self.page.update()
                except: pass
            FormatWorker(drive_path, target_label, on_prog, on_fin).start()
        def show_confirm_3(e):
            self.page.close(self._fmt_dlg)
            self._fmt_dlg = ft.AlertDialog(
                title=ft.Text("⚠ 最終確認 (3/3)", color=COLOR_ERROR),
                content=ft.Text(f"最終確認です。\n\n「{drive_display}」の全データが消去されます。\n\nこの操作は元に戻せません。\n本当に実行しますか？", weight="bold"),
                actions=[
                    ft.TextButton("初期化を実行する", on_click=run_fmt, style=ft.ButtonStyle(color=COLOR_ERROR)),
                    ft.TextButton("キャンセル", on_click=lambda e: self.page.close(self._fmt_dlg))
                ], modal=True)
            self.page.open(self._fmt_dlg)
        def show_confirm_2(e):
            if hasattr(self, '_fmt_dlg') and self._fmt_dlg:
                self.page.close(self._fmt_dlg)
            self._fmt_dlg = ft.AlertDialog(
                title=ft.Text("⚠ 再確認 (2/3)", color=COLOR_ERROR),
                content=ft.Text(f"「{drive_display}」を初期化します。\n\n全てのデータが完全に消去されます。\n続行しますか？"),
                actions=[
                    ft.TextButton("続行する", on_click=show_confirm_3, style=ft.ButtonStyle(color=COLOR_ERROR)),
                    ft.TextButton("キャンセル", on_click=lambda e: self.page.close(self._fmt_dlg))
                ], modal=True)
            self.page.open(self._fmt_dlg)
        def show_confirm_1_or_ssd_warning():
            if total_gb >= 128:
                self._fmt_dlg = ft.AlertDialog(
                    title=ft.Text("⚠ 大容量ドライブ警告", color=COLOR_ACCENT),
                    content=ft.Column([
                        ft.Text(f"選択されたドライブの容量は {total_gb:.0f}GB です。", weight="bold"),
                        ft.Text("128GB以上のドライブが選択されています。", color=COLOR_ERROR),
                        ft.Text("SDカードではなくSSD/HDDを誤って選択していませんか？", color=COLOR_ERROR, weight="bold"),
                        ft.Container(height=10),
                        ft.Text(f"ドライブ: {drive_display}\nパス: {drive_path}", size=11, color=COLOR_TEXT_SEC),
                    ], tight=True, spacing=5),
                    actions=[
                        ft.TextButton("SDカードで間違いない", on_click=show_confirm_2, style=ft.ButtonStyle(color=COLOR_ACCENT)),
                        ft.TextButton("キャンセル", on_click=lambda e: self.page.close(self._fmt_dlg))
                    ], modal=True)
            else:
                self._fmt_dlg = ft.AlertDialog(
                    title=ft.Text("⚠ 初期化確認 (1/3)", color=COLOR_ERROR),
                    content=ft.Text(f"「{drive_display}」を初期化します。\nすべてのデータが消去されます。\n\n本当に実行しますか？"),
                    actions=[
                        ft.TextButton("はい", on_click=show_confirm_2, style=ft.ButtonStyle(color=COLOR_ERROR)),
                        ft.TextButton("いいえ", on_click=lambda e: self.page.close(self._fmt_dlg))
                    ], modal=True)
            self.page.open(self._fmt_dlg)
        unassigned_count = sum(1 for f in self.source_files if f['assigned_scene'] is None)
        if unassigned_count > 0 and not self.sw_emergency_fmt.value:
            def proceed_to_confirm(e):
                self.page.close(self._warn_dlg)
                show_confirm_1_or_ssd_warning()
            self._warn_dlg = ft.AlertDialog(
                title=ft.Text("⚠ 未取り込みファイルの警告", color=COLOR_ACCENT),
                content=ft.Text(f"シーンの設定がされていなくて、取り込みがされていないファイルが {unassigned_count} 件あるようですが、初期化を実行しますか？"),
                actions=[
                    ft.TextButton("はい（続行）", on_click=proceed_to_confirm, style=ft.ButtonStyle(color=COLOR_ERROR)),
                    ft.TextButton("いいえ", on_click=lambda e: self.page.close(self._warn_dlg))
                ], modal=True
            )
            self.page.open(self._warn_dlg)
            return
        show_confirm_1_or_ssd_warning()

    def hide_current_drive(self, e):
        # v7.5.1: スキャン有無に関わらずダイアログ表示
        dd = self.dd_drive.value
        if not dd or dd == "ドライブを接続": return
        
        def do_hide(ev):
            self._close_active_modal()
            excluded = self.cfg_mgr.data["options"].setdefault("excluded_source_drives", [])
            if dd not in excluded:
                excluded.append(dd)
                self.cfg_mgr.save()
            self.drive_map.pop(dd, None)
            self.dd_drive.options = [o for o in self.dd_drive.options if o.key != dd]
            self.dd_drive.value = None
            self.source_files.clear()
            self.range_selection_start_idx = None
            self.selected_scene_info = None
            self.current_photographer = None
            self.current_card_id = None
            self._update_identity_button()
            self.radio_day.value = "0"
            self.refresh_scene_buttons()
            self.scene_assignments.clear()
            self.refresh_thumbnail_grid()
            self.update_preview()
            self.show_snack(f"ドライブ「{dd}」を非表示にしました")
            try: self.page.update()
            except: pass

        self._open_modal_dialog(
            "ドライブの非表示",
            ft.Text(f"このドライブ「{dd}」を非表示にしますか？\n再度表示するには設定から解除してください。"),
            [
                ft.TextButton("はい", on_click=do_hide, style=ft.ButtonStyle(color=COLOR_ERROR)),
                ft.TextButton("いいえ", on_click=self._close_active_modal),
            ]
        )

    def eject_current_drive(self, e):
        dd = self.dd_drive.value
        if not dd: return
        mp = self.drive_map.get(dd)
        if not mp: self.show_snack("ドライブ情報が見つかりません", COLOR_ERROR); return
        self._thumb_gen_id += 1
        self.source_files.clear()
        self.scene_assignments.clear()
        self.dd_drive.value = None
        self.drive_map.pop(dd, None)
        
        self.selected_scene_info = None
        self.current_photographer = None
        self.current_card_id = None
        self._update_identity_button()
        self.radio_day.value = "0"
        self.refresh_scene_buttons()
        self.refresh_thumbnail_grid()
        self.update_preview()
        self.eject_icon_widget.visible = False
        self.eject_ring_widget.visible = True
        self.format_allowed = False
        self.check_format_button_state()
        try: self.page.update()
        except: pass
        def do_eject():
            time.sleep(0.5)
            try:
                if platform.system() == "Darwin":
                    subprocess.run(["diskutil", "eject", mp], check=True, capture_output=True)
                elif platform.system() == "Windows":
                    dl = os.path.splitdrive(mp)[0]
                    subprocess.run(["powershell", "-command", f"(New-Object -comObject Shell.Application).Namespace(17).ParseName('{dl}').InvokeVerb('Eject')"], check=True)
                self._open_modal_dialog(
                    "取り外し完了",
                    ft.Text("安全に取り外せます。", color=COLOR_TEXT_MAIN),
                    [ft.TextButton("OK", on_click=self._close_active_modal)],
                )
            except Exception as ex:
                self.show_snack(f"取り外し失敗: {ex}", COLOR_ERROR)
            finally:
                self.eject_icon_widget.visible = True
                self.eject_ring_widget.visible = False
                try: self.page.update()
                except: pass
        threading.Thread(target=do_eject, daemon=True).start()

    def pick_dest(self, e):
        self.picker_target = "dest"; self.file_picker.get_directory_path(dialog_title="保存先フォルダを選択")

    def on_dialog_result(self, e: ft.FilePickerResultEvent):
        if e.path and self.picker_target == "dest":
            self.tf_dest_dir.value = e.path; self.cfg_mgr.data["paths"]["dest_root"] = e.path; self.cfg_mgr.save()
            self._refresh_library_sidebar()
            try: self.page.update()
            except: pass

    def open_dest_folder(self, e):
        # v9.0.1: インジェストしたデータの保存先フォルダを開く
        p = self.cfg_mgr.data["paths"]["dest_root"]
        if not p or not os.path.exists(p):
            self.show_snack("保存先フォルダが見つかりません", COLOR_ERROR)
            return
        try:
            if platform.system() == "Darwin": subprocess.run(["open", p])
            elif platform.system() == "Windows": os.startfile(p)
            else: subprocess.run(["xdg-open", p])
        except Exception as ex: self.show_snack(f"エラー: {ex}", COLOR_ERROR)

    def open_projects_folder(self, e):
        # v8.0.13: プロジェクト管理ファイル(.umis)の保存先(PROJECTS_DIR)を開く
        p = str(PROJECTS_DIR)
        PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
        try:
            if platform.system() == "Darwin": subprocess.run(["open", p])
            elif platform.system() == "Windows": os.startfile(p)
            else: subprocess.run(["xdg-open", p])
        except Exception as ex: self.show_snack(f"エラー: {ex}", COLOR_ERROR)

    def manual_create_new_project(self, e):
        tf = ft.TextField(label="プロジェクト名", autofocus=True)
        def create(ev):
            val = self.sanitize_text(tf.value)
            if val:
                self._close_active_modal()
                self.close_settings_modal()
                self.cfg_mgr = ConfigManager(val)
                self.load_config_to_ui()
                self.refresh_project_list()
        self._open_modal_dialog(
            "新規プロジェクト",
            tf,
            [
                ft.TextButton("作成", on_click=create),
                ft.TextButton("キャンセル", on_click=self._close_active_modal),
            ],
        )

    def manual_save_project(self, e):
        self.cfg_mgr.save(); self.show_snack("プロジェクトを保存しました", COLOR_SUCCESS)

    def save_project_as(self, e):
        tf = ft.TextField(label="新しいプロジェクト名", autofocus=True)
        def save(ev):
            val = self.sanitize_text(tf.value)
            if val:
                self.cfg_mgr.save_as(val)
                self._close_active_modal()
                self.close_settings_modal()
                self.cfg_mgr = ConfigManager(val)
                self.load_config_to_ui()
                self.refresh_project_list()
        self._open_modal_dialog(
            "別名保存",
            tf,
            [
                ft.TextButton("保存", on_click=save),
                ft.TextButton("キャンセル", on_click=self._close_active_modal),
            ],
        )

    def delete_project(self, e):
        def dele(ev):
            self.cfg_mgr.delete_project()
            self._close_active_modal()
            self.close_settings_modal()
            self.cfg_mgr = ConfigManager("初期プロジェクト")
            self.load_config_to_ui()
            self.refresh_project_list()
            self.show_snack("設定を初期化しました", COLOR_SUCCESS)
        msg = "初期プロジェクトをリセットしますか？" if self.cfg_mgr.project_name == "初期プロジェクト" else f"{self.cfg_mgr.project_name} を削除しますか？"
        self._open_modal_dialog(
            "削除確認",
            ft.Text(msg, color=COLOR_TEXT_MAIN),
            [
                ft.TextButton("はい", on_click=dele, style=ft.ButtonStyle(color=COLOR_ERROR)),
                ft.TextButton("キャンセル", on_click=self._close_active_modal),
            ],
        )

    def save_opts(self, e):
        opts = self.cfg_mgr.data["options"]
        opts["use_location_name"] = self.sw_rename_venue.value
        opts["use_scene_name"] = self.sw_rename_scene.value
        opts["use_photographer_name"] = self.sw_rename_pg.value
        opts["use_card_id"] = self.sw_rename_id.value
        opts["use_date"] = self.sw_rename_date.value
        opts["date_format"] = self.dd_date_format.value or "%y%m%d"
        opts["use_sequential_numbering"] = self.sw_rename_seq.value
        opts["show_file_log"] = self.sw_show_file_log.value
        opts["scene_numbering"] = self.sw_scene_numbering.value
        opts["emergency_fmt"] = self.sw_emergency_fmt.value
        opts["create_sub_folder"] = self.sw_create_sub_folder.value
        opts["sub_folder_name"] = self.sanitize_text(self.tf_sub_folder_name.value)
        self.check_format_button_state(); self.refresh_scene_buttons()
        self.cfg_mgr.save(); self.update_preview()

    def update_cat_status_icons(self):
        # v9.3.9: 直接オンオフ可能なアイコンに変更
        self.row_cat_status.controls.clear()
        for cat, conf in self.cfg_mgr.data["category_settings"].items():
            disabled = conf.get("disabled", False)
            icon_data = CAT_ICONS.get(cat)
            
            def toggle_cat(e, c=cat):
                c_conf = self.cfg_mgr.data["category_settings"][c]
                new_state = not c_conf.get("disabled", False)
                c_conf["disabled"] = new_state
                
                # v9.3.10: カテゴリをオフにした場合、そのカテゴリの選択を解除する
                if new_state: # disabled=True になった場合
                    for f in self.source_files:
                        if f['cat'] == c:
                            f['selected'] = False
                
                self.cfg_mgr.save()
                self.update_cat_status_icons()
                self.refresh_thumbnail_grid()
                self.update_preview()
            
            self.row_cat_status.controls.append(
                ft.IconButton(
                    icon=icon_data[0],
                    icon_color=icon_data[1] if not disabled else COLOR_DISABLED_BTN_TEXT,
                    icon_size=20,
                    tooltip=f"{cat}: {'表示中' if not disabled else '非表示'}",
                    on_click=toggle_cat,
                    padding=0
                )
            )
        try: self.row_cat_status.update()
        except: pass

    def update_preview(self):
        pg = self.current_photographer
        drive = self.dd_drive.value
        drive_valid = bool(drive and drive != "ドライブを接続")
        assigned_count = sum(1 for f in self.source_files if f['assigned_scene'] is not None)
        pg_valid = any((p if isinstance(p, str) else p.get("name", "")) == pg for p in self.cfg_mgr.data["photographers"]) if pg else False
        # v7.6.3: カードIDの選択状態もバリデーションに含める
        cid_valid = bool(self.current_card_id)
        worker_running = self.current_copy_worker and self.current_copy_worker.is_alive()
        
        if self.app_mode == "select":
            # v9.0.0: セレクトモードのバリデーション
            flagged_count = sum(1 for f in self.source_files if f.get('is_selected_for_edit'))
            ready = flagged_count > 0
            
            if ready:
                self.lbl_status.value = f"選別実行可能: {flagged_count}ファイル選択中"
                self.lbl_status.color = COLOR_SELECT_MODE
            else:
                self.lbl_status.value = "[選別するファイルに星マークを付けてください]"
                self.lbl_status.color = COLOR_TEXT_SEC
            
            self.lbl_rename_preview.visible = False
            
            if not worker_running:
                if self.is_complete_state:
                    self.apply_start_button_state("完了（リセット）", COLOR_SUCCESS, "white", False)
                elif ready:
                    self.apply_start_button_state("選別を実行", COLOR_SELECT_MODE, "black", False)
                else:
                    self.apply_start_button_state("選別未完了", COLOR_DISABLED_BTN_BG, COLOR_DISABLED_BTN_TEXT, True)
            return

        ready = pg_valid and cid_valid and drive_valid and assigned_count > 0

        # v7.5.1: 設定不足時のUIハイライト
        highlight_color = COLOR_ERROR if not ready and not worker_running else "transparent"
        
        # v8.0.15: ボタンのスタイル更新方法を安全な形に変更
        border_side = ft.BorderSide(2, COLOR_ERROR) if not pg_valid else ft.BorderSide(1, "transparent")
        self.btn_select_identity.style = ft.ButtonStyle(
            bgcolor=COLOR_BG_CARD,
            color=COLOR_TEXT_MAIN,
            shape=ft.RoundedRectangleBorder(radius=8),
            side={"": border_side},
            padding=ft.padding.symmetric(horizontal=10, vertical=8),
        )
        
        # 2. ソースドライブ
        self.dd_drive.border_color = COLOR_ERROR if not drive_valid else COLOR_DIVIDER
        
        # 3. シーン設定（ファイルはあるが割当がない場合）
        has_files = len(self.source_files) > 0
        self.scene_panel.border = ft.border.all(2, COLOR_ERROR) if (has_files and assigned_count == 0) else ft.border.all(1, COLOR_DIVIDER)

        if ready:
            self.lbl_status.value = f"準備完了: {assigned_count}ファイル割当済"
            self.lbl_status.color = COLOR_TEXT_MAIN
            sample_scene = self.selected_scene_info or {"day": 1, "num": 1, "name": "サンプル"}
            sample_scene_copy = sample_scene.copy()
            sample_scene_copy['venue'] = self.dd_venue.value
            card_id = self.current_card_id or "00"
            date_fmt = self.cfg_mgr.data["options"].get("date_format", "%y%m%d")
            date_str = datetime.datetime.now().strftime(date_fmt)
            use_seq = self.cfg_mgr.data["options"].get("use_sequential_numbering", False)
            file_body = "0001.jpg" if use_seq else "sample.jpg"
            sample_name = self.cfg_mgr.generate_filename(sample_scene_copy, pg, card_id, file_body, date_str)
            self.lbl_rename_preview.value = f"リネーム例: {sample_name}"
            self.lbl_rename_preview.visible = True
        else:
            missing = []
            if not drive_valid: missing.append("ドライブ")
            if not pg_valid: missing.append("カメラマン")
            if not cid_valid: missing.append("カードID")
            if has_files and assigned_count == 0: missing.append("シーン割当")
            self.lbl_status.value = f"[設定不足: {', '.join(missing)}]"
            self.lbl_status.color = COLOR_TEXT_SEC
            self.lbl_rename_preview.visible = False

        if not worker_running:
            if self.is_complete_state:
                self.apply_start_button_state("完了（リセット）", COLOR_SUCCESS, "white", False)
            elif ready:
                self.apply_start_button_state("取り込み開始", COLOR_SUCCESS, "white", False)
            else:
                self.apply_start_button_state("設定不足", COLOR_DISABLED_BTN_BG, COLOR_DISABLED_BTN_TEXT, True)
        self.check_format_button_state()
        try: self.page.update()
        except: pass

    def load_config_to_ui(self):
        pgs = self.cfg_mgr.data.get("photographers", [])
        if pgs:
            self.current_photographer = pgs[0] if isinstance(pgs[0], str) else pgs[0].get('name', '')
        else:
            self.current_photographer = None
        cids = self.cfg_mgr.data.get("card_ids", ["01"])
        self.current_card_id = cids[0] if cids else "01"
        self._update_identity_button()
        locs = self.cfg_mgr.data.get("locations", ["未指定"])
        self.dd_venue.options = [ft.dropdown.Option(v) for v in locs]
        self.dd_venue.value = self.cfg_mgr.data.get("current_location", locs[0] if locs else None)
        self.radio_day.value = "0"; self.selected_scene_info = None
        self.tf_dest_dir.value = self.cfg_mgr.data["paths"]["dest_root"]
        opts = self.cfg_mgr.data["options"]
        self.sw_rename_venue.value = opts.get("use_location_name", False)
        self.sw_rename_scene.value = opts.get("use_scene_name", True)
        self.sw_rename_pg.value = opts.get("use_photographer_name", True)
        self.sw_rename_id.value = opts.get("use_card_id", True)
        self.sw_rename_date.value = opts.get("use_date", True)
        self.dd_date_format.value = opts.get("date_format", "%y%m%d")
        self.sw_rename_seq.value = opts.get("use_sequential_numbering", False)
        self.sw_show_file_log.value = opts.get("show_file_log", True)
        self.sw_scene_numbering.value = opts.get("scene_numbering", True)
        self.sw_emergency_fmt.value = opts.get("emergency_fmt", False)
        self.sw_create_sub_folder.value = opts.get("create_sub_folder", False)
        self.tf_sub_folder_name.value = opts.get("sub_folder_name", "選別")
        self.refresh_day_radio(); self.refresh_scene_buttons()
        self.update_cat_status_icons()
        self.check_format_button_state(); self.update_preview()
        self.refresh_project_list()
        self.update_header() # v7.6.6: ロード完了後にヘッダー表示を同期
        try: self.page.update()
        except: pass

    def drive_monitor(self):
        self.set_status("ドライブ監視中...", spinning=True)
        last_drive_set = set()
        while True:
            drives = []; new_map = {}
            try:
                for p in psutil.disk_partitions(all=False):
                    if 'removable' in p.opts or 'cdrom' in p.opts or p.mountpoint.startswith('/Volumes'):
                        label = "名称未設定"
                        try:
                            if platform.system() == "Windows": label = subprocess.check_output(f'vol {p.device.strip(":")}', shell=True).decode('mbcs').splitlines()[-1].split()[-1]
                            else: label = os.path.basename(p.mountpoint) or "No Name"
                        except: pass
                        drv = f"{label} ({p.device})" if platform.system() != "Windows" else f"{p.device} [{label}]"
                        excluded = self.cfg_mgr.data["options"].get("excluded_source_drives", [])
                        if drv not in excluded: drives.append(drv); new_map[drv] = p.mountpoint
            except: pass
            current_drive_set = set(drives)
            if current_drive_set == last_drive_set:
                time.sleep(1.5)
                continue
            last_drive_set = current_drive_set
            self.drive_map = new_map
            if not drives:
                self.dd_drive.options = [ft.dropdown.Option("ドライブを接続", disabled=True)]
                self.dd_drive.value = "ドライブを接続"
                self.source_files.clear()
                self.scene_assignments.clear()
                self._scan_id += 1
                self._is_scanning = False
                self._scanning_row.visible = False
                self.refresh_thumbnail_grid()
                self.update_preview()
            else:
                self.dd_drive.options = [ft.dropdown.Option(d) for d in drives]
                prev = self.dd_drive.value
                if prev not in drives:
                    self.dd_drive.value = drives[0]
                is_tut = hasattr(self, 'tutorial_overlay') and self.tutorial_overlay.visible
                is_first = self.cfg_mgr.data.get('is_first_run', True)
                if self.dd_drive.value != prev or (prev not in last_drive_set):
                    if not is_tut and not is_first:
                        self._start_scan()
                    else:
                        self.update_preview()
                else:
                    self.update_preview()
            try: self.page.update()
            except: pass
            time.sleep(1.5)

    def check_for_updates(self):
        """v1.1.32: 起動時にバックグラウンドでアップデートを確認"""
        # 実装例: GitHubのrawファイルなどを指定
        UPDATE_URL = "https://raw.githubusercontent.com/user/repo/main/version.json"
        
        try:
            # タイムアウトを設定してリクエスト
            req = urllib.request.Request(UPDATE_URL, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=5) as response:
                data = json.loads(response.read().decode('utf-8'))
                latest_version = data.get("version")
                update_url = data.get("url")
                notes = data.get("notes", "新機能が追加されました。")
                
                if latest_version and latest_version > VERSION:
                    # メインスレッドでダイアログを表示
                    self.show_update_dialog(latest_version, update_url, notes)
        except Exception as e:
            # エラー時は静かに終了
            print(f"Update check failed: {e}")

    def show_update_dialog(self, latest_version, update_url, notes):
        """アップデート通知ダイアログを表示"""
        def on_update_click(e):
            self._close_active_modal()
            threading.Thread(target=self.execute_update, args=(update_url,), daemon=True).start()

        content = ft.Column([
            ft.Text(f"新しいバージョン (v{latest_version}) が利用可能です。", size=14, weight="bold"),
            ft.Text(f"現在のバージョン: v{VERSION}", size=12, color=COLOR_TEXT_SEC),
            ft.Divider(height=10, color="transparent"),
            ft.Text("更新内容:", size=12, weight="bold"),
            ft.Text(notes, size=12),
        ], tight=True, spacing=5, width=400)

        self._open_modal_dialog(
            "アップデートの確認",
            content,
            [
                ft.TextButton("今すぐ更新して再起動", on_click=on_update_click, style=ft.ButtonStyle(color=COLOR_PRIMARY)),
                ft.TextButton("後で", on_click=self._close_active_modal),
            ]
        )

    def execute_update(self, update_url):
        """アップデートの実行ロジック"""
        self.set_status("アップデートをダウンロード中...", spinning=True)
        try:
            # 1. ファイルを一時保存
            with tempfile.NamedTemporaryFile(delete=False, suffix=".py") as tmp:
                req = urllib.request.Request(update_url, headers={'User-Agent': 'Mozilla/5.0'})
                with urllib.request.urlopen(req) as response:
                    tmp.write(response.read())
                temp_file = tmp.name
            
            # 2. 現在のスクリプトパスを取得
            current_script = os.path.abspath(sys.argv[0])
            
            # 3. 差し替え用スクリプトの起動
            if platform.system() == "Windows":
                updater_script = f"""@echo off
timeout /t 2 /nobreak > nul
move /y "{temp_file}" "{current_script}"
start python "{current_script}"
del "%~f0"
"""
                updater_path = os.path.join(tempfile.gettempdir(), "umis_updater.bat")
                with open(updater_path, "w", encoding="cp932") as f:
                    f.write(updater_script)
                subprocess.Popen([updater_path], shell=True)
            else:
                updater_script = f"""#!/bin/bash
sleep 2
mv -f "{temp_file}" "{current_script}"
python3 "{current_script}" &
rm "$0"
"""
                updater_path = os.path.join(tempfile.gettempdir(), "umis_updater.sh")
                with open(updater_path, "w") as f:
                    f.write(updater_script)
                os.chmod(updater_path, 0o755)
                subprocess.Popen(["sh", updater_path])
            
            # アプリを終了
            self.page.window_close()
            
        except Exception as e:
            print(f"Update execution failed: {e}")
            self.show_snack(f"アップデートに失敗しました: {e}", COLOR_ERROR)
            self.set_status("アップデート失敗")

def main(page: ft.Page):
    try:
        page.title = f"{APP_NAME} v{VERSION}"
        page.update()
        app = RinkanUMISApp(page)
        page.update()
    except Exception as e:
        import traceback
        err_msg = traceback.format_exc()
        try:
            page.clean()
            page.add(
                ft.Container(
                    content=ft.Column([
                        ft.Text("致命的なエラーが発生しました", color="red", size=20, weight="bold"),
                        ft.Text(err_msg, color="white", selectable=True, size=12)
                    ], scroll="auto"),
                    padding=20, bgcolor="black", expand=True
                )
            )
            page.update()
        except: pass
        print(f"ERROR: {e}")

if __name__ == "__main__":
    ft.app(target=main)

