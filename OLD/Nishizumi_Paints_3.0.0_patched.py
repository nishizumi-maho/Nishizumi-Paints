#!/usr/bin/env python3
"""Nishizumi Paints.
A lightweight iRacing paint session watcher with a very small built-in UI.
It watches the current session, downloads the matching paints, refreshes the
textures in iRacing, and cleans up session files when you leave.
"""
from __future__ import annotations
import argparse
import bz2
import concurrent.futures
import json
import logging
import os
import queue
import socket
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
import webbrowser
import re
import hashlib
import random
import xml.etree.ElementTree as ET
from collections import Counter
from dataclasses import asdict, dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable
import requests
import yaml
from requests.adapters import HTTPAdapter

try:
    from playwright.sync_api import sync_playwright
except Exception:  # pragma: no cover
    sync_playwright = None
APP_NAME = "Nishizumi Paints"
APP_VERSION = "3.0.0"
APP_REGISTRY_NAME = "NishizumiPaints"
APP_CONFIG_DIRNAME = "NishizumiPaints"
APP_TOOLTIP = f"{APP_NAME} {APP_VERSION}"
APP_USER_AGENT = f"nishizumi-paints/{APP_VERSION}"
DEFAULT_SHOWROOM_PARAMS = (
    "sort=popular&ad=DESC&search=&reuse=1&family=1&hasnumber=1&from=everyone&stampednums=1&official_only=0"
)
TP_SHOWROOM_FETCH_PAGE_SIZE = 24
TP_SHOWROOM_MAX_PAGES = 20
TP_RECENT_SCHEMES_FILENAME = ".nishizumi_tp_recent_schemes.json"
TP_RECENT_SCHEMES_HISTORY_LIMIT = 256
TP_SHOWROOM_MAPPING_FILENAME = "tp_showroom_mapping.seed.json"
TP_LOGIN_STATUS_FILENAME = ".nishizumi_tp_login_status.json"
TP_ORIGINAL_SCHEME_CACHE_FILENAME = ".nishizumi_tp_original_scheme_cache.json"
SUPER_SPEEDWAY_TRACK_KEYWORDS = ("talladega", "iracing superspeedway")
DAYTONA_TRACK_KEYWORD = "daytona"
DAYTONA_NON_SS_CONFIG_KEYWORDS = ("road", "sports car", "bike", "moto", "24h", "chicane")
GITHUB_RELEASE_OWNER = "nishizumi-maho"
GITHUB_RELEASE_REPO = "Nishizumi-Paints"
GITHUB_RELEASES_API_LATEST = f"https://api.github.com/repos/{GITHUB_RELEASE_OWNER}/{GITHUB_RELEASE_REPO}/releases/latest"
GITHUB_RELEASES_PAGE_LATEST = f"https://github.com/{GITHUB_RELEASE_OWNER}/{GITHUB_RELEASE_REPO}/releases/latest"
GITHUB_API_VERSION = "2022-11-28"
GITHUB_UPDATE_CHECK_INTERVAL_SECONDS = 6 * 60 * 60
TRADING_PAINTS_FETCH_CONTEXT_URLS = (
    "https://dl.tradingpaints.com/fetch.php",
    "https://fetch.tradingpaints.gg/fetch.php",
)
TRADING_PAINTS_COLLECTIONS_URL = "https://fetch.tradingpaints.gg/collections.php?user={member_id}"
AI_SPECIAL_CAR_IDS_WITH_DEFAULT_DESIGN = {27, 179}
AI_ROSTER_META_FILENAME = ".nishizumi_ai_roster.json"
AI_LOCAL_ROSTER_SUFFIX = " (local)"
REPLAY_PACK_INDEX_FILENAME = ".nishizumi_replay_packs.json"
REPLAY_PACK_MANIFEST_FILENAME = "manifest.json"
APP_ICON_ICO = "nishizumi_paints_icon.ico"
APP_ICON_PNG = "nishizumi_paints_icon.png"
INSTANCE_HOST = "127.0.0.1"
INSTANCE_PORT = 45891
INSTANCE_MUTEX_NAME = r"Local\NishizumiPaintsSingleInstance"
HEADLESS_CONTROL_HOST = "127.0.0.1"
HEADLESS_CONTROL_PORT = 45892
HEADLESS_CONTROL_CONNECT_TIMEOUT = 1.5
def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


def canonicalize_car_directory(value: str | None) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    text = text.replace("/", "\\")
    text = re.sub(r"\\+", r"\\", text)
    if "\\" in text:
        parts = [part.strip() for part in text.split("\\") if part.strip()]
        return "\\".join(parts)
    if " " in text:
        parts = [part.strip() for part in text.split() if part.strip()]
        if len(parts) >= 2:
            return "\\".join(parts)
    return text

def default_tp_showroom_mapping_path() -> Path:
    return resource_path(TP_SHOWROOM_MAPPING_FILENAME)


def default_tp_showroom_profile_dir() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "Nishizumi-Paints" / "TPAuthProfile"
    return Path.home() / "AppData" / "Roaming" / "Nishizumi-Paints" / "TPAuthProfile"


def normalize_tp_member_id(value: object) -> int:
    try:
        member_id = int(str(value or "").strip())
    except Exception:
        return 0
    return member_id if member_id > 0 else 0


def resolve_tp_manifest_member_id(member_id_override: object, local_user_id: int | None) -> int | None:
    override = normalize_tp_member_id(member_id_override)
    if override > 0:
        return override
    if local_user_id is None:
        return None
    try:
        resolved = int(local_user_id)
    except Exception:
        return None
    return resolved if resolved > 0 else None


def tp_login_status_path(profile_dir: Path | None = None) -> Path:
    base_dir = Path(profile_dir) if profile_dir is not None else default_tp_showroom_profile_dir()
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / TP_LOGIN_STATUS_FILENAME


def write_tp_login_status(profile_dir: Path | None = None, ok: bool = True, message: str = "") -> None:
    try:
        status_path = tp_login_status_path(profile_dir)
        payload = {"ok": bool(ok), "message": str(message or ""), "updated_at": time.time()}
        temp_path = status_path.with_name(status_path.name + ".tmp")
        temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temp_path, status_path)
    except Exception:
        logging.debug("Could not persist Trading Paints login status", exc_info=True)


def clear_tp_login_status(profile_dir: Path | None = None, message: str = "") -> None:
    write_tp_login_status(profile_dir, ok=False, message=message or "Trading Paints login not confirmed.")


def read_tp_login_status(profile_dir: Path | None = None) -> dict[str, object]:
    status_path = tp_login_status_path(profile_dir)
    if not status_path.exists():
        return {"ok": False, "message": "", "updated_at": 0.0}
    try:
        raw = json.loads(status_path.read_text(encoding="utf-8"))
    except Exception:
        return {"ok": False, "message": "", "updated_at": 0.0}
    if not isinstance(raw, dict):
        return {"ok": False, "message": "", "updated_at": 0.0}
    return {
        "ok": bool(raw.get("ok")),
        "message": str(raw.get("message") or ""),
        "updated_at": float(raw.get("updated_at") or 0.0),
    }


def default_tp_recent_schemes_path() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / APP_CONFIG_DIRNAME / TP_RECENT_SCHEMES_FILENAME
    return Path.home() / f".{APP_CONFIG_DIRNAME.lower()}_{TP_RECENT_SCHEMES_FILENAME}"


def load_tp_recent_schemes(path: Path | None = None) -> dict[str, list[str]]:
    resolved = Path(path) if path is not None else default_tp_recent_schemes_path()
    if not resolved.exists():
        return {}
    try:
        raw = json.loads(resolved.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    result: dict[str, list[str]] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not isinstance(value, list):
            continue
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if cleaned:
            result[str(key).strip().lower()] = cleaned[:TP_RECENT_SCHEMES_HISTORY_LIMIT]
    return result


def save_tp_recent_schemes(data: dict[str, list[str]], path: Path | None = None) -> None:
    resolved = Path(path) if path is not None else default_tp_recent_schemes_path()
    resolved.parent.mkdir(parents=True, exist_ok=True)
    payload: dict[str, list[str]] = {}
    for key, value in (data or {}).items():
        if not isinstance(key, str) or not isinstance(value, list):
            continue
        cleaned = [str(item).strip() for item in value if str(item).strip()]
        if cleaned:
            payload[str(key).strip().lower()] = cleaned[:TP_RECENT_SCHEMES_HISTORY_LIMIT]
    temp_path = resolved.with_name(resolved.name + ".tmp")
    temp_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(temp_path, resolved)


def remember_tp_recent_scheme(data: dict[str, list[str]], directory_key: str, scheme_id: str, limit: int = TP_RECENT_SCHEMES_HISTORY_LIMIT) -> None:
    key = canonicalize_car_directory(directory_key).lower()
    scheme = str(scheme_id or "").strip()
    if not key or not scheme:
        return
    current = [item for item in data.get(key, []) if str(item).strip() and str(item).strip() != scheme]
    current.insert(0, scheme)
    data[key] = current[:max(1, int(limit))]


def is_tp_login_confirmed(profile_dir: Path | None = None) -> bool:
    status = read_tp_login_status(profile_dir)
    return bool(status.get("ok"))


def _tp_text_looks_authenticated(url: str, text: str) -> bool:
    url_lower = str(url or "").lower()
    html = str(text or "").lower()
    if "tradingpaints.com" not in url_lower or "/auth" in url_lower:
        return False
    unauth_markers = (
        "sign in with steam",
        "login with steam",
        "log in with steam",
        "connect through steam",
        "steamcommunity.com/openid",
        "oauth",
    )
    if html and any(marker in html for marker in unauth_markers):
        return False
    auth_markers = (
        "event-logged-in=true",
        "logout",
        "sign out",
        "my schemes",
        "my profile",
        "account settings",
        "trading paints dashboard",
        "dashboard",
    )
    if "/dashboard" in url_lower:
        return True
    if html and any(marker in html for marker in auth_markers):
        return True
    if "/showroom" in url_lower and (not html or ("sign in" not in html and "login with steam" not in html and "connect through steam" not in html)):
        return True
    return False


def _tp_page_looks_authenticated(page) -> bool:
    try:
        url = str(page.url or "")
    except Exception:
        url = ""
    try:
        html = page.content()
    except Exception:
        html = ""
    return _tp_text_looks_authenticated(url, html)


def _tp_response_looks_authenticated(response) -> bool:
    try:
        url = str(response.url or "")
    except Exception:
        url = ""
    try:
        body = response.text()
    except Exception:
        body = ""
    return _tp_text_looks_authenticated(url, body)


def _tp_context_looks_authenticated(context, open_pages=None) -> tuple[bool, str]:
    pages = list(open_pages or [])
    if not pages:
        try:
            pages = [page for page in list(context.pages) if not page.is_closed()]
        except Exception:
            pages = []
    for candidate in reversed(pages):
        try:
            if _tp_page_looks_authenticated(candidate):
                return True, f"page:{candidate.url}"
        except Exception:
            continue
    request_checks = (
        "https://www.tradingpaints.com/dashboard",
        "https://www.tradingpaints.com/showroom/filter/from=everyone,sort=popular,ad=DESC,pos=0",
    )
    for url in request_checks:
        try:
            resp = context.request.get(
                url,
                headers={
                    "Cache-Control": "no-cache",
                    "Pragma": "no-cache",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                },
                fail_on_status_code=False,
            )
        except Exception:
            continue
        if _tp_response_looks_authenticated(resp):
            try:
                final_url = str(resp.url or url)
            except Exception:
                final_url = url
            return True, f"request:{final_url}"
    seen_urls = []
    for candidate in pages:
        try:
            seen_urls.append(str(candidate.url or ""))
        except Exception:
            continue
    return False, "open pages: " + " | ".join(seen_urls[:5])


def build_self_launch_command(*extra_args: str) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, *extra_args]
    return [sys.executable, str(Path(__file__).resolve()), *extra_args]


def normalize_launch_mode_preference(value: str | None) -> str:
    mode = str(value or "ask").strip().lower()
    if mode in {"gui", "headless", "ask"}:
        return mode
    if mode in {"nogui", "console"}:
        return "headless"
    return "ask"


def is_shift_pressed_at_startup() -> bool:
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        VK_SHIFT = 0x10
        VK_LSHIFT = 0xA0
        VK_RSHIFT = 0xA1
        user32 = ctypes.windll.user32
        return any(
            bool(user32.GetAsyncKeyState(code) & 0x8000)
            for code in (VK_SHIFT, VK_LSHIFT, VK_RSHIFT)
        )
    except Exception:
        return False


def show_launch_mode_dialog(saved_mode: str = "ask") -> tuple[str, bool] | None:
    saved_mode = normalize_launch_mode_preference(saved_mode)
    try:
        import tkinter as tk
        from tkinter import ttk
    except Exception:
        return ("gui", False)
    result: dict[str, object] = {"mode": "gui", "remember": False, "accepted": False}
    root = tk.Tk()
    root.title(APP_NAME)
    root.resizable(False, False)
    try:
        root.attributes("-topmost", True)
    except Exception:
        pass
    try:
        ico_path = resource_path(APP_ICON_ICO)
        if ico_path.exists():
            root.iconbitmap(default=str(ico_path))
        else:
            png_path = resource_path(APP_ICON_PNG)
            if png_path.exists():
                icon = tk.PhotoImage(file=str(png_path))
                root.iconphoto(True, icon)
                root._launch_mode_icon = icon
    except Exception:
        pass
    mode_var = tk.StringVar(value="gui" if saved_mode == "ask" else saved_mode)
    remember_var = tk.BooleanVar(value=False)
    frame = ttk.Frame(root, padding=14)
    frame.grid(sticky="nsew")
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    ttk.Label(frame, text=APP_NAME, font=("Segoe UI", 12, "bold")).grid(row=0, column=0, sticky="w")
    ttk.Label(
        frame,
        text="Choose how you want to start the app.",
    ).grid(row=1, column=0, sticky="w", pady=(6, 0))
    options = ttk.LabelFrame(frame, text="Startup mode", padding=10)
    options.grid(row=2, column=0, sticky="ew", pady=(12, 0))
    ttk.Radiobutton(
        options,
        text="GUI mode (full window)",
        value="gui",
        variable=mode_var,
    ).grid(row=0, column=0, sticky="w")
    ttk.Label(
        options,
        text="Best for setup, browsing options, and viewing the live interface.",
        foreground="#555555",
        justify="left",
    ).grid(row=1, column=0, sticky="w", padx=(22, 0), pady=(0, 8))
    ttk.Radiobutton(
        options,
        text="Headless mode (console only)",
        value="headless",
        variable=mode_var,
    ).grid(row=2, column=0, sticky="w")
    ttk.Label(
        options,
        text="Advanced users only. Uses less CPU/RAM and keeps running in the terminal window. Finish the first setup in the normal window first. Use --gui later if you want the full UI back.",
        foreground="#555555",
        justify="left",
        wraplength=430,
    ).grid(row=3, column=0, sticky="w", padx=(22, 0))
    if saved_mode == "ask":
        saved_text = "No launch mode is saved yet."
    else:
        saved_text = f"Saved startup choice right now: {saved_mode}. Hold Shift while opening the app to show this screen again."
    ttk.Label(frame, text=saved_text, foreground="#555555", wraplength=460, justify="left").grid(row=3, column=0, sticky="w", pady=(10, 0))
    ttk.Checkbutton(frame, text="Remember this choice", variable=remember_var).grid(row=4, column=0, sticky="w", pady=(10, 0))
    buttons = ttk.Frame(frame)
    buttons.grid(row=5, column=0, sticky="e", pady=(14, 0))
    def _accept() -> None:
        result["mode"] = normalize_launch_mode_preference(mode_var.get())
        result["remember"] = bool(remember_var.get())
        result["accepted"] = True
        root.destroy()
    def _cancel() -> None:
        root.destroy()
    ttk.Button(buttons, text="Cancel", command=_cancel).pack(side="right")
    ttk.Button(buttons, text="Start", command=_accept).pack(side="right", padx=(0, 8))
    root.bind("<Escape>", lambda _e: _cancel())
    root.bind("<Return>", lambda _e: _accept())
    root.protocol("WM_DELETE_WINDOW", _cancel)
    root.update_idletasks()
    try:
        width = root.winfo_width()
        height = root.winfo_height()
        screen_w = root.winfo_screenwidth()
        screen_h = root.winfo_screenheight()
        x = max(0, int((screen_w - width) / 2))
        y = max(0, int((screen_h - height) / 3))
        root.geometry(f"+{x}+{y}")
    except Exception:
        pass
    root.mainloop()
    if not bool(result.get("accepted")):
        return None
    return (normalize_launch_mode_preference(str(result.get("mode") or "gui")), bool(result.get("remember")))


def _get_console_window_handle() -> int:
    if sys.platform != "win32":
        return 0
    try:
        import ctypes
        return int(ctypes.windll.kernel32.GetConsoleWindow() or 0)
    except Exception:
        return 0


def show_console_window() -> None:
    hwnd = _get_console_window_handle()
    if not hwnd:
        return
    try:
        import ctypes
        SW_RESTORE = 9
        ctypes.windll.user32.ShowWindow(hwnd, SW_RESTORE)
    except Exception:
        pass


def hide_console_window() -> None:
    hwnd = _get_console_window_handle()
    if not hwnd:
        return
    try:
        import ctypes
        SW_HIDE = 0
        ctypes.windll.user32.ShowWindow(hwnd, SW_HIDE)
    except Exception:
        pass


def bring_console_to_front() -> None:
    hwnd = _get_console_window_handle()
    if not hwnd:
        return
    try:
        import ctypes
        user32 = ctypes.windll.user32
        SW_RESTORE = 9
        SW_SHOW = 5
        user32.ShowWindow(hwnd, SW_RESTORE)
        user32.ShowWindow(hwnd, SW_SHOW)
        user32.SetForegroundWindow(hwnd)
    except Exception:
        pass

@dataclass(frozen=True)
class GitHubReleaseInfo:
    tag_name: str
    html_url: str
    asset_name: str | None = None
    asset_download_url: str | None = None
    published_at: str | None = None
def _parse_version_parts(tag: str) -> tuple[int, ...]:
    cleaned = (tag or "").strip()
    if cleaned.lower().startswith("release-"):
        cleaned = cleaned[8:]
    if cleaned.lower().startswith("version"):
        cleaned = cleaned[7:]
    if cleaned.lower().startswith("v"):
        cleaned = cleaned[1:]
    nums = [int(part) for part in re.findall(r"\d+", cleaned)]
    return tuple(nums or [0])
def compare_version_tags(left: str, right: str) -> int:
    lparts = list(_parse_version_parts(left))
    rparts = list(_parse_version_parts(right))
    width = max(len(lparts), len(rparts))
    lparts.extend([0] * (width - len(lparts)))
    rparts.extend([0] * (width - len(rparts)))
    if tuple(lparts) > tuple(rparts):
        return 1
    if tuple(lparts) < tuple(rparts):
        return -1
    return 0
def _github_api_headers() -> dict[str, str]:
    return {
        "Accept": "application/vnd.github+json",
        "User-Agent": APP_USER_AGENT,
        "X-GitHub-Api-Version": GITHUB_API_VERSION,
    }
def _extract_release_info(payload: dict) -> GitHubReleaseInfo:
    if not isinstance(payload, dict):
        raise RuntimeError("GitHub update check returned an invalid response.")
    tag_name = str(payload.get("tag_name") or "").strip()
    html_url = str(payload.get("html_url") or GITHUB_RELEASES_PAGE_LATEST).strip()
    if not tag_name:
        raise RuntimeError("GitHub update check did not return a release tag.")
    asset_name = None
    asset_download_url = None
    assets = payload.get("assets")
    if isinstance(assets, list):
        preferred = None
        for asset in assets:
            if not isinstance(asset, dict):
                continue
            name = str(asset.get("name") or "").strip()
            if not name:
                continue
            if preferred is None:
                preferred = asset
            if name.lower().endswith('.exe'):
                preferred = asset
                break
        if isinstance(preferred, dict):
            asset_name = str(preferred.get("name") or "").strip() or None
            asset_download_url = str(preferred.get("browser_download_url") or "").strip() or None
    published_at = str(payload.get("published_at") or "").strip() or None
    return GitHubReleaseInfo(
        tag_name=tag_name,
        html_url=html_url or GITHUB_RELEASES_PAGE_LATEST,
        asset_name=asset_name,
        asset_download_url=asset_download_url,
        published_at=published_at,
    )
def _github_get_json(url: str, timeout: tuple[float, float] = (5.0, 12.0)) -> dict | list:
    try:
        response = requests.get(url, headers=_github_api_headers(), timeout=timeout)
    except requests.RequestException as exc:
        raise RuntimeError(f"Network error while contacting GitHub: {exc}") from exc
    if response.status_code >= 400:
        message = None
        try:
            data = response.json()
            if isinstance(data, dict):
                message = str(data.get("message") or "").strip() or None
        except Exception:
            message = None
        if response.status_code == 404:
            raise RuntimeError("No published GitHub release was found yet.")
        if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
            raise RuntimeError("GitHub rate limit reached. Please try again later.")
        detail = message or response.text[:200].strip() or f"HTTP {response.status_code}"
        raise RuntimeError(f"GitHub update check failed: {detail}")
    try:
        return response.json()
    except ValueError as exc:
        raise RuntimeError("GitHub update check returned invalid JSON.") from exc
def fetch_latest_github_release() -> GitHubReleaseInfo:
    latest_payload = _github_get_json(GITHUB_RELEASES_API_LATEST)
    if isinstance(latest_payload, dict):
        return _extract_release_info(latest_payload)
    # Defensive fallback, though /latest should return a single object.
    releases_url = f"https://api.github.com/repos/{GITHUB_RELEASE_OWNER}/{GITHUB_RELEASE_REPO}/releases?per_page=1"
    releases_payload = _github_get_json(releases_url)
    if isinstance(releases_payload, list) and releases_payload:
        first = releases_payload[0]
        if isinstance(first, dict):
            return _extract_release_info(first)
    raise RuntimeError("GitHub update check did not find a usable release.")
class SingleInstanceLock:
    def __init__(self, name: str) -> None:
        self.name = name
        self.handle = None
        self._ctypes = None
        self._owned = False
    def acquire(self) -> bool:
        if sys.platform != "win32":
            return True
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.CreateMutexW(None, True, self.name)
            if not handle:
                return True
            self.handle = handle
            self._ctypes = ctypes
            error_already_exists = 183
            if ctypes.GetLastError() == error_already_exists:
                kernel32.CloseHandle(handle)
                self.handle = None
                return False
            self._owned = True
            return True
        except Exception:
            return True
    def release(self) -> None:
        if sys.platform != "win32" or self.handle is None or self._ctypes is None:
            return
        try:
            if self._owned:
                self._ctypes.windll.kernel32.ReleaseMutex(self.handle)
        except Exception:
            pass
        try:
            self._ctypes.windll.kernel32.CloseHandle(self.handle)
        except Exception:
            pass
        self.handle = None
        self._owned = False
class SingleInstanceSignalServer:
    def __init__(self, on_activate: Callable[[], None], host: str = INSTANCE_HOST, port: int = INSTANCE_PORT) -> None:
        self.on_activate = on_activate
        self.host = host
        self.port = port
        self._sock = None
        self._stop_event = threading.Event()
        self._thread = None
    def start(self) -> bool:
        if self._thread is not None:
            return True
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            sock.bind((self.host, self.port))
            sock.listen(5)
            sock.settimeout(0.5)
        except Exception:
            try:
                sock.close()
            except Exception:
                pass
            return False
        self._sock = sock
        self._thread = threading.Thread(target=self._serve, name="NishizumiPaintsSingleInstance", daemon=True)
        self._thread.start()
        return True
    def _serve(self) -> None:
        while not self._stop_event.is_set():
            try:
                conn, _addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                with conn:
                    try:
                        conn.recv(64)
                    except Exception:
                        pass
                    try:
                        self.on_activate()
                    except Exception:
                        pass
            except Exception:
                pass
    def stop(self) -> None:
        self._stop_event.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None
    @staticmethod
    def notify_existing_instance(host: str = INSTANCE_HOST, port: int = INSTANCE_PORT, attempts: int = 8, delay: float = 0.25) -> bool:
        for _ in range(max(1, attempts)):
            try:
                with socket.create_connection((host, port), timeout=0.6) as sock:
                    sock.sendall(b"SHOW")
                    return True
            except OSError:
                time.sleep(max(0.05, delay))
        return False
class HeadlessControlServer:
    def __init__(
        self,
        service: "DownloaderService",
        config_store: "ConfigStore",
        request_shutdown: Callable[[], None],
        host: str = HEADLESS_CONTROL_HOST,
        port: int = HEADLESS_CONTROL_PORT,
    ) -> None:
        self._service = service
        self._config_store = config_store
        self._request_shutdown = request_shutdown
        self.host = host
        self.port = port
        self._sock = None
        self._stop_event = threading.Event()
        self._thread = None

    def start(self) -> bool:
        if self._thread is not None:
            return True
        sock = None
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            if sys.platform == "win32":
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
            else:
                sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((self.host, self.port))
            sock.listen(8)
            sock.settimeout(0.5)
        except Exception:
            try:
                if sock is not None:
                    sock.close()
            except Exception:
                pass
            return False
        self._sock = sock
        self._thread = threading.Thread(target=self._serve, name="NishizumiPaintsHeadlessControl", daemon=True)
        self._thread.start()
        return True

    def _serve(self) -> None:
        while not self._stop_event.is_set():
            try:
                conn, _addr = self._sock.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                with conn:
                    conn.settimeout(1.0)
                    chunks: list[bytes] = []
                    while True:
                        try:
                            chunk = conn.recv(65536)
                        except socket.timeout:
                            break
                        if not chunk:
                            break
                        chunks.append(chunk)
                        if len(chunk) < 65536:
                            break
                    try:
                        request = json.loads(b"".join(chunks).decode("utf-8")) if chunks else {}
                    except Exception:
                        request = {}
                    response = self._handle_command(request if isinstance(request, dict) else {})
                    conn.sendall(json.dumps(response, ensure_ascii=False).encode("utf-8"))
            except Exception:
                logging.debug("Headless control request failed", exc_info=True)

    def _handle_command(self, request: dict[str, object]) -> dict[str, object]:
        command = str(request.get("command") or "").strip().lower()
        if command in {"ping", "hello"}:
            return {"ok": True, "mode": "headless", "app": APP_NAME, "version": APP_VERSION}
        if command == "status":
            snapshot = self._service.get_runtime_snapshot()
            current_session = snapshot.current_session.session_id.folder_name() if snapshot.current_session is not None else ""
            return {
                "ok": True,
                "mode": "headless",
                "service_running": self._service.is_running(),
                "service_status": self._service.get_status(),
                "current_session": current_session,
                "session_driver_count": len(snapshot.session_rows),
                "replay_mode_active": bool(getattr(snapshot, "replay_mode_active", False)),
            }
        if command == "reload_config":
            config = self._config_store.load()
            self._service.update_config(config)
            return {"ok": True, "reloaded": True}
        if command == "stop":
            threading.Thread(target=self._request_shutdown, name="NishizumiPaintsHeadlessShutdown", daemon=True).start()
            return {"ok": True, "stopping": True}
        return {"ok": False, "error": f"Unknown command: {command or 'empty'}"}

    def stop(self) -> None:
        self._stop_event.set()
        if self._sock is not None:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        if self._thread is not None and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        self._thread = None


def send_headless_control_command(
    command: str,
    payload: dict[str, object] | None = None,
    host: str = HEADLESS_CONTROL_HOST,
    port: int = HEADLESS_CONTROL_PORT,
    timeout: float = HEADLESS_CONTROL_CONNECT_TIMEOUT,
) -> dict[str, object] | None:
    request = {"command": command}
    if payload:
        request.update(payload)
    try:
        with socket.create_connection((host, port), timeout=timeout) as sock:
            sock.settimeout(timeout)
            sock.sendall(json.dumps(request, ensure_ascii=False).encode("utf-8"))
            try:
                sock.shutdown(socket.SHUT_WR)
            except Exception:
                pass
            chunks: list[bytes] = []
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
            if not chunks:
                return None
            response = json.loads(b"".join(chunks).decode("utf-8"))
            return response if isinstance(response, dict) else None
    except Exception:
        return None


def is_headless_service_available() -> bool:
    response = send_headless_control_command("ping")
    return bool(response and response.get("ok"))

class PaintType(str, Enum):
    CAR = "car"
    CAR_DECAL = "car_decal"
    CAR_NUMBER = "car_num"
    CAR_SPEC = "car_spec"
    HELMET = "helmet"
    SUIT = "suit"
@dataclass(frozen=True)
class SessionId:
    main_session_id: int
    sub_session_id: int | None
    def folder_name(self) -> str:
        if self.sub_session_id is None:
            return str(self.main_session_id)
        return f"{self.main_session_id}_{self.sub_session_id}"
def _normalize_ss_token(value: str | None) -> str:
    return normalize_directory(value or "")
def _is_superspeedway_track(track_name: str, track_display_name: str, track_config_name: str) -> bool:
    name_token = _normalize_ss_token(track_name)
    display_token = _normalize_ss_token(track_display_name)
    config_token = _normalize_ss_token(track_config_name)
    haystack = " ".join(part for part in (name_token, display_token, config_token) if part)
    if not haystack:
        return False
    if any(keyword in haystack for keyword in SUPER_SPEEDWAY_TRACK_KEYWORDS):
        return True
    if DAYTONA_TRACK_KEYWORD not in haystack:
        return False
    if config_token and any(keyword in config_token for keyword in DAYTONA_NON_SS_CONFIG_KEYWORDS):
        return False
    return True
def _is_car_related_paint_type(paint_type: PaintType) -> bool:
    return paint_type in {PaintType.CAR, PaintType.CAR_DECAL, PaintType.CAR_NUMBER, PaintType.CAR_SPEC}
def _download_uses_superspeedway_variant(directory: str, paint_type: PaintType, is_superspeedway_track: bool) -> bool:
    if not is_superspeedway_track:
        return False
    return _is_car_related_paint_type(paint_type)
@dataclass(frozen=True)
class SessionUser:
    user_id: int
    directory: str
    team_id: int | None = None
    number: str = "0"
    paint_ext: str = ""
    is_ai: bool = False
    display_name: str = ""
    car_idx: int | None = None
    irating: int | None = None
    license_label: str = "-"
    safety_rating: str = "-"
    def effective_target_key(self) -> tuple[str, int, str]:
        target_kind = "team" if self.team_id is not None and self.team_id > 0 else "user"
        target_id = self.team_id if target_kind == "team" else self.user_id
        return (target_kind, int(target_id), self.directory.lower())
    def trading_paints_list_value(self) -> str:
        return f"{self.user_id}={self.directory}={self.team_id or 0}={self.number or '0'}={self.paint_ext or ''}"
@dataclass(frozen=True)
class Session:
    session_id: SessionId
    users: set[SessionUser]
    local_user_id: int | None = None
    local_team_id: int | None = None
    team_racing: bool = False
    event_time_raw: str = "10:00 am"
    series_id: int = 0
    league_id: int = 0
    load_num_textures: bool = False
    track_name: str = ""
    track_display_name: str = ""
    track_config_name: str = ""
    is_superspeedway_track: bool = False
    ai_driver_count: int = 0
    ai_roster_id: str = ""
    ai_roster_name: str = ""
    ai_drivers: tuple[dict, ...] = ()
    def fingerprint(self) -> tuple[SessionId, tuple[tuple[str, int, str], ...], tuple[bool, str, int, int, bool, str, str, bool]]:
        normalized_users = tuple(sorted(u.effective_target_key() for u in self.users))
        context_bits = (
            self.team_racing,
            (self.event_time_raw or "10:00 am").strip().lower(),
            int(self.series_id),
            int(self.league_id),
            bool(self.load_num_textures),
            normalize_directory(self.track_name),
            normalize_directory(self.track_config_name),
            bool(self.is_superspeedway_track),
        )
        return (self.session_id, normalized_users, context_bits)
    def local_preserve_targets(self) -> set[tuple[bool, int]]:
        targets: set[tuple[bool, int]] = set()
        if self.local_user_id is not None and self.local_user_id > 0:
            targets.add((False, self.local_user_id))
        if self.local_team_id is not None and self.local_team_id > 0:
            targets.add((True, self.local_team_id))
        return targets
    def trading_paints_context(self) -> dict[str, str] | None:
        if self.local_user_id is None or self.local_user_id <= 0:
            return None
        return {
            "team": "1" if self.team_racing else "0",
            "user": str(self.local_user_id),
            "night": self.event_time_raw or "10:00 am",
            "series": str(int(self.series_id or 0)),
            "league": str(int(self.league_id or 0)),
            "numbers": "True" if self.load_num_textures else "False",
        }
@dataclass(frozen=True)
class DownloadId:
    user_id: int
    directory: str
    paint_type: PaintType
    is_team_paint: bool = False
    is_superspeedway_variant: bool = False
@dataclass(frozen=True)
class DownloadFile:
    download_id: DownloadId
    url: str
@dataclass(frozen=True)
class DownloadedFile:
    session_id: SessionId
    download_id: DownloadId
    file_path: Path
@dataclass(frozen=True)
class SavedFile:
    session_id: SessionId
    download_id: DownloadId
    file_path: Path
@dataclass(frozen=True)
class AIWebRosterItem:
    roster_id: str
    name: str
    roster_file: str
@dataclass(frozen=True)
class RandomPoolEntry:
    source_id: str
    directory: str
    car_file: Path
    spec_file: Path | None = None
    decal_file: Path | None = None
    source_kind: str = "pool"
@dataclass(frozen=True)
class RandomPoolStats:
    total_bytes: int = 0
    set_count: int = 0
    car_count: int = 0
@dataclass
class RandomFallbackSummary:
    attempted_targets: int = 0
    applied_targets: int = 0
    missing_source_targets: int = 0
    repeated_source_uses: int = 0
@dataclass
class AIRosterSyncResult:
    member_id: int
    discovered: int = 0
    downloaded: int = 0
    failed: int = 0
    ai_rosters_dir: Path | None = None
@dataclass
class IracingSdkReader:
    sdk: object
    last_update: int | None = None
class SdkPollState(str, Enum):
    SESSION = "session"
    UNCHANGED = "unchanged"
    INACTIVE = "inactive"
    INVALID = "invalid"
@dataclass
class PendingTextureReload:
    fingerprint: tuple[SessionId, tuple[tuple[int, str], ...]]
    first_requested_at: float
    wait_log_emitted: bool = False
@dataclass
class StageTransferStats:
    stage_name: str
    requested_workers: int = 0
    total_items: int = 0
    completed_items: int = 0
    failed_items: int = 0
    peak_active_items: int = 0
    stage_seconds: float = 0.0
    average_item_seconds: float = 0.0
    files_per_second: float = 0.0
    megabits_per_second: float = 0.0
    total_bytes: int = 0
    effective_parallelism: float = 0.0
@dataclass
class ThroughputMonitorSnapshot:
    session_name: str = "-"
    worker_mode: str = "auto"
    manifest_workers: int = 0
    download_workers: int = 0
    save_workers: int = 0
    queued_items: int = 0
    downloaded_items: int = 0
    saved_items: int = 0
    download_stage_seconds: float = 0.0
    save_stage_seconds: float = 0.0
    download_files_per_second: float = 0.0
    save_files_per_second: float = 0.0
    average_download_seconds: float = 0.0
    average_save_seconds: float = 0.0
    average_download_mbps: float = 0.0
    peak_active_downloads: int = 0
    effective_parallelism: float = 0.0
    ceiling_hint: str = "Not enough data yet"
    best_effective_parallelism: float = 0.0
    best_download_files_per_second: float = 0.0
    updated_at: float = 0.0
@dataclass
class RuntimeSnapshot:
    current_session: Session | None = None
    last_saved: list[SavedFile] = field(default_factory=list)
    last_known_member_id: int | None = None
    session_rows: list["SessionDriverSnapshot"] = field(default_factory=list)
    replay_mode_active: bool = False

@dataclass(frozen=True)
class SessionDriverSnapshot:
    target_kind: str
    target_id: int
    directory: str
    display_name: str
    number: str = "0"
    is_ai: bool = False
    irating: int | None = None
    license_label: str = "-"
    safety_rating: str = "-"
    status_code: str = "queued"
    status_text: str = "Queued"
    status_icon: str = "…"

def session_target_key_from_download_id(download_id: DownloadId) -> tuple[str, int, str]:
    return ("team" if download_id.is_team_paint else "user", int(download_id.user_id), download_id.directory.lower())

def _session_driver_sort_number(number: str) -> tuple[int, str]:
    match = re.search(r"(\d+)", str(number or ""))
    if match:
        return (0, f"{int(match.group(1)):08d}")
    text = str(number or "").strip()
    return (1, text.lower() or "zzzz")

def _session_status_meta(status_code: str) -> tuple[str, str]:
    mapping = {
        "queued": ("…", "Queued"),
        "downloading": ("↓", "Downloading"),
        "downloaded": ("✓", "Downloaded"),
        "replay": ("▶", "Replay pack"),
        "fallback": ("↺", "Fallback"),
        "fallback_local": ("↺", "FALLBACK LOCAL"),
        "fallback_online": ("↺", "FALLBACK ONLINE"),
        "missing": ("✕", "Missing"),
        "skipped": ("○", "Skipped"),
    }
    return mapping.get(status_code, ("?", status_code.title()))

def build_session_driver_rows(session: Session | None, status_by_key: dict[tuple[str, int, str], str] | None = None) -> list[SessionDriverSnapshot]:
    if session is None:
        return []
    status_by_key = status_by_key or {}
    rows: list[SessionDriverSnapshot] = []
    for user in session.users:
        status_code = str(status_by_key.get(user.effective_target_key(), "queued") or "queued")
        icon, label = _session_status_meta(status_code)
        rows.append(
            SessionDriverSnapshot(
                target_kind="team" if user.team_id is not None and user.team_id > 0 else "user",
                target_id=int(user.team_id if user.team_id is not None and user.team_id > 0 else user.user_id),
                directory=user.directory,
                display_name=user.display_name or (f"AI {user.user_id}" if user.is_ai else f"User {user.user_id}"),
                number=user.number or "0",
                is_ai=bool(user.is_ai),
                irating=user.irating,
                license_label=user.license_label or "-",
                safety_rating=user.safety_rating or "-",
                status_code=status_code,
                status_text=label,
                status_icon=icon,
            )
        )
    rows.sort(key=lambda row: (_session_driver_sort_number(row.number), row.display_name.lower(), row.directory.lower(), row.target_id))
    return rows

def build_session_stage_statuses(
    session: Session,
    wanted_items: list[DownloadFile],
    sync_my_livery_from_server: bool,
) -> dict[tuple[str, int, str], str]:
    wanted_keys = {session_target_key_from_download_id(item.download_id) for item in wanted_items}
    statuses: dict[tuple[str, int, str], str] = {}
    for user in session.users:
        key = user.effective_target_key()
        local_team_match = session.local_team_id is not None and user.team_id == session.local_team_id
        local_user_match = session.local_user_id is not None and user.user_id == session.local_user_id
        if not sync_my_livery_from_server and (local_team_match or local_user_match):
            statuses[key] = "skipped"
        elif key in wanted_keys:
            statuses[key] = "downloading"
        else:
            statuses[key] = "missing"
    return statuses

def build_session_final_statuses(
    session: Session,
    wanted_items: list[DownloadFile],
    server_saved: list[SavedFile],
    fallback_saved: list[SavedFile],
    sync_my_livery_from_server: bool,
    replay_mode: bool = False,
    fallback_mode: str = "local",
) -> dict[tuple[str, int, str], str]:
    wanted_keys = {session_target_key_from_download_id(item.download_id) for item in wanted_items}
    server_keys = {session_target_key_from_download_id(item.download_id) for item in server_saved}
    fallback_keys = {session_target_key_from_download_id(item.download_id) for item in fallback_saved}
    statuses: dict[tuple[str, int, str], str] = {}
    for user in session.users:
        key = user.effective_target_key()
        local_team_match = session.local_team_id is not None and user.team_id == session.local_team_id
        local_user_match = session.local_user_id is not None and user.user_id == session.local_user_id
        if key in server_keys:
            statuses[key] = "replay" if replay_mode else "downloaded"
        elif key in fallback_keys:
            normalized_fallback_mode = str(fallback_mode or "local").strip().lower()
            statuses[key] = "fallback_online" if normalized_fallback_mode == "online" else "fallback_local"
        elif not sync_my_livery_from_server and (local_team_match or local_user_match):
            statuses[key] = "skipped"
        elif key in wanted_keys:
            statuses[key] = "missing"
        else:
            statuses[key] = "missing"
    return statuses
class TransferBatchMonitor:
    def __init__(self, stage_name: str, requested_workers: int, total_items: int) -> None:
        self.stage_name = stage_name
        self.requested_workers = max(0, int(requested_workers))
        self.total_items = max(0, int(total_items))
        self._lock = threading.Lock()
        self._active_items = 0
        self._peak_active_items = 0
        self._completed_items = 0
        self._failed_items = 0
        self._total_elapsed_success = 0.0
        self._total_bytes = 0
        self._first_started_at: float | None = None
        self._last_finished_at: float | None = None
    def begin(self) -> float:
        started_at = time.monotonic()
        with self._lock:
            self._active_items += 1
            if self._active_items > self._peak_active_items:
                self._peak_active_items = self._active_items
            if self._first_started_at is None:
                self._first_started_at = started_at
        return started_at
    def end(self, started_at: float, success: bool, bytes_count: int = 0) -> None:
        finished_at = time.monotonic()
        elapsed = max(0.0, finished_at - started_at)
        with self._lock:
            if self._active_items > 0:
                self._active_items -= 1
            self._last_finished_at = finished_at
            if success:
                self._completed_items += 1
                self._total_elapsed_success += elapsed
                self._total_bytes += max(0, int(bytes_count))
            else:
                self._failed_items += 1
    def snapshot(self) -> StageTransferStats:
        with self._lock:
            first_started_at = self._first_started_at
            last_finished_at = self._last_finished_at
            completed_items = self._completed_items
            stage_seconds = 0.0
            if first_started_at is not None and last_finished_at is not None:
                stage_seconds = max(0.0, last_finished_at - first_started_at)
            average_item_seconds = (
                self._total_elapsed_success / completed_items if completed_items > 0 else 0.0
            )
            files_per_second = completed_items / stage_seconds if stage_seconds > 0 else 0.0
            megabits_per_second = (
                (self._total_bytes * 8.0) / stage_seconds / 1_000_000.0 if stage_seconds > 0 else 0.0
            )
            effective_parallelism = files_per_second * average_item_seconds if completed_items > 0 else 0.0
            return StageTransferStats(
                stage_name=self.stage_name,
                requested_workers=self.requested_workers,
                total_items=self.total_items,
                completed_items=completed_items,
                failed_items=self._failed_items,
                peak_active_items=self._peak_active_items,
                stage_seconds=stage_seconds,
                average_item_seconds=average_item_seconds,
                files_per_second=files_per_second,
                megabits_per_second=megabits_per_second,
                total_bytes=self._total_bytes,
                effective_parallelism=effective_parallelism,
            )
_THREAD_LOCAL = threading.local()
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Nishizumi Paints: watch iRacing sessions, fetch Trading Paints assets, "
            "and install them in your local iRacing paint folder."
        )
    )
    parser.add_argument(
        "--session-yaml",
        default=None,
        help="Path to iRacing session_info YAML dump file.",
    )
    parser.add_argument(
        "--iracing-sdk",
        action="store_true",
        help=(
            "Read live session data from the iRacing SDK instead of a file. "
            "If --session-yaml is omitted, SDK mode is used by default."
        ),
    )
    parser.add_argument(
        "--watch",
        action="store_true",
        help="Keep running and process each new session ID in the YAML file.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=0.8,
        help="Polling interval in seconds when --watch is enabled.",
    )
    parser.add_argument(
        "--paints-dir",
        default=None,
        help="Override iRacing paint directory (default: ~/Documents/iRacing/paint).",
    )
    parser.add_argument(
        "--temp-dir",
        default=None,
        help="Override temp folder (default: system temp + /NishizumiPaints).",
    )
    parser.add_argument(
        "--keep-session-paints",
        action="store_true",
        help="Do not delete old session paints when session changes/exits.",
    )
    parser.add_argument(
        "--max-concurrent-manifests",
        type=int,
        default=10,
        help=(
            "Upper cap for Trading Paints manifest requests. "
            "Auto-tuning chooses a value up to this cap (default: 10)."
        ),
    )
    parser.add_argument(
        "--max-concurrent-downloads",
        type=int,
        default=8,
        help=(
            "Upper cap for paint downloads. "
            "Auto-tuning chooses a value up to this cap (default: 8)."
        ),
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=3,
        help="How many attempts to make for manifest/download requests (default: 3).",
    )
    parser.add_argument(
        "--retry-backoff-seconds",
        type=float,
        default=1.0,
        help="Base retry backoff in seconds. Attempts wait 1x, 2x, 4x... (default: 1.0).",
    )
    launch_group = parser.add_mutually_exclusive_group()
    launch_group.add_argument(
        "--gui",
        action="store_true",
        help="Force the built-in GUI even if a launch preference is saved.",
    )
    launch_group.add_argument(
        "--nogui",
        action="store_true",
        help="Run without the built-in UI.",
    )
    parser.add_argument(
        "--managed-headless",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "--autostart-launched",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="Enable verbose debug logs."
    )
    return parser.parse_args()
def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True,
    )
def default_paints_dir() -> Path:
    return Path.home() / "Documents" / "iRacing" / "paint"
def default_ai_rosters_dir() -> Path:
    return Path.home() / "Documents" / "iRacing" / "airosters"
def default_ai_livery_dir() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "Nishizumi-Paints" / "AiLiveries"
    return Path.home() / "AppData" / "Roaming" / "Nishizumi-Paints" / "AiLiveries"
def default_random_pool_dir() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "Nishizumi-Paints" / "RandomPool"
    return Path.home() / "AppData" / "Roaming" / "Nishizumi-Paints" / "RandomPool"

def default_session_exports_dir() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "Nishizumi-Paints" / "Exports"
    return Path.home() / "AppData" / "Roaming" / "Nishizumi-Paints" / "Exports"
def default_replay_dir() -> Path:
    return Path.home() / "Documents" / "iRacing" / "replay"
def default_replay_packs_dir() -> Path:
    appdata = os.getenv("APPDATA")
    if appdata:
        return Path(appdata) / "Nishizumi-Paints" / "ReplayPacks"
    return Path.home() / "AppData" / "Roaming" / "Nishizumi-Paints" / "ReplayPacks"
def clamp_random_pool_gb(value: float | int | str, fallback: float = 5.0) -> float:
    try:
        parsed = float(value)
    except Exception:
        parsed = float(fallback)
    if parsed <= 0:
        parsed = float(fallback)
    return min(max(parsed, 0.25), 500.0)
def random_pool_limit_bytes(max_gb: float) -> int:
    return int(clamp_random_pool_gb(max_gb) * (1024 ** 3))
def default_temp_dir() -> Path:
    return Path(tempfile.gettempdir()) / "NishizumiPaints"
def cleanup_stale_temp_dirs(temp_dir: Path, older_than_hours: float = 24.0) -> None:
    if not temp_dir.exists():
        return
    cutoff = time.time() - max(older_than_hours, 1.0) * 3600.0
    for child in temp_dir.iterdir():
        try:
            stat = child.stat()
        except OSError:
            continue
        if stat.st_mtime > cutoff:
            continue
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        except OSError:
            logging.debug("Could not clean stale temp item: %s", child)
def positive_int(value: int, fallback: int) -> int:
    return value if value > 0 else fallback
def compute_retry_delay(base_seconds: float, attempt: int) -> float:
    base = max(base_seconds, 0.1) * (2 ** max(attempt - 1, 0))
    return min(base, 8.0)
def auto_tune_manifest_workers(user_count: int, configured_cap: int) -> int:
    if user_count <= 0:
        return 0
    cap = positive_int(configured_cap, 10)
    if user_count <= 10:
        tuned = 4
    elif user_count <= 20:
        tuned = 6
    elif user_count <= 40:
        tuned = 8
    else:
        tuned = 10
    return min(user_count, cap, tuned)
def auto_tune_download_workers(item_count: int, configured_cap: int) -> int:
    if item_count <= 0:
        return 0
    cap = positive_int(configured_cap, 8)
    if item_count <= 10:
        tuned = 4
    elif item_count <= 20:
        tuned = 8
    elif item_count <= 40:
        tuned = 12
    elif item_count <= 80:
        tuned = 16
    else:
        tuned = 20
    return min(item_count, cap, tuned)
def normalize_download_workers_mode(value: str) -> str:
    mode = str(value).strip().lower()
    return mode if mode in {"auto", "manual"} else "auto"
def resolve_download_workers(
    item_count: int,
    download_workers_mode: str,
    auto_cap: int,
    manual_workers: int,
) -> int:
    if item_count <= 0:
        return 0
    if normalize_download_workers_mode(download_workers_mode) == "manual":
        return max(1, min(100, positive_int(manual_workers, 8)))
    return auto_tune_download_workers(item_count, positive_int(auto_cap, 8))
def resolve_manifest_workers(
    user_count: int,
    download_workers_mode: str,
    auto_cap: int,
    manual_workers: int,
) -> int:
    if user_count <= 0:
        return 0
    if normalize_download_workers_mode(download_workers_mode) == "manual":
        return max(1, min(100, positive_int(manual_workers, 8)))
    effective_download_value = positive_int(auto_cap, 8)
    manifest_cap = get_manifest_cap_from_download_cap(effective_download_value)
    return auto_tune_manifest_workers(user_count, manifest_cap)
def build_http_session() -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(pool_connections=32, pool_maxsize=32, max_retries=0, pool_block=False)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update({"User-Agent": APP_USER_AGENT})
    return session
def get_thread_http_session() -> requests.Session:
    session = getattr(_THREAD_LOCAL, "http_session", None)
    if session is None:
        session = build_http_session()
        _THREAD_LOCAL.http_session = session
    return session
def _to_int_or_none(value: object) -> int | None:
    try:
        if value in (None, ""):
            return None
        return int(value)
    except (TypeError, ValueError):
        return None
def _to_boolish(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return value != 0
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "on"}:
        return True
    if text in {"0", "false", "no", "n", "off", ""}:
        return False
    return default
def _driver_number_text(driver: dict) -> str:
    for key in ("CarNumber", "CarNumberRaw", "CarNumberDesignStr"):
        value = driver.get(key)
        if value in (None, ""):
            continue
        text = str(value).strip()
        if text:
            return text
    return "0"
def _driver_paint_ext(driver: dict) -> str:
    for key in ("CarCfgCustomPaintExt", "CarCustomPaintExt", "CustomPaintExt"):
        value = driver.get(key)
        if value in (None, ""):
            continue
        text = str(value).strip().lower()
        if text and text not in {"none", "default", "regular"}:
            return text
    return ""

def _driver_irating(driver: dict) -> int | None:
    value = _to_int_or_none(driver.get("IRating"))
    if value is None or value < 0:
        return None
    return value

def _driver_license_parts(driver: dict) -> tuple[str, str]:
    raw = str(driver.get("LicString") or driver.get("LicenseString") or "").strip()
    if raw:
        match = re.match(r"^([A-Za-z+]+)\s+([0-9]+(?:\.[0-9]+)?)$", raw)
        if match:
            return match.group(1), match.group(2)
        parts = raw.split()
        if len(parts) >= 2:
            return parts[0], parts[1]
        return raw, "-"
    lic_level = _to_int_or_none(driver.get("LicLevel"))
    lic_sub = _to_int_or_none(driver.get("LicSubLevel"))
    if lic_level is None:
        lic = "-"
    elif lic_level >= 20:
        lic = "P"
    elif lic_level >= 16:
        lic = "A"
    elif lic_level >= 12:
        lic = "B"
    elif lic_level >= 8:
        lic = "C"
    elif lic_level >= 4:
        lic = "D"
    else:
        lic = "R"
    sr = f"{(lic_sub or 0) / 100.0:.2f}" if lic_sub is not None and lic_sub >= 0 else "-"
    return lic, sr
def _resolve_local_driver_identity(
    driver_info: dict,
    drivers: list[dict],
    driver_car_idx: int | None,
) -> tuple[int | None, int | None]:
    local_user_id = _to_int_or_none(driver_info.get("DriverUserID"))
    local_team_id: int | None = None
    if driver_car_idx is None and local_user_id is None:
        return None, None
    for driver in drivers:
        if not isinstance(driver, dict):
            continue
        user_id = _to_int_or_none(driver.get("UserID"))
        car_idx = _to_int_or_none(driver.get("CarIdx"))
        team_id = _to_int_or_none(driver.get("TeamID"))
        if team_id is not None and team_id <= 0:
            team_id = None
        if local_user_id is not None and user_id == local_user_id:
            return local_user_id, team_id
        if driver_car_idx is not None and car_idx == driver_car_idx and user_id is not None and user_id > 0:
            return user_id, team_id
    return local_user_id, local_team_id

def _read_sdk_local_user_id(sdk: object) -> int | None:
    for section_name in ("UserInfo", "DriverInfo"):
        try:
            section = sdk[section_name]
        except Exception:
            section = None
        if not isinstance(section, dict):
            continue
        for key in ("UserID", "DriverUserID", "CustomerID", "CustID"):
            value = _to_int_or_none(section.get(key))
            if value is not None and value > 0:
                return value
    return None

def _merge_preserve_targets(
    preserve_targets: set[tuple[bool, int]] | None,
    fallback_member_id: int | None = None,
    fallback_team_id: int | None = None,
) -> set[tuple[bool, int]]:
    merged = set(preserve_targets or set())
    if fallback_member_id is not None and fallback_member_id > 0:
        merged.add((False, int(fallback_member_id)))
    if fallback_team_id is not None and fallback_team_id > 0:
        merged.add((True, int(fallback_team_id)))
    return merged

def _build_session_from_parts(
    weekend: object,
    driver_info: object,
    load_num_textures: bool = False,
) -> Session | None:
    if not isinstance(weekend, dict):
        return None
    if not isinstance(driver_info, dict):
        return None
    session_raw = weekend.get("SessionID")
    if session_raw is None:
        return None
    try:
        main_id = int(session_raw)
    except (TypeError, ValueError):
        return None
    sub_id = _to_int_or_none(weekend.get("SubSessionID"))
    team_racing = _to_boolish(weekend.get("TeamRacing"), default=False)
    weekend_options = weekend.get("WeekendOptions") if isinstance(weekend.get("WeekendOptions"), dict) else {}
    event_time_raw = str(weekend.get("EventTimeRaw") or weekend.get("EventTime") or weekend_options.get("TimeOfDay") or "10:00 am").strip() or "10:00 am"
    series_id = _to_int_or_none(weekend.get("SeriesID")) or 0
    league_id = _to_int_or_none(weekend.get("LeagueID")) or 0
    track_name = str(weekend.get("TrackName") or "").strip()
    track_display_name = str(weekend.get("TrackDisplayName") or weekend.get("TrackDisplayShortName") or "").strip()
    track_config_name = str(weekend.get("TrackConfigName") or weekend.get("TrackConfig") or "").strip()
    is_superspeedway_track = _is_superspeedway_track(track_name, track_display_name, track_config_name)
    ai_roster_id = str(weekend.get("AIRosterID") or "").strip()
    ai_roster_name = str(weekend.get("AIRosterName") or "").strip()
    drivers = driver_info.get("Drivers", [])
    if not isinstance(drivers, list):
        drivers = []
    users: set[SessionUser] = set()
    driver_car_idx = _to_int_or_none(driver_info.get("DriverCarIdx"))
    local_user_id, local_team_id = _resolve_local_driver_identity(driver_info, drivers, driver_car_idx)
    ai_driver_count = 0
    ai_drivers: list[dict] = []
    for d in drivers:
        if not isinstance(d, dict):
            continue
        is_ai_driver = _to_boolish(d.get("CarIsAI"), default=False)
        if is_ai_driver:
            ai_driver_count += 1
            ai_drivers.append({
                "driverName": str(d.get("UserName") or "").strip(),
                "carNumber": _driver_number_text(d),
                "carPath": str(d.get("CarPath") or "").strip().replace(" ", "\\"),
                "carId": _to_int_or_none(d.get("CarID")) or 0,
                "carClassId": _to_int_or_none(d.get("CarClassID")) or 0,
            })
        user_id = _to_int_or_none(d.get("UserID"))
        if user_id is None or user_id <= 0:
            continue
        team_id = _to_int_or_none(d.get("TeamID"))
        if team_id is not None and team_id <= 0:
            team_id = None
        car_path = d.get("CarPath")
        if isinstance(car_path, str) and car_path.strip():
            users.add(
                SessionUser(
                    user_id=user_id,
                    directory=car_path.strip(),
                    team_id=team_id,
                    number=_driver_number_text(d),
                    paint_ext=_driver_paint_ext(d),
                    is_ai=is_ai_driver,
                    display_name=str(d.get("UserName") or "").strip(),
                    car_idx=_to_int_or_none(d.get("CarIdx")),
                    irating=_driver_irating(d),
                    license_label=_driver_license_parts(d)[0],
                    safety_rating=_driver_license_parts(d)[1],
                )
            )
    return Session(
        session_id=SessionId(main_id, sub_id),
        users=users,
        local_user_id=local_user_id,
        local_team_id=local_team_id,
        team_racing=team_racing,
        event_time_raw=event_time_raw,
        series_id=series_id,
        league_id=league_id,
        load_num_textures=bool(load_num_textures),
        track_name=track_name,
        track_display_name=track_display_name,
        track_config_name=track_config_name,
        is_superspeedway_track=is_superspeedway_track,
        ai_driver_count=ai_driver_count,
        ai_roster_id=ai_roster_id,
        ai_roster_name=ai_roster_name,
        ai_drivers=tuple(ai_drivers),
    )
def parse_session_yaml(yaml_text: str) -> Session | None:
    try:
        doc = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        logging.error("Failed to parse session YAML: %s", exc)
        return None
    if not isinstance(doc, dict):
        return None
    load_num_textures = False
    for key in ("LoadNumTextures", "load_num_textures"):
        if key in doc:
            load_num_textures = _to_boolish(doc.get(key), default=False)
            break
    return _build_session_from_parts(
        doc.get("WeekendInfo"),
        doc.get("DriverInfo"),
        load_num_textures=load_num_textures,
    )
def _parse_fetch_user_manifest_xml(user_id: int, xml_text: str) -> list[DownloadFile]:
    root = ET.fromstring(xml_text)
    files: list[DownloadFile] = []
    for car in root.findall(".//Car"):
        file_url = (car.findtext("file") or "").strip()
        directory = (car.findtext("directory") or "").strip()
        type_raw = (car.findtext("type") or "").strip().lower()
        if not file_url or not directory or not type_raw:
            continue
        try:
            paint_type = PaintType(type_raw)
        except ValueError:
            logging.debug(
                "Skipping unknown paint type '%s' for user %s",
                type_raw,
                user_id,
            )
            continue
        team_id_text = (car.findtext("teamid") or "0").strip() or "0"
        team_id = _to_int_or_none(team_id_text) or 0
        is_team_paint = bool(team_id > 0 and paint_type in TEAM_PAINT_TYPES)
        target_user_id = team_id if is_team_paint else user_id
        files.append(
            DownloadFile(
                download_id=DownloadId(
                    user_id=target_user_id,
                    directory=directory,
                    paint_type=paint_type,
                    is_team_paint=is_team_paint,
                ),
                url=file_url,
            )
        )
    return files


def _fetch_user_files_fast_uncached(user_id: int, request_timeout: float = 8.0) -> list[DownloadFile]:
    session = get_thread_http_session()
    url = f"https://fetch.tradingpaints.gg/fetch_user.php?user={user_id}&ts={int(time.time() * 1000)}"
    resp = session.get(
        url,
        timeout=max(2.0, float(request_timeout)),
        headers={
            "Cache-Control": "no-cache, no-store, max-age=0",
            "Pragma": "no-cache",
            "Accept": "application/xml,text/xml;q=0.9,*/*;q=0.8",
        },
    )
    resp.raise_for_status()
    return _parse_fetch_user_manifest_xml(user_id, resp.text)


def fetch_user_files(
    user_id: int,
    retries: int,
    retry_backoff_seconds: float,
) -> list[DownloadFile]:
    url = f"https://fetch.tradingpaints.gg/fetch_user.php?user={user_id}"
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            session = get_thread_http_session()
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            return _parse_fetch_user_manifest_xml(user_id, resp.text)
        except (requests.RequestException, ET.ParseError) as exc:
            last_exc = exc
            if attempt >= retries:
                break
            delay = compute_retry_delay(retry_backoff_seconds, attempt)
            logging.debug(
                "Manifest fetch failed for user %s (attempt %s/%s): %s. Retrying in %.1fs",
                user_id,
                attempt,
                retries,
                exc,
                delay,
            )
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc
def _safe_random_pool_bucket(directory: str) -> str:
    bucket = normalize_directory(directory)
    return bucket or "unknown_car"
def _file_sha1(path: Path) -> str:
    hasher = hashlib.sha1()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()
def _path_size_bytes(path: Path) -> int:
    total = 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).stat().st_size
            except OSError:
                continue
    return total
def _random_pool_bucket_dirs(random_pool_dir: Path) -> list[Path]:
    result: list[Path] = []
    if not random_pool_dir.exists():
        return result
    try:
        bucket_roots = [child for child in random_pool_dir.iterdir() if child.is_dir()]
    except OSError:
        return result
    for root in bucket_roots:
        try:
            for child in root.iterdir():
                if child.is_dir():
                    result.append(child)
        except OSError:
            continue
    return result
def current_random_pool_usage_bytes(random_pool_dir: Path) -> int:
    total = 0
    for bucket_dir in _random_pool_bucket_dirs(random_pool_dir):
        total += _path_size_bytes(bucket_dir)
    return total
def get_random_pool_stats(random_pool_dir: Path) -> RandomPoolStats:
    total = 0
    set_count = 0
    cars: set[str] = set()
    for bucket_dir in _random_pool_bucket_dirs(random_pool_dir):
        car_file = bucket_dir / "car.tga"
        if not car_file.exists():
            continue
        set_count += 1
        total += _path_size_bytes(bucket_dir)
        directory_name = bucket_dir.parent.name
        try:
            meta = json.loads((bucket_dir / "meta.json").read_text(encoding="utf-8"))
            directory_name = str(meta.get("directory") or directory_name)
        except Exception:
            pass
        cars.add(directory_name)
    return RandomPoolStats(total_bytes=total, set_count=set_count, car_count=len(cars))
def enforce_random_pool_limit(random_pool_dir: Path, max_gb: float) -> tuple[int, int]:
    limit_bytes = random_pool_limit_bytes(max_gb)
    bucket_dirs = _random_pool_bucket_dirs(random_pool_dir)
    if not bucket_dirs:
        return 0, 0
    bucket_infos: list[tuple[float, int, Path]] = []
    total_bytes = 0
    for bucket_dir in bucket_dirs:
        size_bytes = _path_size_bytes(bucket_dir)
        total_bytes += size_bytes
        try:
            meta = json.loads((bucket_dir / "meta.json").read_text(encoding="utf-8"))
            sort_key = float(meta.get("cached_at", bucket_dir.stat().st_mtime))
        except Exception:
            try:
                sort_key = float(bucket_dir.stat().st_mtime)
            except OSError:
                sort_key = 0.0
        bucket_infos.append((sort_key, size_bytes, bucket_dir))
    if total_bytes <= limit_bytes:
        return total_bytes, 0
    bucket_infos.sort(key=lambda item: item[0])
    freed_bytes = 0
    for _sort_key, size_bytes, bucket_dir in bucket_infos:
        if total_bytes - freed_bytes <= limit_bytes:
            break
        try:
            shutil.rmtree(bucket_dir, ignore_errors=True)
            freed_bytes += size_bytes
        except Exception:
            continue
    return max(total_bytes - freed_bytes, 0), freed_bytes

def clear_random_pool(random_pool_dir: Path) -> tuple[int, int, int]:
    if not random_pool_dir.exists():
        return 0, 0, 0
    stats_before = get_random_pool_stats(random_pool_dir)
    removed_files = 0
    for root, _dirs, files in os.walk(random_pool_dir):
        removed_files += len(files)
    for child in list(random_pool_dir.iterdir()):
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
        except Exception:
            continue
    random_pool_dir.mkdir(parents=True, exist_ok=True)
    return stats_before.set_count, removed_files, stats_before.total_bytes
def _group_saved_car_sets(saved: list[SavedFile]) -> dict[tuple[str, int, bool], dict[PaintType, Path]]:
    grouped: dict[tuple[str, int, bool], dict[PaintType, Path]] = {}
    for saved_file in saved:
        if saved_file.download_id.paint_type not in {PaintType.CAR, PaintType.CAR_SPEC, PaintType.CAR_DECAL}:
            continue
        key = (saved_file.download_id.directory, saved_file.download_id.user_id, bool(saved_file.download_id.is_team_paint))
        grouped.setdefault(key, {})[saved_file.download_id.paint_type] = saved_file.file_path
    return grouped
def archive_saved_tp_sets_to_random_pool(saved: list[SavedFile], random_pool_dir: Path, max_pool_gb: float) -> tuple[int, int, list[str], int, int]:
    random_pool_dir.mkdir(parents=True, exist_ok=True)
    grouped = _group_saved_car_sets(saved)
    added_sets = 0
    added_files = 0
    detail_logs: list[str] = []
    for (directory, target_id, is_team), file_map in grouped.items():
        car_src = file_map.get(PaintType.CAR)
        if car_src is None or not car_src.exists():
            continue
        try:
            source_hash = _file_sha1(car_src)[:16]
        except Exception:
            source_hash = hashlib.sha1(str(car_src).encode("utf-8", "ignore")).hexdigest()[:16]
        bucket_dir = random_pool_dir / _safe_random_pool_bucket(directory) / source_hash
        bucket_dir.mkdir(parents=True, exist_ok=True)
        meta_path = bucket_dir / "meta.json"
        if not meta_path.exists():
            meta_path.write_text(
                json.dumps({
                    "directory": directory,
                    "source_hash": source_hash,
                    "source_path": str(car_src),
                    "cached_at": time.time(),
                    "target_id": int(target_id),
                    "is_team_paint": bool(is_team),
                }, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        mapping = {
            PaintType.CAR: bucket_dir / "car.tga",
            PaintType.CAR_SPEC: bucket_dir / "car_spec.mip",
            PaintType.CAR_DECAL: bucket_dir / "decal.tga",
        }
        copied_any = False
        copied_labels: list[str] = []
        for paint_type, destination in mapping.items():
            source_path = file_map.get(paint_type)
            if source_path is None or not source_path.exists() or destination.exists():
                continue
            shutil.copy2(source_path, destination)
            added_files += 1
            copied_any = True
            copied_labels.append(f"{paint_type.value} -> {destination}")
        if copied_any or (bucket_dir / "car.tga").exists():
            added_sets += 1
            target_label = f"team {target_id}" if is_team else f"user {target_id}"
            if copied_labels:
                detail_logs.append(
                    f"Random pool cached TP paint for {target_label} on {directory}: source={car_src.name}, bucket={bucket_dir.name}, files={'; '.join(copied_labels)}"
                )
            else:
                detail_logs.append(
                    f"Random pool already had TP paint for {target_label} on {directory}: bucket={bucket_dir.name}"
                )
    current_bytes, freed_bytes = enforce_random_pool_limit(random_pool_dir, max_pool_gb)
    return added_sets, added_files, detail_logs, current_bytes, freed_bytes
def _iter_random_pool_entries_for_directory(directory: str, random_pool_dir: Path, ai_livery_root: Path) -> list[RandomPoolEntry]:
    entries: list[RandomPoolEntry] = []
    bucket_dir = random_pool_dir / _safe_random_pool_bucket(directory)
    if bucket_dir.exists():
        for child in sorted(bucket_dir.iterdir()):
            if not child.is_dir():
                continue
            car_file = child / "car.tga"
            if not car_file.exists():
                continue
            spec_file = child / "car_spec.mip"
            decal_file = child / "decal.tga"
            entries.append(
                RandomPoolEntry(
                    source_id=f"pool:{directory}:{child.name}",
                    directory=directory,
                    car_file=car_file,
                    spec_file=spec_file if spec_file.exists() else None,
                    decal_file=decal_file if decal_file.exists() else None,
                    source_kind="pool",
                )
            )
    ai_dir = ai_livery_root / directory
    if ai_dir.exists():
        for car_file in sorted(ai_dir.glob("car_*.tga")):
            stem_suffix = car_file.stem.replace("car_", "", 1)
            spec_file = ai_dir / f"car_spec_{stem_suffix}.mip"
            decal_file = ai_dir / f"decal_{stem_suffix}.tga"
            entries.append(
                RandomPoolEntry(
                    source_id=f"ai_livery:{directory}:{car_file.name}",
                    directory=directory,
                    car_file=car_file,
                    spec_file=spec_file if spec_file.exists() else None,
                    decal_file=decal_file if decal_file.exists() else None,
                    source_kind="ai_livery",
                )
            )
    return entries
def _choose_random_pool_entry(directory: str, random_pool_dir: Path, ai_livery_root: Path, used_source_ids: set[str], seed_text: str) -> tuple[RandomPoolEntry | None, bool]:
    candidates = _iter_random_pool_entries_for_directory(directory, random_pool_dir, ai_livery_root)
    if not candidates:
        return None, False
    available = [entry for entry in candidates if entry.source_id not in used_source_ids]
    if not available:
        return None, False
    rng = random.Random(seed_text)
    selected = available[rng.randrange(len(available))]
    used_source_ids.add(selected.source_id)
    return selected, False
def _copy_source_file_to_saved_targets(source_path: Path | None, session_id: SessionId, download_id: DownloadId, paints_dir: Path) -> list[SavedFile]:
    if source_path is None or not source_path.exists():
        return []
    saved: list[SavedFile] = []
    for destination in save_paths_for(download_id, paints_dir):
        destination.parent.mkdir(parents=True, exist_ok=True)
        temp_destination = destination.with_name(destination.name + ".tmp")
        temp_destination.unlink(missing_ok=True)
        shutil.copy2(source_path, temp_destination)
        os.replace(temp_destination, destination)
        saved.append(SavedFile(session_id=session_id, download_id=download_id, file_path=destination))
    return saved
def apply_local_tp_random_fallbacks(
    session: Session,
    saved: list[SavedFile],
    paints_dir: Path,
    random_pool_dir: Path,
    ai_livery_root: Path,
    enable_real_drivers: bool,
    enable_ai: bool,
    sync_my_livery_from_server: bool,
) -> tuple[list[SavedFile], list[str], RandomFallbackSummary]:
    logs: list[str] = []
    fallback_saved: list[SavedFile] = []
    summary = RandomFallbackSummary()
    existing_car_targets = {
        (bool(item.download_id.is_team_paint), int(item.download_id.user_id), item.download_id.directory.lower())
        for item in saved
        if item.download_id.paint_type is PaintType.CAR
    }
    used_source_ids: set[str] = set()
    matched_ai_users = 0
    for user in sorted(session.users, key=lambda u: (u.is_ai, u.directory.lower(), u.user_id, u.team_id or 0)):
        if user.is_ai:
            matched_ai_users += 1
            if not enable_ai:
                continue
        else:
            if not enable_real_drivers:
                continue
        is_local_target = False
        if session.local_user_id is not None and user.user_id == session.local_user_id:
            is_local_target = True
        if session.local_team_id is not None and user.team_id is not None and user.team_id == session.local_team_id:
            is_local_target = True
        if is_local_target and not sync_my_livery_from_server:
            continue
        target_is_team = bool(user.team_id is not None and user.team_id > 0)
        target_id = int(user.team_id) if target_is_team else int(user.user_id)
        target_key = (target_is_team, target_id, user.directory.lower())
        if target_key in existing_car_targets:
            continue
        seed_text = f"{session.session_id.folder_name()}|{user.directory}|{target_id}|{'ai' if user.is_ai else 'driver'}"
        summary.attempted_targets += 1
        entry, reused_existing_source = _choose_random_pool_entry(user.directory, random_pool_dir, ai_livery_root, used_source_ids, seed_text)
        if entry is None:
            summary.missing_source_targets += 1
            continue
        if reused_existing_source:
            summary.repeated_source_uses += 1
        label = user.display_name or (f"AI {target_id}" if user.is_ai else f"user {target_id}")
        base_kwargs = {
            "user_id": target_id,
            "directory": user.directory,
            "is_team_paint": target_is_team,
            "is_superspeedway_variant": bool(session.is_superspeedway_track),
        }
        added_any = False
        for paint_type, source_path in (
            (PaintType.CAR, entry.car_file),
            (PaintType.CAR_SPEC, entry.spec_file),
            (PaintType.CAR_DECAL, entry.decal_file),
        ):
            copied = _copy_source_file_to_saved_targets(
                source_path,
                session.session_id,
                DownloadId(paint_type=paint_type, **base_kwargs),
                paints_dir,
            )
            if copied:
                fallback_saved.extend(copied)
                added_any = True
        if added_any:
            summary.applied_targets += 1
            existing_car_targets.add(target_key)
            source_parts = [f"car={entry.car_file.name}"]
            if entry.spec_file is not None and entry.spec_file.exists():
                source_parts.append(f"spec={entry.spec_file.name}")
            if entry.decal_file is not None and entry.decal_file.exists():
                source_parts.append(f"decal={entry.decal_file.name}")
            save_targets = ", ".join(sorted({str(item.file_path.name) for item in fallback_saved if item.download_id.user_id == target_id and item.download_id.directory.lower() == user.directory.lower()}))
            logs.append(
                f"TP local random fallback applied to {'AI' if user.is_ai else 'driver'} {label} using {entry.source_kind} source {entry.source_id} for {user.directory}; source_files=({' | '.join(source_parts)}); saved_targets=[{save_targets}]"
            )
    if enable_ai and session.ai_driver_count > 0 and matched_ai_users == 0:
        logs.append("AI session detected, but the SDK did not expose direct AI paint targets. Use 'Randomize active AI roster' to build a local randomized roster from TP-sourced paints.")
    return fallback_saved, logs, summary


@dataclass
class TPShowroomSyncResult:
    ok: bool
    chosen_scheme_id: str = ""
    chosen_title: str = ""
    showroom_count: int = 0
    source_car: str = ""
    source_spec: str = ""
    source_decal: str = ""
    auth_required: bool = False
    message: str = ""
    original_scheme_id: str = ""
    direct_items: list[DownloadFile] = field(default_factory=list)
    set_scheme_applied: bool = False
    reused_previous_scheme: bool = False
    reused_recent_history: bool = False
    showroom_cars: list[dict] = field(default_factory=list)
    showroom_sampled_pages: list[int] = field(default_factory=list)
    detected_total_pages: int = 0
    baseline_manifest_urls: dict[str, str] = field(default_factory=dict)
    original_scheme_link: str = ""
    original_scheme_title: str = ""


def _run_tp_sync_api_in_thread(func: Callable[[], object]) -> object:
    result_holder: dict[str, object] = {}
    error_holder: dict[str, BaseException] = {}

    def _target() -> None:
        try:
            result_holder["value"] = func()
        except BaseException as exc:  # noqa: BLE001
            error_holder["error"] = exc

    worker = threading.Thread(target=_target, name="NishizumiTPPlaywrightWorker", daemon=True)
    worker.start()
    worker.join()
    if "error" in error_holder:
        raise error_holder["error"]
    return result_holder.get("value")


def _load_tp_showroom_mapping(mapping_path: Path | None = None) -> dict:
    try:
        resolved_path = Path(mapping_path) if mapping_path is not None else default_tp_showroom_mapping_path()
        raw = json.loads(resolved_path.read_text(encoding="utf-8")) if resolved_path.exists() else {}
    except Exception:
        raw = {}
    if isinstance(raw, dict) and isinstance(raw.get("cars"), dict):
        return raw
    if isinstance(raw, dict):
        return {"cars": raw, "unsupported": {}}
    return {"cars": {}, "unsupported": {}}


def _pick_showroom_scheme(
    cars: list[dict],
    choice_mode: str,
    prefer_official: bool,
    exclude_scheme_ids: set[str] | None = None,
    exclude_recent_scheme_ids: set[str] | None = None,
) -> tuple[dict, bool, bool]:
    pool = [c for c in cars if isinstance(c, dict)]
    if prefer_official:
        official = [c for c in pool if str(c.get("official", "0")) == "1"]
        if official:
            pool = official
    if not pool:
        raise RuntimeError("No showroom paints were returned for this car.")
    excluded_current = {str(item).strip() for item in (exclude_scheme_ids or set()) if str(item).strip()}
    excluded_recent = {str(item).strip() for item in (exclude_recent_scheme_ids or set()) if str(item).strip()}
    unused_and_fresh = [
        c for c in pool
        if str(c.get("id") or "").strip() not in excluded_current
        and str(c.get("id") or "").strip() not in excluded_recent
    ]
    reused_previous_scheme = False
    reused_recent_history = False
    if unused_and_fresh:
        pool = unused_and_fresh
    else:
        unused_current = [
            c for c in pool
            if str(c.get("id") or "").strip() not in excluded_current
        ]
        if unused_current:
            pool = unused_current
            if excluded_recent:
                reused_recent_history = True
        else:
            if excluded_current:
                reused_previous_scheme = True
    mode = (choice_mode or "random").strip().lower()
    if mode == "popular":
        return max(pool, key=lambda c: (int(c.get("users", 0) or 0), int(c.get("bookmarks", 0) or 0))), reused_previous_scheme, reused_recent_history
    if mode == "recent":
        return pool[0], reused_previous_scheme, reused_recent_history
    return random.choice(pool), reused_previous_scheme, reused_recent_history



def _showroom_available_count(
    cars: list[dict],
    *,
    prefer_official: bool = False,
    exclude_scheme_ids: set[str] | None = None,
    exclude_recent_scheme_ids: set[str] | None = None,
) -> int:
    pool = [c for c in cars if isinstance(c, dict)]
    if prefer_official:
        official = [c for c in pool if str(c.get("official", "0")) == "1"]
        if official:
            pool = official
    if not pool:
        return 0
    excluded_current = {str(item).strip() for item in (exclude_scheme_ids or set()) if str(item).strip()}
    excluded_recent = {str(item).strip() for item in (exclude_recent_scheme_ids or set()) if str(item).strip()}
    unused_and_fresh = [
        c for c in pool
        if str(c.get("id") or "").strip() not in excluded_current
        and str(c.get("id") or "").strip() not in excluded_recent
    ]
    if unused_and_fresh:
        return len(unused_and_fresh)
    unused_current = [
        c for c in pool
        if str(c.get("id") or "").strip() not in excluded_current
    ]
    if unused_current:
        return len(unused_current)
    return len(pool)

def _candidate_local_tp_paths(
    paints_dir: Path,
    directory_variants: Iterable[str],
    manifest_member_id: int | None,
    local_team_id: int | None,
) -> list[Path]:
    candidate_dirs: list[str] = []
    seen_dirs: set[str] = set()
    for raw in directory_variants:
        raw_text = str(raw or "").strip()
        for candidate in (
            raw_text,
            raw_text.replace("/", "\\"),
            raw_text.replace("\\", " "),
            canonicalize_car_directory(raw_text),
        ):
            candidate = str(candidate or "").strip()
            if not candidate:
                continue
            key = candidate.lower()
            if key in seen_dirs:
                continue
            seen_dirs.add(key)
            candidate_dirs.append(candidate)

    result: list[Path] = []
    for directory in candidate_dirs:
        base = paints_dir / directory
        if local_user_id is not None and local_user_id > 0:
            uid = int(local_user_id)
            result.extend([
                base / f"car_{uid}.tga",
                base / f"car_spec_{uid}.mip",
                base / f"decal_{uid}.tga",
            ])
        if local_team_id is not None and local_team_id > 0:
            tid = int(local_team_id)
            result.extend([
                base / f"car_team_{tid}.tga",
                base / f"car_spec_team_{tid}.mip",
                base / f"decal_team_{tid}.tga",
            ])

    dedup: list[Path] = []
    seen: set[str] = set()
    for path in result:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        dedup.append(path)
    return dedup


def _snapshot_local_tp_mtimes(paths: list[Path]) -> dict[str, float]:
    snap: dict[str, float] = {}
    for path in paths:
        try:
            snap[str(path)] = path.stat().st_mtime
        except OSError:
            snap[str(path)] = 0.0
    return snap


def _capture_local_tp_backup(paths: list[Path]) -> dict[str, bytes]:
    backup: dict[str, bytes] = {}
    for path in paths:
        try:
            if path.exists() and path.is_file():
                backup[str(path)] = path.read_bytes()
        except Exception:
            continue
    return backup


def _restore_local_tp_backup(backup: dict[str, bytes]) -> bool:
    restored_any = False
    for raw_path, data in (backup or {}).items():
        try:
            path = Path(raw_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            restored_any = True
        except Exception:
            continue
    return restored_any


def _wait_for_local_tp_sync(paths: list[Path], before: dict[str, float], timeout_seconds: float) -> tuple[str, str, str]:
    deadline = time.monotonic() + max(1.0, float(timeout_seconds))
    while time.monotonic() < deadline:
        car = spec = decal = ""
        for path in paths:
            if not path.exists():
                continue
            try:
                size_ok = path.stat().st_size > 0
                mtime = path.stat().st_mtime
            except OSError:
                continue
            if not size_ok:
                continue
            if mtime <= before.get(str(path), 0.0):
                if time.monotonic() + 0.75 < deadline:
                    continue
            name = path.name.lower()
            if name.startswith("car_spec_") and not spec:
                spec = str(path)
            elif name.startswith("decal_") and not decal:
                decal = str(path)
            elif name.startswith("car_") and not car:
                car = str(path)
        if car:
            return car, spec, decal
        time.sleep(0.35)
    return "", "", ""


def _trigger_local_tp_update() -> None:
    url = f"http://127.0.0.1:34034/?d={int(time.time() * 1000)}&cmd=updateuserfiles"
    try:
        requests.get(url, timeout=2.5)
    except Exception:
        pass


def ensure_trading_paints_login(
    profile_dir: Path,
    browser_channel: str = "chrome",
    start_url: str = "https://www.tradingpaints.com/auth",
    wait_timeout_seconds: float = 900.0,
    confirm_event: threading.Event | None = None,
    manual_confirm_required: bool = True,
    progress: Callable[[str], None] | None = None,
) -> tuple[bool, str]:
    profile_dir.mkdir(parents=True, exist_ok=True)
    clear_tp_login_status(profile_dir, "Trading Paints login is not confirmed yet.")
    if sync_playwright is None:
        return False, "Playwright is not installed in this build."

    def emit(message: str) -> None:
        if progress:
            try:
                progress(message)
            except Exception:
                pass

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=str(profile_dir),
            channel=browser_channel,
            headless=False,
            viewport={"width": 1400, "height": 950},
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(start_url, wait_until="domcontentloaded", timeout=60000)
            emit("Trading Paints login window opened. Finish the login there, then click 'I logged in' in the app.")
            deadline = time.monotonic() + max(60.0, float(wait_timeout_seconds))
            while time.monotonic() < deadline:
                open_pages = []
                for candidate in list(context.pages):
                    try:
                        if not candidate.is_closed():
                            open_pages.append(candidate)
                    except Exception:
                        continue
                if not open_pages:
                    clear_tp_login_status(profile_dir, "The Trading Paints window was closed before login was confirmed.")
                    return False, "The Trading Paints window was closed before login was confirmed."

                should_check = not manual_confirm_required
                if confirm_event is not None and confirm_event.is_set():
                    should_check = True
                    confirm_event.clear()

                if should_check:
                    authenticated, auth_source = _tp_context_looks_authenticated(context, open_pages)
                    if authenticated:
                        write_tp_login_status(profile_dir, ok=True, message=f"Trading Paints login/profile saved. ({auth_source})")
                        return True, "Trading Paints login/profile saved."
                    emit("Trading Paints login is still not confirmed yet. Finish the site login in Chrome, then click 'I logged in' again.")
                time.sleep(0.25)

            clear_tp_login_status(profile_dir, "Trading Paints login was not confirmed before the timeout.")
            return False, "Trading Paints login was not confirmed before the timeout. Keep Chrome open, finish the login, and try again."
        finally:
            context.close()

def tp_original_scheme_cache_path(profile_dir: Path | None = None) -> Path:
    base_dir = Path(profile_dir) if profile_dir is not None else default_tp_showroom_profile_dir()
    base_dir.mkdir(parents=True, exist_ok=True)
    return base_dir / TP_ORIGINAL_SCHEME_CACHE_FILENAME


def load_tp_original_scheme_cache(profile_dir: Path | None = None) -> dict[str, dict[str, str]]:
    cache_path = tp_original_scheme_cache_path(profile_dir)
    try:
        if cache_path.exists():
            cache_path.unlink()
    except Exception:
        logging.debug("Could not remove legacy Trading Paints original scheme cache", exc_info=True)
    return {}


def save_tp_original_scheme_cache(cache: dict[str, dict[str, str]], profile_dir: Path | None = None) -> None:
    cache_path = tp_original_scheme_cache_path(profile_dir)
    try:
        if cache_path.exists():
            cache_path.unlink()
    except Exception:
        logging.debug("Could not remove legacy Trading Paints original scheme cache", exc_info=True)


def remember_tp_original_scheme(profile_dir: Path | None, directory: str, scheme_id: str, showroom_link: str = "", title: str = "", source: str = "dashboard") -> None:
    return


def _tp_extract_scheme_ids_from_text(text: str) -> list[str]:
    haystack = str(text or "")
    ids: list[str] = []
    patterns = (
        r"/showroom/view/(\d+)(?:/|\b)",
        r"setScheme\.php\?id=(\d+)",
        r"data-scheme-id=[\"'](\d+)",
        r'"scheme(?:_id|Id|ID)"\s*[:=]\s*"?(\d+)"?',
        r'"selectedScheme"\s*[:=]\s*"?(\d+)"?',
    )
    for pattern in patterns:
        for match in re.finditer(pattern, haystack, flags=re.IGNORECASE):
            scheme_id = str(match.group(1) or "").strip()
            if scheme_id and scheme_id not in ids:
                ids.append(scheme_id)
    return ids


def _tp_capture_showroom_overlay_link(page) -> tuple[str, str, str]:
    try:
        record = page.evaluate(
            """
            () => {
              const anchors = Array.from(document.querySelectorAll('a[href*="/showroom/view/"]'));
              let best = null;
              for (const a of anchors) {
                const href = a.href || a.getAttribute('href') || '';
                if (!href || !href.includes('/showroom/view/')) continue;
                const text = (a.textContent || '').trim();
                const rect = a.getBoundingClientRect();
                let score = 0;
                if (rect.width > 0 && rect.height > 0) score += 20;
                if (rect.top > window.innerHeight * 0.45) score += 15;
                if (rect.left < window.innerWidth * 0.65) score += 12;
                if (text) score += Math.min(text.length, 20);
                let cur = a;
                for (let i = 0; i < 8 && cur; i++, cur = cur.parentElement) {
                  const ctx = ((cur.innerText || cur.textContent || '').toUpperCase());
                  if (ctx.includes('FROM THE SHOWROOM')) {
                    score += 120;
                    break;
                  }
                }
                if (!best || score > best.score) {
                  best = {href, text, score};
                }
              }
              return best;
            }
            """
        )
    except Exception:
        record = None
    if isinstance(record, dict):
        href = str(record.get('href') or '').strip()
        ids = _tp_extract_scheme_ids_from_text(href)
        if href and ids:
            return str(ids[0] or '').strip(), href, str(record.get('text') or '').strip()
    return '', '', ''


def _tp_try_activate_showroom_view(page, showroom_link: str, target_scheme_id: str, log: Callable[[str], None] | None = None) -> bool:
    link = str(showroom_link or '').strip()
    if not link:
        return False
    try:
        page.goto(link, wait_until='domcontentloaded', timeout=60000)
    except Exception:
        pass

    def write(msg: str) -> None:
        if log:
            log(msg)

    candidates = [
        ('link', re.compile(r'race\s*this\s*paint|race\s*paint|use\s*this\s*paint|paint\s*this', re.I)),
        ('button', re.compile(r'race\s*this\s*paint|race\s*paint|use\s*this\s*paint|paint\s*this', re.I)),
    ]

    for role_type, pattern in candidates:
        try:
            locator = (page.get_by_role('link', name=pattern) if role_type == 'link' else page.get_by_role('button', name=pattern)).first
            locator.click(timeout=3500)
            time.sleep(1.2)
            write(f'Trading Paints restore used UI click on saved showroom link for scheme {target_scheme_id}.')
            return True
        except Exception:
            pass

    try:
        opts = page.get_by_role('button', name=re.compile(r'paint\s*options', re.I)).first
        opts.click(timeout=2500)
        time.sleep(0.5)
        for role_type, pattern in candidates:
            try:
                locator = (page.get_by_role('link', name=pattern) if role_type == 'link' else page.get_by_role('button', name=pattern)).first
                locator.click(timeout=3500)
                time.sleep(1.2)
                write(f'Trading Paints restore used PAINT OPTIONS -> UI click on saved showroom link for scheme {target_scheme_id}.')
                return True
            except Exception:
                pass
    except Exception:
        pass

    try:
        clicked = page.evaluate(
            r"""
            () => {
              const rx = /race\s*this\s*paint|race\s*paint|use\s*this\s*paint|paint\s*this/i;
              const nodes = Array.from(document.querySelectorAll('a,button,[role="button"],[role="link"]'));
              const node = nodes.find(n => rx.test((n.innerText || n.textContent || '').trim()));
              if (node) { node.click(); return true; }
              return false;
            }
            """
        )
        if clicked:
            time.sleep(1.2)
            write(f'Trading Paints restore used JS click on saved showroom link for scheme {target_scheme_id}.')
            return True
    except Exception:
        pass
    return False


def _tp_capture_current_scheme_info(
    context,
    current_page,
    *,
    mid: int,
    slug: str,
    category: str,
) -> tuple[str, str, str, str]:
    dashboard_urls = [
        f"https://www.tradingpaints.com/dashboard/{mid}/{slug}/simstamped",
        f"https://www.tradingpaints.com/dashboard/{mid}/{slug}",
    ]
    candidates = []
    for page in [current_page, *(list(getattr(context, 'pages', []) or []))]:
        if page is None or page in candidates:
            continue
        candidates.append(page)
    try:
        temp_page = context.new_page()
        candidates.append(temp_page)
    except Exception:
        pass

    def capture_from_active_scheme_showroom(page) -> tuple[str, str, str]:
        selector = "#active_scheme_showroom"
        try:
            page.wait_for_selector(selector, state="attached", timeout=12000)
        except Exception:
            return '', '', ''
        for _attempt in range(8):
            try:
                page.wait_for_function(
                    r"""() => {
                        const root = document.querySelector('#active_scheme_showroom');
                        if (!root) return false;
                        const anchor = root.querySelector("a[href*='/showroom/view/']");
                        if (!anchor) return false;
                        const text = (root.textContent || '').toLowerCase();
                        const style = window.getComputedStyle(root);
                        return text.includes('from the showroom') && style.display !== 'none' && style.visibility !== 'hidden';
                    }""",
                    timeout=1500,
                )
            except Exception:
                pass
            try:
                record = page.eval_on_selector(
                    selector,
                    r"""root => {
                        const anchor = root.querySelector("a[href*='/showroom/view/']");
                        if (!anchor) return null;
                        const style = window.getComputedStyle(root);
                        return {
                            rootText: (root.textContent || '').trim(),
                            rootHtml: root.outerHTML || '',
                            href: anchor.href || anchor.getAttribute('href') || '',
                            text: (anchor.textContent || '').trim(),
                            title: (anchor.getAttribute('title') || '').trim(),
                            visible: style.display !== 'none' && style.visibility !== 'hidden'
                        };
                    }""",
                )
            except Exception:
                record = None
            if isinstance(record, dict):
                root_text = str(record.get('rootText') or '').strip().lower()
                href = str(record.get('href') or '').strip()
                if 'from the showroom' in root_text and href:
                    ids = _tp_extract_scheme_ids_from_text(href)
                    scheme_id = str(ids[0] or '').strip() if ids else ''
                    if scheme_id:
                        title = str(record.get('title') or record.get('text') or '').strip()
                        return scheme_id, href, title
            try:
                page.wait_for_timeout(800)
            except Exception:
                time.sleep(0.8)
        return '', '', ''

    seen_urls: set[str] = set()
    for page in candidates:
        for url in dashboard_urls:
            key = f"{id(page)}|{url}"
            if key in seen_urls:
                continue
            seen_urls.add(key)
            try:
                page.goto(url, wait_until="domcontentloaded", timeout=45000)
            except Exception:
                continue
            try:
                page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:
                pass
            scheme_id, showroom_link, title = capture_from_active_scheme_showroom(page)
            if scheme_id:
                return scheme_id, showroom_link, title, f"dashboard-active-showroom:{page.url or url}"
    return '', '', '', ''


def _tp_capture_current_scheme_id(
    context,
    current_page,
    *,
    mid: int,
    slug: str,
    category: str,
) -> tuple[str, str]:
    scheme_id, _showroom_link, _title, source = _tp_capture_current_scheme_info(
        context, current_page, mid=mid, slug=slug, category=category
    )
    return scheme_id, source

def _tp_directory_candidate_keys(value: str) -> list[str]:
    raw = str(value or "").strip()
    if not raw:
        return []
    variants = [
        raw,
        canonicalize_car_directory(raw),
        raw.replace("/", "\\"),
        raw.replace("\\", " "),
        raw.replace(" ", "\\"),
    ]
    normalized: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        candidate = str(variant or "").strip().lower()
        if not candidate:
            continue
        if candidate in seen:
            continue
        seen.add(candidate)
        normalized.append(candidate)
    return normalized


def _tp_manifest_items_for_directory(items: list[DownloadFile], directory: str) -> list[DownloadFile]:
    wanted = set(_tp_directory_candidate_keys(directory))
    result: list[DownloadFile] = []
    for item in items:
        if item.download_id.paint_type not in {PaintType.CAR, PaintType.CAR_SPEC, PaintType.CAR_DECAL}:
            continue
        if str(item.download_id.directory or "").strip().lower() in wanted:
            result.append(item)
            continue
        canonical = canonicalize_car_directory(item.download_id.directory).lower()
        if canonical in wanted:
            result.append(item)
            continue
        spaced = canonical.replace("\\", " ")
        if spaced in wanted:
            result.append(item)
    return result


def _tp_manifest_url_map(items: list[DownloadFile]) -> dict[str, str]:
    result: dict[str, str] = {}
    for item in items:
        result[item.download_id.paint_type.value] = str(item.url or "")
    return result


def _tp_wait_for_fetch_user_manifest(
    *,
    local_user_id: int,
    directory: str,
    retries: int,
    retry_backoff_seconds: float,
    baseline_urls: dict[str, str] | None,
    timeout_seconds: float,
    log: Callable[[str], None] | None = None,
) -> list[DownloadFile]:
    _ = (retries, retry_backoff_seconds)
    deadline = time.monotonic() + max(4.0, float(timeout_seconds))
    best_effort: list[DownloadFile] = []
    baseline_urls = dict(baseline_urls or {})
    saw_same_as_baseline = False
    poll_attempt = 0
    while time.monotonic() < deadline:
        poll_attempt += 1
        remaining = max(1.5, deadline - time.monotonic())
        request_timeout = min(6.0, remaining)
        try:
            manifest = _fetch_user_files_fast_uncached(local_user_id, request_timeout=request_timeout)
        except Exception as exc:
            if log is not None and poll_attempt in {1, 3, 6}:
                log(f"Trading Paints direct manifest poll failed for local user {local_user_id}: {exc}")
            time.sleep(0.9)
            continue
        filtered = _tp_manifest_items_for_directory(manifest, directory)
        if filtered:
            best_effort = filtered
            current_urls = _tp_manifest_url_map(filtered)
            if not baseline_urls or current_urls != baseline_urls:
                if log is not None and baseline_urls:
                    log(f"Trading Paints direct manifest exposed updated car asset URLs for local user {local_user_id} on {directory}.")
                return filtered
            saw_same_as_baseline = True
        time.sleep(1.0)
    if log is not None:
        if best_effort and saw_same_as_baseline:
            log(
                f"Trading Paints direct manifest for local user {local_user_id} on {directory} never changed away from the baseline URLs before timeout."
            )
        elif best_effort:
            log(
                f"Trading Paints direct manifest for local user {local_user_id} on {directory} stayed usable but did not clearly expose a fresh update before timeout."
            )
        else:
            log(f"Trading Paints direct manifest for local user {local_user_id} on {directory} never exposed any car assets before timeout.")
    return best_effort


def _tp_wait_for_fetch_user_manifest_match(
    *,
    local_user_id: int,
    directory: str,
    retries: int,
    retry_backoff_seconds: float,
    baseline_urls: dict[str, str] | None,
    timeout_seconds: float,
    log: Callable[[str], None] | None = None,
) -> list[DownloadFile]:
    _ = (retries, retry_backoff_seconds)
    deadline = time.monotonic() + max(4.0, float(timeout_seconds))
    best_effort: list[DownloadFile] = []
    baseline_urls = dict(baseline_urls or {})
    poll_attempt = 0
    while time.monotonic() < deadline:
        poll_attempt += 1
        remaining = max(1.5, deadline - time.monotonic())
        request_timeout = min(6.0, remaining)
        try:
            manifest = _fetch_user_files_fast_uncached(local_user_id, request_timeout=request_timeout)
        except Exception as exc:
            if log is not None and poll_attempt in {1, 3, 6}:
                log(f"Trading Paints restore manifest poll failed for local user {local_user_id}: {exc}")
            time.sleep(0.9)
            continue
        filtered = _tp_manifest_items_for_directory(manifest, directory)
        if filtered:
            best_effort = filtered
            current_urls = _tp_manifest_url_map(filtered)
            if not baseline_urls or current_urls == baseline_urls:
                return filtered
        time.sleep(1.0)
    return best_effort


def _tp_retarget_manifest_items_for_user(session: Session, user: SessionUser, items: list[DownloadFile]) -> list[DownloadFile]:
    target_is_team = bool(user.team_id is not None and user.team_id > 0)
    target_id = int(user.team_id) if target_is_team else int(user.user_id)
    result: list[DownloadFile] = []
    for item in items:
        if item.download_id.paint_type not in {PaintType.CAR, PaintType.CAR_SPEC, PaintType.CAR_DECAL}:
            continue
        result.append(
            DownloadFile(
                download_id=DownloadId(
                    user_id=target_id,
                    directory=user.directory,
                    paint_type=item.download_id.paint_type,
                    is_team_paint=target_is_team,
                    is_superspeedway_variant=_download_uses_superspeedway_variant(
                        user.directory,
                        item.download_id.paint_type,
                        session.is_superspeedway_track,
                    ),
                ),
                url=item.url,
            )
        )
    return result


def restore_tp_showroom_scheme(
    *,
    directory: str,
    scheme_id: str,
    showroom_link: str = "",
    mapping_path: Path | None,
    profile_dir: Path,
    manifest_member_id: int | None = None,
    baseline_manifest_urls: dict[str, str] | None = None,
    retries: int = 3,
    retry_backoff_seconds: float = 1.5,
    browser_channel: str = "chrome",
    log: Callable[[str], None] | None = None,
    shared_context=None,
    shared_page=None,
    shared_auth_state: dict[str, object] | None = None,
) -> tuple[bool, str]:
    def write(msg: str) -> None:
        if log:
            log(msg)

    target_scheme_id = str(scheme_id or "").strip()
    target_showroom_link = str(showroom_link or "").strip()
    if not target_scheme_id:
        return False, f"No original Trading Paints scheme id was captured for '{directory}'."
    raw_directory = str(directory or "").strip()
    directory_key = canonicalize_car_directory(raw_directory).lower()
    mapping_doc = _load_tp_showroom_mapping(mapping_path)
    cars_map = (mapping_doc.get("cars") or {})
    entry = None
    for candidate in _tp_directory_candidate_keys(directory_key):
        possible = cars_map.get(candidate)
        if isinstance(possible, dict):
            entry = possible
            break
    if not isinstance(entry, dict):
        return False, f"No Trading Paints showroom mapping exists for '{raw_directory or directory_key}'."
    if sync_playwright is None:
        return False, "Playwright is not installed in this build."
    mid = int(entry["mid"])
    category = str(entry.get("category") or "Road")
    slug = str(entry.get("slug") or f"car-{mid}")
    profile_dir.mkdir(parents=True, exist_ok=True)
    owned_context = shared_context is None or shared_page is None
    playwright_manager = None
    context = shared_context
    page = shared_page
    try:
        if owned_context:
            playwright_manager = sync_playwright()
            p = playwright_manager.start()
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel=browser_channel,
                headless=True,
                viewport={"width": 1280, "height": 900},
            )
            page = context.pages[0] if context.pages else context.new_page()
        start_url = f"https://www.tradingpaints.com/showroom/{category}/{mid}/{slug}"
        current_url = ""
        try:
            current_url = str(page.url or "")
        except Exception:
            current_url = ""
        if owned_context or not current_url.startswith(start_url):
            page.goto(start_url, wait_until="domcontentloaded", timeout=60000)
        auth_checked = bool((shared_auth_state or {}).get("checked")) and not owned_context
        if auth_checked:
            authenticated = bool((shared_auth_state or {}).get("authenticated"))
        else:
            authenticated, auth_source = _tp_context_looks_authenticated(context, [page])
            if shared_auth_state is not None and not owned_context:
                shared_auth_state["checked"] = True
                shared_auth_state["authenticated"] = bool(authenticated)
                shared_auth_state["auth_source"] = str(auth_source or "")
        if not authenticated:
            clear_tp_login_status(profile_dir, "Trading Paints login is required again for the saved browser profile.")
            return False, "Trading Paints login is required again for the saved browser profile."
        dashboard_url = f"https://www.tradingpaints.com/dashboard/{mid}/{slug}/simstamped"
        set_url = f"https://www.tradingpaints.com/js/setScheme.php?id={target_scheme_id}&sub_make=0"

        def _verify_restore_window(timeout_seconds: float) -> tuple[bool, str]:
            verify_deadline = time.monotonic() + max(2.0, float(timeout_seconds))
            last_seen = ""
            while time.monotonic() < verify_deadline:
                current_scheme_id, current_showroom_link, _current_title, _capture_source = _tp_capture_current_scheme_info(
                    context,
                    page,
                    mid=mid,
                    slug=slug,
                    category=category,
                )
                last_seen = current_showroom_link or current_scheme_id
                if current_scheme_id == target_scheme_id:
                    return True, last_seen
                if manifest_member_id is not None and int(manifest_member_id or 0) > 0 and baseline_manifest_urls:
                    manifest_ok = _tp_manifest_matches_url_map(
                        local_user_id=int(manifest_member_id),
                        directory=raw_directory or directory_key,
                        url_map=dict(baseline_manifest_urls),
                        retries=retries,
                        retry_backoff_seconds=retry_backoff_seconds,
                    )
                    if manifest_ok:
                        write(
                            f"Trading Paints restore verification accepted a fresh manifest match for {raw_directory or directory_key} even though the dashboard last showed {last_seen or 'unknown'}."
                        )
                        return True, last_seen
                time.sleep(0.9)
            return False, last_seen

        referers = [dashboard_url, target_showroom_link or dashboard_url, start_url]
        verified = False
        last_capture = ""
        last_error = ""
        for referer in referers:
            try:
                page.goto(dashboard_url, wait_until="domcontentloaded", timeout=45000)
            except Exception:
                pass
            try:
                set_resp = context.request.get(
                    set_url,
                    headers={
                        "X-Requested-With": "XMLHttpRequest",
                        "Accept": "application/json, text/javascript, */*; q=0.01",
                        "Referer": referer,
                        "Cache-Control": "no-cache",
                        "Pragma": "no-cache",
                    },
                    fail_on_status_code=False,
                )
            except Exception as exc:
                set_resp = None
                last_error = str(exc)
            if set_resp is not None and set_resp.ok:
                write(f"Trading Paints restore called setScheme directly for {raw_directory or directory_key}: {target_scheme_id}.")
                verified, last_capture = _verify_restore_window(6.5)
                if verified:
                    break
            else:
                status_text = f"HTTP {set_resp.status}" if set_resp is not None else last_error or "request failed"
                write(f"Trading Paints direct restore request did not confirm for {raw_directory or directory_key}: {status_text}")
        if not verified and target_showroom_link:
            restored_via_ui = _tp_try_activate_showroom_view(page, target_showroom_link, target_scheme_id, log=write)
            if restored_via_ui:
                verified, last_capture = _verify_restore_window(8.0)
        if not verified:
            return False, (
                f"Trading Paints original scheme restore could not be verified for {raw_directory or directory_key}. "
                f"Expected {target_scheme_id}{(' / ' + target_showroom_link) if target_showroom_link else ''}, last seen {last_capture or 'unknown'}."
            )
        write(f"Trading Paints original scheme restored for {raw_directory or directory_key}: {target_scheme_id}")
        return True, f"Trading Paints original scheme restored for {raw_directory or directory_key}: {target_scheme_id}."
    finally:
        if owned_context and context is not None:
            try:
                context.close()
            except Exception:
                pass
        if owned_context and playwright_manager is not None:
            try:
                playwright_manager.stop()
            except Exception:
                pass


def _tp_fetch_showroom_page_batch(api, *, mid: int, category: str, slug: str, page_index: int) -> list[dict]:
    start_url = f"https://www.tradingpaints.com/showroom/{category}/{mid}/{slug}"
    pos = max(0, int(page_index)) * TP_SHOWROOM_FETCH_PAGE_SIZE
    showroom_url = f"https://www.tradingpaints.com/js/showroom.php?mid={mid}&{DEFAULT_SHOWROOM_PARAMS}&pos={pos}&ts={int(time.time()*1000)}"
    resp = api.get(
        showroom_url,
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "Referer": start_url,
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        },
        fail_on_status_code=False,
    )
    if not resp.ok:
        return []
    try:
        payload = json.loads(resp.text())
    except Exception:
        return []
    parsed = ((payload.get("output") or {}).get("cars") or []) if isinstance(payload, dict) else []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def _detect_tp_showroom_total_pages(
    api,
    *,
    mid: int,
    category: str,
    slug: str,
    max_pages: int = 50,
    log: Callable[[str], None] | None = None,
) -> int:
    page_limit = max(1, min(int(max_pages or 50), 50))
    started = time.monotonic()
    page_has_results: dict[int, bool] = {}

    def _page_exists(page_index: int) -> bool:
        idx = int(page_index)
        if idx in page_has_results:
            return page_has_results[idx]
        batch = _tp_fetch_showroom_page_batch(api, mid=mid, category=category, slug=slug, page_index=idx)
        exists = bool(batch)
        page_has_results[idx] = exists
        return exists

    if not _page_exists(0):
        if log:
            log(f"Trading Paints showroom total pages detected for {category}/{mid}/{slug}: 0 page(s) in {time.monotonic() - started:.2f}s")
        return 0

    last_good = 0
    probe = 1
    while probe < page_limit and _page_exists(probe):
        last_good = probe
        probe *= 2
    low = last_good + 1
    high = min(probe, page_limit - 1)
    while low <= high:
        mid_page = (low + high) // 2
        if _page_exists(mid_page):
            last_good = mid_page
            low = mid_page + 1
        else:
            high = mid_page - 1
    total_pages = last_good + 1
    if log:
        log(f"Trading Paints showroom total pages detected for {category}/{mid}/{slug}: {total_pages} page(s) in {time.monotonic() - started:.2f}s")
    return total_pages


def _fetch_tp_showroom_pool(
    context,
    *,
    mid: int,
    category: str,
    slug: str,
    existing_cars: list[dict] | None = None,
    sampled_pages: set[int] | None = None,
    min_unused_count: int = 1,
    min_random_pages: int = 1,
    max_pages: int = TP_SHOWROOM_MAX_PAGES,
    prefer_official: bool = False,
    exclude_scheme_ids: set[str] | None = None,
    exclude_recent_scheme_ids: set[str] | None = None,
    log: Callable[[str], None] | None = None,
) -> tuple[list[dict], set[int]]:
    api = context.request
    start_url = f"https://www.tradingpaints.com/showroom/{category}/{mid}/{slug}"
    page_limit = max(1, min(int(max_pages or TP_SHOWROOM_MAX_PAGES), 50))
    minimum_page_count = max(1, min(int(min_random_pages or 1), page_limit))
    sampled = set(int(p) for p in (sampled_pages or set()) if int(p) >= 0)
    initial_sampled = set(sampled)
    cars: list[dict] = []
    seen_ids: set[str] = set()
    for car in list(existing_cars or []):
        if not isinstance(car, dict):
            continue
        scheme_id = str(car.get("id") or "").strip()
        if scheme_id and scheme_id in seen_ids:
            continue
        if scheme_id:
            seen_ids.add(scheme_id)
        car_copy = dict(car)
        page_idx_value = car_copy.get("_nishizumi_page_index")
        if page_idx_value is not None:
            try:
                car_copy["_nishizumi_page_index"] = int(page_idx_value)
                car_copy["_nishizumi_page_number"] = int(page_idx_value) + 1
            except Exception:
                pass
        cars.append(car_copy)
    page_choices = list(range(page_limit))
    random.shuffle(page_choices)
    # Keep fetching random unseen pages until the current selection pool can cover the remaining targets.
    # When total-page detection is enabled, we can also intentionally widen the pool across more
    # pages for better variety instead of stopping at the first page that happens to have enough schemes.
    while (
        _showroom_available_count(
            cars,
            prefer_official=prefer_official,
            exclude_scheme_ids=exclude_scheme_ids,
            exclude_recent_scheme_ids=exclude_recent_scheme_ids,
        ) < max(1, int(min_unused_count or 1))
        or len(sampled) < minimum_page_count
    ):
        next_page = None
        for page_idx in page_choices:
            if page_idx not in sampled:
                next_page = page_idx
                break
        if next_page is None:
            break
        sampled.add(next_page)
        batch = _tp_fetch_showroom_page_batch(
            api,
            mid=mid,
            category=category,
            slug=slug,
            page_index=next_page,
        )
        for car in batch:
            scheme_id = str(car.get("id") or "").strip()
            if scheme_id and scheme_id in seen_ids:
                continue
            if scheme_id:
                seen_ids.add(scheme_id)
            car_copy = dict(car)
            car_copy["_nishizumi_page_index"] = int(next_page)
            car_copy["_nishizumi_page_number"] = int(next_page) + 1
            cars.append(car_copy)
    newly_sampled = sorted(sampled - initial_sampled)
    if log and newly_sampled:
        sampled_list = sorted(sampled)
        sampled_human = ", ".join(str(page_idx + 1) for page_idx in sampled_list)
        log(
            f"Trading Paints showroom pool fetched for {category}/{mid}/{slug}: {len(cars)} unique scheme(s) across {len(sampled_list)} random page(s) [pages: {sampled_human}]"
        )
    return cars, sampled


def _tp_build_direct_items_from_url_map(
    *,
    user_id: int,
    directory: str,
    url_map: dict[str, str],
) -> list[DownloadFile]:
    result: list[DownloadFile] = []
    for paint_type in (PaintType.CAR, PaintType.CAR_SPEC, PaintType.CAR_DECAL):
        url = str((url_map or {}).get(paint_type.value) or "").strip()
        if not url:
            continue
        result.append(
            DownloadFile(
                download_id=DownloadId(
                    user_id=int(user_id),
                    directory=directory,
                    paint_type=paint_type,
                    is_team_paint=False,
                    is_superspeedway_variant=False,
                ),
                url=url,
            )
        )
    return result


def _tp_manifest_matches_url_map(
    *,
    local_user_id: int,
    directory: str,
    url_map: dict[str, str],
    retries: int,
    retry_backoff_seconds: float,
) -> bool:
    try:
        manifest = fetch_user_files(local_user_id, retries, retry_backoff_seconds)
    except Exception:
        return False
    filtered = _tp_manifest_items_for_directory(manifest, directory)
    current_urls = _tp_manifest_url_map(filtered)
    if not current_urls or not url_map:
        return False
    return current_urls == dict(url_map)


def choose_and_sync_showroom_paint(
    *,
    directory: str,
    mapping_path: Path | None,
    profile_dir: Path,
    paints_dir: Path,
    manifest_member_id: int | None,
    local_team_id: int | None,
    browser_channel: str = "chrome",
    pages: int = TP_SHOWROOM_MAX_PAGES,
    prefer_official: bool = False,
    choice_mode: str = "random",
    trigger_local_update: bool = True,
    timeout_seconds: float = 35.0,
    retries: int = 3,
    retry_backoff_seconds: float = 1.5,
    original_scheme_id: str = "",
    exclude_scheme_ids: set[str] | None = None,
    exclude_recent_scheme_ids: set[str] | None = None,
    showroom_cars: list[dict] | None = None,
    showroom_sampled_pages: set[int] | None = None,
    detected_total_pages: int | None = None,
    detect_total_pages: bool = False,
    minimum_unused_choices: int = 1,
    log: Callable[[str], None] | None = None,
    shared_context=None,
    shared_page=None,
    shared_auth_state: dict[str, object] | None = None,
    fast_mule_mode: bool = False,
    baseline_manifest_urls_override: dict[str, str] | None = None,
) -> TPShowroomSyncResult:
    def write(msg: str) -> None:
        if log:
            log(msg)

    raw_directory = str(directory or "").strip()
    directory_key = canonicalize_car_directory(raw_directory).lower()
    mapping_doc = _load_tp_showroom_mapping(mapping_path)
    unsupported = (mapping_doc.get("unsupported") or {})
    cars_map = (mapping_doc.get("cars") or {})
    candidate_keys = _tp_directory_candidate_keys(directory_key)
    for candidate in candidate_keys:
        if candidate in unsupported:
            return TPShowroomSyncResult(ok=False, message=f"Trading Paints does not currently have a supported showroom car for '{candidate}'.")
    entry = None
    matched_key = directory_key
    for candidate in candidate_keys:
        possible = cars_map.get(candidate)
        if isinstance(possible, dict):
            entry = possible
            matched_key = candidate
            break
    if not isinstance(entry, dict):
        return TPShowroomSyncResult(ok=False, message=f"No Trading Paints showroom mapping exists for '{directory_key}'.")
    if sync_playwright is None:
        return TPShowroomSyncResult(ok=False, message="Playwright is not installed in this build.")
    if manifest_member_id is None or int(manifest_member_id) <= 0:
        return TPShowroomSyncResult(ok=False, message="The online Trading Paints fallback requires a Trading Paints member id for manifest polling. Set the TP manifest member ID in the app settings first.")
    mid = int(entry["mid"])
    category = str(entry.get("category") or "Road")
    slug = str(entry.get("slug") or f"car-{mid}")
    profile_dir.mkdir(parents=True, exist_ok=True)
    local_member_id = int(manifest_member_id)
    captured_original_scheme_id = str(original_scheme_id or "").strip()
    captured_original_scheme_link = ""
    captured_original_scheme_title = ""
    baseline_manifest_items: list[DownloadFile] = []
    if baseline_manifest_urls_override:
        baseline_url_map = dict(baseline_manifest_urls_override)
    else:
        try:
            baseline_manifest_items = _tp_manifest_items_for_directory(
                fetch_user_files(local_member_id, retries, retry_backoff_seconds),
                raw_directory or matched_key,
            )
        except Exception:
            baseline_manifest_items = []
        baseline_url_map = _tp_manifest_url_map(baseline_manifest_items)
    sampled_page_set: set[int] = set(int(p) for p in (showroom_sampled_pages or set()) if int(p) >= 0)
    owned_context = shared_context is None or shared_page is None
    playwright_manager = None
    context = shared_context
    page = shared_page
    try:
        if owned_context:
            playwright_manager = sync_playwright()
            p = playwright_manager.start()
            context = p.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel=browser_channel,
                headless=True,
                viewport={"width": 1280, "height": 900},
            )
            page = context.pages[0] if context.pages else context.new_page()
        start_url = f"https://www.tradingpaints.com/showroom/{category}/{mid}/{slug}"
        current_url = ""
        try:
            current_url = str(page.url or "")
        except Exception:
            current_url = ""
        if owned_context or not current_url.startswith(start_url):
            page.goto(start_url, wait_until="domcontentloaded", timeout=60000)
        api = context.request
        detected_total_pages_value = 0
        try:
            if detected_total_pages is not None and int(detected_total_pages or 0) > 0:
                detected_total_pages_value = max(0, int(detected_total_pages or 0))
        except Exception:
            detected_total_pages_value = 0
        if detect_total_pages and detected_total_pages_value <= 0:
            try:
                detected_total_pages_value = _detect_tp_showroom_total_pages(
                    api,
                    mid=mid,
                    category=category,
                    slug=slug,
                    max_pages=50,
                    log=write,
                )
            except Exception as exc:
                write(f"Trading Paints showroom total page detection failed for {category}/{mid}/{slug}: {exc}")
                detected_total_pages_value = 0
        effective_page_limit = max(1, int(detected_total_pages_value or pages or TP_SHOWROOM_MAX_PAGES))
        desired_random_pages = 1
        auth_checked = bool((shared_auth_state or {}).get("checked")) and not owned_context
        if auth_checked:
            authenticated = bool((shared_auth_state or {}).get("authenticated"))
            auth_source = str((shared_auth_state or {}).get("auth_source") or "cached shared context")
        else:
            authenticated, auth_source = _tp_context_looks_authenticated(context, [page])
            if shared_auth_state is not None and not owned_context:
                shared_auth_state["checked"] = True
                shared_auth_state["authenticated"] = bool(authenticated)
                shared_auth_state["auth_source"] = str(auth_source or "")
        if not authenticated:
            clear_tp_login_status(profile_dir, "Trading Paints login is required again for the saved browser profile.")
            return TPShowroomSyncResult(ok=False, auth_required=True, original_scheme_id=captured_original_scheme_id, message="Trading Paints login is required again for the saved browser profile.")
        if not auth_checked:
            write(f"Trading Paints authenticated session confirmed via {auth_source}")
        if (not fast_mule_mode) and not captured_original_scheme_id:
            captured_original_scheme_id, captured_original_scheme_link, captured_original_scheme_title, capture_source = _tp_capture_current_scheme_info(
                context,
                page,
                mid=mid,
                slug=slug,
                category=category,
            )
            if captured_original_scheme_id:
                extra = f" -> {captured_original_scheme_link}" if captured_original_scheme_link else ""
                write(f"Captured original Trading Paints scheme for {raw_directory or matched_key}: {captured_original_scheme_id} ({capture_source}){extra}")
        cars = [item for item in (showroom_cars or []) if isinstance(item, dict)]
        min_choices_needed = max(1, int(minimum_unused_choices or 1))
        if detect_total_pages and detected_total_pages_value > 0:
            # Optional behavior: detect the *real* total number of showroom pages and then
            # keep the same default behavior of sampling a single random page, but now from
            # the real page universe instead of the fixed fallback ceiling.
            desired_random_pages = 1
            write(
                f"Trading Paints showroom total page detection will be used as the random-page universe for {category}/{mid}/{slug}: choosing 1 random page out of {detected_total_pages_value} detected total page(s)."
            )
        current_available = _showroom_available_count(
            cars,
            prefer_official=prefer_official,
            exclude_scheme_ids=exclude_scheme_ids,
            exclude_recent_scheme_ids=exclude_recent_scheme_ids,
        )
        if current_available < min_choices_needed:
            cars, sampled_page_set = _fetch_tp_showroom_pool(
                context,
                mid=mid,
                category=category,
                slug=slug,
                existing_cars=cars,
                sampled_pages=sampled_page_set,
                min_unused_count=min_choices_needed,
                min_random_pages=desired_random_pages,
                max_pages=effective_page_limit,
                prefer_official=prefer_official,
                exclude_scheme_ids=exclude_scheme_ids,
                exclude_recent_scheme_ids=exclude_recent_scheme_ids,
                log=write,
            )
        if not cars:
            return TPShowroomSyncResult(
                ok=False,
                original_scheme_id=captured_original_scheme_id,
                showroom_count=0,
                showroom_cars=cars,
                showroom_sampled_pages=sorted(sampled_page_set),
                detected_total_pages=detected_total_pages_value,
                baseline_manifest_urls=dict(baseline_url_map),
                original_scheme_link=captured_original_scheme_link,
                original_scheme_title=captured_original_scheme_title,
                message=f"No public showroom paints were returned for '{raw_directory or matched_key}'.",
            )
        chosen, reused_previous_scheme, reused_recent_history = _pick_showroom_scheme(
            cars,
            choice_mode=choice_mode,
            prefer_official=prefer_official,
            exclude_scheme_ids=exclude_scheme_ids,
            exclude_recent_scheme_ids=exclude_recent_scheme_ids,
        )
        chosen_scheme_id = str(chosen.get("id") or "").strip()
        chosen_title = str(chosen.get("title") or "").strip()
        if reused_previous_scheme:
            write(
                f"Trading Paints showroom fallback reused a previously used scheme for {raw_directory or matched_key} because no unused showroom schemes remained in the fetched pool."
            )
        elif reused_recent_history:
            write(
                f"Trading Paints showroom fallback reused a recent prior-session scheme for {raw_directory or matched_key} because no unseen showroom schemes remained in the fetched pool."
            )
        chosen_page_number = chosen.get("_nishizumi_page_number")
        chosen_page_label = "unknown"
        try:
            if chosen_page_number is not None:
                chosen_page_label = str(int(chosen_page_number))
        except Exception:
            chosen_page_label = str(chosen_page_number or "unknown")
        write(
            f"Trading Paints showroom fallback picked {chosen_scheme_id} for {raw_directory or matched_key}: {chosen_title} [random page {chosen_page_label}]"
        )
        set_url = f"https://www.tradingpaints.com/js/setScheme.php?id={chosen_scheme_id}&sub_make=0"
        set_resp = api.get(
            set_url,
            headers={
                "X-Requested-With": "XMLHttpRequest",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Referer": start_url,
            },
            fail_on_status_code=False,
        )
        if not set_resp.ok:
            return TPShowroomSyncResult(
                ok=False,
                chosen_scheme_id=chosen_scheme_id,
                chosen_title=chosen_title,
                showroom_count=len(cars),
                original_scheme_id=captured_original_scheme_id,
                showroom_cars=cars,
                showroom_sampled_pages=sorted(sampled_page_set),
                detected_total_pages=detected_total_pages_value,
                baseline_manifest_urls=dict(baseline_url_map),
                original_scheme_link=captured_original_scheme_link,
                original_scheme_title=captured_original_scheme_title,
                message=f"setScheme failed with HTTP {set_resp.status} for {chosen_scheme_id}.",
            )
        chosen_scheme_confirmed = False
        if fast_mule_mode:
            write(f"Trading Paints showroom scheme {chosen_scheme_id} was requested for {raw_directory or matched_key}; TP mule fast mode is skipping the slow dashboard confirmation loop and polling the manifest directly.")
        else:
            confirm_deadline = time.monotonic() + 8.0
            while time.monotonic() < confirm_deadline:
                try:
                    active_scheme_id, _active_source = _tp_capture_current_scheme_id(
                        context,
                        page,
                        mid=mid,
                        slug=slug,
                        category=category,
                    )
                except Exception:
                    active_scheme_id = ""
                if active_scheme_id and active_scheme_id == chosen_scheme_id:
                    chosen_scheme_confirmed = True
                    break
                time.sleep(0.9)
            if chosen_scheme_confirmed:
                write(f"Trading Paints showroom scheme {chosen_scheme_id} is now active for {raw_directory or matched_key}; waiting for manifest refresh.")
            else:
                write(f"Trading Paints showroom scheme {chosen_scheme_id} was requested for {raw_directory or matched_key}, but the dashboard did not confirm the swap quickly; continuing to poll the manifest anyway.")
        direct_items = _tp_wait_for_fetch_user_manifest(
            local_user_id=local_member_id,
            directory=raw_directory or matched_key,
            retries=retries,
            retry_backoff_seconds=retry_backoff_seconds,
            baseline_urls=baseline_url_map,
            timeout_seconds=(18.0 if fast_mule_mode else timeout_seconds),
            log=write,
        )
        if not direct_items:
            return TPShowroomSyncResult(
                ok=False,
                chosen_scheme_id=chosen_scheme_id,
                chosen_title=chosen_title,
                showroom_count=len(cars),
                original_scheme_id=captured_original_scheme_id,
                showroom_cars=cars,
                set_scheme_applied=True,
                reused_previous_scheme=reused_previous_scheme,
                reused_recent_history=reused_recent_history,
                showroom_sampled_pages=sorted(sampled_page_set),
                detected_total_pages=detected_total_pages_value,
                baseline_manifest_urls=dict(baseline_url_map),
                original_scheme_link=captured_original_scheme_link,
                original_scheme_title=captured_original_scheme_title,
                message=(
                    "The showroom paint was selected online, but the local account manifest never exposed fresh car asset URLs in time."
                ),
            )
        return TPShowroomSyncResult(
            ok=True,
            chosen_scheme_id=chosen_scheme_id,
            chosen_title=chosen_title,
            showroom_count=len(cars),
            original_scheme_id=captured_original_scheme_id,
            showroom_cars=cars,
            showroom_sampled_pages=sorted(sampled_page_set),
                detected_total_pages=detected_total_pages_value,
            baseline_manifest_urls=dict(baseline_url_map),
            original_scheme_link=captured_original_scheme_link,
            original_scheme_title=captured_original_scheme_title,
            direct_items=direct_items,
            set_scheme_applied=True,
            reused_previous_scheme=reused_previous_scheme,
            reused_recent_history=reused_recent_history,
            message=f"Prepared direct Trading Paints asset download for showroom scheme {chosen_scheme_id} on {raw_directory or matched_key}.",
        )
    finally:
        if owned_context and context is not None:
            try:
                context.close()
            except Exception:
                pass
        if owned_context and playwright_manager is not None:
            try:
                playwright_manager.stop()
            except Exception:
                pass

def apply_tp_showroom_fallbacks(
    session: Session,
    saved: list[SavedFile],
    paints_dir: Path,
    enable_real_drivers: bool,
    enable_ai: bool,
    sync_my_livery_from_server: bool,
    mapping_path: Path | None = None,
    profile_dir: Path | None = None,
    manifest_member_id: int | None = None,
    mule_profile_mode: bool = False,
    detect_showroom_total_pages: bool = False,
    retries: int = 3,
    retry_backoff_seconds: float = 1.5,
    _thread_handoff_done: bool = False,
) -> tuple[list[SavedFile], list[str], RandomFallbackSummary]:
    if sync_playwright is not None and not _thread_handoff_done:
        return _run_tp_sync_api_in_thread(
            lambda: apply_tp_showroom_fallbacks(
                session=session,
                saved=saved,
                paints_dir=paints_dir,
                enable_real_drivers=enable_real_drivers,
                enable_ai=enable_ai,
                sync_my_livery_from_server=sync_my_livery_from_server,
                mapping_path=mapping_path,
                profile_dir=profile_dir,
                manifest_member_id=manifest_member_id,
                mule_profile_mode=mule_profile_mode,
                detect_showroom_total_pages=detect_showroom_total_pages,
                retries=retries,
                retry_backoff_seconds=retry_backoff_seconds,
                _thread_handoff_done=True,
            )
        )
    logs: list[str] = []
    fallback_saved: list[SavedFile] = []
    summary = RandomFallbackSummary()
    profile_dir = profile_dir or default_tp_showroom_profile_dir()
    effective_mule_mode = bool(mule_profile_mode)
    if not effective_mule_mode:
        try:
            if (
                manifest_member_id is not None
                and int(manifest_member_id or 0) > 0
                and session.local_user_id is not None
                and int(session.local_user_id or 0) > 0
                and int(manifest_member_id) != int(session.local_user_id)
            ):
                effective_mule_mode = True
                logs.append(
                    "Trading Paints mule fast mode was auto-enabled because the TP manifest member ID override differs from the local iRacing user id."
                )
        except Exception:
            effective_mule_mode = bool(mule_profile_mode)
    if effective_mule_mode:
        logs.append("Trading Paints mule fast mode is enabled for the online fallback: the app will skip original-scheme capture and final restore, reuse the showroom/browser context for the whole session, and rely on direct manifest polling after each setScheme.")
    if detect_showroom_total_pages:
        logs.append("Trading Paints showroom total page detection is enabled for this profile. The app will probe the showroom and log the detected total pages before filling the pool.")
    if not is_tp_login_confirmed(profile_dir):
        logs.append("Trading Paints showroom fallback is enabled, but the Trading Paints login has not been confirmed yet.")
        return fallback_saved, logs, summary
    existing_car_targets = {
        (bool(item.download_id.is_team_paint), int(item.download_id.user_id), item.download_id.directory.lower())
        for item in saved
        if item.download_id.paint_type is PaintType.CAR
    }
    original_scheme_cache = load_tp_original_scheme_cache(profile_dir)
    original_scheme_by_directory: dict[str, str] = {k: str(v.get("scheme_id") or "").strip() for k, v in original_scheme_cache.items() if isinstance(v, dict)}
    original_scheme_meta_by_directory: dict[str, dict[str, str]] = {k: dict(v) for k, v in original_scheme_cache.items() if isinstance(v, dict)}
    original_baseline_urls_by_directory: dict[str, dict[str, str]] = {}
    current_manifest_urls_by_directory: dict[str, dict[str, str]] = {}
    original_local_backup_by_directory: dict[str, dict[str, bytes]] = {}
    display_directory_by_key: dict[str, str] = {}
    touched_directories: set[str] = set()
    used_scheme_ids_by_directory: dict[str, set[str]] = {}
    showroom_pool_state_by_directory: dict[str, dict[str, object]] = {}
    recent_schemes_by_directory = load_tp_recent_schemes()
    temp_root = default_temp_dir()
    remaining_targets_by_directory: dict[str, int] = {}
    shared_tp_context = None
    shared_tp_page = None
    shared_tp_auth_state: dict[str, object] = {}
    shared_tp_playwright_manager = None
    if sync_playwright is not None:
        try:
            shared_tp_playwright_manager = sync_playwright()
            shared_tp_browser = shared_tp_playwright_manager.start()
            shared_tp_context = shared_tp_browser.chromium.launch_persistent_context(
                user_data_dir=str(profile_dir),
                channel="chrome",
                headless=True,
                viewport={"width": 1280, "height": 900},
            )
            shared_tp_page = shared_tp_context.pages[0] if shared_tp_context.pages else shared_tp_context.new_page()
        except Exception:
            logging.debug("Could not open shared Trading Paints browser context; falling back to per-call contexts", exc_info=True)
            shared_tp_page = None
            if shared_tp_context is not None:
                try:
                    shared_tp_context.close()
                except Exception:
                    pass
            shared_tp_context = None
            if shared_tp_playwright_manager is not None:
                try:
                    shared_tp_playwright_manager.stop()
                except Exception:
                    pass
            shared_tp_playwright_manager = None
    for candidate in sorted(session.users, key=lambda u: (u.is_ai, u.directory.lower(), u.user_id, u.team_id or 0)):
        if candidate.is_ai:
            if not enable_ai:
                continue
        else:
            if not enable_real_drivers:
                continue
        is_local_target = False
        if session.local_user_id is not None and candidate.user_id == session.local_user_id:
            is_local_target = True
        if session.local_team_id is not None and candidate.team_id is not None and candidate.team_id == session.local_team_id:
            is_local_target = True
        if is_local_target and not sync_my_livery_from_server:
            continue
        target_is_team = bool(candidate.team_id is not None and candidate.team_id > 0)
        target_id = int(candidate.team_id) if target_is_team else int(candidate.user_id)
        target_key = (target_is_team, target_id, candidate.directory.lower())
        if target_key in existing_car_targets:
            continue
        directory_key = canonicalize_car_directory(candidate.directory).lower()
        remaining_targets_by_directory[directory_key] = remaining_targets_by_directory.get(directory_key, 0) + 1
    for user in sorted(session.users, key=lambda u: (u.is_ai, u.directory.lower(), u.user_id, u.team_id or 0)):
        if user.is_ai:
            if not enable_ai:
                continue
        else:
            if not enable_real_drivers:
                continue
        is_local_target = False
        if session.local_user_id is not None and user.user_id == session.local_user_id:
            is_local_target = True
        if session.local_team_id is not None and user.team_id is not None and user.team_id == session.local_team_id:
            is_local_target = True
        if is_local_target and not sync_my_livery_from_server:
            continue
        target_is_team = bool(user.team_id is not None and user.team_id > 0)
        target_id = int(user.team_id) if target_is_team else int(user.user_id)
        target_key = (target_is_team, target_id, user.directory.lower())
        if target_key in existing_car_targets:
            continue
        directory_key = canonicalize_car_directory(user.directory).lower()
        display_directory_by_key.setdefault(directory_key, user.directory)
        cached_original = original_scheme_cache.get(directory_key) if isinstance(original_scheme_cache.get(directory_key), dict) else None
        if cached_original and str(cached_original.get("scheme_id") or "").strip() and directory_key not in touched_directories and directory_key not in original_baseline_urls_by_directory:
            logs.append(f"Using cached Trading Paints original scheme for {user.directory}: {str(cached_original.get('scheme_id') or "").strip()}")
        summary.attempted_targets += 1
        pool_state = showroom_pool_state_by_directory.setdefault(directory_key, {"cars": [], "sampled_pages": set(), "total_pages": 0})
        showroom_cars = pool_state.get("cars") if isinstance(pool_state, dict) else []
        showroom_sampled_pages = pool_state.get("sampled_pages") if isinstance(pool_state, dict) else set()
        detected_total_pages = pool_state.get("total_pages") if isinstance(pool_state, dict) else 0
        if (not effective_mule_mode) and directory_key not in original_local_backup_by_directory:
            try:
                original_local_backup_by_directory[directory_key] = _capture_local_tp_backup(
                    _candidate_local_tp_paths(
                        paints_dir,
                        [user.directory, directory_key],
                        session.local_user_id,
                        session.local_team_id,
                    )
                )
            except Exception:
                original_local_backup_by_directory[directory_key] = {}
        try:
            result = choose_and_sync_showroom_paint(
                directory=user.directory,
                mapping_path=mapping_path,
                profile_dir=profile_dir,
                paints_dir=paints_dir,
                manifest_member_id=manifest_member_id,
                local_team_id=session.local_team_id,
                retries=retries,
                retry_backoff_seconds=retry_backoff_seconds,
                original_scheme_id=original_scheme_by_directory.get(directory_key, ""),
                exclude_scheme_ids=used_scheme_ids_by_directory.get(directory_key, set()),
                exclude_recent_scheme_ids=set(recent_schemes_by_directory.get(directory_key, [])),
                showroom_cars=showroom_cars if isinstance(showroom_cars, list) else [],
                showroom_sampled_pages=showroom_sampled_pages if isinstance(showroom_sampled_pages, set) else set(showroom_sampled_pages or []),
                detected_total_pages=int(detected_total_pages or 0) if str(detected_total_pages).strip() else 0,
                detect_total_pages=bool(detect_showroom_total_pages),
                minimum_unused_choices=max(1, int(remaining_targets_by_directory.get(directory_key, 1) or 1)),
                log=logging.info,
                shared_context=shared_tp_context,
                shared_page=shared_tp_page,
                shared_auth_state=shared_tp_auth_state,
                fast_mule_mode=bool(effective_mule_mode),
                baseline_manifest_urls_override=current_manifest_urls_by_directory.get(directory_key),
            )
        except Exception as exc:  # noqa: BLE001
            label = user.display_name or (f"AI {target_id}" if user.is_ai else f"user {target_id}")
            logs.append(f"Trading Paints showroom fallback errored for {'AI' if user.is_ai else 'driver'} {label} on {user.directory}: {exc}")
            logging.debug("Trading Paints showroom fallback exception", exc_info=True)
            summary.missing_source_targets += 1
            remaining_targets_by_directory[directory_key] = max(0, int(remaining_targets_by_directory.get(directory_key, 0)) - 1)
            continue
        remaining_targets_by_directory[directory_key] = max(0, int(remaining_targets_by_directory.get(directory_key, 0)) - 1)
        if result.showroom_cars:
            pool_state = showroom_pool_state_by_directory.setdefault(directory_key, {"cars": [], "sampled_pages": set(), "total_pages": 0})
            pool_state["cars"] = [item for item in result.showroom_cars if isinstance(item, dict)]
            pool_state["sampled_pages"] = set(int(p) for p in (result.showroom_sampled_pages or []) if str(p).strip())
            if int(getattr(result, "detected_total_pages", 0) or 0) > 0:
                pool_state["total_pages"] = int(getattr(result, "detected_total_pages", 0) or 0)
        if (not effective_mule_mode) and result.original_scheme_id and not str(original_scheme_by_directory.get(directory_key) or "").strip():
            original_scheme_by_directory[directory_key] = result.original_scheme_id
            original_scheme_cache[directory_key] = {
                "scheme_id": str(result.original_scheme_id or "").strip(),
                "showroom_link": str(result.original_scheme_link or "").strip(),
                "title": str(result.original_scheme_title or "").strip(),
                "captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "source": "dashboard",
            }
            save_tp_original_scheme_cache(original_scheme_cache, profile_dir)
            link_extra = f" -> {str(result.original_scheme_link or "").strip()}" if str(result.original_scheme_link or "").strip() else ""
            logs.append(f"Captured original Trading Paints scheme for {user.directory}: {result.original_scheme_id}{link_extra}")
        if result.baseline_manifest_urls and directory_key not in original_baseline_urls_by_directory:
            original_baseline_urls_by_directory[directory_key] = dict(result.baseline_manifest_urls)
        if result.set_scheme_applied:
            touched_directories.add(directory_key)
        if result.chosen_scheme_id:
            used_scheme_ids_by_directory.setdefault(directory_key, set()).add(str(result.chosen_scheme_id).strip())
            remember_tp_recent_scheme(recent_schemes_by_directory, directory_key, result.chosen_scheme_id)
        if result.reused_previous_scheme:
            summary.repeated_source_uses += 1
        if not result.ok:
            summary.missing_source_targets += 1
            label = user.display_name or (f"AI {target_id}" if user.is_ai else f"user {target_id}")
            logs.append(f"Trading Paints showroom fallback could not fill {'AI' if user.is_ai else 'driver'} {label} on {user.directory}: {result.message}")
            continue
        if result.direct_items:
            current_manifest_urls_by_directory[directory_key] = _tp_manifest_url_map(result.direct_items)
        retargeted_items = _tp_retarget_manifest_items_for_user(session, user, result.direct_items)
        if not retargeted_items:
            summary.missing_source_targets += 1
            logs.append(f"Trading Paints showroom fallback selected a scheme for {user.directory}, but the current account manifest did not expose any usable car files.")
            continue
        downloaded_items: list[DownloadedFile] = []
        for ordinal, item in enumerate(retargeted_items, start=1):
            downloaded = download_file(
                session.session_id,
                temp_root,
                item,
                retries,
                retry_backoff_seconds,
                ordinal=ordinal,
                total=len(retargeted_items),
            )
            if downloaded is not None:
                downloaded_items.append(downloaded)
        added_any = False
        for downloaded in downloaded_items:
            saved_items = move_or_extract(downloaded, paints_dir)
            if saved_items:
                fallback_saved.extend(saved_items)
                added_any = True
        if added_any:
            summary.applied_targets += 1
            existing_car_targets.add(target_key)
            label = user.display_name or (f"AI {target_id}" if user.is_ai else f"user {target_id}")
            logs.append(
                f"Trading Paints showroom fallback applied to {'AI' if user.is_ai else 'driver'} {label} on {user.directory} using scheme {result.chosen_scheme_id} ({result.chosen_title})"
            )
        else:
            summary.missing_source_targets += 1
            logs.append(f"Trading Paints showroom fallback selected a scheme for {user.directory}, but nothing could be downloaded or saved into the target paint slots.")
    if effective_mule_mode:
        for directory_key in sorted(touched_directories):
            display_directory = display_directory_by_key.get(directory_key, directory_key)
            logs.append(f"Trading Paints original scheme restore skipped for {display_directory} because TP mule fast mode is enabled for this profile.")
        if shared_tp_context is not None:
            try:
                shared_tp_context.close()
            except Exception:
                pass
            shared_tp_context = None
            shared_tp_page = None
        if shared_tp_playwright_manager is not None:
            try:
                shared_tp_playwright_manager.stop()
            except Exception:
                pass
            shared_tp_playwright_manager = None
        return fallback_saved, logs, summary
    for directory_key in sorted(touched_directories):
        cached_original_entry = original_scheme_meta_by_directory.get(directory_key) if isinstance(original_scheme_meta_by_directory.get(directory_key), dict) else {}
        original_scheme_id = str(original_scheme_by_directory.get(directory_key) or (cached_original_entry or {}).get("scheme_id") or "").strip()
        display_directory = display_directory_by_key.get(directory_key, directory_key)
        if not original_scheme_id:
            logs.append(f"Trading Paints original scheme could not be restored for {display_directory} because no original scheme id was captured. Set your desired main paint on Trading Paints once, then run the app again so it can cache that baseline.")
            continue
        try:
            restored, restore_message = restore_tp_showroom_scheme(
                directory=display_directory,
                scheme_id=original_scheme_id,
                showroom_link=str((cached_original_entry or {}).get("showroom_link") or "").strip(),
                mapping_path=mapping_path,
                profile_dir=profile_dir,
                manifest_member_id=manifest_member_id,
                baseline_manifest_urls=original_baseline_urls_by_directory.get(directory_key),
                retries=retries,
                retry_backoff_seconds=retry_backoff_seconds,
                log=logging.info,
                shared_context=shared_tp_context,
                shared_page=shared_tp_page,
                shared_auth_state=shared_tp_auth_state,
            )
        except Exception as exc:  # noqa: BLE001
            restored = False
            restore_message = f"Trading Paints original scheme restore errored for {display_directory}: {exc}"
            logging.debug("Trading Paints original scheme restore exception", exc_info=True)
        logs.append(restore_message)
        restored_local_any = False
        if session.local_user_id is not None and int(session.local_user_id or 0) > 0:
            try:
                refreshed_items = _tp_wait_for_fetch_user_manifest_match(
                    local_user_id=int(session.local_user_id),
                    directory=display_directory,
                    retries=retries,
                    retry_backoff_seconds=retry_backoff_seconds,
                    baseline_urls=original_baseline_urls_by_directory.get(directory_key),
                    timeout_seconds=10.0,
                    log=logging.info,
                )
                if refreshed_items:
                    restored_downloads: list[DownloadedFile] = []
                    for ordinal, item in enumerate(refreshed_items, start=1):
                        downloaded = download_file(
                            session.session_id,
                            temp_root,
                            item,
                            retries,
                            retry_backoff_seconds,
                            ordinal=ordinal,
                            total=len(refreshed_items),
                        )
                        if downloaded is not None:
                            restored_downloads.append(downloaded)
                    for downloaded in restored_downloads:
                        saved_items = move_or_extract(downloaded, paints_dir)
                        if saved_items:
                            restored_local_any = True
                    if restored_local_any:
                        logs.append(f"Trading Paints original local files restored for {display_directory} (user {session.local_user_id}) using fresh manifest URLs.")
            except Exception as exc:  # noqa: BLE001
                logging.debug("Trading Paints original local file restore exception", exc_info=True)
                logs.append(f"Trading Paints original local files could not be restored from fresh manifest for {display_directory}: {exc}")
        if not restored_local_any:
            backup = dict(original_local_backup_by_directory.get(directory_key) or {})
            if backup:
                try:
                    if _restore_local_tp_backup(backup):
                        restored_local_any = True
                        logs.append(f"Trading Paints original local files restored for {display_directory} from local backup.")
                except Exception as exc:  # noqa: BLE001
                    logging.debug("Trading Paints local backup restore exception", exc_info=True)
                    logs.append(f"Trading Paints original local backup restore failed for {display_directory}: {exc}")
    if shared_tp_context is not None:
        try:
            shared_tp_context.close()
        except Exception:
            pass
        shared_tp_context = None
        shared_tp_page = None
    if shared_tp_playwright_manager is not None:
        try:
            shared_tp_playwright_manager.stop()
        except Exception:
            pass
        shared_tp_playwright_manager = None
    return fallback_saved, logs, summary

def _unique_local_ai_roster_dir(ai_rosters_dir: Path, preferred_name: str) -> Path:
    preferred = _safe_ai_roster_folder_name(preferred_name, "AI_Roster_local")
    candidate = ai_rosters_dir / preferred
    if not candidate.exists():
        return candidate
    suffix = 2
    while True:
        candidate = ai_rosters_dir / f"{preferred} {suffix}"
        if not candidate.exists():
            return candidate
        suffix += 1
def randomize_active_ai_roster_from_pool(session: Session | None, ai_rosters_dir: Path, random_pool_dir: Path, ai_livery_root: Path) -> tuple[bool, str]:
    if session is None:
        return False, "No active session is available yet."
    if session.ai_driver_count <= 0:
        return False, "No AI drivers were detected in the current session."
    source_dir = _find_active_ai_roster_dir(session, ai_rosters_dir)
    if source_dir is None or not (source_dir / "roster.json").exists():
        return False, "No active synced TP AI roster was found locally. Sync TP AI rosters first."
    canonical_payload, drivers = _read_ai_roster_payload(source_dir)
    if not drivers:
        return False, "The active AI roster does not contain any drivers to randomize."
    base_name = session.ai_roster_name or source_dir.name
    target_dir = _unique_local_ai_roster_dir(ai_rosters_dir, f"{base_name} (random local)")
    target_dir.mkdir(parents=True, exist_ok=True)
    used_source_ids: set[str] = set()
    assigned = 0
    copied_files = 0
    assignment_logs: list[str] = []
    for index, driver in enumerate(drivers, start=1):
        directory = str(driver.get("carPath") or "").replace("\\", " ").strip()
        if not directory:
            continue
        seed_text = f"{session.session_id.folder_name()}|ai_roster|{driver.get('driverName','')}|{directory}|{index}"
        entry, reused_existing_source = _choose_random_pool_entry(directory, random_pool_dir, ai_livery_root, used_source_ids, seed_text)
        if entry is None:
            continue
        car_name = f"car_{index}.tga"
        car_dest = target_dir / car_name
        shutil.copy2(entry.car_file, car_dest)
        copied_files += 1
        if entry.spec_file is not None and entry.spec_file.exists():
            shutil.copy2(entry.spec_file, target_dir / f"car_{index}_spec.mip")
            copied_files += 1
        driver["carTgaName"] = car_name
        assigned += 1
        assignment_logs.append(
            f"AI roster random slot {index} ({driver.get('driverName','?')}) on {directory} <= {entry.source_kind}:{entry.source_id} ({entry.car_file.name}){' [repeat used after unique pool exhausted]' if reused_existing_source else ''}"
        )
    if assigned <= 0:
        shutil.rmtree(target_dir, ignore_errors=True)
        return False, "No local TP-sourced random paints were available for the cars in the active AI roster yet."
    _write_ai_roster_files(
        target_dir,
        {"drivers": drivers},
        drivers,
        None,
        is_local=True,
        source_roster_id=session.ai_roster_id,
        source_name=base_name,
    )
    if assignment_logs:
        logging.info("AI roster randomization detail: %s", " || ".join(assignment_logs))
    return True, f"Created randomized local AI roster '{target_dir.name}' with {assigned} driver(s) and {copied_files} copied file(s). Recreate the AI session or select that local roster in iRacing to use it."
def _build_fetch_context_payload(session: Session, user: SessionUser) -> dict[str, str] | None:
    context = session.trading_paints_context()
    if context is None:
        return None
    payload = dict(context)
    payload["list"] = user.trading_paints_list_value()
    return payload
def _matches_context_manifest_entry(user: SessionUser, car: ET.Element) -> bool:
    car_id = (car.findtext("carid") or "").strip()
    if not car_id or car_id == "0":
        return False
    manifest_user = (car.findtext("userid") or "").strip()
    manifest_team = (car.findtext("teamid") or "0").strip() or "0"
    expected_user = str(user.user_id)
    expected_team = str(user.team_id or 0)
    if user.team_id is not None and user.team_id > 0:
        return manifest_user == expected_user or manifest_team == expected_team
    return manifest_user == expected_user and manifest_team == expected_team
def _safe_ai_roster_folder_name(name: str, fallback: str) -> str:
    cleaned = (name or "").strip() or fallback
    cleaned = re.sub(r'[<>:"/\|?*]+', '_', cleaned)
    cleaned = cleaned.rstrip(' .')
    return cleaned or fallback
def _cleanup_ai_roster_dirs(ai_rosters_dir: Path) -> None:
    if not ai_rosters_dir.exists():
        return
    removed = 0
    for child in ai_rosters_dir.iterdir():
        if not child.is_dir():
            continue
        if (child / "roster.json").exists():
            continue
        try:
            shutil.rmtree(child, ignore_errors=False)
            removed += 1
        except Exception as exc:  # noqa: BLE001
            logging.debug("AI roster cleanup could not remove %s: %s", child, exc)
    if removed:
        logging.info("AI roster cleanup removed %s empty folder(s)", removed)
def _write_ai_roster_metadata(roster_dir: Path, roster: AIWebRosterItem | None = None, *, roster_id: str = "", name: str = "", is_local: bool = False, source_roster_id: str = "", source_name: str = "") -> None:
    payload = {
        "roster_id": roster.roster_id if roster is not None else str(roster_id or ""),
        "name": roster.name if roster is not None else str(name or ""),
        "roster_file": roster.roster_file if roster is not None else "",
        "is_local": bool(is_local),
        "source_roster_id": str(source_roster_id or ""),
        "source_name": str(source_name or ""),
    }
    (roster_dir / AI_ROSTER_META_FILENAME).write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
def _read_ai_roster_payload(roster_dir: Path) -> tuple[dict[str, list[dict]], list[dict]]:
    payload = json.loads((roster_dir / "roster.json").read_text(encoding="utf-8"))
    drivers = payload.get("drivers") if isinstance(payload, dict) else None
    if not isinstance(drivers, list):
        raise ValueError("AI roster JSON did not contain a drivers list")
    normalized_drivers = [_normalize_ai_driver_entry(driver) for driver in drivers if isinstance(driver, dict)]
    return {"drivers": normalized_drivers}, normalized_drivers
def _load_ai_roster_metadata(roster_dir: Path) -> dict[str, object]:
    meta_file = roster_dir / AI_ROSTER_META_FILENAME
    if meta_file.exists():
        try:
            data = json.loads(meta_file.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}
def _find_active_ai_roster_dir(session: Session, ai_rosters_dir: Path) -> Path | None:
    if not ai_rosters_dir.exists():
        return None
    candidates: list[Path] = []
    if session.ai_roster_name:
        candidates.append(ai_rosters_dir / _safe_ai_roster_folder_name(session.ai_roster_name, f"AI_Roster_{session.ai_roster_id or 'unknown'}"))
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if (candidate / "roster.json").exists():
            return candidate
    for child in ai_rosters_dir.iterdir():
        if not child.is_dir() or not (child / "roster.json").exists():
            continue
        meta = _load_ai_roster_metadata(child)
        if session.ai_roster_id and str(meta.get("roster_id") or "") == session.ai_roster_id:
            return child
        if session.ai_roster_name and str(meta.get("name") or "") == session.ai_roster_name:
            return child
    return None
def _normalize_ai_driver_entry(driver: dict) -> dict:
    normalized = dict(driver)
    car_id = _to_int_or_none(normalized.get("carId")) or 0
    car_class_id = _to_int_or_none(normalized.get("carClassId")) or 0
    car_design = str(normalized.get("carDesign") or "")
    if car_id in AI_SPECIAL_CAR_IDS_WITH_DEFAULT_DESIGN and car_class_id == 0 and (not car_design or not car_design.startswith("0")):
        normalized["carDesign"] = "0,,,"
    car_path = normalized.get("carPath")
    if isinstance(car_path, str) and car_path:
        normalized["carPath"] = car_path.replace(" ", "\\")
    return normalized
def _canonicalize_ai_roster_payload(raw_json: str) -> tuple[dict[str, list[dict]], list[dict]]:
    payload = json.loads(raw_json)
    drivers = payload.get("drivers") if isinstance(payload, dict) else None
    if not isinstance(drivers, list):
        raise ValueError("AI roster JSON did not contain a drivers list")
    normalized_drivers: list[dict] = []
    for driver in drivers:
        if isinstance(driver, dict):
            normalized_drivers.append(_normalize_ai_driver_entry(driver))
    return {"drivers": normalized_drivers}, normalized_drivers
def _build_ai_roster_notes(drivers: list[dict]) -> str:
    lines = ["Summary:", "", "", "", "Drivers:"]
    for driver in drivers:
        number = str(driver.get("carNumber") or "?")
        name = str(driver.get("driverName") or "Unknown Driver")
        lines.extend([f"{number}: {name}", "", "", ""])
    return "\n".join(lines).rstrip() + "\n"
def _write_ai_roster_files(roster_dir: Path, canonical_payload: dict[str, list[dict]], drivers: list[dict], roster: AIWebRosterItem | None = None, *, is_local: bool = False, source_roster_id: str = "", source_name: str = "") -> None:
    roster_dir.mkdir(parents=True, exist_ok=True)
    roster_json = json.dumps(canonical_payload, indent=2, ensure_ascii=False)
    (roster_dir / "roster.json").write_text(roster_json, encoding="utf-8")
    (roster_dir / "notes.txt").write_text(_build_ai_roster_notes(drivers), encoding="utf-8")
    _write_ai_roster_metadata(roster_dir, roster, is_local=is_local, source_roster_id=source_roster_id, source_name=source_name)
def fetch_ai_roster_list(member_id: int, retries: int, retry_backoff_seconds: float) -> list[AIWebRosterItem]:
    url = TRADING_PAINTS_COLLECTIONS_URL.format(member_id=member_id)
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            session = get_thread_http_session()
            response = session.get(url, timeout=30)
            response.raise_for_status()
            root = ET.fromstring(response.text)
            rosters: list[AIWebRosterItem] = []
            for item in root.findall(".//Collection"):
                roster_id = (item.findtext("ID") or "").strip()
                name = (item.findtext("Name") or "").strip()
                roster_file = (item.findtext("RosterFile") or "").strip()
                if not roster_id or not name or not roster_file:
                    continue
                rosters.append(AIWebRosterItem(roster_id=roster_id, name=name, roster_file=roster_file))
            return rosters
        except (requests.RequestException, ET.ParseError) as exc:
            last_exc = exc
            if attempt >= retries:
                break
            delay = compute_retry_delay(retry_backoff_seconds, attempt)
            logging.debug("AI roster list fetch failed for member %s (attempt %s/%s): %s. Retrying in %.1fs", member_id, attempt, retries, exc, delay)
            time.sleep(delay)
    assert last_exc is not None
    raise last_exc
def fetch_ai_roster_json(roster: AIWebRosterItem, retries: int, retry_backoff_seconds: float) -> str | None:
    last_exc: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            session = get_thread_http_session()
            response = session.get(roster.roster_file, timeout=30)
            response.raise_for_status()
            payload = response.text or ""
            if len(payload.strip()) <= 2:
                return None
            return payload
        except requests.RequestException as exc:
            last_exc = exc
            if attempt >= retries:
                break
            delay = compute_retry_delay(retry_backoff_seconds, attempt)
            logging.debug("AI roster JSON fetch failed for %s (attempt %s/%s): %s. Retrying in %.1fs", roster.name, attempt, retries, exc, delay)
            time.sleep(delay)
    if last_exc is not None:
        raise last_exc
    return None
def sync_ai_rosters(member_id: int, ai_rosters_dir: Path, retries: int, retry_backoff_seconds: float, do_cleanup: bool = True) -> AIRosterSyncResult:
    result = AIRosterSyncResult(member_id=member_id, ai_rosters_dir=ai_rosters_dir)
    ai_rosters_dir.mkdir(parents=True, exist_ok=True)
    started_at = time.monotonic()
    try:
        rosters = fetch_ai_roster_list(member_id, retries=retries, retry_backoff_seconds=retry_backoff_seconds)
        result.discovered = len(rosters)
        if not rosters:
            logging.info("AI roster sync found no Trading Paints AI carsets for member %s", member_id)
            return result
        for item in rosters:
            try:
                raw_json = fetch_ai_roster_json(item, retries=retries, retry_backoff_seconds=retry_backoff_seconds)
                if not raw_json:
                    result.failed += 1
                    logging.warning("AI roster sync skipped empty roster JSON for %s", item.name)
                    continue
                try:
                    canonical_payload, drivers = _canonicalize_ai_roster_payload(raw_json)
                except Exception as exc:  # noqa: BLE001
                    result.failed += 1
                    logging.warning("AI roster sync could not validate roster %s: %s", item.name, exc)
                    continue
                folder_name = _safe_ai_roster_folder_name(item.name, f"AI_Roster_{item.roster_id}")
                roster_dir = ai_rosters_dir / folder_name
                _write_ai_roster_files(roster_dir, canonical_payload, drivers, item)
                result.downloaded += 1
                logging.info("AI roster synced: %s (%s drivers)", item.name, len(drivers))
            except Exception as exc:  # noqa: BLE001
                result.failed += 1
                logging.warning("AI roster sync failed for %s: %s", item.name, exc)
        return result
    except Exception as exc:  # noqa: BLE001
        logging.warning("AI roster sync failed for member %s: %s", member_id, exc)
        return result
    finally:
        if do_cleanup:
            _cleanup_ai_roster_dirs(ai_rosters_dir)
        elapsed = time.monotonic() - started_at
        logging.info("AI roster sync complete for member %s: %s found, %s saved, %s failed in %.2fs", member_id, result.discovered, result.downloaded, result.failed, elapsed)
        if result.downloaded:
            logging.info("AI rosters were saved to %s", ai_rosters_dir)
            logging.info("If iRacing already loaded an AI roster, recreate the AI session to pick up newly synced carsets.")
def clone_active_ai_roster_to_local(session: Session | None, ai_rosters_dir: Path) -> tuple[bool, str]:
    if session is None:
        return False, "No current iRacing session is active."
    if not session.ai_roster_name and not session.ai_roster_id:
        return False, "The current session does not report an active AI roster."
    source_dir = _find_active_ai_roster_dir(session, ai_rosters_dir)
    if source_dir is None:
        return False, "The active Trading Paints AI roster has not been synced locally yet."
    try:
        canonical_payload, drivers = _read_ai_roster_payload(source_dir)
    except Exception as exc:
        return False, f"Could not read the active AI roster: {exc}"
    base_name = (session.ai_roster_name or source_dir.name).strip() or (source_dir.name or "AI Roster")
    local_name = f"{base_name}{AI_LOCAL_ROSTER_SUFFIX}"
    target_dir = ai_rosters_dir / _safe_ai_roster_folder_name(local_name, f"AI_Roster_{session.ai_roster_id or 'local'}{AI_LOCAL_ROSTER_SUFFIX}")
    if target_dir.exists():
        return False, f"A local AI roster folder already exists for {local_name}."
    target_dir.mkdir(parents=True, exist_ok=False)
    copied_files = 0
    for driver in drivers:
        car_tga_name = str(driver.get("carTgaName") or "").strip()
        helmet_tga_name = str(driver.get("helmetTgaName") or "").strip()
        suit_tga_name = str(driver.get("suitTgaName") or "").strip()
        for filename in (car_tga_name, helmet_tga_name, suit_tga_name):
            if not filename:
                continue
            src = source_dir / filename
            dest = target_dir / filename
            if src.exists():
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                copied_files += 1
                if filename.lower().endswith('.tga'):
                    spec_src = source_dir / filename[:-4].replace('car_', 'car_')
                    spec_src = source_dir / f"{Path(filename).stem}_spec.mip"
                    if spec_src.exists():
                        shutil.copy2(spec_src, target_dir / spec_src.name)
                        copied_files += 1
    _write_ai_roster_files(
        target_dir,
        canonical_payload,
        drivers,
        None,
        is_local=True,
        source_roster_id=session.ai_roster_id,
        source_name=session.ai_roster_name or base_name,
    )
    message = f"Created local AI roster '{local_name}' with {len(drivers)} driver(s)"
    if copied_files > 0:
        message += f" and copied {copied_files} local file(s)."
    else:
        message += "."
    return True, message
def _extract_ai_cache_numeric_id(filename: str) -> int | None:
    match = re.search(r"_(\d+)(?:_ss)?\.(?:tga|mip)$", filename, re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None
def _next_ai_cache_id(ai_livery_car_dir: Path) -> str:
    ai_livery_car_dir.mkdir(parents=True, exist_ok=True)
    highest = 0
    for child in ai_livery_car_dir.iterdir():
        if not child.is_file():
            continue
        num = _extract_ai_cache_numeric_id(child.name)
        if num is not None and num > highest:
            highest = num
    return str(highest + 1)
def _copy_optional_file(src: Path | None, dest: Path) -> bool:
    if src is None or not src.exists():
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)
    return True
def import_saved_paint_groups_to_ai_livery(saved: list[SavedFile], session: Session | None, ai_livery_root: Path, only_local_user: bool = False) -> tuple[int, int]:
    grouped: dict[tuple[str, int, bool], dict[PaintType, Path]] = {}
    local_user_id = session.local_user_id if session is not None else None
    for saved_file in saved:
        paint_type = saved_file.download_id.paint_type
        if paint_type not in {PaintType.CAR, PaintType.CAR_SPEC, PaintType.CAR_DECAL}:
            continue
        if only_local_user and (local_user_id is None or saved_file.download_id.user_id != local_user_id):
            continue
        key = (saved_file.download_id.directory, saved_file.download_id.user_id, saved_file.download_id.is_team_paint)
        grouped.setdefault(key, {})[paint_type] = saved_file.file_path
    copied_sets = 0
    copied_files = 0
    for (directory, _target_id, _is_team), file_map in grouped.items():
        car_src = file_map.get(PaintType.CAR)
        if car_src is None or not car_src.exists():
            continue
        car_dir = ai_livery_root / directory
        new_id = _next_ai_cache_id(car_dir)
        if _copy_optional_file(car_src, car_dir / f"car_{new_id}.tga"):
            copied_files += 1
        if _copy_optional_file(file_map.get(PaintType.CAR_SPEC), car_dir / f"car_spec_{new_id}.mip"):
            copied_files += 1
        if _copy_optional_file(file_map.get(PaintType.CAR_DECAL), car_dir / f"decal_{new_id}.tga"):
            copied_files += 1
        copied_sets += 1
    return copied_sets, copied_files

def _parse_saved_paint_filename(path: Path) -> tuple[PaintType, str, int, bool, bool] | None:
    directory = path.parent.name
    name = path.name.lower()
    patterns: list[tuple[PaintType, str]] = [
        (PaintType.CAR, r"^car_(team_)?(\d+)(?:(_ss))?\.tga$"),
        (PaintType.CAR_SPEC, r"^car_spec_(team_)?(\d+)(?:(_ss))?\.mip$"),
        (PaintType.CAR_DECAL, r"^decal_(team_)?(\d+)(?:(_ss))?\.tga$"),
    ]
    for paint_type, pattern in patterns:
        match = re.match(pattern, name, re.IGNORECASE)
        if not match:
            continue
        is_team = bool(match.group(1))
        target_id = int(match.group(2))
        is_ss = bool(match.group(3))
        return paint_type, directory, target_id, is_team, is_ss
    return None

def rebuild_random_pool_from_paints_root(paints_root: Path, random_pool_dir: Path, max_pool_gb: float) -> tuple[int, int, int, int]:
    grouped: dict[tuple[str, int, bool], dict[PaintType, tuple[Path, bool]]] = {}
    if not paints_root.exists():
        return 0, 0, 0, 0
    for child in paints_root.rglob('*'):
        if not child.is_file():
            continue
        parsed = _parse_saved_paint_filename(child)
        if parsed is None:
            continue
        paint_type, directory, target_id, is_team, is_ss = parsed
        key = (directory, target_id, is_team)
        existing = grouped.setdefault(key, {}).get(paint_type)
        if existing is None or (existing[1] and not is_ss):
            grouped.setdefault(key, {})[paint_type] = (child, is_ss)
    saved: list[SavedFile] = []
    synthetic_session = SessionId(0, None)
    for (directory, target_id, is_team), file_map in grouped.items():
        for paint_type, path_and_ss in file_map.items():
            source_path, is_ss = path_and_ss
            saved.append(
                SavedFile(
                    session_id=synthetic_session,
                    download_id=DownloadId(
                        user_id=target_id,
                        directory=directory,
                        paint_type=paint_type,
                        is_team_paint=is_team,
                        is_superspeedway_variant=is_ss,
                    ),
                    file_path=source_path,
                )
            )
    added_sets, added_files, _detail_logs, pool_bytes_after, pool_freed_bytes = archive_saved_tp_sets_to_random_pool(
        saved,
        random_pool_dir,
        max_pool_gb,
    )
    return added_sets, added_files, pool_bytes_after, pool_freed_bytes

def fetch_context_files(
    session: Session,
    user: SessionUser,
    retries: int,
    retry_backoff_seconds: float,
) -> list[DownloadFile]:
    payload = _build_fetch_context_payload(session, user)
    if payload is None:
        raise RuntimeError("Trading Paints context is unavailable for this session.")
    last_exc: Exception | None = None
    for url in TRADING_PAINTS_FETCH_CONTEXT_URLS:
        for attempt in range(1, retries + 1):
            try:
                http = get_thread_http_session()
                resp = http.post(url, data=payload, timeout=30)
                resp.raise_for_status()
                root = ET.fromstring(resp.text)
                files: list[DownloadFile] = []
                for car in root.findall(".//Car"):
                    if not _matches_context_manifest_entry(user, car):
                        continue
                    file_url = (car.findtext("file") or "").strip()
                    type_raw = (car.findtext("type") or "").strip().lower()
                    directory = (car.findtext("directory") or "").strip()
                    team_id_text = (car.findtext("teamid") or "0").strip() or "0"
                    if not file_url or not type_raw:
                        continue
                    if not directory and type_raw.startswith("car"):
                        continue
                    try:
                        paint_type = PaintType(type_raw)
                    except ValueError:
                        logging.debug(
                            "Skipping unknown contextual paint type '%s' for user %s",
                            type_raw,
                            user.user_id,
                        )
                        continue
                    response_team_id = _to_int_or_none(team_id_text)
                    is_team_paint = bool(response_team_id and response_team_id > 0 and paint_type in TEAM_PAINT_TYPES)
                    target_user_id = int(response_team_id) if is_team_paint else user.user_id
                    target_directory = directory or user.directory
                    files.append(
                        DownloadFile(
                            download_id=DownloadId(
                                user_id=target_user_id,
                                directory=target_directory,
                                paint_type=paint_type,
                                is_team_paint=is_team_paint,
                            ),
                            url=file_url,
                        )
                    )
                if files:
                    logging.debug(
                        "Context fetch succeeded for user %s via %s with %s file(s) (list=%s)",
                        user.user_id,
                        url,
                        len(files),
                        payload.get("list", ""),
                    )
                    return files
                logging.debug(
                    "Context fetch returned no matching files for user %s via %s (attempt %s/%s, list=%s)",
                    user.user_id,
                    url,
                    attempt,
                    retries,
                    payload.get("list", ""),
                )
                return []
            except (requests.RequestException, ET.ParseError, RuntimeError) as exc:
                last_exc = exc
                if attempt >= retries:
                    break
                delay = compute_retry_delay(retry_backoff_seconds, attempt)
                logging.debug(
                    "Context manifest fetch failed for user %s via %s (attempt %s/%s): %s. Retrying in %.1fs",
                    user.user_id,
                    url,
                    attempt,
                    retries,
                    exc,
                    delay,
                )
                time.sleep(delay)
    assert last_exc is not None
    raise last_exc
def _apply_special_variant_flags(session: Session, user: SessionUser, items: list[DownloadFile]) -> list[DownloadFile]:
    updated: list[DownloadFile] = []
    for item in items:
        use_ss_variant = _download_uses_superspeedway_variant(
            item.download_id.directory or user.directory,
            item.download_id.paint_type,
            session.is_superspeedway_track,
        )
        if item.download_id.is_superspeedway_variant == use_ss_variant:
            updated.append(item)
            continue
        updated.append(
            DownloadFile(
                download_id=DownloadId(
                    user_id=item.download_id.user_id,
                    directory=item.download_id.directory,
                    paint_type=item.download_id.paint_type,
                    is_team_paint=item.download_id.is_team_paint,
                    is_superspeedway_variant=use_ss_variant,
                ),
                url=item.url,
            )
        )
    return updated
def fetch_best_manifest_files(
    session: Session,
    user: SessionUser,
    retries: int,
    retry_backoff_seconds: float,
) -> list[DownloadFile]:
    context = session.trading_paints_context()
    if context is None:
        logging.debug(
            "No Trading Paints context available for session %s; falling back to fetch_user for user %s",
            session.session_id.folder_name(),
            user.user_id,
        )
        return _apply_special_variant_flags(session, user, fetch_user_files(user.user_id, retries, retry_backoff_seconds))
    try:
        return _apply_special_variant_flags(session, user, fetch_context_files(session, user, retries, retry_backoff_seconds))
    except Exception as exc:
        logging.warning(
            "Context fetch.php manifest failed for user %s; falling back to fetch_user.php: %s",
            user.user_id,
            exc,
        )
        return _apply_special_variant_flags(session, user, fetch_user_files(user.user_id, retries, retry_backoff_seconds))
SAFE_PAINT_DIRECTORY_RE = re.compile(r"^[A-Za-z0-9._ -]+$")
def normalize_directory(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized

def sanitize_paint_directory(value: str, *, fallback: str = "misc") -> str:
    text = str(value or "").strip()
    if not text:
        text = str(fallback or "").strip()
    text = text.replace("/", "\\")
    parts = [part.strip() for part in text.split("\\") if part.strip()]
    if len(parts) != 1:
        raise ValueError(f"Unsafe paint directory: {value!r}")
    part = parts[0]
    if part in {".", ".."}:
        raise ValueError(f"Unsafe paint directory: {value!r}")
    if ":" in part:
        raise ValueError(f"Unsafe paint directory: {value!r}")
    if part.endswith(".") or part.endswith(" "):
        raise ValueError(f"Unsafe paint directory: {value!r}")
    if not SAFE_PAINT_DIRECTORY_RE.fullmatch(part):
        raise ValueError(f"Unsafe paint directory: {value!r}")
    return part

def safe_join_under(root: Path, *parts: str) -> Path:
    root_resolved = root.resolve(strict=False)
    candidate = root.joinpath(*parts)
    candidate_resolved = candidate.resolve(strict=False)
    if candidate_resolved != root_resolved and root_resolved not in candidate_resolved.parents:
        raise ValueError(f"Path escaped base directory: {candidate}")
    return candidate
def is_user_file(session_user: SessionUser, item: DownloadFile) -> bool:
    if item.download_id.paint_type in {PaintType.HELMET, PaintType.SUIT}:
        return True
    if item.download_id.directory.lower() == session_user.directory.lower():
        return True
    normalized_manifest = normalize_directory(item.download_id.directory)
    normalized_session = normalize_directory(session_user.directory)
    if normalized_manifest == normalized_session:
        logging.debug(
            "Directory matched after normalization: '%s' -> '%s', '%s' -> '%s'",
            item.download_id.directory,
            normalized_manifest,
            session_user.directory,
            normalized_session,
        )
        return True
    return False
TEAM_PAINT_TYPES = {
    PaintType.CAR,
    PaintType.CAR_DECAL,
    PaintType.CAR_NUMBER,
    PaintType.CAR_SPEC,
    PaintType.HELMET,
    PaintType.SUIT,
}
def uses_team_target(session_user: SessionUser, item: DownloadFile) -> bool:
    return (
        session_user.team_id is not None
        and session_user.team_id > 0
        and item.download_id.paint_type in TEAM_PAINT_TYPES
        and bool(item.download_id.is_team_paint)
    )
def normalize_download_for_session_user(session_user: SessionUser, item: DownloadFile) -> DownloadFile:
    target_user_id = item.download_id.user_id
    is_team_paint = item.download_id.is_team_paint
    if uses_team_target(session_user, item):
        target_user_id = int(session_user.team_id)
        is_team_paint = True

    target_directory = item.download_id.directory
    if _is_car_related_paint_type(item.download_id.paint_type):
        preferred_directory = str(session_user.directory or "").strip() or item.download_id.directory
        target_directory = sanitize_paint_directory(preferred_directory, fallback="misc")

    if (
        item.download_id.user_id == target_user_id
        and item.download_id.directory == target_directory
        and item.download_id.is_team_paint == is_team_paint
    ):
        return item

    return DownloadFile(
        download_id=DownloadId(
            user_id=target_user_id,
            directory=target_directory,
            paint_type=item.download_id.paint_type,
            is_team_paint=is_team_paint,
            is_superspeedway_variant=item.download_id.is_superspeedway_variant,
        ),
        url=item.url,
    )
def download_file(
    session_id: SessionId,
    temp_root: Path,
    item: DownloadFile,
    retries: int,
    retry_backoff_seconds: float,
    ordinal: int | None = None,
    total: int | None = None,
    batch_monitor: TransferBatchMonitor | None = None,
) -> DownloadedFile | None:
    parsed = urllib.parse.urlparse(item.url)
    name = Path(parsed.path).name
    if not name:
        return None
    try:
        safe_dir = sanitize_paint_directory(item.download_id.directory, fallback="misc")
    except ValueError as exc:
        logging.warning(
            "Skipping download with unsafe directory %r for %s: %s",
            item.download_id.directory,
            item.url,
            exc,
        )
        return None
    base_temp_dir = temp_root / session_id.folder_name()
    dest_dir = safe_join_under(base_temp_dir, safe_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    url_hash = hashlib.sha1(item.url.encode("utf-8", errors="ignore")).hexdigest()[:12]
    temp_name = f"{item.download_id.paint_type.value}_{item.download_id.user_id}_{url_hash}_{name}"
    dest_file = dest_dir / temp_name
    last_exc: Exception | None = None
    progress_prefix = f"[{ordinal}/{total}] " if ordinal is not None and total else ""
    task_started_at = batch_monitor.begin() if batch_monitor is not None else time.monotonic()
    bytes_downloaded_total = 0
    success = False
    try:
        for attempt in range(1, retries + 1):
            logging.info(
                "%sDownloading %s for user %s (%s) [attempt %s/%s]",
                progress_prefix,
                item.download_id.paint_type.value,
                item.download_id.user_id,
                item.download_id.directory,
                attempt,
                retries,
            )
            try:
                session = get_thread_http_session()
                with session.get(item.url, timeout=(10, 90), stream=True) as response:
                    response.raise_for_status()
                    with dest_file.open("wb") as f:
                        for chunk in response.iter_content(chunk_size=1024 * 1024):
                            if chunk:
                                bytes_downloaded_total += len(chunk)
                                f.write(chunk)
                logging.info("%sDownloaded to temp file: %s", progress_prefix, dest_file)
                success = True
                return DownloadedFile(
                    session_id=session_id,
                    download_id=item.download_id,
                    file_path=dest_file,
                )
            except requests.RequestException as exc:
                last_exc = exc
                dest_file.unlink(missing_ok=True)
                if attempt >= retries:
                    break
                delay = compute_retry_delay(retry_backoff_seconds, attempt)
                logging.warning(
                    "%sFailed download %s on attempt %s/%s: %s. Retrying in %.1fs",
                    progress_prefix,
                    item.url,
                    attempt,
                    retries,
                    exc,
                    delay,
                )
                time.sleep(delay)
            except Exception:
                dest_file.unlink(missing_ok=True)
                raise
        if last_exc is not None:
            logging.warning("%sFailed download %s after %s attempts: %s", progress_prefix, item.url, retries, last_exc)
        return None
    finally:
        if batch_monitor is not None:
            batch_monitor.end(task_started_at, success=success, bytes_count=bytes_downloaded_total)
def save_path_for(download_id: DownloadId, paints_dir: Path) -> Path:
    uid = download_id.user_id
    team_suffix = f"team_{uid}" if download_id.is_team_paint else str(uid)
    ss_suffix = "_ss" if download_id.is_superspeedway_variant else ""
    if download_id.paint_type is PaintType.CAR:
        safe_dir = sanitize_paint_directory(download_id.directory, fallback="misc")
        return safe_join_under(paints_dir, safe_dir, f"car_{team_suffix}{ss_suffix}.tga")
    if download_id.paint_type is PaintType.CAR_DECAL:
        safe_dir = sanitize_paint_directory(download_id.directory, fallback="misc")
        return safe_join_under(paints_dir, safe_dir, f"decal_{team_suffix}{ss_suffix}.tga")
    if download_id.paint_type is PaintType.CAR_NUMBER:
        safe_dir = sanitize_paint_directory(download_id.directory, fallback="misc")
        return safe_join_under(paints_dir, safe_dir, f"car_num_{team_suffix}{ss_suffix}.tga")
    if download_id.paint_type is PaintType.CAR_SPEC:
        safe_dir = sanitize_paint_directory(download_id.directory, fallback="misc")
        return safe_join_under(paints_dir, safe_dir, f"car_spec_{team_suffix}{ss_suffix}.mip")
    if download_id.paint_type is PaintType.HELMET:
        return safe_join_under(paints_dir, f"helmet_{team_suffix}.tga")
    if download_id.paint_type is PaintType.SUIT:
        return safe_join_under(paints_dir, f"suit_{team_suffix}.tga")
    raise ValueError(f"Unsupported paint type: {download_id.paint_type}")
def save_paths_for(download_id: DownloadId, paints_dir: Path) -> list[Path]:
    primary = save_path_for(
        DownloadId(
            user_id=download_id.user_id,
            directory=download_id.directory,
            paint_type=download_id.paint_type,
            is_team_paint=download_id.is_team_paint,
            is_superspeedway_variant=False,
        ),
        paints_dir,
    )
    if not download_id.is_superspeedway_variant or not _is_car_related_paint_type(download_id.paint_type):
        return [primary]
    ss_path = save_path_for(download_id, paints_dir)
    if ss_path == primary:
        return [primary]
    return [primary, ss_path]
def move_or_extract(
    downloaded: DownloadedFile,
    paints_dir: Path,
    batch_monitor: TransferBatchMonitor | None = None,
) -> list[SavedFile] | None:
    src = downloaded.file_path
    dest_paths = save_paths_for(downloaded.download_id, paints_dir)
    primary_dest = dest_paths[0]
    primary_dest.parent.mkdir(parents=True, exist_ok=True)
    temp_primary_dest = primary_dest.with_name(primary_dest.name + ".tmp")
    task_started_at = batch_monitor.begin() if batch_monitor is not None else time.monotonic()
    saved_bytes = 0
    success = False
    try:
        temp_primary_dest.unlink(missing_ok=True)
        if src.suffix.lower() == ".bz2":
            with src.open("rb") as source, bz2.open(source, "rb") as decompressor, temp_primary_dest.open(
                "wb"
            ) as out:
                shutil.copyfileobj(decompressor, out)
            src.unlink(missing_ok=True)
        else:
            shutil.move(str(src), str(temp_primary_dest))
        os.replace(temp_primary_dest, primary_dest)
        saved_paths = [primary_dest]
        for extra_dest in dest_paths[1:]:
            extra_dest.parent.mkdir(parents=True, exist_ok=True)
            temp_extra_dest = extra_dest.with_name(extra_dest.name + ".tmp")
            temp_extra_dest.unlink(missing_ok=True)
            shutil.copy2(primary_dest, temp_extra_dest)
            os.replace(temp_extra_dest, extra_dest)
            saved_paths.append(extra_dest)
        if len(saved_paths) > 1:
            logging.info(
                "Superspeedway dual-save active for %s: regular=%s | ss=%s",
                downloaded.download_id.paint_type.value,
                primary_dest,
                ", ".join(str(p) for p in saved_paths[1:]),
            )
        for saved_path in saved_paths:
            try:
                saved_bytes += int(saved_path.stat().st_size)
            except OSError:
                pass
        success = True
    except Exception as exc:  # noqa: BLE001
        temp_primary_dest.unlink(missing_ok=True)
        for extra_dest in dest_paths[1:]:
            extra_dest.with_name(extra_dest.name + ".tmp").unlink(missing_ok=True)
        logging.error("Failed to save %s -> %s: %s", src, ", ".join(str(p) for p in dest_paths), exc)
        return None
    finally:
        if batch_monitor is not None:
            batch_monitor.end(task_started_at, success=success, bytes_count=saved_bytes)
    for saved_path in saved_paths:
        logging.info("Saved paint file: %s", saved_path)
    return [
        SavedFile(
            session_id=downloaded.session_id,
            download_id=downloaded.download_id,
            file_path=saved_path,
        )
        for saved_path in saved_paths
    ]
def _remove_empty_parent_dirs(path: Path, stop_at: Path | None = None) -> None:
    current = path.parent
    stop_resolved = stop_at.resolve() if stop_at is not None and stop_at.exists() else None
    while True:
        try:
            current_resolved = current.resolve()
        except Exception:
            current_resolved = current
        if stop_resolved is not None and current_resolved == stop_resolved:
            break
        try:
            current.rmdir()
        except OSError:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
def _hard_delete_file(path: Path, paints_root: Path | None = None, retries: int = 8, delay: float = 0.12) -> bool:
    for attempt in range(1, retries + 1):
        try:
            path.unlink(missing_ok=True)
        except FileNotFoundError:
            return True
        except PermissionError:
            try:
                os.chmod(path, 0o666)
            except Exception:
                pass
        except OSError as exc:
            logging.debug("Delete attempt %s failed for %s: %s", attempt, path, exc)
        if not path.exists():
            _remove_empty_parent_dirs(path, stop_at=paints_root)
            return True
        if attempt < retries:
            time.sleep(delay)
    if path.exists():
        logging.warning("Could not fully delete paint file: %s", path)
        return False
    _remove_empty_parent_dirs(path, stop_at=paints_root)
    return True
def _safe_replay_pack_name(name: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', '_', (name or '').strip())
    cleaned = cleaned.strip().strip('.')
    return cleaned or 'Replay'

def _session_fingerprint_key(session: Session) -> str:
    normalized_users = [
        {
            "kind": ("team" if user.team_id is not None and user.team_id > 0 else "user"),
            "id": int(user.team_id if user.team_id is not None and user.team_id > 0 else user.user_id),
            "directory": user.directory.lower(),
        }
        for user in sorted(session.users, key=lambda u: ((u.team_id or 0) > 0, u.team_id or 0, u.user_id, u.directory.lower()))
    ]
    payload = {
        "session_id": session.session_id.folder_name(),
        "users": normalized_users,
        "context": {
            "team_racing": bool(session.team_racing),
            "event_time_raw": (session.event_time_raw or '10:00 am').strip().lower(),
            "series_id": int(session.series_id or 0),
            "league_id": int(session.league_id or 0),
            "load_num_textures": bool(session.load_num_textures),
            "track_name": normalize_directory(session.track_name),
            "track_config_name": normalize_directory(session.track_config_name),
            "is_superspeedway_track": bool(session.is_superspeedway_track),
        },
    }
    return json.dumps(payload, sort_keys=True, separators=(',', ':'))

def _download_id_to_dict(download_id: DownloadId) -> dict[str, object]:
    return {
        "user_id": int(download_id.user_id),
        "directory": download_id.directory,
        "paint_type": download_id.paint_type.value,
        "is_team_paint": bool(download_id.is_team_paint),
        "is_superspeedway_variant": bool(download_id.is_superspeedway_variant),
    }

def _download_id_from_dict(payload: dict[str, object]) -> DownloadId:
    return DownloadId(
        user_id=int(payload.get("user_id") or 0),
        directory=str(payload.get("directory") or ""),
        paint_type=PaintType(str(payload.get("paint_type") or PaintType.CAR.value)),
        is_team_paint=bool(payload.get("is_team_paint")),
        is_superspeedway_variant=bool(payload.get("is_superspeedway_variant")),
    )

def _replay_pack_index_path(replay_packs_dir: Path) -> Path:
    return replay_packs_dir / REPLAY_PACK_INDEX_FILENAME

def _load_replay_pack_index(replay_packs_dir: Path) -> dict[str, dict[str, object]]:
    path = _replay_pack_index_path(replay_packs_dir)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return {}
    packs = raw.get('packs') if isinstance(raw, dict) else None
    if not isinstance(packs, dict):
        return {}
    normalized: dict[str, dict[str, object]] = {}
    for key, value in packs.items():
        if isinstance(key, str) and isinstance(value, dict):
            normalized[key.lower()] = value
    return normalized

def _save_replay_pack_index(replay_packs_dir: Path, packs: dict[str, dict[str, object]]) -> None:
    replay_packs_dir.mkdir(parents=True, exist_ok=True)
    path = _replay_pack_index_path(replay_packs_dir)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps({"packs": packs}, indent=2, sort_keys=True), encoding='utf-8')
    os.replace(temp, path)

def _snapshot_replay_files(replay_dir: Path) -> dict[str, dict[str, object]]:
    snapshot: dict[str, dict[str, object]] = {}
    if not replay_dir.exists():
        return snapshot
    try:
        replay_files = sorted(replay_dir.glob('*.rpy'))
    except Exception:
        return snapshot
    for replay_file in replay_files:
        try:
            stat = replay_file.stat()
        except OSError:
            continue
        snapshot[str(replay_file.resolve()).lower()] = {
            "path": replay_file,
            "size": int(stat.st_size),
            "mtime": float(stat.st_mtime),
        }
    return snapshot

def _write_replay_pack_manifest(pack_dir: Path, manifest: dict[str, object]) -> None:
    pack_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = pack_dir / REPLAY_PACK_MANIFEST_FILENAME
    temp_path = manifest_path.with_name(manifest_path.name + '.tmp')
    temp_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding='utf-8')
    os.replace(temp_path, manifest_path)

def _load_replay_pack_manifest(pack_dir: Path) -> dict[str, object] | None:
    manifest_path = pack_dir / REPLAY_PACK_MANIFEST_FILENAME
    if not manifest_path.exists():
        return None
    try:
        raw = json.loads(manifest_path.read_text(encoding='utf-8'))
    except Exception:
        return None
    return raw if isinstance(raw, dict) else None

def _copy_saved_files_into_replay_pack(
    replay_file: Path,
    session: Session | None,
    saved: list[SavedFile],
    paints_root: Path,
    replay_packs_dir: Path,
) -> tuple[bool, str]:
    if session is None or not saved:
        return False, 'Current session paints are not available yet, so no replay pack was created.'
    replay_packs_dir.mkdir(parents=True, exist_ok=True)
    replay_file_resolved = replay_file.resolve()
    replay_key = str(replay_file_resolved).lower()
    pack_name = _safe_replay_pack_name(replay_file.stem)
    pack_dir = replay_packs_dir / pack_name
    existing_index = _load_replay_pack_index(replay_packs_dir)
    existing_entry = existing_index.get(replay_key)
    if existing_entry is not None:
        old_pack_name = str(existing_entry.get('pack_name') or pack_name)
        old_pack_dir = replay_packs_dir / old_pack_name
        if old_pack_dir != pack_dir and old_pack_dir.exists():
            shutil.rmtree(old_pack_dir, ignore_errors=True)
    if pack_dir.exists():
        shutil.rmtree(pack_dir, ignore_errors=True)
    paint_root = pack_dir / 'paint'
    copied_items: list[dict[str, object]] = []
    seen_rel_paths: set[str] = set()
    for item in saved:
        try:
            relative = item.file_path.resolve().relative_to(paints_root.resolve())
        except Exception:
            continue
        relative_key = relative.as_posix()
        if relative_key in seen_rel_paths:
            continue
        if not item.file_path.exists():
            continue
        destination = paint_root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(item.file_path, destination)
        copied_items.append({
            "relative_path": relative_key,
            "download_id": _download_id_to_dict(item.download_id),
        })
        seen_rel_paths.add(relative_key)
    if not copied_items:
        shutil.rmtree(pack_dir, ignore_errors=True)
        return False, 'The replay was detected, but there were no saved paint files left to archive.'
    manifest = {
        "replay_file_path": str(replay_file_resolved),
        "replay_file_name": replay_file.name,
        "pack_name": pack_name,
        "created_at": time.time(),
        "source_session_id": session.session_id.folder_name(),
        "session_fingerprint_key": _session_fingerprint_key(session),
        "saved_files": copied_items,
    }
    _write_replay_pack_manifest(pack_dir, manifest)
    existing_index[replay_key] = {
        "replay_file_path": str(replay_file_resolved),
        "replay_file_name": replay_file.name,
        "pack_name": pack_name,
        "created_at": manifest["created_at"],
        "source_session_id": manifest["source_session_id"],
        "session_fingerprint_key": manifest["session_fingerprint_key"],
    }
    _save_replay_pack_index(replay_packs_dir, existing_index)
    return True, f"Replay pack '{pack_name}' captured from session {session.session_id.folder_name()} with {len(copied_items)} file(s)"

def _delete_replay_pack_for_missing_file(replay_file_key: str, replay_packs_dir: Path, packs: dict[str, dict[str, object]]) -> str | None:
    entry = packs.pop(replay_file_key, None)
    if entry is None:
        return None
    pack_name = str(entry.get('pack_name') or '').strip()
    if not pack_name:
        _save_replay_pack_index(replay_packs_dir, packs)
        return None
    pack_dir = replay_packs_dir / pack_name
    shutil.rmtree(pack_dir, ignore_errors=True)
    _save_replay_pack_index(replay_packs_dir, packs)
    replay_name = str(entry.get('replay_file_name') or Path(replay_file_key).name)
    return f"Replay pack '{pack_name}' removed because replay file '{replay_name}' no longer exists"

def reconcile_replay_pack_index(replay_dir: Path, replay_packs_dir: Path) -> list[str]:
    current_files = _snapshot_replay_files(replay_dir)
    packs = _load_replay_pack_index(replay_packs_dir)
    logs: list[str] = []
    dirty = False
    for replay_key in list(packs.keys()):
        if replay_key in current_files:
            continue
        entry = packs.pop(replay_key, None)
        if entry is None:
            continue
        pack_name = str(entry.get('pack_name') or '').strip()
        if pack_name:
            shutil.rmtree(replay_packs_dir / pack_name, ignore_errors=True)
            replay_name = str(entry.get('replay_file_name') or Path(replay_key).name)
            logs.append(f"Replay pack '{pack_name}' removed because replay file '{replay_name}' no longer exists")
        dirty = True
    if dirty:
        _save_replay_pack_index(replay_packs_dir, packs)
    return logs

def sync_replay_packs_for_folder(
    replay_dir: Path,
    replay_packs_dir: Path,
    known_files: dict[str, dict[str, object]],
    current_session: Session | None,
    saved: list[SavedFile],
    paints_root: Path,
    known_packs: dict[str, dict[str, object]] | None = None,
) -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    current_files = _snapshot_replay_files(replay_dir)
    packs = dict(known_packs) if known_packs is not None else _load_replay_pack_index(replay_packs_dir)
    added_keys = sorted(set(current_files) - set(known_files), key=lambda key: str(current_files[key]['path']))
    removed_keys = sorted(set(known_files) - set(current_files))
    dirty = False
    if removed_keys:
        for replay_key in removed_keys:
            entry = packs.pop(replay_key, None)
            if entry is None:
                continue
            pack_name = str(entry.get('pack_name') or '').strip()
            if pack_name:
                shutil.rmtree(replay_packs_dir / pack_name, ignore_errors=True)
                replay_name = str(entry.get('replay_file_name') or Path(replay_key).name)
                logging.info("Replay pack '%s' removed because replay file '%s' was deleted", pack_name, replay_name)
            dirty = True
    if added_keys:
        for replay_key in added_keys:
            replay_path = current_files[replay_key]['path']
            ok, message = _copy_saved_files_into_replay_pack(replay_path, current_session, saved, paints_root, replay_packs_dir)
            if ok:
                logging.info(message)
            else:
                logging.debug("Replay file '%s' detected but replay pack capture was skipped: %s", replay_path.name, message)
        packs = _load_replay_pack_index(replay_packs_dir)
    elif dirty:
        _save_replay_pack_index(replay_packs_dir, packs)
    return current_files, packs

def restore_replay_pack_for_session(
    session: Session,
    paints_root: Path,
    replay_packs_dir: Path,
    packs: dict[str, dict[str, object]] | None = None,
) -> tuple[list[SavedFile], str | None]:
    packs = packs if packs is not None else _load_replay_pack_index(replay_packs_dir)
    wanted_key = _session_fingerprint_key(session)
    candidates = [entry for entry in packs.values() if str(entry.get('session_fingerprint_key') or '') == wanted_key]
    if not candidates:
        return [], None
    candidates.sort(key=lambda entry: float(entry.get('created_at') or 0.0), reverse=True)
    for entry in candidates:
        pack_name = str(entry.get('pack_name') or '').strip()
        if not pack_name:
            continue
        replay_path = Path(str(entry.get('replay_file_path') or ''))
        if replay_path and str(replay_path) and not replay_path.exists():
            continue
        pack_dir = replay_packs_dir / pack_name
        manifest = _load_replay_pack_manifest(pack_dir)
        if manifest is None:
            continue
        items = manifest.get('saved_files')
        if not isinstance(items, list):
            continue
        restored: list[SavedFile] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            relative_path = Path(str(item.get('relative_path') or ''))
            if not str(relative_path):
                continue
            source_path = pack_dir / 'paint' / relative_path
            if not source_path.exists():
                continue
            try:
                download_id = _download_id_from_dict(item.get('download_id') if isinstance(item.get('download_id'), dict) else {})
            except Exception:
                continue
            destination = paints_root / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            temp_destination = destination.with_name(destination.name + '.tmp')
            temp_destination.unlink(missing_ok=True)
            shutil.copy2(source_path, temp_destination)
            os.replace(temp_destination, destination)
            restored.append(SavedFile(session_id=session.session_id, download_id=download_id, file_path=destination))
        if restored:
            restored.sort(key=lambda s: (s.download_id.is_team_paint, s.download_id.user_id, s.download_id.directory.lower(), s.download_id.paint_type.value))
            return restored, pack_name
    return [], None

def delete_saved(
    files: Iterable[SavedFile],
    keep_targets: set[tuple[bool, int]] | None = None,
    paints_root: Path | None = None,
) -> list[SavedFile]:
    kept: list[SavedFile] = []
    to_delete: list[SavedFile] = []
    for f in files:
        target_key = (bool(f.download_id.is_team_paint), int(f.download_id.user_id))
        if keep_targets and target_key in keep_targets:
            kept.append(f)
        else:
            to_delete.append(f)
    if not to_delete:
        return kept
    worker_count = max(1, min(16, len(to_delete)))
    with concurrent.futures.ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_item = {
            executor.submit(_hard_delete_file, item.file_path, paints_root): item
            for item in to_delete
        }
        for future in concurrent.futures.as_completed(future_to_item):
            item = future_to_item[future]
            try:
                deleted = future.result()
            except Exception as exc:
                deleted = False
                logging.debug("Delete worker crashed for %s: %s", item.file_path, exc)
            if not deleted and item.file_path.exists():
                logging.warning("Paint file still present after delete attempts: %s", item.file_path)
    return kept
def _collect_wanted_downloads(
    session: Session,
    manifest_workers: int,
    retries: int,
    retry_backoff_seconds: float,
    sync_my_livery_from_server: bool,
) -> list[DownloadFile]:
    wanted_items: list[DownloadFile] = []
    users_sorted = sorted(session.users, key=lambda u: u.user_id)
    manifest_workers = max(1, int(manifest_workers))
    if not users_sorted:
        return wanted_items
    with concurrent.futures.ThreadPoolExecutor(max_workers=manifest_workers) as executor:
        future_to_user = {
            executor.submit(fetch_best_manifest_files, session, user, retries, retry_backoff_seconds): user
            for user in users_sorted
        }
        completed = 0
        total_users = len(future_to_user)
        for future in concurrent.futures.as_completed(future_to_user):
            user = future_to_user[future]
            completed += 1
            if not sync_my_livery_from_server:
                local_team_match = session.local_team_id is not None and user.team_id == session.local_team_id
                local_user_match = session.local_user_id is not None and user.user_id == session.local_user_id
                if local_team_match or local_user_match:
                    target_label = f"team {user.team_id}" if local_team_match and user.team_id is not None else f"user {user.user_id}"
                    logging.info("Manifest progress %s/%s • %s skipped local sync", completed, total_users, target_label)
                    continue
            try:
                all_files = future.result()
            except Exception as exc:  # noqa: BLE001
                logging.warning(
                    "Manifest progress %s/%s • user %s failed after retries: %s",
                    completed,
                    total_users,
                    user.user_id,
                    exc,
                )
                continue
            user_wanted = [normalize_download_for_session_user(user, f) for f in all_files if is_user_file(user, f)]
            label = f"team {user.team_id}" if user.team_id is not None and user.team_id > 0 else f"user {user.user_id}"
            logging.info(
                "Manifest progress %s/%s • %s: %s matching files",
                completed,
                total_users,
                label,
                len(user_wanted),
            )
            if not user_wanted and all_files:
                manifest_dirs = sorted({f.download_id.directory for f in all_files})
                logging.debug(
                    "No matching car files for source user %s (session dir='%s', team_id=%s). Manifest dirs=%s",
                    user.user_id,
                    user.directory,
                    user.team_id,
                    manifest_dirs,
                )
            elif not all_files:
                logging.debug("Manifest returned no files for source user %s", user.user_id)
            wanted_items.extend(user_wanted)
    wanted_items.sort(
        key=lambda f: (
            f.download_id.is_team_paint,
            f.download_id.user_id,
            f.download_id.directory.lower(),
            f.download_id.paint_type.value,
        )
    )
    return wanted_items
def _dedupe_download_items(items: list[DownloadFile]) -> list[DownloadFile]:
    unique: dict[tuple[int, str, PaintType], DownloadFile] = {}
    for item in items:
        key = (
            item.download_id.is_team_paint,
            item.download_id.user_id,
            item.download_id.directory.lower(),
            item.download_id.paint_type,
        )
        unique[key] = item
    deduped = sorted(
        unique.values(),
        key=lambda f: (
            f.download_id.is_team_paint,
            f.download_id.user_id,
            f.download_id.directory.lower(),
            f.download_id.paint_type.value,
        ),
    )
    removed = len(items) - len(deduped)
    if removed > 0:
        logging.debug("Removed %s duplicate manifest item(s) before download", removed)
    return deduped
def _download_items_parallel(
    session: Session,
    temp_dir: Path,
    items: list[DownloadFile],
    download_workers: int,
    retries: int,
    retry_backoff_seconds: float,
) -> tuple[list[DownloadedFile], StageTransferStats]:
    if not items:
        return [], StageTransferStats(stage_name="downloads")
    downloads: list[DownloadedFile] = []
    download_workers = max(1, int(download_workers))
    total = len(items)
    batch_monitor = TransferBatchMonitor("downloads", requested_workers=download_workers, total_items=total)
    with concurrent.futures.ThreadPoolExecutor(max_workers=download_workers) as executor:
        future_to_item: dict[concurrent.futures.Future[DownloadedFile | None], tuple[int, DownloadFile]] = {}
        for index, item in enumerate(items, start=1):
            future = executor.submit(
                download_file,
                session.session_id,
                temp_dir,
                item,
                retries,
                retry_backoff_seconds,
                index,
                total,
                batch_monitor,
            )
            future_to_item[future] = (index, item)
        completed = 0
        for future in concurrent.futures.as_completed(future_to_item):
            index, item = future_to_item[future]
            completed += 1
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                logging.error(
                    "Download progress %s/%s • worker crashed for user %s %s: %s",
                    completed,
                    total,
                    item.download_id.user_id,
                    item.download_id.paint_type.value,
                    exc,
                )
                continue
            if result is not None:
                downloads.append(result)
                logging.info(
                    "Download progress %s/%s • completed user %s %s",
                    completed,
                    total,
                    item.download_id.user_id,
                    item.download_id.paint_type.value,
                )
            else:
                logging.warning(
                    "Download progress %s/%s • failed user %s %s",
                    completed,
                    total,
                    item.download_id.user_id,
                    item.download_id.paint_type.value,
                )
    downloads.sort(
        key=lambda d: (
            d.download_id.is_team_paint,
            d.download_id.user_id,
            d.download_id.directory.lower(),
            d.download_id.paint_type.value,
        )
    )
    return downloads, batch_monitor.snapshot()
def resolve_save_workers(
    download_workers_mode: str,
    download_workers: int,
    item_count: int,
    manual_workers: int,
) -> int:
    if item_count <= 0:
        return 0
    if normalize_download_workers_mode(download_workers_mode) == "manual":
        return max(1, min(100, positive_int(manual_workers, 8)))
    tuned = min(item_count, max(2, min(download_workers, 16)))
    return max(1, tuned)
def _save_downloads_parallel(
    downloads: list[DownloadedFile],
    paints_dir: Path,
    save_workers: int,
) -> tuple[list[SavedFile], StageTransferStats]:
    if not downloads:
        return [], StageTransferStats(stage_name="saves")
    saved: list[SavedFile] = []
    save_workers = max(1, int(save_workers))
    total = len(downloads)
    batch_monitor = TransferBatchMonitor("saves", requested_workers=save_workers, total_items=total)
    with concurrent.futures.ThreadPoolExecutor(max_workers=save_workers) as executor:
        future_to_item: dict[concurrent.futures.Future[list[SavedFile] | None], tuple[int, DownloadedFile]] = {}
        for index, downloaded in enumerate(downloads, start=1):
            future = executor.submit(move_or_extract, downloaded, paints_dir, batch_monitor)
            future_to_item[future] = (index, downloaded)
        completed = 0
        for future in concurrent.futures.as_completed(future_to_item):
            _index, downloaded = future_to_item[future]
            completed += 1
            try:
                result = future.result()
            except Exception as exc:  # noqa: BLE001
                logging.error(
                    "Save progress %s/%s • worker crashed for user %s %s: %s",
                    completed,
                    total,
                    downloaded.download_id.user_id,
                    downloaded.download_id.paint_type.value,
                    exc,
                )
                continue
            if result:
                saved.extend(result)
                logging.info(
                    "Save progress %s/%s • completed user %s %s (%s file(s))",
                    completed,
                    total,
                    downloaded.download_id.user_id,
                    downloaded.download_id.paint_type.value,
                    len(result),
                )
            else:
                logging.warning(
                    "Save progress %s/%s • failed user %s %s",
                    completed,
                    total,
                    downloaded.download_id.user_id,
                    downloaded.download_id.paint_type.value,
                )
    saved.sort(
        key=lambda s: (
            s.download_id.is_team_paint,
            s.download_id.user_id,
            s.download_id.directory.lower(),
            s.download_id.paint_type.value,
        )
    )
    return saved, batch_monitor.snapshot()
def process_session(
    session: Session,
    paints_dir: Path,
    temp_dir: Path,
    max_concurrent_manifests: int,
    max_concurrent_downloads: int,
    download_workers_mode: str,
    manual_manifest_workers: int,
    manual_download_workers: int,
    manual_save_workers: int,
    retries: int,
    retry_backoff_seconds: float,
    sync_my_livery_from_server: bool,
    random_fallback_real_drivers: bool,
    random_fallback_ai: bool,
    keep_tp_paints_in_random_pool: bool,
    max_random_pool_gb: float,
    tp_fallback_mode: str = "online",
    tp_manifest_member_id_override: int = 0,
    tp_mule_profile_fast_mode: bool = False,
    tp_detect_showroom_total_pages: bool = False,
    progress_callback: Callable[[list[SessionDriverSnapshot]], None] | None = None,
) -> tuple[list[SavedFile], ThroughputMonitorSnapshot, list[SessionDriverSnapshot]]:
    session_temp = temp_dir / session.session_id.folder_name()
    if session_temp.exists():
        shutil.rmtree(session_temp, ignore_errors=True)
    logging.info("Session users discovered: %s", len(session.users))
    context_fields = session.trading_paints_context()
    if context_fields is not None:
        logging.info(
            "Trading Paints context active: team=%s user=%s night=%s series=%s league=%s numbers=%s",
            context_fields.get("team", "0"),
            context_fields.get("user", "0"),
            context_fields.get("night", "10:00 am"),
            context_fields.get("series", "0"),
            context_fields.get("league", "0"),
            context_fields.get("numbers", "False"),
        )
    else:
        logging.info("Trading Paints context unavailable; using fetch_user.php fallback manifests")
    if session.is_superspeedway_track:
        logging.info(
            "Superspeedway session detected for track %s (%s); car-related paints will be saved in both regular and _ss forms when available",
            session.track_display_name or session.track_name or "unknown",
            session.track_config_name or "default",
        )
    mode = normalize_download_workers_mode(download_workers_mode)
    manifest_workers = resolve_manifest_workers(
        len(session.users),
        download_workers_mode=mode,
        auto_cap=max_concurrent_manifests,
        manual_workers=manual_manifest_workers,
    )
    wanted_items = _collect_wanted_downloads(
        session=session,
        manifest_workers=manifest_workers,
        retries=retries,
        retry_backoff_seconds=retry_backoff_seconds,
        sync_my_livery_from_server=sync_my_livery_from_server,
    )
    wanted_items = _dedupe_download_items(wanted_items)
    if progress_callback is not None:
        try:
            progress_callback(build_session_driver_rows(session, build_session_stage_statuses(session, wanted_items, sync_my_livery_from_server)))
        except Exception:
            logging.debug("Session progress callback failed during queued/downloading stage", exc_info=True)
    download_workers = resolve_download_workers(
        len(wanted_items),
        download_workers_mode=mode,
        auto_cap=max_concurrent_downloads,
        manual_workers=manual_download_workers,
    )
    save_workers = resolve_save_workers(
        download_workers_mode=mode,
        download_workers=download_workers,
        item_count=len(wanted_items),
        manual_workers=manual_save_workers,
    )
    if mode == "manual":
        logging.info(
            "Queued %s matching downloads with fixed workers: manifests=%s, downloads=%s, saves=%s",
            len(wanted_items),
            manifest_workers,
            download_workers,
            save_workers,
        )
        logging.debug(
            "Worker detail: mode=manual, users=%s, items=%s, manual_manifest_workers=%s, manual_download_workers=%s, manual_save_workers=%s",
            len(session.users),
            len(wanted_items),
            manual_manifest_workers,
            manual_download_workers,
            manual_save_workers,
        )
    else:
        logging.info(
            "Queued %s matching downloads with auto-tuned workers: manifests=%s, downloads=%s, saves=%s",
            len(wanted_items),
            manifest_workers,
            download_workers,
            save_workers,
        )
        logging.debug(
            "Worker detail: mode=auto, users=%s, manifest_cap=%s, items=%s, download_cap=%s",
            len(session.users),
            max_concurrent_manifests,
            len(wanted_items),
            max_concurrent_downloads,
        )
    downloads, download_stats = _download_items_parallel(
        session=session,
        temp_dir=temp_dir,
        items=wanted_items,
        download_workers=download_workers,
        retries=retries,
        retry_backoff_seconds=retry_backoff_seconds,
    )
    saved, save_stats = _save_downloads_parallel(
        downloads=downloads,
        paints_dir=paints_dir,
        save_workers=save_workers,
    )
    random_pool_dir = default_random_pool_dir()
    ai_livery_root = default_ai_livery_dir()
    tp_saved_file_count = len(saved)
    tp_saved_set_count = len(_group_saved_car_sets(saved))
    fallback_mode = str(tp_fallback_mode or "local").strip().lower()
    tp_manifest_member_id = resolve_tp_manifest_member_id(tp_manifest_member_id_override, session.local_user_id)
    if fallback_mode == "online":
        fallback_saved, fallback_logs, fallback_summary = apply_tp_showroom_fallbacks(
            session=session,
            saved=saved,
            paints_dir=paints_dir,
            enable_real_drivers=random_fallback_real_drivers,
            enable_ai=random_fallback_ai,
            sync_my_livery_from_server=sync_my_livery_from_server,
            mapping_path=default_tp_showroom_mapping_path(),
            profile_dir=default_tp_showroom_profile_dir(),
            manifest_member_id=tp_manifest_member_id,
            mule_profile_mode=bool(tp_mule_profile_fast_mode),
            detect_showroom_total_pages=bool(tp_detect_showroom_total_pages),
            retries=retries,
            retry_backoff_seconds=retry_backoff_seconds,
        )
    else:
        fallback_saved, fallback_logs, fallback_summary = apply_local_tp_random_fallbacks(
            session=session,
            saved=saved,
            paints_dir=paints_dir,
            random_pool_dir=random_pool_dir,
            ai_livery_root=ai_livery_root,
            enable_real_drivers=random_fallback_real_drivers,
            enable_ai=random_fallback_ai,
            sync_my_livery_from_server=sync_my_livery_from_server,
        )
    for line in fallback_logs:
        logging.info(line)
    server_saved = list(saved)
    if fallback_saved:
        saved.extend(fallback_saved)
        saved.sort(
            key=lambda s: (
                s.download_id.is_team_paint,
                s.download_id.user_id,
                s.download_id.directory.lower(),
                s.download_id.paint_type.value,
            )
        )
    if keep_tp_paints_in_random_pool:
        pool_saved = list(saved)
        if fallback_mode == "online" and (session.local_user_id is not None or session.local_team_id is not None):
            filtered_pool_saved: list[SavedFile] = []
            skipped_local_pool = False
            for item in pool_saved:
                skip_item = False
                if session.local_user_id is not None and not item.download_id.is_team_paint and int(item.download_id.user_id) == int(session.local_user_id):
                    skip_item = True
                if session.local_team_id is not None and item.download_id.is_team_paint and int(item.download_id.user_id) == int(session.local_team_id):
                    skip_item = True
                if skip_item:
                    skipped_local_pool = True
                    continue
                filtered_pool_saved.append(item)
            pool_saved = filtered_pool_saved
            if skipped_local_pool:
                logging.info("Random TP pool skipped the local user's own saved files to avoid caching a temporary showroom-swapped livery.")
        archived_sets, archived_files, archived_logs, pool_bytes_after, pool_freed_bytes = archive_saved_tp_sets_to_random_pool(
            pool_saved,
            random_pool_dir,
            max_random_pool_gb,
        )
        if archived_sets > 0:
            logging.info(
                "Random TP pool updated with %s set(s) and %s file(s) after fallback resolution",
                archived_sets,
                archived_files,
            )
            for line in archived_logs:
                logging.info(line)
        else:
            logging.debug("Random TP pool is enabled, but this session did not add any new reusable car paint set to the pool")
        if pool_freed_bytes > 0:
            logging.info(
                "Random TP pool trimmed by %.2f GB to honor the configured limit of %.2f GB",
                pool_freed_bytes / float(1024 ** 3),
                clamp_random_pool_gb(max_random_pool_gb),
            )
        logging.info(
            "Random TP pool usage: %.2f GB / %.2f GB",
            pool_bytes_after / float(1024 ** 3),
            clamp_random_pool_gb(max_random_pool_gb),
        )
    else:
        logging.info(
            "Random TP pool archival is disabled, so deleting downloaded livery will remove those files permanently instead of recycling them into the local fallback pool"
        )
    shutil.rmtree(session_temp, ignore_errors=True)
    logging.info(
        "Session summary • TP files saved=%s • TP car sets=%s • fallback mode=%s • recycled to pool=%s set(s)/%s file(s) • random fallback applied=%s target(s)/%s file(s) • random fallback misses=%s • repeated random source uses=%s",
        tp_saved_file_count,
        tp_saved_set_count,
        fallback_mode,
        archived_sets if keep_tp_paints_in_random_pool else 0,
        archived_files if keep_tp_paints_in_random_pool else 0,
        fallback_summary.applied_targets,
        len(fallback_saved),
        fallback_summary.missing_source_targets,
        fallback_summary.repeated_source_uses,
    )
    logging.info(
        "Session %s complete: %s queued, %s downloaded, %s saved",
        session.session_id.folder_name(),
        len(wanted_items),
        len(downloads),
        len(saved),
    )
    monitor_snapshot = ThroughputMonitorSnapshot(
        session_name=session.session_id.folder_name(),
        worker_mode=mode,
        manifest_workers=manifest_workers,
        download_workers=download_workers,
        save_workers=save_workers,
        queued_items=len(wanted_items),
        downloaded_items=len(downloads),
        saved_items=len(saved),
        download_stage_seconds=download_stats.stage_seconds,
        save_stage_seconds=save_stats.stage_seconds,
        download_files_per_second=download_stats.files_per_second,
        save_files_per_second=save_stats.files_per_second,
        average_download_seconds=download_stats.average_item_seconds,
        average_save_seconds=save_stats.average_item_seconds,
        average_download_mbps=download_stats.megabits_per_second,
        peak_active_downloads=download_stats.peak_active_items,
        effective_parallelism=download_stats.effective_parallelism,
        ceiling_hint=build_tp_ceiling_hint(download_stats),
        updated_at=time.time(),
    )
    logging.info(
        "TP monitor • requested downloads=%s, peak active=%s, download stage=%.2fs, avg file=%.2fs, throughput=%.2f files/s, avg rate=%.1f Mbps, effective parallelism=%.1f, hint=%s",
        download_workers,
        download_stats.peak_active_items,
        download_stats.stage_seconds,
        download_stats.average_item_seconds,
        download_stats.files_per_second,
        download_stats.megabits_per_second,
        download_stats.effective_parallelism,
        monitor_snapshot.ceiling_hint,
    )
    logging.info(
        "Save monitor • requested saves=%s, save stage=%.2fs, avg file=%.2fs, throughput=%.2f files/s",
        save_workers,
        save_stats.stage_seconds,
        save_stats.average_item_seconds,
        save_stats.files_per_second,
    )
    final_rows = build_session_driver_rows(
        session,
        build_session_final_statuses(
            session,
            wanted_items=wanted_items,
            server_saved=server_saved,
            fallback_saved=fallback_saved,
            sync_my_livery_from_server=sync_my_livery_from_server,
            replay_mode=False,
            fallback_mode=fallback_mode,
        ),
    )
    if progress_callback is not None:
        try:
            progress_callback(final_rows)
        except Exception:
            logging.debug("Session progress callback failed during final stage", exc_info=True)
    return saved, monitor_snapshot, final_rows
def should_use_sdk(args: argparse.Namespace) -> bool:
    return args.iracing_sdk or args.session_yaml is None
def create_sdk_reader() -> IracingSdkReader | None:
    try:
        import irsdk as irsdk_module
    except ImportError:
        logging.error(
            "iRacing SDK mode requested but package 'irsdk' is not installed. "
            "Install it with: pip install pyirsdk"
        )
        return None
    sdk = irsdk_module.IRSDK()
    try:
        started = bool(sdk.startup())
    except Exception as exc:  # noqa: BLE001
        logging.debug("Initial SDK startup() raised an exception: %s", exc)
        started = False
    if started and getattr(sdk, "is_connected", False):
        logging.info("Connected to iRacing SDK")
    else:
        logging.info("iRacing SDK watcher started. Waiting for iRacing/session...")
    return IracingSdkReader(sdk=sdk)
def close_sdk_reader(reader: IracingSdkReader | None) -> None:
    if reader is None:
        return
    try:
        reader.sdk.shutdown()
    except Exception:
        pass
def _read_session_info_update(sdk: object) -> int:
    try:
        value = getattr(sdk, "session_info_update", None)
        if value is not None:
            return int(value)
    except Exception:  # noqa: BLE001
        pass
    try:
        value = sdk["SessionInfoUpdate"]
        if value is not None:
            return int(value)
    except Exception:  # noqa: BLE001
        pass
    return 0
def read_session_from_sdk(reader: IracingSdkReader) -> tuple[SdkPollState, Session | None]:
    sdk = reader.sdk
    try:
        if not sdk.is_initialized:
            if not sdk.startup():
                logging.debug("SDK not initialized and startup() failed")
                return SdkPollState.INACTIVE, None
    except Exception as exc:  # noqa: BLE001
        logging.debug("SDK startup() failed while polling: %s", exc)
        return SdkPollState.INACTIVE, None
    if not sdk.is_connected:
        logging.debug("SDK initialized but not connected to an active iRacing session")
        reader.last_update = None
        return SdkPollState.INACTIVE, None
    try:
        sdk.freeze_var_buffer_latest()
    except Exception as exc:  # noqa: BLE001
        logging.debug("freeze_var_buffer_latest() failed: %s", exc)
    update = _read_session_info_update(sdk)
    if reader.last_update is not None and update == reader.last_update:
        logging.debug("SessionInfoUpdate unchanged (%s); skipping this poll", update)
        return SdkPollState.UNCHANGED, None
    try:
        weekend = sdk["WeekendInfo"]
        driver_info = sdk["DriverInfo"]
    except Exception as exc:  # noqa: BLE001
        logging.debug("Failed to read session sections from SDK: %s", exc)
        reader.last_update = update
        return SdkPollState.INVALID, None
    if not isinstance(weekend, dict):
        logging.debug("WeekendInfo missing or invalid (type=%s)", type(weekend).__name__)
        reader.last_update = update
        return SdkPollState.INVALID, None
    if not isinstance(driver_info, dict):
        logging.debug("DriverInfo missing or invalid (type=%s)", type(driver_info).__name__)
        reader.last_update = update
        return SdkPollState.INVALID, None
    load_num_textures = False
    try:
        load_num_value = sdk["LoadNumTextures"]
        load_num_textures = _to_boolish(load_num_value, default=False)
    except Exception as exc:  # noqa: BLE001
        logging.debug("Could not read LoadNumTextures from SDK: %s", exc)
    session = _build_session_from_parts(weekend, driver_info, load_num_textures=load_num_textures)
    reader.last_update = update
    if session is not None and (session.local_user_id is None or session.local_user_id <= 0):
        fallback_local_user_id = _read_sdk_local_user_id(sdk)
        if fallback_local_user_id is not None and fallback_local_user_id > 0:
            session = replace(session, local_user_id=fallback_local_user_id)
            logging.debug("Recovered local user ID %s from SDK fallback fields", fallback_local_user_id)
    if session is None:
        logging.debug("SDK returned session data, but it could not be converted into a Session")
        return SdkPollState.INVALID, None
    logging.debug(
        "Loaded session from SDK (update=%s, session=%s, users=%s)",
        update,
        session.session_id.folder_name(),
        len(session.users),
    )
    return SdkPollState.SESSION, session
def has_replay_pack_for_session(
    session: Session,
    replay_packs_dir: Path,
    packs: dict[str, dict[str, object]] | None = None,
) -> bool:
    packs = packs if packs is not None else _load_replay_pack_index(replay_packs_dir)
    wanted_key = _session_fingerprint_key(session)
    for entry in packs.values():
        if str(entry.get('session_fingerprint_key') or '').strip() != wanted_key:
            continue
        pack_name = str(entry.get('pack_name') or '').strip()
        if not pack_name:
            continue
        replay_path = Path(str(entry.get('replay_file_path') or ''))
        if str(replay_path) and not replay_path.exists():
            continue
        pack_dir = replay_packs_dir / pack_name
        if (pack_dir / REPLAY_PACK_MANIFEST_FILENAME).exists():
            return True
    return False

def _read_replay_mode_active(reader: IracingSdkReader) -> bool:
    sdk = reader.sdk
    try:
        if not sdk.is_initialized and not sdk.startup():
            return False
    except Exception:
        return False
    if not sdk.is_connected:
        return False
    try:
        sdk.freeze_var_buffer_latest()
    except Exception:
        pass
    try:
        replay_playing = sdk["IsReplayPlaying"]
        if replay_playing is not None and bool(replay_playing):
            return True
    except Exception:
        pass
    for key in ("ReplayFrameNum", "ReplayFrameNumEnd", "ReplaySessionNum", "ReplaySessionTime"):
        try:
            value = sdk[key]
        except Exception:
            continue
        if value is None:
            continue
        try:
            numeric = float(value)
        except Exception:
            continue
        if numeric not in (0.0, -1.0):
            return True
    return False
def _read_ok_to_reload_textures(reader: IracingSdkReader) -> bool | None:
    sdk = reader.sdk
    try:
        if not sdk.is_initialized:
            if not sdk.startup():
                return None
    except Exception as exc:  # noqa: BLE001
        logging.debug("SDK startup() failed while checking OkToReloadTextures: %s", exc)
        return None
    if not sdk.is_connected:
        return None
    try:
        sdk.freeze_var_buffer_latest()
    except Exception as exc:  # noqa: BLE001
        logging.debug("freeze_var_buffer_latest() failed while checking OkToReloadTextures: %s", exc)
    try:
        value = sdk["OkToReloadTextures"]
    except Exception as exc:  # noqa: BLE001
        logging.debug("Could not read OkToReloadTextures from SDK: %s", exc)
        return None
    if value is None:
        return None
    return bool(value)
def trigger_texture_reload(reader: IracingSdkReader) -> bool:
    sdk = reader.sdk
    try:
        if not sdk.is_initialized:
            if not sdk.startup():
                logging.warning("Could not initialize SDK to trigger texture reload")
                return False
    except Exception as exc:  # noqa: BLE001
        logging.warning("SDK startup() failed before texture reload: %s", exc)
        return False
    if not sdk.is_connected:
        logging.debug("SDK not connected; cannot trigger texture reload right now")
        return False
    reload_method = getattr(sdk, "reload_all_textures", None)
    if not callable(reload_method):
        logging.warning("This irsdk package does not expose reload_all_textures(); cannot auto-refresh paints")
        return False
    try:
        reload_method()
    except Exception as exc:  # noqa: BLE001
        logging.warning("Failed to trigger iRacing texture reload: %s", exc)
        return False
    logging.info("Triggered iRacing texture reload via SDK")
    return True
def maybe_trigger_pending_texture_reload(
    reader: IracingSdkReader,
    pending_reload: PendingTextureReload | None,
    active_fingerprint: tuple[SessionId, tuple[tuple[int, str], ...]] | None,
    force_after_seconds: float = 15.0,
) -> bool:
    if pending_reload is None:
        return False
    if active_fingerprint != pending_reload.fingerprint:
        return False
    ok_to_reload = _read_ok_to_reload_textures(reader)
    elapsed = max(0.0, time.monotonic() - pending_reload.first_requested_at)
    if ok_to_reload is False:
        if elapsed < max(force_after_seconds, 0.0):
            if not pending_reload.wait_log_emitted:
                logging.info("Waiting for iRacing to allow texture reload before refreshing paints...")
                pending_reload.wait_log_emitted = True
            return False
        logging.warning(
            "OkToReloadTextures stayed false for %.1fs; attempting forced texture reload anyway",
            elapsed,
        )
    elif ok_to_reload is None and not pending_reload.wait_log_emitted:
        logging.debug("OkToReloadTextures unavailable; trying texture reload anyway")
        pending_reload.wait_log_emitted = True
    return trigger_texture_reload(reader)
@dataclass
class AppConfig:
    auto_start: bool = True
    start_minimized: bool = True
    minimize_to_tray_on_close: bool = True
    auto_refresh_paints: bool = True
    cleanup_before_fetch: bool = True
    delete_downloaded_livery: bool = True
    sync_my_livery_from_server: bool = True
    keep_my_livery_locally: bool = True
    sync_ai_rosters_from_server: bool = True
    random_fallback_real_drivers: bool = True
    random_fallback_ai: bool = True
    tp_fallback_mode: str = "online"
    tp_manifest_member_id_override: int = 0
    tp_mule_profile_fast_mode: bool = False
    tp_detect_showroom_total_pages: bool = False
    quick_start_completed: bool = False
    keep_tp_paints_in_random_pool: bool = True
    max_random_pool_gb: float = 5.0
    auto_manage_replay_packs: bool = True
    show_activity_log: bool = True
    show_tp_monitor: bool = True
    check_updates_automatically: bool = True
    download_workers_mode: str = "auto"
    manual_download_workers: int = 100
    manual_manifest_workers: int = 100
    manual_save_workers: int = 100
    max_concurrent_downloads: int = 8
    verbose: bool = False
    poll_seconds: float = 0.8
    retries: int = 3
    retry_backoff_seconds: float = 1.0
    launch_mode_preference: str = "ask"
class ConfigStore:
    def __init__(self) -> None:
        self.path = self._default_path()
        self.path.parent.mkdir(parents=True, exist_ok=True)
    @staticmethod
    def _default_path() -> Path:
        appdata = os.getenv("APPDATA")
        if appdata:
            return Path(appdata) / APP_CONFIG_DIRNAME / "settings.json"
        return Path.home() / f".{APP_CONFIG_DIRNAME.lower()}_settings.json"
    def load(self) -> AppConfig:
        if not self.path.exists():
            return AppConfig()
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return AppConfig()
        config = AppConfig()
        for key, value in raw.items():
            if hasattr(config, key):
                setattr(config, key, value)
        loaded_mode = str(raw.get("download_workers_mode", config.download_workers_mode)).strip().lower()
        if loaded_mode not in {"auto", "manual"}:
            loaded_mode = "auto"
        config.download_workers_mode = loaded_mode
        try:
            migrated_manual_workers = int(raw.get("max_concurrent_downloads", config.manual_download_workers))
        except Exception:
            migrated_manual_workers = config.manual_download_workers
        try:
            config.manual_download_workers = int(raw.get("manual_download_workers", migrated_manual_workers))
        except Exception:
            config.manual_download_workers = migrated_manual_workers
        config.manual_download_workers = max(1, min(100, int(config.manual_download_workers)))
        try:
            config.manual_manifest_workers = int(raw.get("manual_manifest_workers", config.manual_download_workers))
        except Exception:
            config.manual_manifest_workers = config.manual_download_workers
        config.manual_manifest_workers = max(1, min(100, int(config.manual_manifest_workers)))
        try:
            config.manual_save_workers = int(raw.get("manual_save_workers", config.manual_download_workers))
        except Exception:
            config.manual_save_workers = config.manual_download_workers
        config.manual_save_workers = max(1, min(100, int(config.manual_save_workers)))
        # Auto mode now means the built-in adaptive behavior with the default cap of 8.
        config.max_concurrent_downloads = 8
        config.poll_seconds = max(0.2, float(config.poll_seconds))
        config.retries = max(1, int(config.retries))
        config.retry_backoff_seconds = max(0.1, float(config.retry_backoff_seconds))
        config.verbose = bool(config.verbose)
        config.auto_refresh_paints = bool(config.auto_refresh_paints)
        config.cleanup_before_fetch = bool(config.cleanup_before_fetch)
        config.delete_downloaded_livery = bool(config.delete_downloaded_livery)
        config.sync_my_livery_from_server = bool(config.sync_my_livery_from_server)
        config.keep_my_livery_locally = bool(config.keep_my_livery_locally)
        config.sync_ai_rosters_from_server = bool(getattr(config, "sync_ai_rosters_from_server", True))
        config.random_fallback_real_drivers = bool(getattr(config, "random_fallback_real_drivers", True))
        config.random_fallback_ai = bool(getattr(config, "random_fallback_ai", True))
        config.tp_fallback_mode = str(getattr(config, "tp_fallback_mode", "online") or "online").strip().lower()
        if config.tp_fallback_mode not in {"local", "online"}:
            config.tp_fallback_mode = "online"
        config.tp_manifest_member_id_override = normalize_tp_member_id(getattr(config, "tp_manifest_member_id_override", 0))
        config.tp_mule_profile_fast_mode = bool(getattr(config, "tp_mule_profile_fast_mode", False))
        config.tp_detect_showroom_total_pages = bool(getattr(config, "tp_detect_showroom_total_pages", False))
        config.quick_start_completed = bool(getattr(config, "quick_start_completed", False))
        config.keep_tp_paints_in_random_pool = bool(getattr(config, "keep_tp_paints_in_random_pool", True))
        config.max_random_pool_gb = clamp_random_pool_gb(getattr(config, "max_random_pool_gb", 5.0), 5.0)
        config.show_activity_log = bool(config.show_activity_log)
        config.show_tp_monitor = bool(getattr(config, "show_tp_monitor", True))
        config.check_updates_automatically = bool(getattr(config, "check_updates_automatically", True))
        config.launch_mode_preference = normalize_launch_mode_preference(getattr(config, "launch_mode_preference", "ask"))
        return config
    def save(self, config: AppConfig) -> None:
        safe = AppConfig(**asdict(config))
        safe.launch_mode_preference = normalize_launch_mode_preference(getattr(safe, "launch_mode_preference", "ask"))
        safe.download_workers_mode = str(safe.download_workers_mode).strip().lower()
        if safe.download_workers_mode not in {"auto", "manual"}:
            safe.download_workers_mode = "auto"
        safe.manual_download_workers = max(1, min(100, int(safe.manual_download_workers)))
        safe.manual_manifest_workers = max(1, min(100, int(safe.manual_manifest_workers)))
        safe.manual_save_workers = max(1, min(100, int(safe.manual_save_workers)))
        safe.max_concurrent_downloads = 8
        safe.tp_fallback_mode = str(getattr(safe, "tp_fallback_mode", "online") or "online").strip().lower()
        if safe.tp_fallback_mode not in {"local", "online"}:
            safe.tp_fallback_mode = "online"
        safe.tp_manifest_member_id_override = normalize_tp_member_id(getattr(safe, "tp_manifest_member_id_override", 0))
        safe.tp_mule_profile_fast_mode = bool(getattr(safe, "tp_mule_profile_fast_mode", False))
        safe.tp_detect_showroom_total_pages = bool(getattr(safe, "tp_detect_showroom_total_pages", False))
        safe.quick_start_completed = bool(getattr(safe, "quick_start_completed", False))
        safe.keep_tp_paints_in_random_pool = bool(safe.keep_tp_paints_in_random_pool)
        safe.max_random_pool_gb = clamp_random_pool_gb(safe.max_random_pool_gb, 5.0)
        safe.poll_seconds = max(0.2, float(safe.poll_seconds))
        safe.retries = max(1, int(safe.retries))
        safe.retry_backoff_seconds = max(0.1, float(safe.retry_backoff_seconds))
        self.path.write_text(json.dumps(asdict(safe), indent=2), encoding="utf-8")
class QueueLogHandler(logging.Handler):
    def __init__(self, target_queue: "queue.Queue[str]") -> None:
        super().__init__()
        self.target_queue = target_queue
    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.target_queue.put_nowait(self.format(record))
        except Exception:
            pass
def get_manifest_cap_from_download_cap(download_cap: int) -> int:
    capped = max(1, download_cap)
    if capped <= 4:
        return 3
    if capped <= 8:
        return 5
    if capped <= 12:
        return 7
    if capped <= 16:
        return 8
    return 10
def build_tp_ceiling_hint(download_stats: StageTransferStats) -> str:
    if download_stats.completed_items <= 0:
        return "Not enough data yet"
    requested = max(1, int(download_stats.requested_workers))
    if download_stats.total_items < min(requested, 12):
        return "Need a larger session to probe the limit"
    effective = max(0.0, float(download_stats.effective_parallelism))
    if effective <= 0.0:
        return "Not enough data yet"
    if requested <= max(4, int(round(effective + 1.0))):
        return "No clear TP ceiling seen yet at this worker count"
    low = max(1, int(round(effective * 0.90)))
    high = max(low, int(round(effective * 1.10)))
    if high - low <= 1:
        return f"Approx observed ceiling: ~{int(round(effective))} parallel downloads"
    return f"Approx observed ceiling: ~{low}-{high} parallel downloads"
class DownloaderService:
    def __init__(self, config: AppConfig, log_queue: "queue.Queue[str] | None" = None) -> None:
        self._config = AppConfig(**asdict(config))
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._status = "Stopped"
        self._status_callback: Callable[[str], None] | None = None
        self._log_queue = log_queue
        self._force_refresh_event = threading.Event()
        self._clear_current_event = threading.Event()
        self._sync_ai_rosters_event = threading.Event()
        self._monitor_snapshot = ThroughputMonitorSnapshot()
        self._runtime_snapshot = RuntimeSnapshot()
    def set_status_callback(self, callback: Callable[[str], None]) -> None:
        self._status_callback = callback
    def _set_status(self, value: str) -> None:
        self._status = value
        if self._status_callback is not None:
            try:
                self._status_callback(value)
            except Exception:
                pass
    def get_status(self) -> str:
        return self._status
    def get_monitor_snapshot(self) -> ThroughputMonitorSnapshot:
        with self._lock:
            return ThroughputMonitorSnapshot(**asdict(self._monitor_snapshot))
    def get_runtime_snapshot(self) -> RuntimeSnapshot:
        with self._lock:
            current_session = self._runtime_snapshot.current_session
            last_saved = list(self._runtime_snapshot.last_saved)
            last_known_member_id = self._runtime_snapshot.last_known_member_id
            session_rows = list(getattr(self._runtime_snapshot, "session_rows", []))
            replay_mode_active = bool(getattr(self._runtime_snapshot, "replay_mode_active", False))
        return RuntimeSnapshot(
            current_session=current_session,
            last_saved=last_saved,
            last_known_member_id=last_known_member_id,
            session_rows=session_rows,
            replay_mode_active=replay_mode_active,
        )
    def _update_runtime_snapshot(
        self,
        current_session: Session | None,
        last_saved: list[SavedFile],
        last_known_member_id: int | None,
        session_rows: list[SessionDriverSnapshot] | None = None,
        replay_mode_active: bool = False,
    ) -> None:
        if session_rows is None:
            session_rows = build_session_driver_rows(current_session)
        with self._lock:
            self._runtime_snapshot = RuntimeSnapshot(
                current_session=current_session,
                last_saved=list(last_saved),
                last_known_member_id=last_known_member_id,
                session_rows=list(session_rows),
                replay_mode_active=bool(replay_mode_active),
            )
    def reset_monitor_snapshot(self) -> None:
        with self._lock:
            self._monitor_snapshot = ThroughputMonitorSnapshot()
    def _update_monitor_snapshot(self, snapshot: ThroughputMonitorSnapshot) -> None:
        with self._lock:
            best_effective = max(self._monitor_snapshot.best_effective_parallelism, snapshot.effective_parallelism)
            best_fps = max(self._monitor_snapshot.best_download_files_per_second, snapshot.download_files_per_second)
            snapshot.best_effective_parallelism = best_effective
            snapshot.best_download_files_per_second = best_fps
            snapshot.updated_at = time.time()
            self._monitor_snapshot = ThroughputMonitorSnapshot(**asdict(snapshot))
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()
    def update_config(self, config: AppConfig) -> None:
        with self._lock:
            self._config = AppConfig(**asdict(config))
        root = logging.getLogger()
        root.setLevel(logging.DEBUG if config.verbose else logging.INFO)
        logging.debug(
            "Config updated: download_mode=%s, manual_manifest_workers=%s, manual_download_workers=%s, manual_save_workers=%s, auto_refresh=%s, cleanup_before_fetch=%s, cleanup_on_exit=%s",
            self._config.download_workers_mode,
            self._config.manual_manifest_workers,
            self._config.manual_download_workers,
            self._config.manual_save_workers,
            self._config.auto_refresh_paints,
            self._config.cleanup_before_fetch,
            self._config.delete_downloaded_livery,
        )
    def get_config(self) -> AppConfig:
        with self._lock:
            return AppConfig(**asdict(self._config))
    def request_refresh_now(self) -> None:
        self._force_refresh_event.set()
    def request_clear_current_downloads(self) -> None:
        self._clear_current_event.set()
    def request_sync_ai_rosters_now(self) -> None:
        self._sync_ai_rosters_event.set()
    def start(self) -> None:
        if self.is_running():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_forever, name="NishizumiPaintsService", daemon=True)
        self._thread.start()
    def stop(self, join_timeout: float = 5.0) -> None:
        self._stop_event.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=join_timeout)
        self._thread = None
        self._set_status("Stopped")
    def _install_logging(self) -> None:
        config = self.get_config()
        setup_logging(config.verbose)
        if self._log_queue is not None:
            handler = QueueLogHandler(self._log_queue)
            handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"))
            root = logging.getLogger()
            if not any(isinstance(existing, QueueLogHandler) for existing in root.handlers):
                handler.setLevel(logging.NOTSET)
                root.addHandler(handler)
        for existing in logging.getLogger().handlers:
            existing.setLevel(logging.NOTSET)
        logging.debug("Verbose logging active")
    def _cleanup_saved(
        self,
        saved: list[SavedFile],
        keep_my_livery_locally: bool,
        preserve_targets: set[tuple[bool, int]] | None,
        reason: str,
        paints_root: Path | None = None,
        fallback_member_id: int | None = None,
        fallback_team_id: int | None = None,
    ) -> list[SavedFile]:
        keep_targets = _merge_preserve_targets(
            preserve_targets,
            fallback_member_id=fallback_member_id,
            fallback_team_id=fallback_team_id,
        ) if keep_my_livery_locally else set()
        if keep_my_livery_locally and not keep_targets:
            logging.warning("Keep my livery locally is enabled, but no local iRacing member/team target could be resolved for this cleanup pass.")
        if not saved:
            return []
        logging.info(reason)
        kept = delete_saved(saved, keep_targets=keep_targets, paints_root=paints_root)
        if keep_targets and kept:
            labels = []
            for is_team, target_id in sorted(keep_targets):
                labels.append(f"team {target_id}" if is_team else f"user {target_id}")
            logging.info("Kept %s local livery file(s) for your local targets (%s)", len(kept), ", ".join(labels))
        return kept
    def _run_forever(self) -> None:
        crash_count = 0
        while not self._stop_event.is_set():
            try:
                self._run_loop()
                crash_count = 0
                break
            except Exception as exc:  # noqa: BLE001
                crash_count += 1
                logging.error("Service loop crashed (%s): %s", crash_count, exc)
                logging.debug("Service crash traceback\n%s", traceback.format_exc())
                self._set_status("Recovering")
                self._stop_event.wait(min(5.0, 1.0 + crash_count))
    def _run_loop(self) -> None:
        self._install_logging()
        self._set_status("Starting")
        paints_dir = default_paints_dir()
        temp_dir = default_temp_dir()
        replay_dir = default_replay_dir()
        replay_packs_dir = default_replay_packs_dir()
        paints_dir.mkdir(parents=True, exist_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        replay_packs_dir.mkdir(parents=True, exist_ok=True)
        cleanup_stale_temp_dirs(temp_dir)
        sdk_reader: IracingSdkReader | None = None
        next_sdk_open_at = 0.0
        last_session: SessionId | None = None
        current_session: Session | None = None
        last_session_fingerprint: tuple[SessionId, tuple[tuple[int, str], ...]] | None = None
        last_session_preserve_targets: set[tuple[bool, int]] = set()
        last_saved: list[SavedFile] = []
        session_rows: list[SessionDriverSnapshot] = []
        last_known_member_id: int | None = None
        last_known_team_id: int | None = None
        last_ai_roster_sync_member_id: int | None = None
        pending_reload: PendingTextureReload | None = None
        last_poll_state: SdkPollState | None = None
        replay_mode_active = False
        known_replay_files = _snapshot_replay_files(replay_dir)
        for line in reconcile_replay_pack_index(replay_dir, replay_packs_dir):
            logging.info(line)
        replay_pack_index = _load_replay_pack_index(replay_packs_dir)
        next_replay_pack_scan_at = 0.0
        self._update_runtime_snapshot(current_session, last_saved, last_known_member_id, session_rows=session_rows, replay_mode_active=replay_mode_active)
        try:
            while not self._stop_event.is_set():
                config = self.get_config()
                now_monotonic = time.monotonic()
                if getattr(config, "auto_manage_replay_packs", True) and now_monotonic >= next_replay_pack_scan_at:
                    known_replay_files, replay_pack_index = sync_replay_packs_for_folder(
                        replay_dir=replay_dir,
                        replay_packs_dir=replay_packs_dir,
                        known_files=known_replay_files,
                        current_session=current_session,
                        saved=last_saved,
                        paints_root=paints_dir,
                        known_packs=replay_pack_index,
                    )
                    next_replay_pack_scan_at = now_monotonic + 2.5
                if self._force_refresh_event.is_set() and sdk_reader is not None:
                    sdk_reader.last_update = None
                if self._clear_current_event.is_set():
                    self._clear_current_event.clear()
                    if last_saved:
                        last_saved = self._cleanup_saved(
                            saved=last_saved,
                            keep_my_livery_locally=config.keep_my_livery_locally,
                            preserve_targets=last_session_preserve_targets,
                            reason="Manual clear requested. Removing current downloaded paints",
                            paints_root=paints_dir,
                            fallback_member_id=last_known_member_id,
                            fallback_team_id=last_known_team_id,
                        )
                        if config.auto_refresh_paints and last_session_fingerprint is not None:
                            pending_reload = PendingTextureReload(
                                fingerprint=last_session_fingerprint,
                                first_requested_at=time.monotonic(),
                            )
                        self._update_runtime_snapshot(current_session, last_saved, last_known_member_id, session_rows=session_rows, replay_mode_active=replay_mode_active)
                    else:
                        logging.info("Manual clear requested, but there are no current downloaded paints to remove")
                if self._sync_ai_rosters_event.is_set():
                    self._sync_ai_rosters_event.clear()
                    member_id_for_sync = last_known_member_id
                    if member_id_for_sync is None or member_id_for_sync <= 0:
                        logging.info("Manual AI roster sync requested, but no local member ID is known yet. Join any iRacing session first.")
                    else:
                        self._set_status("Syncing AI rosters")
                        sync_ai_rosters(
                            member_id=member_id_for_sync,
                            ai_rosters_dir=default_ai_rosters_dir(),
                            retries=positive_int(config.retries, 3),
                            retry_backoff_seconds=max(config.retry_backoff_seconds, 0.1),
                            do_cleanup=True,
                        )
                        last_ai_roster_sync_member_id = member_id_for_sync
                        self._set_status("Watching")
                if pending_reload is not None:
                    if sdk_reader is not None and config.auto_refresh_paints and maybe_trigger_pending_texture_reload(
                        reader=sdk_reader,
                        pending_reload=pending_reload,
                        active_fingerprint=last_session_fingerprint,
                    ):
                        pending_reload = None
                    elif not config.auto_refresh_paints or sdk_reader is None:
                        pending_reload = None
                self._set_status("Watching")
                if sdk_reader is None:
                    now = time.monotonic()
                    if now < next_sdk_open_at:
                        self._stop_event.wait(min(max(config.poll_seconds, 0.2), max(0.0, next_sdk_open_at - now)))
                        continue
                    sdk_reader = create_sdk_reader()
                    if sdk_reader is None:
                        self._set_status("SDK unavailable")
                        self._stop_event.wait(max(config.poll_seconds, 0.5))
                        continue
                poll_state, session = read_session_from_sdk(sdk_reader)
                if poll_state != last_poll_state:
                    logging.debug("Poll state changed: %s -> %s", last_poll_state, poll_state)
                    last_poll_state = poll_state
                if poll_state in {SdkPollState.INACTIVE, SdkPollState.INVALID}:
                    if getattr(config, "auto_manage_replay_packs", True):
                        known_replay_files, replay_pack_index = sync_replay_packs_for_folder(
                            replay_dir=replay_dir,
                            replay_packs_dir=replay_packs_dir,
                            known_files=known_replay_files,
                            current_session=current_session,
                            saved=last_saved,
                            paints_root=paints_dir,
                        )
                    if last_saved and config.delete_downloaded_livery:
                        last_saved = self._cleanup_saved(
                            saved=last_saved,
                            keep_my_livery_locally=config.keep_my_livery_locally,
                            preserve_targets=last_session_preserve_targets,
                            reason=(
                                f"No active valid session detected. Clearing paints from previous session {last_session}"
                            ),
                            paints_root=paints_dir,
                            fallback_member_id=last_known_member_id,
                            fallback_team_id=last_known_team_id,
                        )
                    if sdk_reader is not None:
                        logging.debug("Closing SDK after inactive/invalid state so next session starts with a fresh SDK connection")
                        close_sdk_reader(sdk_reader)
                        sdk_reader = None
                        next_sdk_open_at = time.monotonic() + max(config.poll_seconds, 1.0)
                    last_session = None
                    current_session = None
                    session_rows = []
                    replay_mode_active = False
                    last_session_fingerprint = None
                    last_session_preserve_targets = set()
                    pending_reload = None
                    self._update_runtime_snapshot(None, last_saved, last_known_member_id, session_rows=[])
                    self._stop_event.wait(max(config.poll_seconds, 0.2))
                    continue
                if poll_state is SdkPollState.UNCHANGED:
                    self._stop_event.wait(max(config.poll_seconds, 0.2))
                    continue
                assert session is not None
                current_session = session
                base_session_rows = build_session_driver_rows(session)
                if session.local_user_id is not None and session.local_user_id > 0:
                    last_known_member_id = session.local_user_id
                if session.local_team_id is not None and session.local_team_id > 0:
                    last_known_team_id = session.local_team_id
                if session.ai_driver_count > 0:
                    logging.info(
                        "AI session context detected: ai_drivers=%s%s",
                        session.ai_driver_count,
                        f" | roster={session.ai_roster_id} {session.ai_roster_name}" if (session.ai_roster_id or session.ai_roster_name) else "",
                    )
                if (
                    config.sync_ai_rosters_from_server
                    and session.local_user_id is not None
                    and session.local_user_id > 0
                    and last_ai_roster_sync_member_id != session.local_user_id
                ):
                    self._set_status("Syncing AI rosters")
                    sync_ai_rosters(
                        member_id=session.local_user_id,
                        ai_rosters_dir=default_ai_rosters_dir(),
                        retries=positive_int(config.retries, 3),
                        retry_backoff_seconds=max(config.retry_backoff_seconds, 0.1),
                        do_cleanup=True,
                    )
                    last_ai_roster_sync_member_id = session.local_user_id
                    self._set_status("Watching")
                current_fingerprint = session.fingerprint()
                replay_mode_active = bool(
                    getattr(config, "auto_manage_replay_packs", True)
                    and sdk_reader is not None
                    and _read_replay_mode_active(sdk_reader)
                    and has_replay_pack_for_session(session, replay_packs_dir, replay_pack_index)
                )
                forced_refresh = self._force_refresh_event.is_set()
                if last_session_fingerprint == current_fingerprint and not forced_refresh:
                    existing_rows = self.get_runtime_snapshot().session_rows
                    self._update_runtime_snapshot(
                        current_session,
                        last_saved,
                        last_known_member_id,
                        session_rows=list(existing_rows) if existing_rows else base_session_rows,
                        replay_mode_active=replay_mode_active,
                    )
                    self._stop_event.wait(max(config.poll_seconds, 0.2))
                    continue
                self._update_runtime_snapshot(current_session, last_saved, last_known_member_id, session_rows=base_session_rows, replay_mode_active=replay_mode_active)
                session_rows = base_session_rows
                if forced_refresh:
                    self._force_refresh_event.clear()
                    logging.info("Manual re-download requested for session %s", session.session_id.folder_name())
                if last_saved and config.cleanup_before_fetch:
                    same_session_identity = last_session == session.session_id
                    reason = (
                        f"Refreshing current session files before new fetch for {session.session_id.folder_name()}"
                        if current_fingerprint == last_session_fingerprint or same_session_identity
                        else f"Deleting paints from previous session {last_session}"
                    )
                    if same_session_identity and current_fingerprint != last_session_fingerprint:
                        logging.info("Session roster changed inside the same session %s, so the paint sync will run again.", session.session_id.folder_name())
                    last_saved = self._cleanup_saved(
                        saved=last_saved,
                        keep_my_livery_locally=config.keep_my_livery_locally,
                        preserve_targets=last_session_preserve_targets,
                        reason=reason,
                        paints_root=paints_dir,
                    )
                    pending_reload = None
                self._set_status(f"Processing {session.session_id.folder_name()}")
                logging.info("Processing session %s", session.session_id.folder_name())
                restored_saved: list[SavedFile] = []
                restored_pack_name: str | None = None
                if replay_mode_active and getattr(config, "auto_manage_replay_packs", True):
                    restored_saved, restored_pack_name = restore_replay_pack_for_session(
                        session=session,
                        paints_root=paints_dir,
                        replay_packs_dir=replay_packs_dir,
                        packs=replay_pack_index,
                    )
                if restored_saved:
                    last_saved = restored_saved
                    session_rows = build_session_driver_rows(
                        session,
                        build_session_final_statuses(
                            session,
                            wanted_items=[],
                            server_saved=restored_saved,
                            fallback_saved=[],
                            sync_my_livery_from_server=config.sync_my_livery_from_server,
                            replay_mode=True,
                        ),
                    )
                    logging.info(
                        "Replay pack '%s' restored for replay session %s with %s file(s)",
                        restored_pack_name or "unknown",
                        session.session_id.folder_name(),
                        len(restored_saved),
                    )
                    monitor_snapshot = ThroughputMonitorSnapshot(
                        session_name=f"{session.session_id.folder_name()} [replay]",
                        worker_mode="replay-pack",
                        saved_items=len(restored_saved),
                    )
                    self._update_runtime_snapshot(current_session, last_saved, last_known_member_id, session_rows=session_rows, replay_mode_active=True)
                else:
                    last_saved, monitor_snapshot, session_rows = process_session(
                        session=session,
                        paints_dir=paints_dir,
                        temp_dir=temp_dir,
                        max_concurrent_manifests=get_manifest_cap_from_download_cap(config.max_concurrent_downloads),
                        max_concurrent_downloads=config.max_concurrent_downloads,
                        download_workers_mode=config.download_workers_mode,
                        manual_download_workers=config.manual_download_workers,
                        manual_manifest_workers=config.manual_manifest_workers,
                        manual_save_workers=config.manual_save_workers,
                        retries=positive_int(config.retries, 3),
                        retry_backoff_seconds=max(config.retry_backoff_seconds, 0.1),
                        sync_my_livery_from_server=config.sync_my_livery_from_server,
                        random_fallback_real_drivers=config.random_fallback_real_drivers,
                        random_fallback_ai=config.random_fallback_ai,
                        keep_tp_paints_in_random_pool=getattr(config, "keep_tp_paints_in_random_pool", True),
                        max_random_pool_gb=getattr(config, "max_random_pool_gb", 5.0),
                        tp_fallback_mode=getattr(config, "tp_fallback_mode", "local"),
                        tp_manifest_member_id_override=getattr(config, "tp_manifest_member_id_override", 0),
                        tp_mule_profile_fast_mode=bool(getattr(config, "tp_mule_profile_fast_mode", False)),
                        tp_detect_showroom_total_pages=bool(getattr(config, "tp_detect_showroom_total_pages", False)),
                        progress_callback=lambda rows, _session=session, _replay=replay_mode_active: self._update_runtime_snapshot(_session, last_saved, last_known_member_id, session_rows=rows, replay_mode_active=_replay),
                    )
                self._update_monitor_snapshot(monitor_snapshot)
                last_session = session.session_id
                last_session_fingerprint = current_fingerprint
                last_session_preserve_targets = _merge_preserve_targets(
                    session.local_preserve_targets(),
                    fallback_member_id=last_known_member_id,
                    fallback_team_id=last_known_team_id,
                )
                self._update_runtime_snapshot(current_session, last_saved, last_known_member_id, session_rows=session_rows, replay_mode_active=replay_mode_active)
                self._set_status(f"Watching • {session.session_id.folder_name()}")
                if last_saved and config.auto_refresh_paints:
                    pending_reload = PendingTextureReload(
                        fingerprint=current_fingerprint,
                        first_requested_at=time.monotonic(),
                    )
                    if sdk_reader is not None and maybe_trigger_pending_texture_reload(
                        reader=sdk_reader,
                        pending_reload=pending_reload,
                        active_fingerprint=last_session_fingerprint,
                    ):
                        pending_reload = None
                else:
                    pending_reload = None
                self._stop_event.wait(max(config.poll_seconds, 0.2))
        finally:
            final_config = self.get_config()
            if last_saved and final_config.delete_downloaded_livery:
                self._cleanup_saved(
                    saved=last_saved,
                    keep_my_livery_locally=final_config.keep_my_livery_locally,
                    preserve_targets=last_session_preserve_targets,
                    reason="Cleaning up session paints before exit",
                    paints_root=paints_dir,
                )
            self._update_runtime_snapshot(None, last_saved if "last_saved" in locals() else [], last_known_member_id if "last_known_member_id" in locals() else None, session_rows=[])
            close_sdk_reader(sdk_reader)
            self._set_status("Stopped")
class WindowsTrayIcon:
    def __init__(self, on_restore: Callable[[], None]) -> None:
        self.on_restore = on_restore
        self._thread: threading.Thread | None = None
        self._ready = threading.Event()
        self._visible = False
        self._started = False
        self._hwnd = None
        self._wndproc = None
        self._class_name = f"NishizumiPaintsTrayWindow_{id(self)}"
        self._tooltip = APP_TOOLTIP
        self._stop_requested = False
        self._icon_handle = None
        self._ctypes = None
        self._NOTIFYICONDATAW = None
        self._shell32 = None
        self._user32 = None
    def is_supported(self) -> bool:
        return sys.platform == "win32"
    def start(self) -> bool:
        if not self.is_supported():
            return False
        if self._thread is not None:
            return self._started
        self._thread = threading.Thread(target=self._message_loop, name="NishizumiPaintsTray", daemon=True)
        self._thread.start()
        self._ready.wait(timeout=2.0)
        return self._started
    def show(self, tooltip: str = APP_TOOLTIP) -> bool:
        self._tooltip = tooltip[:120]
        if not self.start():
            return False
        if self._visible:
            return True
        return self._add_icon()
    def hide(self) -> None:
        if self._started and self._visible:
            self._notify_icon(self._nim_delete())
            self._visible = False
    def stop(self) -> None:
        self.hide()
        if self._started and self._hwnd is not None:
            self._post_close()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        self._thread = None
        self._started = False
    def _message_loop(self) -> None:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        WM_DESTROY = 0x0002
        WM_CLOSE = 0x0010
        WM_APP = 0x8000
        self._wm_trayicon = WM_APP + 1
        self._wm_lbuttonup = 0x0202
        self._wm_lbuttondblclk = 0x0203
        self._wm_rbuttonup = 0x0205
        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", wintypes.DWORD),
                ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD),
                ("Data4", ctypes.c_ubyte * 8),
            ]
        class NOTIFYICONDATAW(ctypes.Structure):
            _fields_ = [
                ("cbSize", wintypes.DWORD),
                ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT),
                ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT),
                ("hIcon", wintypes.HANDLE),
                ("szTip", wintypes.WCHAR * 128),
                ("dwState", wintypes.DWORD),
                ("dwStateMask", wintypes.DWORD),
                ("szInfo", wintypes.WCHAR * 256),
                ("uTimeoutOrVersion", wintypes.UINT),
                ("szInfoTitle", wintypes.WCHAR * 64),
                ("dwInfoFlags", wintypes.DWORD),
                ("guidItem", GUID),
                ("hBalloonIcon", wintypes.HANDLE),
            ]
        self._ctypes = ctypes
        self._NOTIFYICONDATAW = NOTIFYICONDATAW
        self._shell32 = ctypes.windll.shell32
        self._user32 = user32
        self._WM_CLOSE = WM_CLOSE
        LPARAM_T = ctypes.c_ssize_t
        LRESULT_T = ctypes.c_ssize_t
        user32.DefWindowProcW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, LPARAM_T]
        user32.DefWindowProcW.restype = LRESULT_T
        WNDPROCTYPE = ctypes.WINFUNCTYPE(LRESULT_T, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, LPARAM_T)
        def wndproc(hwnd, msg, wparam, lparam):
            if msg == self._wm_trayicon and lparam in (self._wm_lbuttonup, self._wm_lbuttondblclk, self._wm_rbuttonup):
                try:
                    self.on_restore()
                except Exception:
                    pass
                return 0
            if msg == WM_CLOSE:
                user32.DestroyWindow(hwnd)
                return 0
            if msg == WM_DESTROY:
                self.hide()
                user32.PostQuitMessage(0)
                return 0
            return user32.DefWindowProcW(hwnd, msg, wparam, lparam)
        self._wndproc = WNDPROCTYPE(wndproc)
        class WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", WNDPROCTYPE),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HANDLE),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HANDLE),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]
        hinstance = kernel32.GetModuleHandleW(None)
        wndclass = WNDCLASSW()
        wndclass.lpfnWndProc = self._wndproc
        wndclass.lpszClassName = self._class_name
        wndclass.hInstance = hinstance
        atom = user32.RegisterClassW(ctypes.byref(wndclass))
        if not atom and ctypes.GetLastError() != 1410:
            self._ready.set()
            return
        hwnd = user32.CreateWindowExW(
            0,
            self._class_name,
            self._class_name,
            0,
            0,
            0,
            0,
            0,
            0,
            0,
            hinstance,
            0,
        )
        if not hwnd:
            self._ready.set()
            return
        self._hwnd = hwnd
        self._started = True
        self._ready.set()
        msg = wintypes.MSG()
        while user32.GetMessageW(ctypes.byref(msg), 0, 0, 0) != 0:
            user32.TranslateMessage(ctypes.byref(msg))
            user32.DispatchMessageW(ctypes.byref(msg))
        try:
            user32.UnregisterClassW(self._class_name, hinstance)
        except Exception:
            pass
    def _make_nid(self):
        nid = self._NOTIFYICONDATAW()
        nid.cbSize = self._ctypes.sizeof(self._NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = 0x00000001 | 0x00000002 | 0x00000004
        nid.uCallbackMessage = self._wm_trayicon
        nid.hIcon = self._load_tray_icon()
        nid.szTip = self._tooltip
        return nid
    def _load_tray_icon(self):
        if self._icon_handle is not None:
            return self._icon_handle
        try:
            IMAGE_ICON = 1
            LR_LOADFROMFILE = 0x00000010
            LR_DEFAULTSIZE = 0x00000040
            icon_path = str(resource_path(APP_ICON_ICO))
            if os.path.exists(icon_path):
                handle = self._user32.LoadImageW(0, icon_path, IMAGE_ICON, 0, 0, LR_LOADFROMFILE | LR_DEFAULTSIZE)
                if handle:
                    self._icon_handle = handle
                    return handle
        except Exception:
            pass
        self._icon_handle = self._user32.LoadIconW(0, 32512)
        return self._icon_handle
    def _notify_icon(self, message: int) -> bool:
        if self._hwnd is None:
            return False
        nid = self._make_nid()
        return bool(self._shell32.Shell_NotifyIconW(message, self._ctypes.byref(nid)))
    @staticmethod
    def _nim_add() -> int:
        return 0x00000000
    @staticmethod
    def _nim_delete() -> int:
        return 0x00000002
    def _add_icon(self) -> bool:
        ok = self._notify_icon(self._nim_add())
        self._visible = ok
        return ok
    def _post_close(self) -> None:
        self._user32.PostMessageW(self._hwnd, self._WM_CLOSE, 0, 0)
class DownloaderUI:
    def __init__(self, launched_from_autostart: bool = False) -> None:
        import tkinter as tk
        from tkinter import filedialog, messagebox, scrolledtext, simpledialog, ttk
        self.tk = tk
        self.ttk = ttk
        self.messagebox = messagebox
        self.filedialog = filedialog
        self.scrolledtext = scrolledtext
        self.simpledialog = simpledialog
        self.config_store = ConfigStore()
        self.config = self.config_store.load()
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.service = DownloaderService(self.config, self.log_queue)
        self.service.set_status_callback(self._on_service_status)
        self._exiting = False
        self._launched_from_autostart = launched_from_autostart
        self._preview_photo_refs: dict[str, object] = {}
        self._session_row_lookup: dict[str, SessionDriverSnapshot] = {}
        self._last_session_snapshot_signature: tuple | None = None
        self._selected_session_row_iid: str | None = None
        self._session_sort_column: str = "ir"
        self._session_sort_reverse: bool = True
        self._PILImage = None
        self._PILImageDraw = None
        self._PILImageOps = None
        self._PILImageTk = None
        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("1440x760")
        self.root.minsize(1220, 620)
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self._apply_window_icon()
        self.tray_icon = WindowsTrayIcon(lambda: self.root.after(0, self.restore_from_background))
        self.tray_icon.start()
        self.instance_signal_server = SingleInstanceSignalServer(lambda: self.root.after(0, self.bring_to_front))
        self.status_var = tk.StringVar(value="Starting")
        self.auto_start_var = tk.BooleanVar(value=self.config.auto_start)
        self.start_minimized_var = tk.BooleanVar(value=self.config.start_minimized)
        self.minimize_to_tray_var = tk.BooleanVar(value=self.config.minimize_to_tray_on_close)
        self.auto_refresh_var = tk.BooleanVar(value=self.config.auto_refresh_paints)
        self.cleanup_on_exit_var = tk.BooleanVar(value=self.config.delete_downloaded_livery)
        self.cleanup_before_fetch_var = tk.BooleanVar(value=self.config.cleanup_before_fetch)
        self.sync_my_livery_var = tk.BooleanVar(value=self.config.sync_my_livery_from_server)
        self.keep_my_livery_var = tk.BooleanVar(value=self.config.keep_my_livery_locally)
        self.sync_ai_rosters_var = tk.BooleanVar(value=getattr(self.config, "sync_ai_rosters_from_server", True))
        self.random_real_var = tk.BooleanVar(value=getattr(self.config, "random_fallback_real_drivers", True))
        self.random_ai_var = tk.BooleanVar(value=getattr(self.config, "random_fallback_ai", True))
        self.tp_fallback_mode_var = tk.StringVar(value=str(getattr(self.config, "tp_fallback_mode", "online") or "online").strip().lower().title())
        self.keep_tp_pool_var = tk.BooleanVar(value=getattr(self.config, "keep_tp_paints_in_random_pool", True))
        self.random_pool_size_gb_var = tk.DoubleVar(value=clamp_random_pool_gb(getattr(self.config, "max_random_pool_gb", 5.0), 5.0))
        self.random_pool_summary_var = tk.StringVar(value="Random pool: waiting")
        self.tp_auth_profile_summary_var = tk.StringVar(value="Trading Paints login: waiting")
        current_member_id = normalize_tp_member_id(getattr(self.config, "tp_manifest_member_id_override", 0))
        self.tp_manifest_member_id_var = tk.StringVar(value=str(current_member_id) if current_member_id > 0 else "")
        self.tp_manifest_member_id_summary_var = tk.StringVar(value="TP manifest member ID: using your normal local user id from the iRacing session.")
        self.tp_mule_fast_mode_var = tk.BooleanVar(value=bool(getattr(self.config, "tp_mule_profile_fast_mode", False)))
        self.tp_detect_showroom_total_pages_var = tk.BooleanVar(value=bool(getattr(self.config, "tp_detect_showroom_total_pages", False)))
        self.tp_connect_button_var = tk.StringVar(value="Connect Trading Paints")
        self._tp_login_in_progress = False
        self._tp_login_confirm_event: threading.Event | None = None
        self._tp_login_restart_on_success = False
        self._quick_start_nav_refresh: Callable[[], None] | None = None
        self.quick_start_tp_confirm_button = None
        self.quick_start_tp_status_label = None
        self.tp_mode_summary_var = tk.StringVar(value="Choose how missing paints should be filled.")
        self.online_section_state_var = tk.StringVar(value="OFF")
        self.online_section_hint_var = tk.StringVar(value="Saved here for later use.")
        self.local_backup_hint_var = tk.StringVar(value="Local backup pool settings live in General.")
        self.session_summary_var = tk.StringVar(value="No active iRacing session detected yet.")
        self.session_status_summary_var = tk.StringVar(value="Join a session and the driver list will appear here.")
        self.session_selected_title_var = tk.StringVar(value="No driver selected")
        self.session_selected_detail_var = tk.StringVar(value="")
        self.session_all_detail_var = tk.StringVar(value="")
        self.session_car_detail_var = tk.StringVar(value="")
        self.session_driver_detail_var = tk.StringVar(value="")
        self.session_tga_detail_var = tk.StringVar(value="")
        self.show_activity_var = tk.BooleanVar(value=self.config.show_activity_log)
        self.show_tp_monitor_var = tk.BooleanVar(value=getattr(self.config, "show_tp_monitor", False))
        self.check_updates_var = tk.BooleanVar(value=getattr(self.config, "check_updates_automatically", True))
        self.headless_status_var = tk.StringVar(value="Headless mode is recommended for daily use because it skips the live Tk UI redraws and usually uses less CPU and RAM.")
        self.headless_hint_var = tk.StringVar(value="Save your settings here, then switch to headless whenever you want. The GUI can attach to an already-running headless service too.")
        self.download_workers_mode_var = tk.StringVar(value=normalize_download_workers_mode(self.config.download_workers_mode).title())
        self.manual_download_workers_var = tk.IntVar(value=self.config.manual_download_workers)
        self.manual_manifest_workers_var = tk.IntVar(value=self.config.manual_manifest_workers)
        self.manual_save_workers_var = tk.IntVar(value=self.config.manual_save_workers)
        self.verbose_var = tk.BooleanVar(value=self.config.verbose)
        self.tp_monitor_summary_var = tk.StringVar(value="TP worker monitor: waiting for a completed session.")
        self.update_status_var = tk.StringVar(value="Updates: waiting")
        self.tp_monitor_detail_var = tk.StringVar(value="Run a session and the app will estimate the effective Trading Paints parallel allowance from observed throughput.")
        self.tp_monitor_save_var = tk.StringVar(value="Save stage stats will appear here too.")
        self._update_check_in_progress = False
        self._latest_release_info: GitHubReleaseInfo | None = None
        self._last_notified_update_tag: str | None = None
        self._auto_update_after_id = None
        self._random_pool_opt_in_notified = bool(getattr(self.config, "keep_tp_paints_in_random_pool", True))
        self._headless_controller_mode = False
        self._last_pool_stats_refresh_at = 0.0
        self._build_ui()
        try:
            pool_after_bytes, pool_freed_bytes = enforce_random_pool_limit(default_random_pool_dir(), getattr(self.config, "max_random_pool_gb", 5.0))
            if pool_freed_bytes > 0:
                logging.info(
                    "Random TP pool trimmed by %.2f GB during startup to honor the configured limit of %.2f GB",
                    pool_freed_bytes / float(1024 ** 3),
                    clamp_random_pool_gb(getattr(self.config, "max_random_pool_gb", 5.0), 5.0),
                )
            logging.info(
                "Random TP pool startup usage: %.2f GB / %.2f GB",
                pool_after_bytes / float(1024 ** 3),
                clamp_random_pool_gb(getattr(self.config, "max_random_pool_gb", 5.0), 5.0),
            )
        except Exception as exc:
            logging.debug("Random pool size check failed during startup: %s", exc)
        self._update_download_mode_ui()
        self._update_tp_fallback_ui(force=True)
        self._hide_console_window()
        self._apply_autostart(self.config.auto_start)
        if self._attach_to_existing_headless_if_available():
            self._append_log("Attached to a running headless service. This window is acting as a controller only.")
        else:
            self.service.start()
        self.instance_signal_server.start()
        self._update_headless_ui()
        self._update_log_visibility()
        self._update_monitor_visibility()
        self._refresh_random_pool_summary(force=True)
        self._refresh_session_tree()
        self._schedule_update_check(initial=True)
        self.root.after(150, self._drain_logs)
        self.root.after(600, self._poll_service)
        self.root.after(850, self.show_quick_start_if_needed)
        if self.config.start_minimized and self._launched_from_autostart:
            self.root.after(500, self.start_minimized)
    def _apply_window_icon(self) -> None:
        try:
            ico_path = resource_path(APP_ICON_ICO)
            if ico_path.exists():
                self.root.iconbitmap(default=str(ico_path))
                return
        except Exception:
            pass
        try:
            png_path = resource_path(APP_ICON_PNG)
            if png_path.exists():
                self._window_icon_image = self.tk.PhotoImage(file=str(png_path))
                self.root.iconphoto(True, self._window_icon_image)
        except Exception:
            pass
    def _build_ui(self) -> None:
        ttk = self.ttk
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)
        outer = ttk.Frame(root, padding=12)
        outer.grid(sticky="nsew")
        outer.columnconfigure(0, weight=1)
        outer.rowconfigure(1, weight=1, minsize=260)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text=APP_NAME, font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(header, text=f"Version {APP_VERSION}", foreground="#555555").grid(row=0, column=1, sticky="w", padx=(10, 0))
        ttk.Label(header, textvariable=self.status_var, font=("Segoe UI", 10, "bold"), foreground="#0b63b6").grid(row=0, column=2, sticky="e")

        notebook = ttk.Notebook(outer)
        notebook.grid(row=1, column=0, sticky="nsew", pady=(10, 8))
        session_tab = ttk.Frame(notebook, padding=10)
        general_tab = ttk.Frame(notebook, padding=10)
        ai_tab = ttk.Frame(notebook, padding=10)
        random_tab = ttk.Frame(notebook, padding=10)
        logs_tab = ttk.Frame(notebook, padding=10)
        notebook.add(session_tab, text="Session")
        notebook.add(general_tab, text="General")
        notebook.add(ai_tab, text="AI")
        notebook.add(random_tab, text="Random")
        notebook.add(logs_tab, text="Logs")
        notebook.select(general_tab)

        session_tab.columnconfigure(0, weight=1)
        session_tab.rowconfigure(1, weight=1)
        session_info = ttk.LabelFrame(session_tab, text="Current session", padding=10)
        session_info.grid(row=0, column=0, sticky="ew")
        session_info.columnconfigure(0, weight=1)
        ttk.Label(session_info, textvariable=self.session_summary_var, justify="left").grid(row=0, column=0, sticky="w")
        ttk.Label(session_info, textvariable=self.session_status_summary_var, justify="left", foreground="#555555").grid(row=1, column=0, sticky="w", pady=(4, 0))

        driver_list_frame = ttk.LabelFrame(session_tab, text="Drivers in session", padding=8)
        driver_list_frame.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        driver_list_frame.columnconfigure(0, weight=1)
        driver_list_frame.rowconfigure(0, weight=1)
        self.session_tree = ttk.Treeview(driver_list_frame, columns=("state", "num", "ir", "lic", "sr", "name"), show="headings", height=18)
        self.session_tree.heading("state", text="State", command=lambda: self.on_session_heading_clicked("state"))
        self.session_tree.heading("num", text="#", command=lambda: self.on_session_heading_clicked("num"))
        self.session_tree.heading("ir", text="iR", command=lambda: self.on_session_heading_clicked("ir"))
        self.session_tree.heading("lic", text="Lic", command=lambda: self.on_session_heading_clicked("lic"))
        self.session_tree.heading("sr", text="SR", command=lambda: self.on_session_heading_clicked("sr"))
        self.session_tree.heading("name", text="Name", command=lambda: self.on_session_heading_clicked("name"))
        self.session_tree.column("state", width=170, minwidth=156, anchor="center", stretch=False)
        self.session_tree.column("num", width=54, minwidth=48, anchor="center", stretch=False)
        self.session_tree.column("ir", width=84, minwidth=74, anchor="e", stretch=False)
        self.session_tree.column("lic", width=54, minwidth=48, anchor="center", stretch=False)
        self.session_tree.column("sr", width=62, minwidth=56, anchor="center", stretch=False)
        self.session_tree.column("name", width=300, minwidth=230, anchor="w", stretch=False)
        session_tree_scroll = ttk.Scrollbar(driver_list_frame, orient="vertical", command=self.session_tree.yview)
        self.session_tree.configure(yscrollcommand=session_tree_scroll.set)
        self.session_tree.grid(row=0, column=0, sticky="nsew")
        session_tree_scroll.grid(row=0, column=1, sticky="ns")
        for tag_name, color in {
            "queued": "#6a6a6a",
            "downloading": "#0b63b6",
            "downloaded": "#176d2b",
            "replay": "#6d3ca6",
            "fallback": "#a06a00",
            "fallback_local": "#a06a00",
            "fallback_online": "#7a3fb0",
            "missing": "#9a2020",
            "skipped": "#555555",
        }.items():
            self.session_tree.tag_configure(tag_name, foreground=color)

        general_tab.columnconfigure(0, weight=1)
        general_settings = ttk.Frame(general_tab)
        general_settings.grid(row=0, column=0, sticky="ew")
        general_settings.columnconfigure(0, weight=1)
        general_settings.columnconfigure(1, weight=0)
        prefs = ttk.LabelFrame(general_settings, text="Settings", padding=10)
        prefs.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        perf = ttk.LabelFrame(general_settings, text="Downloads", padding=10)
        perf.grid(row=0, column=1, sticky="nsew")
        prefs.columnconfigure(0, weight=1)
        prefs.columnconfigure(1, weight=1)
        ttk.Label(prefs, text="General", font=("Segoe UI", 9, "bold"), foreground="#0b63b6").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(prefs, text="Auto start", variable=self.auto_start_var, command=self.on_setting_changed).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(prefs, text="Start minimized", variable=self.start_minimized_var, command=self.on_setting_changed).grid(row=1, column=1, sticky="w", padx=(12, 0))
        ttk.Checkbutton(prefs, text="Keep running in background on close", variable=self.minimize_to_tray_var, command=self.on_setting_changed).grid(row=2, column=0, sticky="w")
        ttk.Checkbutton(prefs, text="Auto refresh paints", variable=self.auto_refresh_var, command=self.on_setting_changed).grid(row=2, column=1, sticky="w", padx=(12, 0))
        ttk.Checkbutton(prefs, text="Check for updates automatically", variable=self.check_updates_var, command=self.on_setting_changed).grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))
        ttk.Separator(prefs, orient="horizontal").grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 8))
        ttk.Label(prefs, text="Session", font=("Segoe UI", 9, "bold"), foreground="#0b63b6").grid(row=5, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(prefs, text="Update my own paints", variable=self.sync_my_livery_var, command=self.on_setting_changed).grid(row=6, column=0, sticky="w")
        ttk.Checkbutton(prefs, text="Keep my livery locally", variable=self.keep_my_livery_var, command=self.on_setting_changed).grid(row=6, column=1, sticky="w", padx=(12, 0))
        ttk.Checkbutton(prefs, text="Delete live session paints", variable=self.cleanup_on_exit_var, command=self.on_setting_changed).grid(row=7, column=0, sticky="w")

        perf.columnconfigure(1, weight=1)
        ttk.Label(perf, text="Worker mode").grid(row=0, column=0, sticky="w")
        mode_combo = ttk.Combobox(perf, state="readonly", values=["Auto", "Manual"], width=10, textvariable=self.download_workers_mode_var)
        mode_combo.grid(row=0, column=1, sticky="ew")
        mode_combo.bind("<<ComboboxSelected>>", lambda _e: self.on_download_workers_mode_changed())
        ttk.Label(perf, text="Manual manifests").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.manual_manifest_workers_spin = ttk.Spinbox(perf, from_=1, to=100, width=5, textvariable=self.manual_manifest_workers_var, command=self.on_manual_manifest_workers_changed)
        self.manual_manifest_workers_spin.grid(row=1, column=1, sticky="w", pady=(8, 0))
        self.manual_manifest_workers_spin.bind("<FocusOut>", lambda _e: self.on_manual_manifest_workers_changed())
        self.manual_manifest_workers_spin.bind("<Return>", lambda _e: self.on_manual_manifest_workers_changed())
        ttk.Label(perf, text="Manual downloads").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.manual_workers_spin = ttk.Spinbox(perf, from_=1, to=100, width=5, textvariable=self.manual_download_workers_var, command=self.on_manual_download_workers_changed)
        self.manual_workers_spin.grid(row=2, column=1, sticky="w", pady=(6, 0))
        self.manual_workers_spin.bind("<FocusOut>", lambda _e: self.on_manual_download_workers_changed())
        self.manual_workers_spin.bind("<Return>", lambda _e: self.on_manual_download_workers_changed())
        ttk.Label(perf, text="Manual saves").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.manual_save_workers_spin = ttk.Spinbox(perf, from_=1, to=100, width=5, textvariable=self.manual_save_workers_var, command=self.on_manual_save_workers_changed)
        self.manual_save_workers_spin.grid(row=3, column=1, sticky="w", pady=(6, 0))
        self.manual_save_workers_spin.bind("<FocusOut>", lambda _e: self.on_manual_save_workers_changed())
        self.manual_save_workers_spin.bind("<Return>", lambda _e: self.on_manual_save_workers_changed())
        ttk.Label(perf, text="Auto = adaptive workers • Manual = fixed manifests, downloads, and saves for every session (1-100)", foreground="#666666", wraplength=320, justify="left").grid(row=4, column=0, columnspan=2, sticky="w", pady=(8, 0))

        general_actions = ttk.LabelFrame(general_tab, text="Actions", padding=10)
        general_actions.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(general_actions, text="Clear downloaded", command=self.clear_downloaded_now).pack(side="left")
        ttk.Button(general_actions, text="Refresh paints", command=self.redownload_now).pack(side="left", padx=(8, 0))
        ttk.Button(general_actions, text="Paint folder", command=self.open_paint_folder).pack(side="left", padx=(8, 0))
        ttk.Button(general_actions, text="Check updates", command=self.check_updates_now).pack(side="left", padx=(8, 0))

        self.local_pool_frame = ttk.LabelFrame(general_tab, text="Local random paints pool", padding=10)
        self.local_pool_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.local_pool_frame.columnconfigure(0, weight=1)
        self.local_pool_frame.columnconfigure(3, weight=1)
        ttk.Label(self.local_pool_frame, text="Keeps extra local paints the app can reuse later when a driver or AI has no TP paint. This still matters even if you prefer Online.", foreground="#176d2b", justify="left", wraplength=920).grid(row=0, column=0, columnspan=4, sticky="w")
        ttk.Checkbutton(self.local_pool_frame, text="Recycle downloaded TP car paints into the local random pool", variable=self.keep_tp_pool_var, command=self.on_setting_changed).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(self.local_pool_frame, text="Max size (GB)").grid(row=1, column=2, sticky="e", pady=(8, 0), padx=(12, 6))
        self.random_pool_size_spin = ttk.Spinbox(self.local_pool_frame, from_=1, to=500, increment=1, width=6, textvariable=self.random_pool_size_gb_var, command=self.on_random_pool_size_changed)
        self.random_pool_size_spin.grid(row=1, column=3, sticky="w", pady=(8, 0))
        self.random_pool_size_spin.bind("<FocusOut>", lambda _e: self.on_random_pool_size_changed())
        self.random_pool_size_spin.bind("<Return>", lambda _e: self.on_random_pool_size_changed())
        ttk.Label(self.local_pool_frame, textvariable=self.random_pool_summary_var, justify="left", foreground="#555555").grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0))
        local_pool_actions = ttk.Frame(self.local_pool_frame)
        local_pool_actions.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(10, 0))
        ttk.Button(local_pool_actions, text="Open pool", command=self.open_random_pool_folder).pack(side="left")
        ttk.Button(local_pool_actions, text="Clean pool now", command=self.clean_random_pool_now).pack(side="left", padx=(8, 0))
        ttk.Button(local_pool_actions, text="Rebuild from current files", command=self.rebuild_random_pool_now).pack(side="left", padx=(8, 0))

        ai_tab.columnconfigure(0, weight=1)
        ai_tab.columnconfigure(1, weight=1)
        ai_sync = ttk.LabelFrame(ai_tab, text="AI sync", padding=10)
        ai_sync.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        ttk.Checkbutton(ai_sync, text="Sync TP AI rosters", variable=self.sync_ai_rosters_var, command=self.on_setting_changed).pack(anchor="w")
        ttk.Label(ai_sync, text="Keeps Trading Paints AI rosters ready for copy and import actions.", foreground="#555555", justify="left", wraplength=360).pack(anchor="w", pady=(6, 0))
        ai_actions = ttk.LabelFrame(ai_tab, text="AI actions", padding=10)
        ai_actions.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        ttk.Button(ai_actions, text="Sync AI rosters", command=self.sync_ai_rosters_now).pack(fill="x")
        ttk.Button(ai_actions, text="Randomize active AI roster", command=self.randomize_active_ai_roster).pack(fill="x", pady=(6, 0))
        ttk.Button(ai_actions, text="Clone active AI roster", command=self.clone_active_ai_roster).pack(fill="x", pady=(6, 0))
        ttk.Button(ai_actions, text="Copy my car to AI", command=self.copy_my_current_car_to_ai).pack(fill="x", pady=(6, 0))
        ttk.Button(ai_actions, text="Copy session cars to AI", command=self.copy_session_cars_to_ai).pack(fill="x", pady=(6, 0))
        ai_folders = ttk.LabelFrame(ai_tab, text="Folders", padding=10)
        ai_folders.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        ai_folder_row = ttk.Frame(ai_folders)
        ai_folder_row.pack(fill="x")
        ttk.Button(ai_folder_row, text="AI rosters", command=self.open_ai_rosters_folder).pack(side="left")
        ttk.Button(ai_folder_row, text="AI livery folder", command=self.open_ai_livery_folder).pack(side="left", padx=(8, 0))

        random_tab.columnconfigure(0, weight=1)
        random_top = ttk.LabelFrame(random_tab, text="Step 1 • Who should get fallback paints?", padding=10)
        random_top.grid(row=0, column=0, sticky="ew")
        ttk.Label(random_top, text="Choose who should receive a random fallback paint when Trading Paints has nothing for them.", foreground="#0b63b6", justify="left", wraplength=920).pack(anchor="w")
        target_row = ttk.Frame(random_top)
        target_row.pack(anchor="w", pady=(8, 0))
        ttk.Checkbutton(target_row, text="Fallback for drivers without a TP paint", variable=self.random_real_var, command=self.on_random_fallback_targets_changed).pack(side="left")
        ttk.Checkbutton(target_row, text="Fallback for AI drivers without a TP paint", variable=self.random_ai_var, command=self.on_random_fallback_targets_changed).pack(side="left", padx=(16, 0))

        self.source_pref_frame = ttk.LabelFrame(random_tab, text="Step 2 • Preferred source", padding=10)
        self.source_pref_frame.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        source_row = ttk.Frame(self.source_pref_frame)
        source_row.pack(anchor="w")
        ttk.Radiobutton(source_row, text="Local", value="Local", variable=self.tp_fallback_mode_var, command=self.on_tp_fallback_mode_changed).pack(side="left")
        ttk.Radiobutton(source_row, text="Online", value="Online", variable=self.tp_fallback_mode_var, command=self.on_tp_fallback_mode_changed).pack(side="left", padx=(12, 0))
        self.tp_mode_summary_label = ttk.Label(self.source_pref_frame, textvariable=self.tp_mode_summary_var, justify="left", wraplength=920, foreground="#555555")
        self.tp_mode_summary_label.pack(anchor="w", pady=(8, 0))

        local_note_frame = ttk.LabelFrame(random_tab, text="Local backup", padding=10)
        local_note_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(local_note_frame, textvariable=self.local_backup_hint_var, foreground="#176d2b", justify="left", wraplength=920).pack(anchor="w")

        self.online_mode_frame = ttk.LabelFrame(random_tab, text="Step 3 • Online Trading Paints", padding=10)
        self.online_mode_frame.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        self.online_mode_frame.columnconfigure(0, weight=1)
        self.online_mode_frame.columnconfigure(1, weight=1)
        online_header = ttk.Frame(self.online_mode_frame)
        online_header.grid(row=0, column=0, columnspan=2, sticky="ew")
        online_header.columnconfigure(0, weight=1)
        ttk.Label(online_header, text="Online Trading Paints", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        self.online_state_label = ttk.Label(online_header, textvariable=self.online_section_state_var, font=("Segoe UI", 10, "bold"), foreground="#b00020")
        self.online_state_label.grid(row=0, column=1, sticky="e")
        self.online_state_hint_label = ttk.Label(online_header, textvariable=self.online_section_hint_var, foreground="#555555", justify="left", wraplength=920)
        self.online_state_hint_label.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        online_left = ttk.Frame(self.online_mode_frame)
        online_left.grid(row=1, column=0, sticky="nsew", pady=(10, 0), padx=(0, 10))
        online_left.columnconfigure(0, weight=1)
        ttk.Label(online_left, textvariable=self.tp_auth_profile_summary_var, justify="left", foreground="#555555", wraplength=360).grid(row=0, column=0, sticky="w")
        online_login_row = ttk.Frame(online_left)
        online_login_row.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        self.tp_connect_button = ttk.Button(online_login_row, textvariable=self.tp_connect_button_var, command=self.connect_tp_login)
        self.tp_connect_button.pack(side="left")
        self.tp_confirm_button = ttk.Button(online_login_row, text="I logged in", command=self.confirm_tp_login)
        self.tp_confirm_button.pack(side="left", padx=(8, 0))
        online_left_actions = ttk.Frame(online_left)
        online_left_actions.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(online_left_actions, text="Showroom", command=self.open_tp_showroom).pack(side="left")
        ttk.Button(online_left_actions, text="Auth profile", command=self.open_tp_auth_profile).pack(side="left", padx=(8, 0))
        online_right = ttk.Frame(self.online_mode_frame)
        online_right.grid(row=1, column=1, sticky="nsew", pady=(10, 0), padx=(10, 0))
        online_right.columnconfigure(0, weight=1)
        ttk.Label(online_right, text="TP manifest member ID override", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(online_right, text="Use this only when the Trading Paints account in the app is not the same iRacing user you are racing with.", justify="left", foreground="#555555", wraplength=430).grid(row=1, column=0, sticky="w", pady=(4, 0))
        member_row = ttk.Frame(online_right)
        member_row.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        member_row.columnconfigure(0, weight=1)
        self.tp_manifest_member_id_entry = ttk.Entry(member_row, textvariable=self.tp_manifest_member_id_var)
        self.tp_manifest_member_id_entry.grid(row=0, column=0, sticky="ew")
        self.tp_manifest_member_id_entry.bind("<Return>", lambda _e: self.save_tp_manifest_member_id())
        self.tp_manifest_member_id_entry.bind("<FocusOut>", lambda _e: self._refresh_tp_manifest_member_id_summary())
        ttk.Button(member_row, text="OK", command=self.save_tp_manifest_member_id).grid(row=0, column=1, sticky="e", padx=(8, 0))
        ttk.Label(online_right, textvariable=self.tp_manifest_member_id_summary_var, justify="left", foreground="#555555", wraplength=430).grid(row=3, column=0, sticky="w", pady=(6, 0))
        ttk.Checkbutton(online_right, text="Use TP mule fast mode for this profile", variable=self.tp_mule_fast_mode_var, command=self.on_setting_changed).grid(row=4, column=0, sticky="w", pady=(10, 0))
        ttk.Label(online_right, text="Recommended only for a secondary TP account used as a paint mule.", justify="left", foreground="#555555", wraplength=430).grid(row=5, column=0, sticky="w", pady=(4, 0))
        ttk.Checkbutton(online_right, text="Detect showroom total pages (slower)", variable=self.tp_detect_showroom_total_pages_var, command=self.on_setting_changed).grid(row=6, column=0, sticky="w", pady=(10, 0))
        ttk.Label(online_right, text="Optional. Detect the real total page count, then pick random pages from that real range.", justify="left", foreground="#555555", wraplength=430).grid(row=7, column=0, sticky="w", pady=(4, 0))

        logs_tab.columnconfigure(0, weight=1)
        logs_tab.rowconfigure(3, weight=1)
        logs_toolbar = ttk.LabelFrame(logs_tab, text="Log options", padding=10)
        logs_toolbar.grid(row=0, column=0, sticky="ew")
        ttk.Checkbutton(logs_toolbar, text="Show activity", variable=self.show_activity_var, command=self.on_setting_changed).pack(side="left")
        ttk.Checkbutton(logs_toolbar, text="Verbose logs", variable=self.verbose_var, command=self.on_setting_changed).pack(side="left", padx=(12, 0))
        ttk.Checkbutton(logs_toolbar, text="Show TP monitor", variable=self.show_tp_monitor_var, command=self.on_setting_changed).pack(side="left", padx=(12, 0))
        ttk.Button(logs_toolbar, text="Export log", command=self.export_log).pack(side="right")
        ttk.Button(logs_toolbar, text="Reset app settings", command=self.reset_program_config).pack(side="right", padx=(0, 8))
        ttk.Label(logs_tab, text="Reset app settings deletes the saved settings file and restarts the app with defaults.", foreground="#b00020", justify="left").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.monitor_frame = ttk.LabelFrame(logs_tab, text="TP worker monitor", padding=8)
        self.monitor_frame.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        self.monitor_frame.columnconfigure(0, weight=1)
        ttk.Label(self.monitor_frame, textvariable=self.tp_monitor_summary_var, justify="left").grid(row=0, column=0, sticky="w")
        ttk.Label(self.monitor_frame, textvariable=self.tp_monitor_detail_var, justify="left").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(self.monitor_frame, textvariable=self.tp_monitor_save_var, justify="left").grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Button(self.monitor_frame, text="Reset TP monitor", command=self.reset_tp_monitor).grid(row=0, column=1, rowspan=3, sticky="ns", padx=(12, 0))
        self.log_frame = ttk.LabelFrame(logs_tab, text="Activity", padding=8)
        self.log_frame.grid(row=3, column=0, sticky="nsew", pady=(10, 0))
        self.log_frame.columnconfigure(0, weight=1)
        self.log_frame.rowconfigure(0, weight=1)
        self.log_text = self.scrolledtext.ScrolledText(self.log_frame, height=10, wrap="word", font=("Consolas", 9))
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.insert("end", f"{APP_NAME} {APP_VERSION} ready.\n")
        self.log_text.configure(state="disabled")

        footer = ttk.Frame(outer)
        footer.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(footer, text="Always active while open", foreground="#555555").pack(side="left")
        ttk.Label(footer, textvariable=self.update_status_var).pack(side="right", padx=(0, 12))
        ttk.Label(footer, text=f"Version: {APP_VERSION}").pack(side="right")

    def _session_row_iid(self, row: SessionDriverSnapshot) -> str:
        return f"{row.target_kind}:{row.target_id}:{row.directory.lower()}"
    def _session_snapshot_signature(self, snapshot: RuntimeSnapshot) -> tuple:
        session_label = snapshot.current_session.session_id.folder_name() if snapshot.current_session is not None else ""
        rows_sig = tuple(
            (
                row.target_kind,
                row.target_id,
                row.directory.lower(),
                row.display_name,
                row.number,
                row.irating,
                row.license_label,
                row.safety_rating,
                row.status_code,
            )
            for row in snapshot.session_rows
        )
        return (session_label, bool(getattr(snapshot, "replay_mode_active", False)), rows_sig)
    def _format_session_driver_name(self, row: SessionDriverSnapshot) -> str:
        return f"{row.display_name} [AI]" if row.is_ai else row.display_name
    def _session_status_sort_key(self, row: SessionDriverSnapshot) -> tuple[int, str]:
        order = {
            "downloading": 0,
            "downloaded": 1,
            "fallback_online": 2,
            "fallback_local": 3,
            "fallback": 4,
            "replay": 5,
            "missing": 6,
            "skipped": 7,
            "queued": 8,
        }
        return (order.get(row.status_code, 99), row.status_text.lower())
    def _session_license_sort_key(self, row: SessionDriverSnapshot) -> tuple[int, str]:
        label = str(row.license_label or "-").strip().upper()
        base = label[:1] if label else "-"
        order = {"A": 0, "B": 1, "C": 2, "D": 3, "R": 4, "P": 5, "WC": 6, "-": 99}
        return (order.get(base, 98), label)
    def _session_sr_sort_key(self, row: SessionDriverSnapshot) -> tuple[int, float]:
        text = str(row.safety_rating or "").strip()
        try:
            return (0, float(text.replace(",", ".")))
        except Exception:
            return (1, -1.0)
    def _session_rows_sorted(self, rows: list[SessionDriverSnapshot]) -> list[SessionDriverSnapshot]:
        column = getattr(self, "_session_sort_column", "ir")
        reverse = bool(getattr(self, "_session_sort_reverse", False))
        if column == "state":
            key_fn = self._session_status_sort_key
        elif column == "num":
            key_fn = lambda row: _session_driver_sort_number(row.number)
        elif column == "ir":
            key_fn = lambda row: (-1 if row.irating is None else 0, int(row.irating or -1), self._format_session_driver_name(row).lower())
        elif column == "lic":
            key_fn = self._session_license_sort_key
        elif column == "sr":
            key_fn = self._session_sr_sort_key
        else:
            key_fn = lambda row: self._format_session_driver_name(row).lower()
        return sorted(rows, key=key_fn, reverse=reverse)
    def on_session_heading_clicked(self, column: str) -> None:
        column = str(column or "name").strip().lower()
        if self._session_sort_column == column:
            self._session_sort_reverse = not self._session_sort_reverse
        else:
            self._session_sort_column = column
            self._session_sort_reverse = column in {"ir", "sr"}
        self._last_session_snapshot_signature = None
        self._refresh_session_tree()
    def _format_irating_text(self, value: int | None) -> str:
        return "-" if value is None or value <= 0 else f"{int(value):,}"
    def _current_session_row(self) -> SessionDriverSnapshot | None:
        if not self._selected_session_row_iid:
            return None
        return self._session_row_lookup.get(self._selected_session_row_iid)
    def _refresh_session_tree(self) -> None:
        snapshot = self.service.get_runtime_snapshot()
        signature = self._session_snapshot_signature(snapshot)
        if signature == self._last_session_snapshot_signature:
            return
        self._last_session_snapshot_signature = signature
        rows = self._session_rows_sorted(list(snapshot.session_rows))
        self._session_row_lookup = {}
        selected = self._selected_session_row_iid
        self.session_tree.delete(*self.session_tree.get_children())
        if snapshot.current_session is None or not rows:
            self.session_summary_var.set("No active iRacing session detected yet.")
            self.session_status_summary_var.set("Join a session and the driver list will appear here.")
            self._selected_session_row_iid = None
            return
        session_name = snapshot.current_session.track_display_name or snapshot.current_session.track_name or snapshot.current_session.session_id.folder_name()
        replay_suffix = " • replay pack" if getattr(snapshot, "replay_mode_active", False) else ""
        self.session_summary_var.set(
            f"Session {snapshot.current_session.session_id.folder_name()} • {session_name}{replay_suffix} • drivers {len(rows)}"
        )
        counts = Counter(row.status_code for row in rows)
        summary_bits = []
        for code in ("downloaded", "replay", "downloading", "fallback_online", "fallback_local", "fallback", "missing", "skipped"):
            if counts.get(code):
                summary_bits.append(f"{_session_status_meta(code)[1]} {counts[code]}")
        self.session_status_summary_var.set(" • ".join(summary_bits) if summary_bits else "No paint activity yet.")
        for row in rows:
            iid = self._session_row_iid(row)
            self._session_row_lookup[iid] = row
            values = (
                f"{row.status_icon} {row.status_text}",
                row.number,
                self._format_irating_text(row.irating),
                row.license_label,
                row.safety_rating,
                self._format_session_driver_name(row),
            )
            self.session_tree.insert("", "end", iid=iid, values=values, tags=(row.status_code,))
        if selected not in self._session_row_lookup:
            selected = next(iter(self._session_row_lookup.keys()), None)
        self._selected_session_row_iid = selected
        if selected:
            self.session_tree.selection_set(selected)
            self.session_tree.focus(selected)
            self.session_tree.see(selected)
    def on_session_driver_selected(self, _event=None) -> None:
        selection = self.session_tree.selection()
        self._selected_session_row_iid = selection[0] if selection else None
    def refresh_session_preview(self, snapshot: RuntimeSnapshot | None = None) -> None:
        return
    def export_session_preview(self) -> None:
        self._append_log('Session preview export was removed from this lightweight build.')
    def _append_log(self, line: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        total_lines = int(self.log_text.index("end-1c").split(".")[0])
        if total_lines > 2000:
            self.log_text.delete("1.0", f"{max(1, total_lines - 1500)}.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
    def _drain_logs(self) -> None:
        appended = 0
        try:
            while appended < 300:
                line = self.log_queue.get_nowait()
                self._append_log(line)
                appended += 1
        except queue.Empty:
            pass
        if not self._exiting:
            self.root.after(200, self._drain_logs)
    def _refresh_monitor_ui(self) -> None:
        snapshot = self.service.get_monitor_snapshot()
        if snapshot.updated_at <= 0.0 or snapshot.queued_items <= 0:
            self.tp_monitor_summary_var.set("TP worker monitor: waiting for a completed session.")
            self.tp_monitor_detail_var.set("Run a session and the app will estimate the effective Trading Paints parallel allowance from observed throughput.")
            self.tp_monitor_save_var.set("Save stage stats will appear here too.")
            return
        self.tp_monitor_summary_var.set(
            f"Last session {snapshot.session_name} • mode {snapshot.worker_mode} • requested workers: manifests {snapshot.manifest_workers}, downloads {snapshot.download_workers}, saves {snapshot.save_workers} • files {snapshot.downloaded_items}/{snapshot.queued_items}"
        )
        self.tp_monitor_detail_var.set(
            f"Downloads: {snapshot.download_stage_seconds:.2f}s • {snapshot.download_files_per_second:.2f} files/s • avg file {snapshot.average_download_seconds:.2f}s • avg rate {snapshot.average_download_mbps:.1f} Mbps • effective parallelism {snapshot.effective_parallelism:.1f} • {snapshot.ceiling_hint}"
        )
        self.tp_monitor_save_var.set(
            f"Saves: {snapshot.save_stage_seconds:.2f}s • {snapshot.save_files_per_second:.2f} files/s • avg file {snapshot.average_save_seconds:.2f}s • best observed effective parallelism {snapshot.best_effective_parallelism:.1f} • best observed download rate {snapshot.best_download_files_per_second:.2f} files/s"
        )
    def _refresh_tp_auth_profile_summary(self, force: bool = False) -> None:
        profile_dir = default_tp_showroom_profile_dir()
        profile_dir.mkdir(parents=True, exist_ok=True)
        file_count = 0
        try:
            file_count = sum(1 for child in profile_dir.rglob("*") if child.is_file())
        except Exception:
            file_count = 0
        status = read_tp_login_status(profile_dir)
        confirmed = is_tp_login_confirmed(profile_dir)
        if getattr(self, "_tp_login_in_progress", False):
            self.tp_auth_profile_summary_var.set("Trading Paints login browser is open. Finish the site login there, then click 'I logged in' here.")
            self.tp_connect_button_var.set("Login window open...")
        elif confirmed:
            updated_at = float(status.get("updated_at") or 0.0)
            when_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(updated_at)) if updated_at > 0 else "saved"
            self.tp_auth_profile_summary_var.set(f"Trading Paints account connected ✓ • profile files: {file_count} • last confirmed: {when_text}")
            self.tp_connect_button_var.set("Trading Paints connected ✓")
        else:
            message = str(status.get("message") or "").strip()
            if message:
                self.tp_auth_profile_summary_var.set(f"Trading Paints login not confirmed yet • {message}")
            else:
                self.tp_auth_profile_summary_var.set(f"Trading Paints login not confirmed yet • profile files: {file_count}")
            self.tp_connect_button_var.set("Connect Trading Paints")
        try:
            self.tp_connect_button.state(["disabled"] if getattr(self, "_tp_login_in_progress", False) else ["!disabled"])
            self.tp_confirm_button.state(["!disabled"] if getattr(self, "_tp_login_in_progress", False) else ["disabled"])
        except Exception:
            pass
        try:
            if self.quick_start_tp_confirm_button is not None:
                self.quick_start_tp_confirm_button.state(["!disabled"] if getattr(self, "_tp_login_in_progress", False) else ["disabled"])
            if self.quick_start_tp_status_label is not None:
                self.quick_start_tp_status_label.configure(foreground="#176d2b" if confirmed else ("#0b63b6" if getattr(self, "_tp_login_in_progress", False) else "#555555"))
        except Exception:
            pass
        try:
            if callable(self._quick_start_nav_refresh):
                self._quick_start_nav_refresh()
        except Exception:
            logging.debug("Could not refresh quick start navigation state", exc_info=True)

    def _parse_tp_manifest_member_id_ui(self) -> int:
        return normalize_tp_member_id(self.tp_manifest_member_id_var.get())

    def _refresh_tp_manifest_member_id_summary(self) -> None:
        override_id = self._parse_tp_manifest_member_id_ui()
        if override_id > 0:
            self.tp_manifest_member_id_summary_var.set(
                f"TP manifest member ID override active: {override_id}. Online fallback will poll fetch_user for this member instead of your local iRacing user id."
            )
        else:
            self.tp_manifest_member_id_summary_var.set(
                "TP manifest member ID: using your normal local user id from the iRacing session."
            )

    def save_tp_manifest_member_id(self) -> None:
        member_id = self._parse_tp_manifest_member_id_ui()
        self.tp_manifest_member_id_var.set(str(member_id) if member_id > 0 else "")
        self._refresh_tp_manifest_member_id_summary()
        self.on_setting_changed()
        if member_id > 0:
            self._append_log(f"Trading Paints manifest member ID override saved: {member_id}")
        else:
            self._append_log("Trading Paints manifest member ID override cleared. The app will use the normal local user id again.")

    def _update_tp_fallback_ui(self, force: bool = False) -> None:
        mode = str(self.tp_fallback_mode_var.get() or "Local").strip().lower()
        has_any_targets = bool(self.random_real_var.get() or self.random_ai_var.get())
        self._refresh_tp_manifest_member_id_summary()
        try:
            if has_any_targets:
                self.source_pref_frame.grid()
            else:
                self.source_pref_frame.grid_remove()
        except Exception:
            pass
        if has_any_targets and mode == "online":
            self.online_section_state_var.set("ON")
            self.online_section_hint_var.set("Online is active. The app will try the TP showroom first and can still fall back to the local pool if needed.")
            self.local_backup_hint_var.set("Local backup still stays available. Pool settings live in General.")
            self.tp_mode_summary_var.set("Online first. Local backup can still help if the showroom path does not provide a usable paint.")
            try:
                self.online_state_label.configure(foreground="#176d2b")
                self.online_state_hint_label.configure(foreground="#555555")
                self.tp_mode_summary_label.configure(foreground="#176d2b")
            except Exception:
                pass
        elif has_any_targets:
            self.online_section_state_var.set("OFF")
            self.online_section_hint_var.set("Saved for later use only. These online settings apply when Online is selected above.")
            self.local_backup_hint_var.set("Local mode is active. The app will use the local random paints pool from General.")
            self.tp_mode_summary_var.set("Local is active right now. The online tools below are still configurable, but they are not being used.")
            try:
                self.online_state_label.configure(foreground="#b00020")
                self.online_state_hint_label.configure(foreground="#555555")
                self.tp_mode_summary_label.configure(foreground="#0b63b6")
            except Exception:
                pass
        else:
            self.online_section_state_var.set("OFF")
            self.online_section_hint_var.set("Turn on at least one fallback target above to use random fallback paints.")
            self.local_backup_hint_var.set("Fallback is currently disabled for both real drivers and AI.")
            self.tp_mode_summary_var.set("Enable a fallback checkbox above to choose Local or Online.")
            try:
                self.online_state_label.configure(foreground="#b00020")
                self.online_state_hint_label.configure(foreground="#b00020")
                self.tp_mode_summary_label.configure(foreground="#555555")
            except Exception:
                pass
        self._refresh_tp_auth_profile_summary(force=force)

    def restart_app(self, reason: str = "", save_current: bool = True, launch_args: list[str] | None = None) -> None:
        if reason:
            self._append_log(reason)
        if save_current:
            self.config = self._read_ui_config()
            self.config_store.save(self.config)
        argv = build_self_launch_command(*(launch_args if launch_args is not None else ["--gui"]))
        self._exiting = True
        try:
            try:
                if self._headless_controller_mode:
                    send_headless_control_command("stop")
                    for _ in range(20):
                        time.sleep(0.15)
                        if not is_headless_service_available():
                            break
            except Exception:
                logging.debug("Could not stop headless service during restart", exc_info=True)
            self.instance_signal_server.stop()
            self.tray_icon.stop()
            self.service.stop(join_timeout=2.0)
            try:
                self.root.update_idletasks()
            except Exception:
                pass
            self.root.destroy()
        finally:
            os.execv(argv[0], argv)

    def on_random_fallback_targets_changed(self) -> None:
        self._update_tp_fallback_ui(force=True)
        self.on_setting_changed()

    def _confirm_keep_local_fallback(self, parent=None) -> bool:
        message = (
            "Online is recommended because it usually gives much better paint variety, and it can still fall back to the local pool if an online step fails.\n\n"
            "Do you still want to keep Local as the preferred source?\n\n"
            "Yes = keep Local\n"
            "No = switch back to Online"
        )
        try:
            return bool(self.messagebox.askyesno(APP_NAME, message, parent=parent))
        except Exception:
            return True

    def _apply_tp_fallback_mode_selection(self, new_mode: str, parent=None, allow_restart: bool = True) -> None:
        previous_mode = str(getattr(self.config, "tp_fallback_mode", "online") or "online").strip().lower()
        normalized = str(new_mode or "Online").strip().lower()
        if normalized not in {"local", "online"}:
            normalized = "online"
        if normalized == "local" and previous_mode != "local":
            keep_local = self._confirm_keep_local_fallback(parent=parent)
            if not keep_local:
                normalized = "online"
                self.tp_fallback_mode_var.set("Online")
        self.config.tp_fallback_mode = normalized
        self.tp_fallback_mode_var.set(normalized.title())
        self._update_tp_fallback_ui(force=True)
        self.on_setting_changed()
        if normalized == previous_mode or not allow_restart:
            return
        if normalized == "online":
            if is_tp_login_confirmed(default_tp_showroom_profile_dir()):
                self.restart_app("Online fallback mode selected. Restarting now so the Trading Paints pipeline starts cleanly.")
            else:
                self.connect_tp_login(restart_on_success=True)
            return
        self.restart_app("Local fallback mode selected. Restarting now so the local pool pipeline starts cleanly.")

    def on_tp_fallback_mode_changed(self) -> None:
        self._apply_tp_fallback_mode_selection(self.tp_fallback_mode_var.get(), parent=self.root, allow_restart=True)

    def on_quick_start_tp_fallback_mode_changed(self, parent=None) -> None:
        self._apply_tp_fallback_mode_selection(self.tp_fallback_mode_var.get(), parent=parent, allow_restart=False)

    def reset_program_config(self) -> None:
        try:
            confirmed = self.messagebox.askyesno(APP_NAME, "Delete the saved settings file and restart the app with defaults?", parent=self.root)
        except Exception:
            confirmed = True
        if not confirmed:
            return
        try:
            if self.config_store.path.exists():
                self.config_store.path.unlink()
            self._append_log(f"Deleted saved settings file: {self.config_store.path}")
        except Exception as exc:
            try:
                self.messagebox.showerror(APP_NAME, f"Could not delete the settings file.\n\n{exc}", parent=self.root)
            except Exception:
                pass
            self._append_log(f"Could not delete settings file: {exc}")
            return
        self.restart_app("App settings were reset. Restarting with defaults now.", save_current=False, launch_args=[])

    def _refresh_random_pool_summary(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and (now - getattr(self, "_last_pool_stats_refresh_at", 0.0)) < 15.0:
            return
        self._last_pool_stats_refresh_at = now
        try:
            stats = get_random_pool_stats(default_random_pool_dir())
            self.random_pool_summary_var.set(
                f"Random pool: {stats.total_bytes / float(1024 ** 3):.2f} / {clamp_random_pool_gb(getattr(self.config, 'max_random_pool_gb', 5.0), 5.0):.2f} GB • {stats.set_count} set(s) • {stats.car_count} car type(s)"
            )
        except Exception as exc:
            self.random_pool_summary_var.set(f"Random pool: unavailable ({exc})")
    def _poll_service(self) -> None:
        if self._headless_controller_mode:
            response = send_headless_control_command("status")
            if response and response.get("ok"):
                session_label = str(response.get("current_session") or "").strip()
                status_label = str(response.get("service_status") or "Watching").strip() or "Watching"
                self.status_var.set(f"Headless • {status_label}")
                detail = f"Current session: {session_label}" if session_label else "Waiting for iRacing/session..."
                self.session_summary_var.set("Headless service is active in the background.")
                self.session_status_summary_var.set(detail)
            else:
                self._append_log("Lost connection to the headless service. Returning to the embedded GUI service.")
                self._headless_controller_mode = False
                self._update_headless_ui()
                if not self.service.is_running():
                    self.service.start()
        self._refresh_monitor_ui()
        self._refresh_tp_auth_profile_summary()
        self._refresh_random_pool_summary()
        self._refresh_session_tree()
        if not self._exiting and not self._headless_controller_mode and not self.service.is_running():
            self._append_log("Service stopped unexpectedly. Restarting...")
            self.service.start()
        if not self._exiting:
            self.root.after(750, self._poll_service)
    def _on_service_status(self, value: str) -> None:
        self.root.after(0, lambda: self.status_var.set(value))
    def _attach_to_existing_headless_if_available(self) -> bool:
        response = send_headless_control_command("status")
        if not response or not response.get("ok"):
            return False
        self._headless_controller_mode = True
        self.status_var.set(f"Headless • {str(response.get('service_status') or 'Watching').strip() or 'Watching'}")
        self._update_headless_ui(response)
        return True

    def _persist_launch_mode_preference(self, mode: str) -> None:
        normalized_mode = normalize_launch_mode_preference(mode)
        if str(getattr(self.config, "launch_mode_preference", "ask")) == normalized_mode:
            return
        self.config.launch_mode_preference = normalized_mode
        try:
            self.config_store.save(self.config)
        except Exception:
            logging.debug("Could not persist launch mode preference", exc_info=True)
            return
        self._apply_autostart(self.config.auto_start)

    def _update_headless_ui(self, status_response: dict[str, object] | None = None) -> None:
        if self._headless_controller_mode:
            session_label = ""
            if status_response:
                session_label = str(status_response.get("current_session") or "").strip()
            session_text = f" Current session: {session_label}." if session_label else ""
            self.headless_status_var.set(
                "Headless mode is active. The downloader engine is running in the background without the live Tk interface, which keeps daily resource usage lower." + session_text
            )
            self.headless_hint_var.set(
                "This window is attached only as a settings controller. Any setting saved here is pushed to the running headless service immediately when possible."
            )
            return
        self.headless_status_var.set(
            "Headless mode is available from the same script or .exe with --nogui."
        )
        self.headless_hint_var.set(
            "The GUI and headless modes share the same saved settings file automatically."
        )

    def _launch_headless_process(self) -> tuple[bool, str]:
        command = build_self_launch_command("--nogui", "--managed-headless")
        creationflags = 0
        if sys.platform == "win32":
            creationflags |= getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            creationflags |= getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
        popen_kwargs: dict[str, object] = {"creationflags": creationflags} if creationflags else {}
        try:
            subprocess.Popen(command, cwd=str(Path(getattr(sys, "executable", Path(__file__))).resolve().parent), **popen_kwargs)
        except Exception as exc:
            return False, str(exc)
        for _ in range(20):
            time.sleep(0.15)
            response = send_headless_control_command("status")
            if response and response.get("ok"):
                return True, "ok"
        return False, "The headless process started, but no local control response was received."

    def switch_to_headless(self) -> None:
        self.on_setting_changed()
        response = send_headless_control_command("status")
        if response and response.get("ok"):
            if self.service.is_running():
                self.service.stop(join_timeout=2.0)
            self._headless_controller_mode = True
            self._persist_launch_mode_preference("headless")
            self._update_headless_ui(response)
            self._append_log("Attached to the existing headless service.")
            return
        was_running = self.service.is_running()
        if was_running:
            self.service.stop(join_timeout=2.0)
        ok, detail = self._launch_headless_process()
        if not ok:
            if was_running and not self.service.is_running():
                self.service.start()
            self.messagebox.showerror(APP_NAME, f"Could not switch to headless mode.\n\n{detail}", parent=self.root)
            return
        response = send_headless_control_command("status")
        self._headless_controller_mode = True
        self._persist_launch_mode_preference("headless")
        self._update_headless_ui(response)
        self.status_var.set("Headless • Watching")
        self._append_log("Switched from the embedded GUI service to the lighter headless service.")

    def return_to_gui_service(self) -> None:
        if not self._headless_controller_mode:
            if not self.service.is_running():
                self.service.start()
            self._update_headless_ui()
            return
        send_headless_control_command("stop")
        disconnected = False
        for _ in range(20):
            time.sleep(0.15)
            if not is_headless_service_available():
                disconnected = True
                break
        if not disconnected and is_headless_service_available():
            self.messagebox.showwarning(
                APP_NAME,
                "The headless service is still responding, so the GUI service was not started to avoid running two downloader loops at the same time.",
                parent=self.root,
            )
            return
        self._headless_controller_mode = False
        self._persist_launch_mode_preference("gui")
        self._update_headless_ui()
        if not self.service.is_running():
            self.service.update_config(self.config)
            self.service.start()
        self._append_log("Returned from headless mode to the embedded GUI service.")

    def _schedule_update_check(self, initial: bool = False) -> None:
        if self._auto_update_after_id is not None:
            try:
                self.root.after_cancel(self._auto_update_after_id)
            except Exception:
                pass
            self._auto_update_after_id = None
        if not self.check_updates_var.get():
            self.update_status_var.set("Updates: manual only")
            return
        delay_ms = 1200 if initial else int(GITHUB_UPDATE_CHECK_INTERVAL_SECONDS * 1000)
        self._auto_update_after_id = self.root.after(delay_ms, self._run_scheduled_update_check)
    def _run_scheduled_update_check(self) -> None:
        self._auto_update_after_id = None
        if self._exiting or not self.check_updates_var.get():
            return
        self.start_update_check(manual=False)
    def check_updates_now(self) -> None:
        self.start_update_check(manual=True)
    def start_update_check(self, manual: bool) -> None:
        if self._update_check_in_progress:
            if manual:
                self._append_log("Update check already in progress.")
            return
        self._update_check_in_progress = True
        if manual:
            self.update_status_var.set("Updates: checking now...")
            self._append_log("Checking GitHub releases for updates...")
        thread = threading.Thread(target=self._update_check_worker, args=(manual,), daemon=True, name="NishizumiPaintsUpdateCheck")
        thread.start()
    def _update_check_worker(self, manual: bool) -> None:
        try:
            release = fetch_latest_github_release()
            error = None
        except Exception as exc:
            release = None
            error = str(exc)
        self.root.after(0, lambda: self._finish_update_check(release, error, manual))
    def _finish_update_check(self, release: GitHubReleaseInfo | None, error: str | None, manual: bool) -> None:
        self._update_check_in_progress = False
        if error:
            self.update_status_var.set("Updates: check failed")
            self._append_log(f"Update check failed: {error}")
            if manual:
                self.messagebox.showerror(APP_NAME, f"Could not check for updates.\n\n{error}")
            if self.check_updates_var.get() and not self._exiting:
                self._schedule_update_check(initial=False)
            return
        assert release is not None
        self._latest_release_info = release
        comparison = compare_version_tags(release.tag_name, APP_VERSION)
        if comparison > 0:
            self.update_status_var.set(f"Update available: {release.tag_name}")
            self._append_log(f"Update available: {release.tag_name} (current {APP_VERSION}).")
            should_prompt = manual or self._last_notified_update_tag != release.tag_name
            self._last_notified_update_tag = release.tag_name
            if should_prompt:
                message = [
                    "A new version is available.",
                    "",
                    f"Current version: {APP_VERSION}",
                    f"Latest release: {release.tag_name}",
                ]
                if release.asset_name:
                    message.append(f"Asset: {release.asset_name}")
                message.append("")
                message.append("Open the GitHub release page now?")
                if self.messagebox.askyesno(APP_NAME, "\n".join(message)):
                    self.open_latest_release()
        elif comparison == 0:
            self.update_status_var.set(f"Up to date: {APP_VERSION}")
            self._append_log(f"Update check complete: already on {APP_VERSION}.")
            if manual:
                self.messagebox.showinfo(APP_NAME, f"You are already on the latest version.\n\nCurrent version: {APP_VERSION}")
        else:
            self.update_status_var.set(f"Running newer build: {APP_VERSION}")
            self._append_log(f"Update check complete: local build {APP_VERSION} is newer than GitHub latest {release.tag_name}.")
            if manual:
                self.messagebox.showinfo(APP_NAME, f"Your current build ({APP_VERSION}) is newer than the latest public GitHub release ({release.tag_name}).")
        if self.check_updates_var.get() and not self._exiting:
            self._schedule_update_check(initial=False)
    def open_latest_release(self) -> None:
        target_url = GITHUB_RELEASES_PAGE_LATEST
        if self._latest_release_info is not None:
            target_url = self._latest_release_info.html_url or target_url
        try:
            webbrowser.open(target_url)
        except Exception as exc:
            self._append_log(f"Could not open release page: {exc}")
    def _read_ui_config(self) -> AppConfig:
        mode = normalize_download_workers_mode(self.download_workers_mode_var.get())
        self.download_workers_mode_var.set(mode.title())
        try:
            manual_manifest_workers = int(self.manual_manifest_workers_var.get())
        except Exception:
            manual_manifest_workers = 8
        try:
            manual_workers = int(self.manual_download_workers_var.get())
        except Exception:
            manual_workers = 8
        try:
            manual_save_workers = int(self.manual_save_workers_var.get())
        except Exception:
            manual_save_workers = 8
        manual_manifest_workers = max(1, min(100, manual_manifest_workers))
        manual_workers = max(1, min(100, manual_workers))
        manual_save_workers = max(1, min(100, manual_save_workers))
        self.manual_manifest_workers_var.set(manual_manifest_workers)
        self.manual_download_workers_var.set(manual_workers)
        self.manual_save_workers_var.set(manual_save_workers)
        try:
            max_random_pool_gb = float(self.random_pool_size_gb_var.get())
        except Exception:
            max_random_pool_gb = getattr(self.config, "max_random_pool_gb", 5.0)
        max_random_pool_gb = clamp_random_pool_gb(max_random_pool_gb, 5.0)
        self.random_pool_size_gb_var.set(max_random_pool_gb)
        return AppConfig(
            auto_start=bool(self.auto_start_var.get()),
            start_minimized=bool(self.start_minimized_var.get()),
            minimize_to_tray_on_close=bool(self.minimize_to_tray_var.get()),
            auto_refresh_paints=bool(self.auto_refresh_var.get()),
            cleanup_before_fetch=bool(self.cleanup_before_fetch_var.get()),
            delete_downloaded_livery=bool(self.cleanup_on_exit_var.get()),
            sync_my_livery_from_server=bool(self.sync_my_livery_var.get()),
            keep_my_livery_locally=bool(self.keep_my_livery_var.get()),
            sync_ai_rosters_from_server=bool(self.sync_ai_rosters_var.get()),
            random_fallback_real_drivers=bool(self.random_real_var.get()),
            random_fallback_ai=bool(self.random_ai_var.get()),
            tp_fallback_mode=str(self.tp_fallback_mode_var.get() or "Local").strip().lower(),
            tp_manifest_member_id_override=self._parse_tp_manifest_member_id_ui(),
            tp_mule_profile_fast_mode=bool(self.tp_mule_fast_mode_var.get()),
            tp_detect_showroom_total_pages=bool(self.tp_detect_showroom_total_pages_var.get()),
            quick_start_completed=bool(getattr(self.config, "quick_start_completed", False)),
            keep_tp_paints_in_random_pool=bool(self.keep_tp_pool_var.get()),
            max_random_pool_gb=max_random_pool_gb,
            auto_manage_replay_packs=bool(getattr(self.config, 'auto_manage_replay_packs', True)),
            show_activity_log=bool(self.show_activity_var.get()),
            show_tp_monitor=bool(self.show_tp_monitor_var.get()),
            check_updates_automatically=bool(self.check_updates_var.get()),
            download_workers_mode=mode,
            manual_download_workers=manual_workers,
            manual_manifest_workers=manual_manifest_workers,
            manual_save_workers=manual_save_workers,
            max_concurrent_downloads=8,
            verbose=bool(self.verbose_var.get()),
            poll_seconds=self.config.poll_seconds,
            retries=self.config.retries,
            retry_backoff_seconds=self.config.retry_backoff_seconds,
            launch_mode_preference=normalize_launch_mode_preference(getattr(self.config, "launch_mode_preference", "ask")),
        )
    def _update_log_visibility(self) -> None:
        if self.show_activity_var.get():
            self.log_frame.grid()
        else:
            self.log_frame.grid_remove()
    def _update_monitor_visibility(self) -> None:
        if self.show_tp_monitor_var.get():
            self.monitor_frame.grid()
        else:
            self.monitor_frame.grid_remove()
    def _update_download_mode_ui(self) -> None:
        mode = normalize_download_workers_mode(self.download_workers_mode_var.get())
        self.download_workers_mode_var.set(mode.title())
        if mode == "manual":
            self.manual_manifest_workers_spin.state(["!disabled"])
            self.manual_workers_spin.state(["!disabled"])
            self.manual_save_workers_spin.state(["!disabled"])
        else:
            self.manual_manifest_workers_spin.state(["disabled"])
            self.manual_workers_spin.state(["disabled"])
            self.manual_save_workers_spin.state(["disabled"])
    def on_download_workers_mode_changed(self) -> None:
        self._update_download_mode_ui()
        self.on_setting_changed()
    def on_manual_manifest_workers_changed(self) -> None:
        try:
            manual_workers = int(self.manual_manifest_workers_var.get())
        except Exception:
            manual_workers = self.config.manual_manifest_workers
        manual_workers = max(1, min(100, manual_workers))
        self.manual_manifest_workers_var.set(manual_workers)
        self.on_setting_changed()
    def on_manual_download_workers_changed(self) -> None:
        try:
            manual_workers = int(self.manual_download_workers_var.get())
        except Exception:
            manual_workers = self.config.manual_download_workers
        manual_workers = max(1, min(100, manual_workers))
        self.manual_download_workers_var.set(manual_workers)
        self.on_setting_changed()
    def on_manual_save_workers_changed(self) -> None:
        try:
            manual_workers = int(self.manual_save_workers_var.get())
        except Exception:
            manual_workers = self.config.manual_save_workers
        manual_workers = max(1, min(100, manual_workers))
        self.manual_save_workers_var.set(manual_workers)
        self.on_setting_changed()
    def on_random_pool_size_changed(self) -> None:
        try:
            value = float(self.random_pool_size_gb_var.get())
        except Exception:
            value = getattr(self.config, "max_random_pool_gb", 5.0)
        value = clamp_random_pool_gb(value, 5.0)
        self.random_pool_size_gb_var.set(value)
        self.on_setting_changed()
        self._refresh_random_pool_summary(force=True)
    def on_setting_changed(self) -> None:
        if self.verbose_var.get() and not self.show_activity_var.get():
            self.show_activity_var.set(True)
        if self.keep_tp_pool_var.get() and not self._random_pool_opt_in_notified:
            try:
                self.messagebox.showinfo(
                    APP_NAME,
                    "Downloaded Trading Paints car paints can be copied into the local random pool before Delete live session paints clears the active session files. This lets Nishizumi-Paints recycle those TP-sourced paints later as local random fallbacks for drivers or AI. Turn this off if you want deleted session paints to be removed permanently instead.",
                    parent=self.root,
                )
            except Exception:
                pass
            self._random_pool_opt_in_notified = True
        self.config = self._read_ui_config()
        self.config_store.save(self.config)
        self._apply_autostart(self.config.auto_start)
        if self._headless_controller_mode:
            response = send_headless_control_command("reload_config")
            if response and response.get("ok"):
                logging.info("Running headless service reloaded the updated config from the GUI.")
            else:
                logging.warning("Settings were saved, but the running headless service could not be reached to reload them immediately.")
        else:
            self.service.update_config(self.config)
        if getattr(self.config, "tp_mule_profile_fast_mode", False):
            logging.info("Trading Paints mule fast mode is enabled for the online fallback profile. The app will skip original-scheme capture and final restore, and it will poll the member manifest directly after each setScheme.")
        if self.config.keep_tp_paints_in_random_pool:
            logging.info(
                "Random TP pool is enabled: live session paints may still be deleted after use, but reusable TP car paints will be archived into the local pool first (limit %.2f GB)",
                self.config.max_random_pool_gb,
            )
        elif self.config.delete_downloaded_livery:
            logging.info(
                "Random TP pool is disabled: Delete live session paints will remove session files permanently instead of recycling them into the local fallback pool"
            )
        self._update_log_visibility()
        self._update_monitor_visibility()
        self._update_download_mode_ui()
        self._update_tp_fallback_ui(force=True)
        self._refresh_random_pool_summary(force=True)
        self._schedule_update_check(initial=True)
        if self.config.verbose:
            logging.debug("Verbose logging is enabled from the UI")
    def _apply_autostart(self, enabled: bool) -> None:
        if sys.platform != "win32":
            return
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Run",
                0,
                winreg.KEY_SET_VALUE,
            )
            with key:
                launch_args = ["--autostart-launched"]
                launch_mode = normalize_launch_mode_preference(getattr(self.config, "launch_mode_preference", "ask"))
                if launch_mode == "headless":
                    launch_args.insert(0, "--nogui")
                elif launch_mode == "gui":
                    launch_args.insert(0, "--gui")
                command = subprocess.list2cmdline(build_self_launch_command(*launch_args))
                if enabled:
                    winreg.SetValueEx(key, APP_REGISTRY_NAME, 0, winreg.REG_SZ, command)
                else:
                    try:
                        winreg.DeleteValue(key, APP_REGISTRY_NAME)
                    except FileNotFoundError:
                        pass
        except Exception as exc:
            self._append_log(f"Autostart update failed: {exc}")
    def _hide_console_window(self) -> None:
        hide_console_window()
    def redownload_now(self) -> None:
        mode = normalize_download_workers_mode(self.download_workers_mode_var.get())
        if mode == "manual":
            workers = max(1, min(100, int(self.manual_download_workers_var.get())))
            self._append_log(f"Manual re-download requested (download workers: manual {workers}).")
        else:
            self._append_log("Manual re-download requested (download workers: auto).")
        self.service.request_refresh_now()
    def clear_downloaded_now(self) -> None:
        self._append_log("Manual clear requested.")
        self.service.request_clear_current_downloads()
    def sync_ai_rosters_now(self) -> None:
        self._append_log("Manual AI roster sync requested.")
        self.service.request_sync_ai_rosters_now()
    def reset_tp_monitor(self) -> None:
        self.service.reset_monitor_snapshot()
        self._refresh_monitor_ui()
        self._append_log("TP worker monitor reset.")
    def export_log(self) -> None:
        default_name = f"nishizumi-paints-log-{time.strftime('%Y%m%d-%H%M%S')}" + ".txt"
        try:
            path = self.filedialog.asksaveasfilename(
                parent=self.root,
                title="Export activity log",
                defaultextension=".txt",
                initialfile=default_name,
                filetypes=(("Text files", "*.txt"), ("All files", "*.*")),
            )
        except Exception as exc:
            self._append_log(f"Could not open Export log dialog: {exc}")
            return
        if not path:
            return
        try:
            log_text = self.log_text.get("1.0", "end-1c")
            monitor_lines: list[str] = []
            if self.tp_monitor_summary_var.get():
                monitor_lines.append(self.tp_monitor_summary_var.get())
            if self.tp_monitor_detail_var.get():
                monitor_lines.append(self.tp_monitor_detail_var.get())
            if self.tp_monitor_save_var.get():
                monitor_lines.append(self.tp_monitor_save_var.get())
            chunks: list[str] = []
            if monitor_lines:
                chunks.append("TP worker monitor")
                chunks.extend(monitor_lines)
                chunks.append("")
            chunks.append("Activity")
            chunks.append(log_text)
            Path(path).write_text("\n".join(chunks).rstrip() + "\n", encoding="utf-8")
            self._append_log(f"Exported log to {path}")
        except Exception as exc:
            self._append_log(f"Could not export log: {exc}")
    def open_paint_folder(self) -> None:
        path = default_paints_dir()
        path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
        except Exception as exc:
            self._append_log(f"Could not open paint folder: {exc}")
    def _copy_saved_paints_to_ai(self, only_local_user: bool) -> None:
        snapshot = self.service.get_runtime_snapshot()
        if not snapshot.last_saved:
            self._append_log("There are no current downloaded car paints to copy into the AI livery folder.")
            return
        copied_sets, copied_files = import_saved_paint_groups_to_ai_livery(
            saved=snapshot.last_saved,
            session=snapshot.current_session,
            ai_livery_root=default_ai_livery_dir(),
            only_local_user=only_local_user,
        )
        if copied_sets <= 0:
            self._append_log("No matching car paints were available to copy into the AI livery folder.")
            return
        label = "your current car" if only_local_user else "the current session"
        self._append_log(f"Copied {copied_sets} car set(s) and {copied_files} file(s) from {label} into the AI livery folder.")
        self.status_var.set(f"AI livery cache updated ({copied_sets} set{'s' if copied_sets != 1 else ''})")
    def copy_my_current_car_to_ai(self) -> None:
        self._copy_saved_paints_to_ai(True)
    def copy_session_cars_to_ai(self) -> None:
        self._copy_saved_paints_to_ai(False)
    def clone_active_ai_roster(self) -> None:
        snapshot = self.service.get_runtime_snapshot()
        success, message = clone_active_ai_roster_to_local(snapshot.current_session, default_ai_rosters_dir())
        self._append_log(message)
        if success:
            self.status_var.set("Local AI roster created")
    def randomize_active_ai_roster(self) -> None:
        snapshot = self.service.get_runtime_snapshot()
        success, message = randomize_active_ai_roster_from_pool(
            snapshot.current_session,
            default_ai_rosters_dir(),
            default_random_pool_dir(),
            default_ai_livery_dir(),
        )
        self._append_log(message)
        if success:
            self.status_var.set("Random AI roster created")
    def open_ai_rosters_folder(self) -> None:
        path = default_ai_rosters_dir()
        path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
        except Exception as exc:
            self._append_log(f"Could not open AI rosters folder: {exc}")
    def open_ai_livery_folder(self) -> None:
        path = default_ai_livery_dir()
        path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
        except Exception as exc:
            self._append_log(f"Could not open AI livery folder: {exc}")
    def open_random_pool_folder(self) -> None:
        path = default_random_pool_dir()
        path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
        except Exception as exc:
            self._append_log(f"Could not open random pool folder: {exc}")
    def _prompt_tp_account_kind(self) -> str | None:
        dialog = self.tk.Toplevel(self.root)
        dialog.title("Trading Paints account")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.grab_set()
        choice = {"value": None}
        frame = self.ttk.Frame(dialog, padding=14)
        frame.grid(sticky="nsew")
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(0, weight=1)
        self.ttk.Label(frame, text="Choose the Trading Paints account type", font=("Segoe UI", 10, "bold")).grid(row=0, column=0, sticky="w")
        msg = (
            "You can connect Trading Paints with your main account or with a secondary smurf/mule account. "
            "A secondary account is recommended because it can act only as the paint mule while you race on your main account."
        )
        self.ttk.Label(frame, text=msg, justify="left", wraplength=470, foreground="#444444").grid(row=1, column=0, sticky="w", pady=(8, 0))
        buttons = self.ttk.Frame(frame)
        buttons.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        def _pick(value: str) -> None:
            choice["value"] = value
            dialog.destroy()
        self.ttk.Button(buttons, text="Primary account", command=lambda: _pick("primary")).pack(side="left")
        self.ttk.Button(buttons, text="Smurf / mule account", command=lambda: _pick("smurf")).pack(side="left", padx=(8, 0))
        self.ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="right")
        dialog.bind("<Escape>", lambda _e: dialog.destroy())
        try:
            dialog.update_idletasks()
            w = dialog.winfo_width(); h = dialog.winfo_height()
            x = max(0, self.root.winfo_rootx() + (self.root.winfo_width() - w) // 2)
            y = max(0, self.root.winfo_rooty() + 80)
            dialog.geometry(f"+{x}+{y}")
        except Exception:
            pass
        self.root.wait_window(dialog)
        return choice["value"]

    def _show_tp_login_instruction_popup(self, account_kind: str) -> bool:
        account_text = "secondary smurf / mule account" if account_kind == "smurf" else "primary account"
        message = (
            f"The browser will open now. Sign in to Trading Paints with your {account_text}.\n\n"
            "When the site finishes authentication, minimize the browser and click 'I logged in' back in Nishizumi Paints.\n\n"
            "Press OK to continue."
        )
        try:
            self.messagebox.showinfo(APP_NAME, message, parent=self.root)
        except Exception:
            return True
        return True

    def _prompt_tp_manifest_member_id_after_login(self) -> None:
        prompt = (
            "This Trading Paints account is different from the iRacing account you will race with.\n\n"
            "Enter the Trading Paints member ID for the secondary account. "
            "Nishizumi Paints cannot detect it automatically, and online fallback downloads need it."
        )
        while True:
            value = self.simpledialog.askstring(APP_NAME, prompt, parent=self.root, initialvalue=self.tp_manifest_member_id_var.get().strip())
            if value is None:
                self._append_log("Secondary Trading Paints account connected, but the TP member ID override was not provided yet. Online fallback may fail until you fill it in.")
                try:
                    self.messagebox.showwarning(APP_NAME, "The secondary Trading Paints member ID was not saved. Fill in 'TP manifest member ID override' later if online fallback complains.", parent=self.root)
                except Exception:
                    pass
                return
            member_id = normalize_tp_member_id(value)
            if member_id > 0:
                self.tp_manifest_member_id_var.set(str(member_id))
                self.save_tp_manifest_member_id()
                return
            try:
                retry = self.messagebox.askretrycancel(APP_NAME, "Please enter a valid numeric Trading Paints member ID.", parent=self.root)
            except Exception:
                retry = False
            if not retry:
                return

    def show_quick_start_if_needed(self) -> None:
        if getattr(self.config, "quick_start_completed", False):
            return
        if self._launched_from_autostart:
            return
        if getattr(self, "_quick_start_open", False):
            return
        self._quick_start_open = True
        self._tp_login_restart_pending_after_quick_start = False
        self._open_quick_start_wizard()

    def _open_quick_start_wizard(self) -> None:
        wizard = self.tk.Toplevel(self.root)
        wizard.title(f"{APP_NAME} Quick Start")
        wizard.transient(self.root)
        wizard.resizable(False, False)
        wizard.grab_set()
        wizard.columnconfigure(0, weight=1)
        wizard.rowconfigure(1, weight=1)
        header = self.ttk.Frame(wizard, padding=(14, 14, 14, 0))
        header.grid(row=0, column=0, sticky="ew")
        self.ttk.Label(header, text="Quick Start", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.ttk.Label(header, text="Recommended setup: normal window first, then Online fallback with a secondary mule Trading Paints account.", foreground="#176d2b").pack(anchor="w", pady=(4, 0))
        body = self.ttk.Frame(wizard, padding=14)
        body.grid(row=1, column=0, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        pages = []
        step_var = self.tk.StringVar(value="Step 1 of 4")

        def _page_container() -> object:
            frame = self.ttk.Frame(body)
            frame.grid(row=0, column=0, sticky="nsew")
            frame.columnconfigure(0, weight=1)
            return frame

        p1 = _page_container()
        self.ttk.Label(p1, text="1 • Startup mode", font=("Segoe UI", 10, "bold"), foreground="#0b63b6").pack(anchor="w")
        self.ttk.Label(
            p1,
            text=(
                "You already chose window or console before this screen. Use the normal window for the first setup. "
                "Console mode is for advanced users after the app is already configured. "
                "You can show that startup choice again later by holding Shift while opening the app."
            ),
            wraplength=520,
            justify="left",
            foreground="#444444",
        ).pack(anchor="w", pady=(8, 0))
        self.ttk.Checkbutton(p1, text="Start minimized", variable=self.start_minimized_var, command=self.on_setting_changed).pack(anchor="w", pady=(12, 0))
        self.ttk.Checkbutton(p1, text="Keep running in background on close", variable=self.minimize_to_tray_var, command=self.on_setting_changed).pack(anchor="w", pady=(6, 0))
        pages.append(p1)

        p2 = _page_container()
        self.ttk.Label(p2, text="2 • Missing paint fallback", font=("Segoe UI", 10, "bold"), foreground="#0b63b6").pack(anchor="w")
        self.ttk.Label(p2, text="Choose who should receive a backup paint when Trading Paints has no paint for them.", wraplength=520, justify="left", foreground="#444444").pack(anchor="w", pady=(8, 0))
        self.ttk.Checkbutton(p2, text="Fallback for real drivers without TP paints", variable=self.random_real_var, command=self.on_random_fallback_targets_changed).pack(anchor="w", pady=(10, 0))
        self.ttk.Checkbutton(p2, text="Fallback for AI drivers without TP paints", variable=self.random_ai_var, command=self.on_random_fallback_targets_changed).pack(anchor="w", pady=(6, 0))
        mode_row = self.ttk.Frame(p2)
        mode_row.pack(anchor="w", pady=(14, 0))
        self.ttk.Label(mode_row, text="Preferred source:", font=("Segoe UI", 9, "bold")).pack(side="left")
        self.ttk.Radiobutton(mode_row, text="Local", value="Local", variable=self.tp_fallback_mode_var, command=lambda: self.on_quick_start_tp_fallback_mode_changed(parent=wizard)).pack(side="left", padx=(10, 0))
        self.ttk.Radiobutton(mode_row, text="Online", value="Online", variable=self.tp_fallback_mode_var, command=lambda: self.on_quick_start_tp_fallback_mode_changed(parent=wizard)).pack(side="left", padx=(10, 0))
        self.ttk.Label(p2, text="Recommended: Online. It usually gives much better variety because the app can pull random paints directly from the Trading Paints showroom.", wraplength=520, justify="left", foreground="#176d2b").pack(anchor="w", pady=(10, 0))
        self.ttk.Label(p2, text="Local stays useful too because Online can still fall back to the local pool if a showroom step fails.", wraplength=520, justify="left", foreground="#555555").pack(anchor="w", pady=(6, 0))
        pages.append(p2)

        p3 = _page_container()
        self.ttk.Label(p3, text="3 • Trading Paints login", font=("Segoe UI", 10, "bold"), foreground="#0b63b6").pack(anchor="w")
        explain = (
            "Online fallback is the recommended mode. To download random showroom paints, Nishizumi Paints temporarily switches the paint on the connected Trading Paints account, captures the files, then continues. "
            "If you connect your primary account, the app protects and restores your original paint. If you connect a secondary mule account, the mule can skip those extra checks for speed."
        )
        self.ttk.Label(p3, text=explain, wraplength=520, justify="left", foreground="#444444").pack(anchor="w", pady=(8, 0))
        self.quick_start_tp_status_label = self.ttk.Label(p3, textvariable=self.tp_auth_profile_summary_var, wraplength=520, justify="left", foreground="#555555")
        self.quick_start_tp_status_label.pack(anchor="w", pady=(10, 0))
        actions = self.ttk.Frame(p3)
        actions.pack(anchor="w", pady=(12, 0))
        self.ttk.Button(actions, text="Connect primary account", command=lambda: self.connect_tp_login(account_kind="primary")).pack(side="left")
        self.ttk.Button(actions, text="Connect smurf / mule account", command=lambda: self.connect_tp_login(account_kind="smurf")).pack(side="left", padx=(8, 0))
        self.quick_start_tp_confirm_button = self.ttk.Button(actions, text="I logged in", command=self.confirm_tp_login)
        self.quick_start_tp_confirm_button.pack(side="left", padx=(8, 0))
        self.ttk.Checkbutton(p3, text="Use TP mule fast mode", variable=self.tp_mule_fast_mode_var, command=self.on_setting_changed).pack(anchor="w", pady=(12, 0))
        self.ttk.Label(p3, text="Use mule fast mode only for a secondary mule account. It skips restore steps to be faster.", wraplength=520, justify="left", foreground="#b00020").pack(anchor="w", pady=(4, 0))
        self.ttk.Label(p3, text="If you selected Online above, you must finish a successful Trading Paints login here before you can continue.", wraplength=520, justify="left", foreground="#176d2b").pack(anchor="w", pady=(8, 0))
        pages.append(p3)

        p4 = _page_container()
        self.ttk.Label(p4, text="4 • Ready", font=("Segoe UI", 10, "bold"), foreground="#0b63b6").pack(anchor="w")
        self.ttk.Label(p4, text=("You can still change everything later in the tabs. The General tab keeps the local random pool. "
                                 "The Random tab controls whether missing paints prefer Local or Online."),
                      wraplength=520, justify="left", foreground="#444444").pack(anchor="w", pady=(8, 0))
        self.ttk.Label(p4, text="Recommended final setup: Online fallback + secondary mule Trading Paints account + mule fast mode enabled.", wraplength=520, justify="left", foreground="#176d2b").pack(anchor="w", pady=(8, 0))
        pages.append(p4)

        footer = self.ttk.Frame(wizard, padding=(14, 0, 14, 14))
        footer.grid(row=2, column=0, sticky="ew")
        footer.columnconfigure(1, weight=1)
        self.ttk.Label(footer, textvariable=step_var, foreground="#555555").grid(row=0, column=0, sticky="w")
        nav = self.ttk.Frame(footer)
        nav.grid(row=0, column=1, sticky="e")
        page_index = {"value": 0}

        def _online_setup_required() -> bool:
            has_any_targets = bool(self.random_real_var.get() or self.random_ai_var.get())
            mode = str(self.tp_fallback_mode_var.get() or "Local").strip().lower()
            return has_any_targets and mode == "online"

        def _tp_login_ready() -> bool:
            return bool(is_tp_login_confirmed(default_tp_showroom_profile_dir()))

        def _finish() -> None:
            if _online_setup_required() and not _tp_login_ready():
                try:
                    self.messagebox.showwarning(APP_NAME, "Online fallback is selected, so you need to connect Trading Paints successfully before finishing Quick Start.", parent=wizard)
                except Exception:
                    pass
                return
            pending_restart = bool(getattr(self, "_tp_login_restart_pending_after_quick_start", False))
            self._tp_login_restart_pending_after_quick_start = False
            self.config.quick_start_completed = True
            self.on_setting_changed()
            self._quick_start_open = False
            self._quick_start_nav_refresh = None
            self.quick_start_tp_confirm_button = None
            self.quick_start_tp_status_label = None
            wizard.destroy()
            if pending_restart:
                self.restart_app("Trading Paints login confirmed. Restarting now so online mode becomes active cleanly.")

        def _refresh_nav_state() -> None:
            index = page_index["value"]
            needs_login = _online_setup_required() and not _tp_login_ready()
            back_btn.state(["disabled"] if index == 0 else ["!disabled"])
            if index == len(pages) - 1:
                next_btn.configure(text="Finish")
            else:
                next_btn.configure(text="Next →")
            if needs_login and index >= 2:
                next_btn.state(["disabled"])
                skip_btn.state(["disabled"])
            else:
                next_btn.state(["!disabled"])
                skip_btn.state(["!disabled"])

        self._quick_start_nav_refresh = _refresh_nav_state

        def _show_page(index: int) -> None:
            index = max(0, min(len(pages) - 1, index))
            page_index["value"] = index
            for i, page in enumerate(pages):
                if i == index:
                    page.tkraise()
                else:
                    page.lower()
            step_var.set(f"Step {index + 1} of {len(pages)}")
            _refresh_nav_state()

        def _next() -> None:
            if _online_setup_required() and not _tp_login_ready() and page_index["value"] >= 2:
                try:
                    self.messagebox.showwarning(APP_NAME, "Finish the Trading Paints login first. Use Connect, then come back and click 'I logged in'.", parent=wizard)
                except Exception:
                    pass
                return
            if page_index["value"] >= len(pages) - 1:
                _finish()
            else:
                _show_page(page_index["value"] + 1)

        back_btn = self.ttk.Button(nav, text="← Back", command=lambda: _show_page(page_index["value"] - 1))
        back_btn.pack(side="left")
        next_btn = self.ttk.Button(nav, text="Next →", command=_next)
        next_btn.pack(side="left", padx=(8, 0))
        skip_btn = self.ttk.Button(nav, text="Skip", command=_finish)
        skip_btn.pack(side="left", padx=(8, 0))
        wizard.protocol("WM_DELETE_WINDOW", _finish)
        _show_page(0)
        self._refresh_tp_auth_profile_summary(force=True)
        try:
            wizard.update_idletasks()
            w = wizard.winfo_width(); h = wizard.winfo_height()
            x = max(0, self.root.winfo_rootx() + (self.root.winfo_width() - w) // 2)
            y = max(0, self.root.winfo_rooty() + 60)
            wizard.geometry(f"+{x}+{y}")
        except Exception:
            pass

    def open_tp_auth_profile(self) -> None:
        path = default_tp_showroom_profile_dir()
        path.mkdir(parents=True, exist_ok=True)
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                os.system(f'open "{path}"')
            else:
                os.system(f'xdg-open "{path}"')
        except Exception as exc:
            self._append_log(f"Could not open Trading Paints auth profile folder: {exc}")

    def connect_tp_login(self, restart_on_success: bool = False, account_kind: str | None = None) -> None:
        if getattr(self, "_tp_login_in_progress", False):
            self._append_log("Trading Paints login is already in progress.")
            return
        chosen_account_kind = str(account_kind or "").strip().lower()
        if chosen_account_kind not in {"primary", "smurf"}:
            chosen_account_kind = str(self._prompt_tp_account_kind() or "").strip().lower()
        if chosen_account_kind not in {"primary", "smurf"}:
            return
        if chosen_account_kind == "smurf":
            self.tp_mule_fast_mode_var.set(True)
            try:
                self.on_setting_changed()
            except Exception:
                logging.debug("Could not persist mule fast mode immediately after account choice", exc_info=True)
        self._show_tp_login_instruction_popup(chosen_account_kind)
        self._tp_login_in_progress = True
        self._tp_login_restart_on_success = bool(restart_on_success)
        self._tp_login_confirm_event = threading.Event()
        clear_tp_login_status(default_tp_showroom_profile_dir(), "Trading Paints login is waiting for your confirmation in the app.")
        self._append_log(f"Opening Trading Paints login in a persistent Chrome profile for the selected {chosen_account_kind} account. Finish the login there, then click 'I logged in' in the app.")
        self.status_var.set("Trading Paints login...")
        self._refresh_tp_auth_profile_summary(force=True)
        self._update_tp_fallback_ui(force=True)

        def _progress(message: str) -> None:
            self.root.after(0, lambda: (self._append_log(message), self._refresh_tp_auth_profile_summary(force=True)))

        def _worker() -> None:
            try:
                ok, message = ensure_trading_paints_login(
                    default_tp_showroom_profile_dir(),
                    confirm_event=self._tp_login_confirm_event,
                    manual_confirm_required=True,
                    progress=_progress,
                )
            except Exception as exc:
                clear_tp_login_status(default_tp_showroom_profile_dir(), f"Trading Paints login flow failed: {exc}")
                ok, message = False, f"Trading Paints login flow failed: {exc}"

            def _finish() -> None:
                self._tp_login_in_progress = False
                self._tp_login_confirm_event = None
                self._append_log(message)
                self.status_var.set("Trading Paints login ready" if ok else "Watching")
                self._refresh_tp_auth_profile_summary(force=True)
                self._update_tp_fallback_ui(force=True)
                selected_mode = str(self.tp_fallback_mode_var.get() or "Local").strip().lower()
                self._refresh_tp_manifest_member_id_summary()
                if ok:
                    try:
                        self.messagebox.showinfo(APP_NAME, "Logged in successfully!", parent=self.root)
                    except Exception:
                        pass
                    if chosen_account_kind == "smurf":
                        self._prompt_tp_manifest_member_id_after_login()
                should_restart_into_online = bool(ok and selected_mode == "online")
                if ok and selected_mode == "online":
                    try:
                        self.config.tp_fallback_mode = "online"
                    except Exception:
                        pass
                    try:
                        self.on_setting_changed()
                    except Exception:
                        logging.debug("Could not persist online fallback mode immediately after TP login confirmation", exc_info=True)
                if should_restart_into_online or (ok and self._tp_login_restart_on_success):
                    self._tp_login_restart_on_success = False
                    if getattr(self, "_quick_start_open", False):
                        self._tp_login_restart_pending_after_quick_start = True
                        self._append_log("Trading Paints login confirmed. The app will restart after you finish Quick Start.")
                    else:
                        self.restart_app("Trading Paints login confirmed. Restarting now so online mode becomes active cleanly.")
                else:
                    self._tp_login_restart_on_success = False

            self.root.after(0, _finish)

        threading.Thread(target=_worker, name="NishizumiPaintsTPLogin", daemon=True).start()

    def confirm_tp_login(self) -> None:
        if not getattr(self, "_tp_login_in_progress", False) or self._tp_login_confirm_event is None:
            self._append_log("No Trading Paints login window is currently waiting for confirmation.")
            self._refresh_tp_auth_profile_summary(force=True)
            return
        self._append_log("Trading Paints login confirmation requested. Checking the current Chrome session now...")
        self.status_var.set("Confirming TP login...")
        self._tp_login_confirm_event.set()
        self._refresh_tp_auth_profile_summary(force=True)

    def open_tp_showroom(self) -> None:
        try:
            webbrowser.open("https://www.tradingpaints.com/showroom/filter/from=everyone,sort=popular,ad=DESC,pos=0")
            self._append_log("Opened Trading Paints showroom in your browser.")
        except Exception as exc:
            self._append_log(f"Could not open Trading Paints showroom: {exc}")
        self._refresh_tp_auth_profile_summary(force=True)

    def clean_random_pool_now(self) -> None:
        try:
            removed_sets, removed_files, freed_bytes = clear_random_pool(default_random_pool_dir())
            self._append_log(
                f"Random pool cleared: removed {removed_sets} set(s), {removed_files} file(s), and freed {freed_bytes / float(1024 ** 3):.2f} GB."
            )
        except Exception as exc:
            self._append_log(f"Random pool cleanup failed: {exc}")
        self._refresh_random_pool_summary(force=True)
    def rebuild_random_pool_now(self) -> None:
        try:
            added_sets, added_files, pool_bytes_after, pool_freed_bytes = rebuild_random_pool_from_paints_root(
                default_paints_dir(),
                default_random_pool_dir(),
                getattr(self.config, "max_random_pool_gb", 5.0),
            )
            self._append_log(
                f"Random pool rebuild complete: added {added_sets} set(s) and {added_files} file(s) from current paint files. Pool now uses {pool_bytes_after / float(1024 ** 3):.2f} GB."
            )
            if pool_freed_bytes > 0:
                self._append_log(
                    f"Random pool rebuild also trimmed {pool_freed_bytes / float(1024 ** 3):.2f} GB to stay within the configured limit."
                )
        except Exception as exc:
            self._append_log(f"Random pool rebuild failed: {exc}")
        self._refresh_random_pool_summary(force=True)
    def start_minimized(self) -> None:
        if self.minimize_to_tray_var.get():
            self.hide_to_background()
        else:
            self.root.iconify()
    def hide_to_background(self) -> None:
        try:
            shown = self.tray_icon.show(f"{APP_NAME} is running")
        except Exception as exc:
            shown = False
            self._append_log(f"Background icon failed: {exc}")
        if shown:
            self.root.withdraw()
            try:
                self.root.update_idletasks()
            except Exception:
                pass
            return
        self.root.iconify()
    def bring_to_front(self) -> None:
        self.tray_icon.hide()
        try:
            if self.root.state() == "iconic":
                self.root.deiconify()
            else:
                self.root.deiconify()
        except Exception:
            try:
                self.root.deiconify()
            except Exception:
                pass
        self.root.lift()
        try:
            self.root.focus_force()
        except Exception:
            pass
        try:
            self.root.attributes("-topmost", True)
            self.root.after(250, lambda: self.root.attributes("-topmost", False))
        except Exception:
            pass
    def restore_from_background(self) -> None:
        self.bring_to_front()
    def on_close(self) -> None:
        if self.minimize_to_tray_var.get():
            self.hide_to_background()
            return
        self.exit_app()
    def exit_app(self) -> None:
        self._exiting = True
        if self._auto_update_after_id is not None:
            try:
                self.root.after_cancel(self._auto_update_after_id)
            except Exception:
                pass
            self._auto_update_after_id = None
        self.instance_signal_server.stop()
        self.tray_icon.stop()
        self.service.stop()
        self.root.destroy()
    def run(self) -> None:
        self.root.mainloop()
def run_headless(args: argparse.Namespace | None = None) -> int:
    if args is None:
        args = parse_args()
    setup_logging(args.verbose)
    instance_lock = SingleInstanceLock(INSTANCE_MUTEX_NAME)
    if not instance_lock.acquire():
        SingleInstanceSignalServer.notify_existing_instance()
        logging.info("Another Nishizumi Paints instance is already running. Bringing it to the foreground instead of starting a second copy.")
        return 0
    show_console_window()
    bring_console_to_front()
    logging.info("Headless mode is active. To open the full interface again later, run the app with --gui or hold Shift while starting it.")
    instance_signal_server = SingleInstanceSignalServer(bring_console_to_front)
    instance_signal_server.start()
    config_store = ConfigStore()
    stored_config = config_store.load()
    config = AppConfig(**asdict(stored_config))
    config.auto_start = False
    config.start_minimized = False
    config.minimize_to_tray_on_close = False
    if args.keep_session_paints:
        config.delete_downloaded_livery = False
        config.keep_my_livery_locally = True
    config.verbose = bool(config.verbose or args.verbose)
    config.poll_seconds = max(args.poll_seconds, 0.2)
    config.retries = max(1, args.retries)
    config.retry_backoff_seconds = max(0.1, args.retry_backoff_seconds)
    if args.max_concurrent_downloads != 8:
        config.download_workers_mode = "manual"
        config.manual_download_workers = max(1, min(100, int(args.max_concurrent_downloads)))
    if args.max_concurrent_manifests != 10:
        config.download_workers_mode = "manual"
        config.manual_manifest_workers = max(1, min(100, int(args.max_concurrent_manifests)))
    config.max_concurrent_downloads = 8
    service = DownloaderService(config)
    stop_event = threading.Event()
    def _request_shutdown() -> None:
        stop_event.set()
        service.stop()
    control_server = HeadlessControlServer(service, config_store, _request_shutdown)
    control_server_started = control_server.start()
    if not control_server_started and is_headless_service_available():
        logging.info("A headless service is already running, so this new headless launch will exit without starting a second instance.")
        instance_signal_server.stop()
        instance_lock.release()
        return 0
    if not control_server_started:
        logging.warning("Headless control port %s is unavailable. The service will still run, but live GUI handoff/control will not be available for this instance.", HEADLESS_CONTROL_PORT)
    def _sig_handler(_signum, _frame):
        stop_event.set()
        service.stop()
    signal.signal(signal.SIGINT, _sig_handler)
    signal.signal(signal.SIGTERM, _sig_handler)
    service.start()
    try:
        while not stop_event.is_set():
            if not service.is_running():
                logging.warning("Service stopped unexpectedly. Restarting...")
                service.start()
            time.sleep(0.5)
    finally:
        control_server.stop()
        instance_signal_server.stop()
        service.stop()
        instance_lock.release()
    return 0
def resolve_requested_launch_mode(args: argparse.Namespace, config_store: ConfigStore) -> str | None:
    if bool(getattr(args, "gui", False)):
        return "gui"
    if bool(getattr(args, "nogui", False)):
        return "headless"
    saved_mode = normalize_launch_mode_preference(getattr(config_store.load(), "launch_mode_preference", "ask"))
    if not is_shift_pressed_at_startup() and saved_mode != "ask":
        return saved_mode
    if bool(getattr(args, "autostart_launched", False)):
        return "gui"
    selection = show_launch_mode_dialog(saved_mode)
    if selection is None:
        return None
    chosen_mode, remember_choice = selection
    if remember_choice:
        config = config_store.load()
        config.launch_mode_preference = normalize_launch_mode_preference(chosen_mode)
        try:
            config_store.save(config)
        except Exception:
            logging.debug("Could not save launch mode preference", exc_info=True)
    return normalize_launch_mode_preference(chosen_mode)


def main() -> int:
    args = parse_args()
    config_store = ConfigStore()
    launch_mode = resolve_requested_launch_mode(args, config_store)
    if launch_mode is None:
        return 0
    if launch_mode == "headless":
        return run_headless(args)
    instance_lock = SingleInstanceLock(INSTANCE_MUTEX_NAME)
    if not instance_lock.acquire():
        SingleInstanceSignalServer.notify_existing_instance()
        return 0
    try:
        app = DownloaderUI(launched_from_autostart=args.autostart_launched)
        app.run()
        return 0
    finally:
        instance_lock.release()
if __name__ == "__main__":
    sys.exit(main())