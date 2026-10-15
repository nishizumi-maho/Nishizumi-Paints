"""process_session end to end: manifests -> downloads -> installed paints, HTTP faked.

The service-loop tests replace process_session with a fake; these run the real one
against a temporary paint folder, with random fallbacks off and no real network.
"""
import bz2
import gc
import importlib.util
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_process_session_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)

CAR = "dirtlatemodel 350"


def setUpModule():
    # Tk widgets left behind by other test modules must be collected on the main
    # thread; process_session's worker threads collecting them aborts Tcl.
    gc.collect()


def _paint_bytes(user_id, kind):
    return f"{kind}-{user_id}".encode() * 512


class _Response:
    def __init__(self, status=200, text="", body=b""):
        self.status_code = status
        self.text = text
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def iter_content(self, chunk_size=None):
        yield self.body


class _FakeTradingPaints:
    """Answers manifests for every user and serves their files; some files can be missing."""

    def __init__(self, missing_files=()):
        self.missing_files = set(missing_files)
        self.requests = []

    def _manifest(self, user_ids):
        cars = "".join(
            "<Car>"
            f"<carid>1</carid><userid>{uid}</userid><teamid>0</teamid><directory>{CAR}</directory><type>car</type>"
            f"<file>https://files.example.invalid/{uid}/car.tga.bz2</file>"
            "</Car>"
            "<Car>"
            f"<carid>1</carid><userid>{uid}</userid><teamid>0</teamid><directory>helmets</directory><type>helmet</type>"
            f"<file>https://files.example.invalid/{uid}/helmet.tga.bz2</file>"
            "</Car>"
            for uid in user_ids
        )
        return f"<Response>{cars}</Response>"

    def post(self, url, data=None, timeout=None, **_kwargs):
        self.requests.append(("POST", url))
        listed = str((data or {}).get("list", ""))
        # list is "<user>=<car dir>=<team>=<numbers>=", one entry per driver, comma separated.
        user_ids = [int(entry.split("=", 1)[0]) for entry in listed.split(",") if entry.split("=", 1)[0].isdigit()]
        return _Response(text=self._manifest(user_ids))

    def get(self, url, timeout=None, stream=False, headers=None, **_kwargs):
        self.requests.append(("GET", url))
        match = re.match(r"https://files\.example\.invalid/(\d+)/(car|helmet)\.tga\.bz2$", url)
        if match:
            uid, kind = int(match.group(1)), match.group(2)
            if (uid, kind) in self.missing_files:
                return _Response(status=404)
            return _Response(body=bz2.compress(_paint_bytes(uid, kind)))
        user = re.search(r"[?&]user=(\d+)", url)
        if "fetch_user" in url and user:
            return _Response(text=self._manifest([int(user.group(1))]))
        return _Response(status=404)


class ProcessSessionIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="nishizumi-process-session-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.paints = self.root / "paint"
        self.paints.mkdir()
        for patcher in (
            mock.patch.dict(os.environ, {"APPDATA": str(self.root / "appdata")}),
            mock.patch.object(APP.time, "sleep"),
            mock.patch.object(APP, "compute_retry_delay", lambda _base, _attempt: 0.0),
            mock.patch.object(APP, "_fetch_tp_car_identity_doc", side_effect=RuntimeError("offline in tests")),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
        with APP._TP_FETCH_URL_DOWN_LOCK:
            APP._TP_FETCH_URL_DOWN_UNTIL.clear()
            APP._TP_FETCH_HOST_UNREACHABLE_UNTIL.clear()

    def _run(self, http, user_ids, local_user_id=1):
        users = {APP.SessionUser(user_id=uid, directory=CAR, car_idx=index) for index, uid in enumerate(user_ids)}
        session = APP.Session(
            session_id=APP.SessionId(555, 777),
            users=users,
            local_user_id=local_user_id,
            event_time_raw="2:00 pm",
            series_id=164,
        )
        with mock.patch.object(APP, "get_thread_http_session", return_value=http):
            saved, _monitor, _drivers = APP.process_session(
                session=session,
                paints_dir=self.paints,
                temp_dir=self.root / "temp",
                ai_rosters_dir=None,
                max_concurrent_manifests=4,
                max_concurrent_downloads=4,
                download_workers_mode="manual",
                manual_manifest_workers=4,
                manual_download_workers=4,
                manual_save_workers=4,
                retries=2,
                retry_backoff_seconds=0.0,
                sync_my_livery_from_server=True,
                random_fallback_real_drivers=False,
                random_fallback_ai=False,
                random_helmets=False,
                random_suits=False,
                random_helmets_real_drivers=False,
                random_helmets_ai=False,
                random_suits_real_drivers=False,
                random_suits_ai=False,
                disable_random_in_team_events=True,
                disable_random_for_local_user=True,
                team_driver_personal_fallback_slots=(),
                ai_collection_skip_random_cars=True,
                ai_collection_skip_random_helmets=True,
                ai_collection_skip_random_suits=True,
                keep_tp_paints_in_random_pool=False,
                max_random_pool_gb=0.0,
                tp_fallback_mode="local",
            )
        return saved

    def _installed(self, uid, kind):
        path = self.paints / CAR / f"car_{uid}.tga" if kind == "car" else self.paints / f"helmet_{uid}.tga"
        return path.read_bytes() if path.exists() else None

    def test_every_driver_gets_their_own_paints(self):
        http = _FakeTradingPaints()
        saved = self._run(http, [1, 2, 3])
        for uid in (1, 2, 3):
            self.assertEqual(self._installed(uid, "car"), _paint_bytes(uid, "car"), uid)
            self.assertEqual(self._installed(uid, "helmet"), _paint_bytes(uid, "helmet"), uid)
        self.assertEqual(len(saved), 6)
        self.assertEqual(sorted(p.name for p in self.root.rglob("*.tmp")), [])
        downloads = [url for method, url in http.requests if method == "GET" and "files.example" in url]
        self.assertEqual(len(downloads), len(set(downloads)), "a file was downloaded twice")

    def test_one_missing_file_does_not_cost_the_other_drivers_their_paints(self):
        http = _FakeTradingPaints(missing_files={(2, "car")})
        self._run(http, [1, 2, 3])
        self.assertIsNone(self._installed(2, "car"))
        self.assertEqual(self._installed(2, "helmet"), _paint_bytes(2, "helmet"))
        for uid in (1, 3):
            self.assertEqual(self._installed(uid, "car"), _paint_bytes(uid, "car"), uid)

    def test_a_second_pass_for_a_new_driver_downloads_only_that_driver(self):
        http = _FakeTradingPaints()
        first = self._run(http, [1, 2])
        http.requests.clear()
        second = self._run(http, [3])  # the service passes only the joiner after a join
        self.assertEqual(self._installed(3, "car"), _paint_bytes(3, "car"))
        self.assertEqual(self._installed(1, "car"), _paint_bytes(1, "car"))
        downloads = [url for method, url in http.requests if method == "GET" and "files.example" in url]
        self.assertTrue(downloads and all("/3/" in url for url in downloads), downloads)
        self.assertEqual(len(first) + len(second), 6)

if __name__ == "__main__":
    unittest.main()
