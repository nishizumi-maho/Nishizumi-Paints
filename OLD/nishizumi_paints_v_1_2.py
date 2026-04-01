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
import sys
import tempfile
import threading
import time
import traceback
import urllib.parse
import webbrowser
import re
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable

import requests
import yaml
from requests.adapters import HTTPAdapter


APP_NAME = "Nishizumi Paints"
APP_VERSION = "v1.2"
APP_REGISTRY_NAME = "NishizumiPaints"
APP_CONFIG_DIRNAME = "NishizumiPaints"
APP_TOOLTIP = f"{APP_NAME} {APP_VERSION}"
APP_USER_AGENT = f"nishizumi-paints/{APP_VERSION}"
GITHUB_RELEASE_OWNER = "nishizumi-maho"
GITHUB_RELEASE_REPO = "Nishizumi-Paints"
GITHUB_RELEASES_API_LATEST = f"https://api.github.com/repos/{GITHUB_RELEASE_OWNER}/{GITHUB_RELEASE_REPO}/releases/latest"
GITHUB_RELEASES_PAGE_LATEST = f"https://github.com/{GITHUB_RELEASE_OWNER}/{GITHUB_RELEASE_REPO}/releases/latest"
GITHUB_API_VERSION = "2022-11-28"
GITHUB_UPDATE_CHECK_INTERVAL_SECONDS = 6 * 60 * 60

APP_ICON_ICO = "nishizumi_paints_icon.ico"
APP_ICON_PNG = "nishizumi_paints_icon.png"
INSTANCE_HOST = "127.0.0.1"
INSTANCE_PORT = 45891
INSTANCE_MUTEX_NAME = r"Local\NishizumiPaintsSingleInstance"


def resource_path(name: str) -> Path:
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return base / name


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


@dataclass(frozen=True)
class SessionUser:
    user_id: int
    directory: str
    team_id: int | None = None

    def effective_target_key(self) -> tuple[str, int, str]:
        target_kind = "team" if self.team_id is not None and self.team_id > 0 else "user"
        target_id = self.team_id if target_kind == "team" else self.user_id
        return (target_kind, int(target_id), self.directory.lower())


@dataclass(frozen=True)
class Session:
    session_id: SessionId
    users: set[SessionUser]
    local_user_id: int | None = None
    local_team_id: int | None = None

    def fingerprint(self) -> tuple[SessionId, tuple[tuple[str, int, str], ...]]:
        normalized_users = tuple(sorted(u.effective_target_key() for u in self.users))
        return (self.session_id, normalized_users)

    def local_preserve_targets(self) -> set[tuple[bool, int]]:
        targets: set[tuple[bool, int]] = set()
        if self.local_user_id is not None and self.local_user_id > 0:
            targets.add((False, self.local_user_id))
        if self.local_team_id is not None and self.local_team_id > 0:
            targets.add((True, self.local_team_id))
        return targets


@dataclass(frozen=True)
class DownloadId:
    user_id: int
    directory: str
    paint_type: PaintType
    is_team_paint: bool = False


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
    parser.add_argument(
        "--nogui",
        action="store_true",
        help="Run without the built-in UI.",
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



def _build_session_from_parts(weekend: object, driver_info: object) -> Session | None:
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

    sub_raw = weekend.get("SubSessionID")
    sub_id = None
    try:
        if sub_raw is not None:
            sub_id = int(sub_raw)
    except (TypeError, ValueError):
        sub_id = None

    drivers = driver_info.get("Drivers", [])
    users: set[SessionUser] = set()
    local_user_id: int | None = None
    local_team_id: int | None = None
    try:
        driver_car_idx = int(driver_info.get("DriverCarIdx"))
    except (TypeError, ValueError):
        driver_car_idx = None

    if isinstance(drivers, list):
        for d in drivers:
            if not isinstance(d, dict):
                continue
            try:
                user_id = int(d.get("UserID"))
            except (TypeError, ValueError):
                continue

            try:
                team_id_raw = d.get("TeamID")
                team_id = int(team_id_raw) if team_id_raw not in (None, "") else None
            except (TypeError, ValueError):
                team_id = None
            if team_id is not None and team_id <= 0:
                team_id = None

            car_path = d.get("CarPath")
            if user_id > 0 and isinstance(car_path, str) and car_path.strip():
                users.add(SessionUser(user_id=user_id, directory=car_path.strip(), team_id=team_id))

            if driver_car_idx is not None:
                try:
                    car_idx = int(d.get("CarIdx"))
                except (TypeError, ValueError):
                    car_idx = None
                if car_idx == driver_car_idx and user_id > 0:
                    local_user_id = user_id
                    local_team_id = team_id

    return Session(
        session_id=SessionId(main_id, sub_id),
        users=users,
        local_user_id=local_user_id,
        local_team_id=local_team_id,
    )



def parse_session_yaml(yaml_text: str) -> Session | None:
    try:
        doc = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        logging.error("Failed to parse session YAML: %s", exc)
        return None

    if not isinstance(doc, dict):
        return None

    return _build_session_from_parts(doc.get("WeekendInfo"), doc.get("DriverInfo"))



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

            root = ET.fromstring(resp.text)
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

                files.append(
                    DownloadFile(
                        download_id=DownloadId(
                            user_id=user_id,
                            directory=directory,
                            paint_type=paint_type,
                        ),
                        url=file_url,
                    )
                )
            return files
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



def normalize_directory(value: str) -> str:
    normalized = value.strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("_")
    return normalized



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
    )


def normalize_download_for_session_user(session_user: SessionUser, item: DownloadFile) -> DownloadFile:
    if not uses_team_target(session_user, item):
        return item
    team_id = int(session_user.team_id)
    if item.download_id.user_id == team_id and item.download_id.is_team_paint:
        return item
    return DownloadFile(
        download_id=DownloadId(
            user_id=team_id,
            directory=item.download_id.directory,
            paint_type=item.download_id.paint_type,
            is_team_paint=True,
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

    dest_dir = temp_root / session_id.folder_name() / item.download_id.directory
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_file = dest_dir / name

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
    if download_id.paint_type is PaintType.CAR:
        return paints_dir / download_id.directory / f"car_{team_suffix}.tga"
    if download_id.paint_type is PaintType.CAR_DECAL:
        return paints_dir / download_id.directory / f"decal_{team_suffix}.tga"
    if download_id.paint_type is PaintType.CAR_NUMBER:
        return paints_dir / download_id.directory / f"car_num_{team_suffix}.tga"
    if download_id.paint_type is PaintType.CAR_SPEC:
        return paints_dir / download_id.directory / f"car_spec_{team_suffix}.mip"
    if download_id.paint_type is PaintType.HELMET:
        return paints_dir / f"helmet_{team_suffix}.tga"
    if download_id.paint_type is PaintType.SUIT:
        return paints_dir / f"suit_{team_suffix}.tga"
    raise ValueError(f"Unsupported paint type: {download_id.paint_type}")



def move_or_extract(
    downloaded: DownloadedFile,
    paints_dir: Path,
    batch_monitor: TransferBatchMonitor | None = None,
) -> SavedFile | None:
    src = downloaded.file_path
    dest = save_path_for(downloaded.download_id, paints_dir)
    dest.parent.mkdir(parents=True, exist_ok=True)
    temp_dest = dest.with_name(dest.name + ".tmp")
    task_started_at = batch_monitor.begin() if batch_monitor is not None else time.monotonic()
    saved_bytes = 0
    success = False

    try:
        temp_dest.unlink(missing_ok=True)
        if src.suffix.lower() == ".bz2":
            with src.open("rb") as source, bz2.open(source, "rb") as decompressor, temp_dest.open(
                "wb"
            ) as out:
                shutil.copyfileobj(decompressor, out)
            src.unlink(missing_ok=True)
        else:
            shutil.move(str(src), str(temp_dest))
        os.replace(temp_dest, dest)
        try:
            saved_bytes = int(dest.stat().st_size)
        except OSError:
            saved_bytes = 0
        success = True
    except Exception as exc:  # noqa: BLE001
        temp_dest.unlink(missing_ok=True)
        logging.error("Failed to save %s -> %s: %s", src, dest, exc)
        return None
    finally:
        if batch_monitor is not None:
            batch_monitor.end(task_started_at, success=success, bytes_count=saved_bytes)

    logging.info("Saved paint file: %s", dest)
    return SavedFile(
        session_id=downloaded.session_id,
        download_id=downloaded.download_id,
        file_path=dest,
    )


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
            executor.submit(fetch_user_files, user.user_id, retries, retry_backoff_seconds): user
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
        future_to_item: dict[concurrent.futures.Future[SavedFile | None], tuple[int, DownloadedFile]] = {}
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
            if result is not None:
                saved.append(result)
                logging.info(
                    "Save progress %s/%s • completed user %s %s",
                    completed,
                    total,
                    downloaded.download_id.user_id,
                    downloaded.download_id.paint_type.value,
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
) -> tuple[list[SavedFile], ThroughputMonitorSnapshot]:
    session_temp = temp_dir / session.session_id.folder_name()
    if session_temp.exists():
        shutil.rmtree(session_temp, ignore_errors=True)

    logging.info("Session users discovered: %s", len(session.users))

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

    shutil.rmtree(session_temp, ignore_errors=True)
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
    return saved, monitor_snapshot



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

    session = _build_session_from_parts(weekend, driver_info)
    reader.last_update = update
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
    show_activity_log: bool = True
    show_tp_monitor: bool = False
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
        config.show_activity_log = bool(config.show_activity_log)
        config.show_tp_monitor = bool(getattr(config, "show_tp_monitor", False))
        config.check_updates_automatically = bool(getattr(config, "check_updates_automatically", True))
        return config

    def save(self, config: AppConfig) -> None:
        safe = AppConfig(**asdict(config))
        safe.download_workers_mode = str(safe.download_workers_mode).strip().lower()
        if safe.download_workers_mode not in {"auto", "manual"}:
            safe.download_workers_mode = "auto"
        safe.manual_download_workers = max(1, min(100, int(safe.manual_download_workers)))
        safe.manual_manifest_workers = max(1, min(100, int(safe.manual_manifest_workers)))
        safe.manual_save_workers = max(1, min(100, int(safe.manual_save_workers)))
        safe.max_concurrent_downloads = 8
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
        self._monitor_snapshot = ThroughputMonitorSnapshot()

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
    ) -> list[SavedFile]:
        keep_targets = set(preserve_targets or set()) if keep_my_livery_locally else set()
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
        paints_dir.mkdir(parents=True, exist_ok=True)
        temp_dir.mkdir(parents=True, exist_ok=True)
        cleanup_stale_temp_dirs(temp_dir)

        sdk_reader: IracingSdkReader | None = None
        next_sdk_open_at = 0.0

        last_session: SessionId | None = None
        last_session_fingerprint: tuple[SessionId, tuple[tuple[int, str], ...]] | None = None
        last_session_preserve_targets: set[tuple[bool, int]] = set()
        last_saved: list[SavedFile] = []
        pending_reload: PendingTextureReload | None = None
        last_poll_state: SdkPollState | None = None

        try:
            while not self._stop_event.is_set():
                config = self.get_config()

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
                        )
                        if config.auto_refresh_paints and last_session_fingerprint is not None:
                            pending_reload = PendingTextureReload(
                                fingerprint=last_session_fingerprint,
                                first_requested_at=time.monotonic(),
                            )
                    else:
                        logging.info("Manual clear requested, but there are no current downloaded paints to remove")

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
                    if last_saved and config.delete_downloaded_livery:
                        last_saved = self._cleanup_saved(
                            saved=last_saved,
                            keep_my_livery_locally=config.keep_my_livery_locally,
                            preserve_targets=last_session_preserve_targets,
                            reason=(
                                f"No active valid session detected. Clearing paints from previous session {last_session}"
                            ),
                            paints_root=paints_dir,
                        )
                    if sdk_reader is not None:
                        logging.debug("Closing SDK after inactive/invalid state so next session starts with a fresh SDK connection")
                        close_sdk_reader(sdk_reader)
                        sdk_reader = None
                        next_sdk_open_at = time.monotonic() + max(config.poll_seconds, 1.0)
                    last_session = None
                    last_session_fingerprint = None
                    last_session_preserve_targets = set()
                    pending_reload = None
                    self._stop_event.wait(max(config.poll_seconds, 0.2))
                    continue

                if poll_state is SdkPollState.UNCHANGED:
                    self._stop_event.wait(max(config.poll_seconds, 0.2))
                    continue

                assert session is not None
                current_fingerprint = session.fingerprint()
                forced_refresh = self._force_refresh_event.is_set()

                if last_session_fingerprint == current_fingerprint and not forced_refresh:
                    self._stop_event.wait(max(config.poll_seconds, 0.2))
                    continue

                if forced_refresh:
                    self._force_refresh_event.clear()
                    logging.info("Manual re-download requested for session %s", session.session_id.folder_name())

                if last_saved and config.cleanup_before_fetch:
                    reason = (
                        f"Refreshing current session files before new fetch for {session.session_id.folder_name()}"
                        if current_fingerprint == last_session_fingerprint
                        else f"Deleting paints from previous session {last_session}"
                    )
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
                last_saved, monitor_snapshot = process_session(
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
                )
                self._update_monitor_snapshot(monitor_snapshot)
                last_session = session.session_id
                last_session_fingerprint = current_fingerprint
                last_session_preserve_targets = session.local_preserve_targets()
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

        WNDPROCTYPE = ctypes.WINFUNCTYPE(ctypes.c_long, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)

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
        from tkinter import messagebox, scrolledtext, ttk

        self.tk = tk
        self.ttk = ttk
        self.messagebox = messagebox
        self.scrolledtext = scrolledtext
        self.config_store = ConfigStore()
        self.config = self.config_store.load()
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.service = DownloaderService(self.config, self.log_queue)
        self.service.set_status_callback(self._on_service_status)
        self._exiting = False
        self._launched_from_autostart = launched_from_autostart

        self.root = tk.Tk()
        self.root.title(APP_NAME)
        self.root.geometry("1230x500")
        self.root.minsize(1130, 430)
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
        self.show_activity_var = tk.BooleanVar(value=self.config.show_activity_log)
        self.show_tp_monitor_var = tk.BooleanVar(value=getattr(self.config, "show_tp_monitor", False))
        self.check_updates_var = tk.BooleanVar(value=getattr(self.config, "check_updates_automatically", True))
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

        self._build_ui()
        self._update_download_mode_ui()
        self._hide_console_window()
        self._apply_autostart(self.config.auto_start)
        self.service.start()
        self.instance_signal_server.start()
        self._update_log_visibility()
        self._update_monitor_visibility()
        self._schedule_update_check(initial=True)
        self.root.after(150, self._drain_logs)
        self.root.after(600, self._poll_service)
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
        outer.rowconfigure(2, weight=1, minsize=165)

        header = ttk.Frame(outer)
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(1, weight=1)
        ttk.Label(header, text=APP_NAME, font=("Segoe UI", 14, "bold")).grid(row=0, column=0, sticky="w")
        ttk.Label(header, text=f"Version {APP_VERSION}").grid(row=0, column=1, sticky="w", padx=(10, 0))
        ttk.Label(header, textvariable=self.status_var, font=("Segoe UI", 10, "bold")).grid(row=0, column=2, sticky="e")

        settings = ttk.Frame(outer)
        settings.grid(row=1, column=0, sticky="ew", pady=(10, 8))
        settings.columnconfigure(0, weight=1)
        settings.columnconfigure(1, weight=0)

        prefs = ttk.LabelFrame(settings, text="Settings", padding=10)
        prefs.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        perf = ttk.LabelFrame(settings, text="Downloads", padding=10)
        perf.grid(row=0, column=1, sticky="nsew")

        prefs.columnconfigure(0, weight=1)
        prefs.columnconfigure(1, weight=1)

        ttk.Label(prefs, text="General", font=("Segoe UI", 9, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(prefs, text="Auto start", variable=self.auto_start_var, command=self.on_setting_changed).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(prefs, text="Start minimized", variable=self.start_minimized_var, command=self.on_setting_changed).grid(row=1, column=1, sticky="w", padx=(12, 0))
        ttk.Checkbutton(prefs, text="Keep running in background on close", variable=self.minimize_to_tray_var, command=self.on_setting_changed).grid(row=2, column=0, sticky="w")
        ttk.Checkbutton(prefs, text="Auto refresh paints", variable=self.auto_refresh_var, command=self.on_setting_changed).grid(row=2, column=1, sticky="w", padx=(12, 0))
        ttk.Checkbutton(prefs, text="Check for updates automatically", variable=self.check_updates_var, command=self.on_setting_changed).grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))

        ttk.Separator(prefs, orient="horizontal").grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 8))
        ttk.Label(prefs, text="Session", font=("Segoe UI", 9, "bold")).grid(row=5, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(prefs, text="Update my own paints", variable=self.sync_my_livery_var, command=self.on_setting_changed).grid(row=6, column=0, sticky="w")
        ttk.Checkbutton(prefs, text="Keep my livery locally", variable=self.keep_my_livery_var, command=self.on_setting_changed).grid(row=6, column=1, sticky="w", padx=(12, 0))
        ttk.Checkbutton(prefs, text="Delete downloaded livery", variable=self.cleanup_on_exit_var, command=self.on_setting_changed).grid(row=7, column=0, sticky="w")
        ttk.Checkbutton(prefs, text="Show activity", variable=self.show_activity_var, command=self.on_setting_changed).grid(row=7, column=1, sticky="w", padx=(12, 0))
        ttk.Checkbutton(prefs, text="Verbose logs", variable=self.verbose_var, command=self.on_setting_changed).grid(row=8, column=0, sticky="w", pady=(2, 0))
        ttk.Checkbutton(prefs, text="Show TP monitor", variable=self.show_tp_monitor_var, command=self.on_setting_changed).grid(row=8, column=1, sticky="w", padx=(12, 0), pady=(2, 0))

        perf.columnconfigure(1, weight=1)
        ttk.Label(perf, text="Worker mode").grid(row=0, column=0, sticky="w")
        mode_combo = ttk.Combobox(
            perf,
            state="readonly",
            values=["Auto", "Manual"],
            width=10,
            textvariable=self.download_workers_mode_var,
        )
        mode_combo.grid(row=0, column=1, sticky="ew")
        mode_combo.bind("<<ComboboxSelected>>", lambda _e: self.on_download_workers_mode_changed())
        ttk.Label(perf, text="Manual manifests").grid(row=1, column=0, sticky="w", pady=(8, 0))
        self.manual_manifest_workers_spin = ttk.Spinbox(
            perf,
            from_=1,
            to=100,
            width=5,
            textvariable=self.manual_manifest_workers_var,
            command=self.on_manual_manifest_workers_changed,
        )
        self.manual_manifest_workers_spin.grid(row=1, column=1, sticky="w", pady=(8, 0))
        self.manual_manifest_workers_spin.bind("<FocusOut>", lambda _e: self.on_manual_manifest_workers_changed())
        self.manual_manifest_workers_spin.bind("<Return>", lambda _e: self.on_manual_manifest_workers_changed())
        ttk.Label(perf, text="Manual downloads").grid(row=2, column=0, sticky="w", pady=(6, 0))
        self.manual_workers_spin = ttk.Spinbox(
            perf,
            from_=1,
            to=100,
            width=5,
            textvariable=self.manual_download_workers_var,
            command=self.on_manual_download_workers_changed,
        )
        self.manual_workers_spin.grid(row=2, column=1, sticky="w", pady=(6, 0))
        self.manual_workers_spin.bind("<FocusOut>", lambda _e: self.on_manual_download_workers_changed())
        self.manual_workers_spin.bind("<Return>", lambda _e: self.on_manual_download_workers_changed())
        ttk.Label(perf, text="Manual saves").grid(row=3, column=0, sticky="w", pady=(6, 0))
        self.manual_save_workers_spin = ttk.Spinbox(
            perf,
            from_=1,
            to=100,
            width=5,
            textvariable=self.manual_save_workers_var,
            command=self.on_manual_save_workers_changed,
        )
        self.manual_save_workers_spin.grid(row=3, column=1, sticky="w", pady=(6, 0))
        self.manual_save_workers_spin.bind("<FocusOut>", lambda _e: self.on_manual_save_workers_changed())
        self.manual_save_workers_spin.bind("<Return>", lambda _e: self.on_manual_save_workers_changed())
        ttk.Button(perf, text="Refresh paints", command=self.redownload_now).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Label(
            perf,
            text="Auto = adaptive workers • Manual = fixed manifests, downloads, and saves used in every session (1-100)",
            foreground="#666666",
        ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(6, 0))

        actions = ttk.Frame(outer)
        actions.grid(row=2, column=0, sticky="nsew")
        actions.columnconfigure(0, weight=1)
        actions.rowconfigure(2, weight=1, minsize=145)

        buttons = ttk.Frame(actions)
        buttons.grid(row=0, column=0, sticky="ew")
        buttons.columnconfigure(0, weight=1)
        ttk.Button(buttons, text="Clear downloaded", command=self.clear_downloaded_now).pack(side="left")
        ttk.Button(buttons, text="Check updates", command=self.check_updates_now).pack(side="left", padx=(8, 0))
        ttk.Button(buttons, text="Paint folder", command=self.open_paint_folder).pack(side="right")

        self.monitor_frame = ttk.LabelFrame(actions, text="TP worker monitor", padding=8)
        self.monitor_frame.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        self.monitor_frame.columnconfigure(0, weight=1)
        ttk.Label(self.monitor_frame, textvariable=self.tp_monitor_summary_var, justify="left").grid(row=0, column=0, sticky="w")
        ttk.Label(self.monitor_frame, textvariable=self.tp_monitor_detail_var, justify="left").grid(row=1, column=0, sticky="w", pady=(4, 0))
        ttk.Label(self.monitor_frame, textvariable=self.tp_monitor_save_var, justify="left").grid(row=2, column=0, sticky="w", pady=(4, 0))
        ttk.Button(self.monitor_frame, text="Reset TP monitor", command=self.reset_tp_monitor).grid(row=0, column=1, rowspan=3, sticky="ns", padx=(12, 0))

        self.log_frame = ttk.LabelFrame(actions, text="Activity", padding=8)
        self.log_frame.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        self.log_text = self.scrolledtext.ScrolledText(self.log_frame, height=10, wrap="word", font=("Consolas", 9))
        self.log_text.pack(fill="both", expand=True)
        self.log_text.insert("end", f"{APP_NAME} {APP_VERSION} ready.\n")
        self.log_text.configure(state="disabled")

        footer = ttk.Frame(outer)
        footer.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(footer, text="Always active while open").pack(side="left")
        ttk.Label(footer, textvariable=self.update_status_var).pack(side="right", padx=(0, 12))
        ttk.Label(footer, text=f"Version: {APP_VERSION}").pack(side="right")

    def _append_log(self, line: str) -> None:
        self.log_text.configure(state="normal")
        self.log_text.insert("end", line + "\n")
        total_lines = int(self.log_text.index("end-1c").split(".")[0])
        if total_lines > 2000:
            self.log_text.delete("1.0", f"{max(1, total_lines - 1500)}.0")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _drain_logs(self) -> None:
        try:
            while True:
                line = self.log_queue.get_nowait()
                self._append_log(line)
        except queue.Empty:
            pass
        if not self._exiting:
            self.root.after(150, self._drain_logs)

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

    def _poll_service(self) -> None:
        self._refresh_monitor_ui()
        if not self._exiting and not self.service.is_running():
            self._append_log("Service stopped unexpectedly. Restarting...")
            self.service.start()
        if not self._exiting:
            self.root.after(600, self._poll_service)

    def _on_service_status(self, value: str) -> None:
        self.root.after(0, lambda: self.status_var.set(value))

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
        return AppConfig(
            auto_start=bool(self.auto_start_var.get()),
            start_minimized=bool(self.start_minimized_var.get()),
            minimize_to_tray_on_close=bool(self.minimize_to_tray_var.get()),
            auto_refresh_paints=bool(self.auto_refresh_var.get()),
            cleanup_before_fetch=bool(self.cleanup_before_fetch_var.get()),
            delete_downloaded_livery=bool(self.cleanup_on_exit_var.get()),
            sync_my_livery_from_server=bool(self.sync_my_livery_var.get()),
            keep_my_livery_locally=bool(self.keep_my_livery_var.get()),
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

    def on_setting_changed(self) -> None:
        if self.verbose_var.get() and not self.show_activity_var.get():
            self.show_activity_var.set(True)
        self.config = self._read_ui_config()
        self.config_store.save(self.config)
        self._apply_autostart(self.config.auto_start)
        self.service.update_config(self.config)
        self._update_log_visibility()
        self._update_monitor_visibility()
        self._update_download_mode_ui()
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
                if getattr(sys, "frozen", False):
                    command = f'"{sys.executable}" --autostart-launched'
                else:
                    command = f'"{sys.executable}" "{Path(__file__).resolve()}" --autostart-launched'
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
        if sys.platform != "win32":
            return
        try:
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                ctypes.windll.user32.ShowWindow(hwnd, 0)
        except Exception:
            pass

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

    def reset_tp_monitor(self) -> None:
        self.service.reset_monitor_snapshot()
        self._refresh_monitor_ui()
        self._append_log("TP worker monitor reset.")

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


def run_headless() -> int:
    args = parse_args()
    setup_logging(args.verbose)
    config = AppConfig(
        auto_start=False,
        start_minimized=False,
        minimize_to_tray_on_close=False,
        auto_refresh_paints=True,
        cleanup_before_fetch=True,
        delete_downloaded_livery=not args.keep_session_paints,
        sync_my_livery_from_server=True,
        keep_my_livery_locally=not args.keep_session_paints,
        show_activity_log=False,
        check_updates_automatically=False,
        download_workers_mode="auto",
        manual_download_workers=max(1, min(100, args.max_concurrent_downloads)),
        max_concurrent_downloads=8,
        verbose=args.verbose,
        poll_seconds=max(args.poll_seconds, 0.2),
        retries=max(1, args.retries),
        retry_backoff_seconds=max(0.1, args.retry_backoff_seconds),
    )
    service = DownloaderService(config)
    stop_event = threading.Event()

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
        service.stop()
    return 0


def main() -> int:
    args = parse_args()
    if args.nogui:
        return run_headless()

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
