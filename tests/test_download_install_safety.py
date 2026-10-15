import bz2
import importlib.util
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_install_safety_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


class _Response:
    def __init__(self, chunks=(), status=200):
        self.chunks = list(chunks)
        self.status_code = status

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def iter_content(self, chunk_size=None):
        for chunk in self.chunks:
            if isinstance(chunk, Exception):
                raise chunk
            yield chunk


GOOD_PAINT = b"TGA" + b"\x01" * 4096
OLD_PAINT = b"OLD" + b"\x02" * 2048


class DownloadAndInstallTests(unittest.TestCase):
    """Download -> install of one paint, against a temporary paint folder."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="nishizumi-install-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.temp_dir = self.root / "temp"
        self.paints = self.root / "paint"
        appdata = mock.patch.dict(os.environ, {"APPDATA": str(self.root / "appdata")})
        appdata.start()
        self.addCleanup(appdata.stop)
        self.http = mock.Mock()
        session = mock.patch.object(APP, "get_thread_http_session", return_value=self.http)
        session.start()
        self.addCleanup(session.stop)
        no_wait = mock.patch.object(APP.time, "sleep")
        no_wait.start()
        self.addCleanup(no_wait.stop)
        self.download_id = APP.DownloadId(5, "mx5 mx52016", APP.PaintType.CAR)
        self.target = APP.save_path_for(self.download_id, self.paints)

    def _item(self, url="https://example.invalid/car_5.tga.bz2"):
        return APP.DownloadFile(download_id=self.download_id, url=url)

    def _run(self, *responses, url="https://example.invalid/car_5.tga.bz2", retries=3):
        self.http.get.side_effect = list(responses)
        return APP._download_and_save_with_auto_repair(
            session_id=APP.SessionId(1, 2),
            temp_dir=self.temp_dir,
            paints_dir=self.paints,
            items=[self._item(url)],
            retries=retries,
            retry_backoff_seconds=0.0,
        )

    def _existing_paint(self):
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_bytes(OLD_PAINT)

    def _leftovers(self):
        return sorted(p.name for p in self.root.rglob("*.tmp")) + sorted(
            p.name for p in self.temp_dir.rglob("*") if p.is_file()
        )

    def test_a_good_download_is_installed_and_leaves_nothing_behind(self):
        self._existing_paint()
        saved = self._run(_Response([bz2.compress(GOOD_PAINT)]))
        self.assertEqual([s.file_path for s in saved], [self.target])
        self.assertEqual(self.target.read_bytes(), GOOD_PAINT)
        self.assertEqual(self._leftovers(), [])

    def test_a_truncated_bz2_keeps_the_old_paint(self):
        self._existing_paint()
        cut = bz2.compress(GOOD_PAINT)[:-20]
        saved = self._run(_Response([cut]), _Response([cut]))
        self.assertEqual(saved, [])
        self.assertEqual(self.target.read_bytes(), OLD_PAINT)
        self.assertEqual(self._leftovers(), [])

    def test_an_empty_bz2_body_keeps_the_old_paint(self):
        self._existing_paint()
        saved = self._run(_Response([b""]), _Response([b""]))
        self.assertEqual(saved, [])
        self.assertEqual(self.target.read_bytes(), OLD_PAINT)

    def test_an_empty_tga_body_keeps_the_old_paint(self):
        self._existing_paint()
        url = "https://example.invalid/car_5.tga"
        saved = self._run(_Response([b""]), _Response([b""]), url=url)
        self.assertEqual(saved, [])
        self.assertEqual(self.target.read_bytes(), OLD_PAINT)

    def test_a_connection_dropped_mid_body_is_retried(self):
        self._existing_paint()
        dropped = _Response([b"BZh", requests.exceptions.ChunkedEncodingError("reset")])
        saved = self._run(dropped, _Response([bz2.compress(GOOD_PAINT)]))
        self.assertEqual(len(saved), 1)
        self.assertEqual(self.target.read_bytes(), GOOD_PAINT)
        self.assertEqual(self.http.get.call_count, 2)

    def test_a_missing_paint_is_not_retried(self):
        saved = self._run(_Response(status=404), _Response(status=404))
        self.assertEqual(saved, [])
        # One request per auto-repair round, never one per retry.
        self.assertEqual(self.http.get.call_count, 2)
        self.assertFalse(self.target.exists())

    def test_server_errors_stop_after_the_retry_budget(self):
        responses = [_Response(status=503) for _ in range(10)]
        saved = self._run(*responses, retries=3)
        self.assertEqual(saved, [])
        # 3 retries x 2 auto-repair rounds.
        self.assertEqual(self.http.get.call_count, 6)

    def test_a_target_locked_for_good_keeps_the_old_paint(self):
        self._existing_paint()
        real_replace = os.replace

        def locked(src, dst):
            if Path(dst) == self.target:
                raise PermissionError(32, "being used by another process")
            return real_replace(src, dst)

        with mock.patch.object(APP.os, "replace", side_effect=locked):
            saved = self._run(_Response([bz2.compress(GOOD_PAINT)]), _Response([bz2.compress(GOOD_PAINT)]))
        self.assertEqual(saved, [])
        self.assertEqual(self.target.read_bytes(), OLD_PAINT)
        self.assertEqual(self._leftovers(), [])

    def test_a_short_lock_on_the_target_is_retried(self):
        self._existing_paint()
        real_replace = os.replace
        failures = {"left": 1}

        def locked_once(src, dst):
            if Path(dst) == self.target and failures["left"]:
                failures["left"] -= 1
                raise PermissionError(32, "being used by another process")
            return real_replace(src, dst)

        with mock.patch.object(APP.os, "replace", side_effect=locked_once):
            saved = self._run(_Response([bz2.compress(GOOD_PAINT)]))
        self.assertEqual(len(saved), 1)
        self.assertEqual(self.target.read_bytes(), GOOD_PAINT)
        self.assertEqual(self.http.get.call_count, 1)

    def test_a_disk_error_while_writing_keeps_the_old_paint(self):
        self._existing_paint()
        with mock.patch.object(APP, "_copy_bz2_capped", side_effect=OSError(28, "No space left on device")):
            saved = self._run(_Response([bz2.compress(GOOD_PAINT)]), _Response([bz2.compress(GOOD_PAINT)]))
        self.assertEqual(saved, [])
        self.assertEqual(self.target.read_bytes(), OLD_PAINT)
        self.assertEqual(self._leftovers(), [])

    def test_the_replaced_paint_is_kept_in_the_history(self):
        self._existing_paint()
        self._run(_Response([bz2.compress(GOOD_PAINT)]))
        history = [p for p in APP.default_paint_history_dir().rglob("*") if p.is_file() and p.suffix == ".tga"]
        self.assertEqual([p.read_bytes() for p in history], [OLD_PAINT])


class SavePathTests(unittest.TestCase):
    def test_a_car_folder_cannot_escape_the_paint_folder(self):
        paints = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, paints, True)
        for directory in ("..\\..\\Windows", "../../etc", "C:\\Windows"):
            with self.subTest(directory=directory):
                try:
                    path = APP.save_path_for(APP.DownloadId(5, directory, APP.PaintType.CAR), paints)
                except ValueError:
                    continue
                self.assertTrue(path.resolve().is_relative_to(paints.resolve()), path)

    def test_team_and_user_paints_never_share_a_file(self):
        paints = Path("C:/paint")
        user = APP.save_path_for(APP.DownloadId(5, "mx5", APP.PaintType.CAR), paints)
        team = APP.save_path_for(APP.DownloadId(5, "mx5", APP.PaintType.CAR, is_team_paint=True), paints)
        self.assertNotEqual(user, team)
        self.assertEqual(team.name, "car_team_5.tga")


if __name__ == "__main__":
    unittest.main()
