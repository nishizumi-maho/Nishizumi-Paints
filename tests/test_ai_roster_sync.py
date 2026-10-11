import importlib.util
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_ai_roster_sync_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


CAR = "dallarap217"


def _driver(number, name, car_tga=None):
    return {
        "driverName": name,
        "carNumber": str(number),
        "carId": 128,
        "carClassId": 0,
        "carPath": CAR,
        "carTgaName": car_tga,
        "helmetTgaName": None,
        "suitTgaName": None,
    }


class _TempDir:
    def make_tmp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        return tmp


class RosterAssetProbeTests(_TempDir, unittest.TestCase):
    def test_an_existing_spec_map_is_checked_at_most_once_a_day(self):
        roster = self.make_tmp() / "My Roster"
        roster.mkdir()
        (roster / "car_1234.tga").write_bytes(b"car")
        (roster / "car_1234_spec.mip").write_bytes(b"spec")
        drivers = [_driver(1, "Alpha", "car_1234.tga")]
        probes = []

        def fake_probe(url):
            probes.append(url)
            return 200

        with mock.patch.object(APP, "_probe_optional_ai_roster_asset_status", side_effect=fake_probe), \
             mock.patch.object(APP, "get_thread_http_session", side_effect=AssertionError("no download expected")):
            APP.sync_ai_roster_collection_assets(roster, drivers, retries=1, retry_backoff_seconds=0.1)
            self.assertEqual(len(probes), 1)
            APP.sync_ai_roster_collection_assets(roster, drivers, retries=1, retry_backoff_seconds=0.1)
            self.assertEqual(len(probes), 1, "the spec map was checked again on the next sync")
        state = json.loads((roster / APP.AI_ROSTER_PROBE_STATE_FILENAME).read_text(encoding="utf-8"))
        self.assertIn("car_1234_spec.mip", state)


class RosterSyncCompletionTests(_TempDir, unittest.TestCase):
    def test_a_failed_list_fetch_is_not_counted_as_synced(self):
        with mock.patch.object(APP, "fetch_ai_roster_list", side_effect=RuntimeError("offline")):
            result = APP.sync_ai_rosters(42, self.make_tmp(), retries=1, retry_backoff_seconds=0.1)
        self.assertFalse(result.completed)

    def test_an_account_without_rosters_is_synced(self):
        with mock.patch.object(APP, "fetch_ai_roster_list", return_value=[]):
            result = APP.sync_ai_rosters(42, self.make_tmp(), retries=1, retry_backoff_seconds=0.1)
        self.assertTrue(result.completed)

    def test_stopping_ends_the_sync_between_rosters(self):
        stop = threading.Event()
        stop.set()
        rosters = [APP.AIWebRosterItem(roster_id="1", name="A", roster_file="a.json")]
        with mock.patch.object(APP, "fetch_ai_roster_list", return_value=rosters), \
             mock.patch.object(APP, "fetch_ai_roster_json", side_effect=AssertionError("must not fetch after stop")):
            result = APP.sync_ai_rosters(42, self.make_tmp(), retries=1, retry_backoff_seconds=0.1, cancel_event=stop)
        self.assertFalse(result.completed)


class RosterFileTests(_TempDir, unittest.TestCase):
    def test_an_unchanged_file_is_not_rewritten(self):
        path = self.make_tmp() / "roster.json"
        self.assertTrue(APP._write_text_if_changed(path, '{"drivers": []}'))
        os.utime(path, (1_000_000, 1_000_000))
        self.assertFalse(APP._write_text_if_changed(path, '{"drivers": []}'))
        self.assertEqual(path.stat().st_mtime, 1_000_000)
        self.assertTrue(APP._write_text_if_changed(path, '{"drivers": [1]}'))
        self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_a_parsed_roster_is_reused_until_the_file_changes(self):
        roster = self.make_tmp()
        (roster / "roster.json").write_text(json.dumps({"drivers": [_driver(1, "Alpha")]}), encoding="utf-8")
        real_loads = APP.json.loads
        with mock.patch.object(APP.json, "loads", side_effect=real_loads) as loads:
            _payload, first = APP._read_ai_roster_payload(roster)
            first[0]["driverName"] = "changed by a caller"
            _payload, second = APP._read_ai_roster_payload(roster)
            self.assertEqual(loads.call_count, 1)
        self.assertEqual(second[0]["driverName"], "Alpha")
        (roster / "roster.json").write_text(json.dumps({"drivers": [_driver(1, "Bravo"), _driver(2, "C")]}), encoding="utf-8")
        _payload, third = APP._read_ai_roster_payload(roster)
        self.assertEqual(third[0]["driverName"], "Bravo")


class RosterInferenceTests(_TempDir, unittest.TestCase):
    def _roster(self, root, name, meta):
        folder = root / name
        folder.mkdir()
        drivers = [_driver(index, f"Driver {index}") for index in range(1, 6)]
        (folder / "roster.json").write_text(json.dumps({"drivers": drivers}), encoding="utf-8")
        (folder / APP.AI_ROSTER_META_FILENAME).write_text(json.dumps(meta), encoding="utf-8")
        return folder

    def test_a_tie_between_a_roster_and_its_local_copy_does_not_flip(self):
        root = self.make_tmp()
        tp = self._roster(root, "Club", {"roster_id": "7", "name": "Club", "is_local": False})
        local = self._roster(root, "Club (local)", {"is_local": True, "name": "Club (local)"})
        users = {
            APP.SessionUser(user_id=9700 + index, directory=CAR, is_ai=True, display_name=f"Driver {index}", number=str(index))
            for index in range(1, 6)
        }
        session = APP.Session(session_id=APP.SessionId(1, 2), users=users, ai_driver_count=5)
        picks = set()
        for newest in (tp, local, tp):
            later = time.time() + len(picks) + 10
            os.utime(newest / "roster.json", (later, later))
            picks.add(APP._infer_active_ai_roster_dir_from_session(session, root))
        self.assertEqual(picks, {local})


class UiTaskTests(unittest.TestCase):
    def test_button_work_runs_off_the_tk_thread(self):
        ui = mock.MagicMock()
        ui.__dict__["_ui_tasks_in_progress"] = set()
        ui.root.after.side_effect = lambda _delay, callback: callback()
        threads = []
        finished = threading.Event()

        def done(result, error):
            threads.append(("done", result, error))
            finished.set()

        APP.DownloaderUI._run_ui_task(ui, "job", "Job", lambda: threads.append(threading.current_thread().name) or 7, done)
        self.assertTrue(finished.wait(5.0))
        self.assertNotEqual(threads[0], threading.current_thread().name)
        self.assertEqual(threads[1], ("done", 7, None))


if __name__ == "__main__":
    unittest.main()
