import bz2
import importlib.util
import os
import re
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

import requests


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_review_fixes_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)

CAR = "dirtlatemodel 350"


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
    def __init__(self):
        self.requests = []

    def _manifest(self, user_ids):
        cars = "".join(
            "<Car>"
            f"<carid>1</carid><userid>{uid}</userid><teamid>0</teamid><directory>{CAR}</directory><type>car</type>"
            f"<file>https://files.example.invalid/{uid}/car.tga.bz2</file>"
            "</Car>"
            for uid in user_ids
        )
        return f"<Response>{cars}</Response>"

    def post(self, url, data=None, timeout=None, **_kwargs):
        self.requests.append(("POST", url))
        listed = str((data or {}).get("list", ""))
        user_ids = [int(entry.split("=", 1)[0]) for entry in listed.split(",") if entry.split("=", 1)[0].isdigit()]
        return _Response(text=self._manifest(user_ids))

    def get(self, url, timeout=None, stream=False, headers=None, **_kwargs):
        self.requests.append(("GET", url))
        match = re.match(r"https://files\.example\.invalid/(\d+)/car\.tga\.bz2$", url)
        if match:
            return _Response(body=bz2.compress(f"car-{match.group(1)}".encode() * 512))
        user = re.search(r"[?&]user=(\d+)", url)
        if "fetch_user" in url and user:
            return _Response(text=self._manifest([int(user.group(1))]))
        return _Response(status=404)


class _ProcessSessionExtrasTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="nishizumi-review-fixes-"))
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

    def _run_process_session(self, http):
        users = {APP.SessionUser(user_id=2, directory=CAR, car_idx=0)}
        session = APP.Session(
            session_id=APP.SessionId(555, 777),
            users=users,
            local_user_id=1,
            event_time_raw="2:00 pm",
            series_id=164,
        )
        decal = self.paints / CAR / "decal_2.tga"

        def fake_extras(_session, _users, paints_dir, **_kwargs):
            target = Path(paints_dir) / CAR / "decal_2.tga"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"league decal")
            return [target]

        with mock.patch.object(APP, "get_thread_http_session", return_value=http), mock.patch.object(
            APP, "apply_post_save_extras", side_effect=fake_extras
        ):
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
        return decal, saved

    def test_extras_are_tracked_for_cleanup(self):
        decal, saved = self._run_process_session(_FakeTradingPaints())
        tracked = [item.file_path for item in saved]
        self.assertIn(decal, tracked)
        APP.delete_saved(saved, paints_root=self.paints)
        self.assertFalse(decal.exists(), "the extra decal was not swept by session cleanup")


class _StaleSpecMapTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="nishizumi-review-spec-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.paints = self.root / "paint"
        self.paints.mkdir()
        self.session = APP.Session(
            session_id=APP.SessionId(1, 2),
            users={
                APP.SessionUser(user_id=1, directory=CAR, car_idx=0),
                APP.SessionUser(user_id=2, directory=CAR, car_idx=1),
            },
            local_user_id=1,
        )

    def _spec_path(self, user_id, *, numbered=False, team=False):
        return APP.save_path_for(
            APP.DownloadId(user_id, CAR, APP.PaintType.CAR_SPEC, is_team_paint=team, is_numbered_car_spec=numbered),
            self.paints,
        )

    def _saved_car(self, user_id, *, team=False):
        path = APP.save_path_for(
            APP.DownloadId(user_id, CAR, APP.PaintType.CAR, is_team_paint=team),
            self.paints,
        )
        return APP.SavedFile(self.session.session_id, APP.DownloadId(user_id, CAR, APP.PaintType.CAR, is_team_paint=team), path)

    def test_fallback_car_without_spec_removes_old_spec(self):
        normal = self._spec_path(2)
        numbered = self._spec_path(2, numbered=True)
        for path in (normal, numbered):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"previous driver spec")
        local_spec = self._spec_path(1)
        local_spec.write_bytes(b"my spec")

        removed = APP._remove_stale_spec_maps_for_saved([self._saved_car(2)], self.paints, self.session)
        self.assertEqual(removed, 2)
        self.assertFalse(normal.exists())
        self.assertFalse(numbered.exists())
        self.assertTrue(local_spec.exists(), "the local user's spec map was removed")

        removed_local = APP._remove_stale_spec_maps_for_saved([self._saved_car(1)], self.paints, self.session)
        self.assertEqual(removed_local, 0)
        self.assertTrue(local_spec.exists())


class _PaintPayloadValidationTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="nishizumi-review-payload-"))
        self.addCleanup(shutil.rmtree, self.root, True)

    def _write(self, name, payload):
        path = self.root / name
        path.write_bytes(payload)
        return path

    def test_paint_payload_validation(self):
        from PIL import Image

        valid = self.root / "valid.tga"
        Image.new("RGBA", (8, 8), (10, 20, 30, 255)).save(valid, format="TGA", compression="tga_rle")
        self.assertTrue(APP._paint_payload_looks_valid(valid, APP.PaintType.CAR))

        truncated = self._write("truncated.tga", valid.read_bytes()[:10])
        self.assertFalse(APP._paint_payload_looks_valid(truncated, APP.PaintType.CAR))

        header = bytearray(18)
        header[2] = 3  # indexed colour, not truecolor
        header[12:14] = (8).to_bytes(2, "little")
        header[14:16] = (8).to_bytes(2, "little")
        header[16] = 32
        bad_type = self._write("bad_type.tga", bytes(header) + b"\0" * 64)
        self.assertFalse(APP._paint_payload_looks_valid(bad_type, APP.PaintType.CAR))

        json_body = self._write("json.tga", b'{"error": "not a paint"}')
        self.assertFalse(APP._paint_payload_looks_valid(json_body, APP.PaintType.CAR))

        no_magic = self._write("payload.bz2", b"not a bz2 stream")
        self.assertFalse(APP._paint_payload_looks_valid(no_magic, APP.PaintType.CAR))
        real_bz2 = self._write("payload-real.bz2", bz2.compress(b"paint"))
        self.assertTrue(APP._paint_payload_looks_valid(real_bz2, APP.PaintType.CAR))

        mip = self._write("spec.mip", b"spec map")
        self.assertTrue(APP._paint_payload_looks_valid(mip, APP.PaintType.CAR_SPEC))
        empty_mip = self._write("empty.mip", b"")
        self.assertFalse(APP._paint_payload_looks_valid(empty_mip, APP.PaintType.CAR_SPEC))


class _StuckServiceThread:
    def __init__(self):
        self.joins = []

    def is_alive(self):
        return True

    def join(self, timeout=None):
        self.joins.append(timeout)


class _ServiceStopCleanupTests(unittest.TestCase):
    def test_stop_runs_cleanup_when_worker_is_stuck(self):
        service = APP.DownloaderService(APP.AppConfig())
        calls = []
        service._exit_cleanup = lambda: calls.append("cleanup")
        service._thread = _StuckServiceThread()

        service.stop(join_timeout=0.01)
        service.stop(join_timeout=0.01)

        self.assertEqual(calls, ["cleanup"])


if __name__ == "__main__":
    unittest.main()
