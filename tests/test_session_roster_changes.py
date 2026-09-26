import gc
import importlib.util
import shutil
import sys
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_roster_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


def setUpModule():
    # Tk widgets left behind by other test modules must be collected on the main
    # thread; letting a worker thread started here collect them aborts Tcl.
    gc.collect()


CAR = "dirtlatemodel 350"


class FakeSdk:
    """Just enough of pyirsdk for the service loop and the cancel monitor."""

    def __init__(self, session_id=555, sub_session_id=777):
        self._lock = threading.Lock()
        self.session_id = session_id
        self.sub_session_id = sub_session_id
        self.time_of_day = "2:00 pm"
        self.drivers = []
        self.session_info_update = 1
        self.is_initialized = True
        self.is_connected = True

    def startup(self):
        return True

    def shutdown(self):
        pass

    def freeze_var_buffer_latest(self):
        pass

    def reload_texture(self, _car_idx):
        pass

    def add_driver(self, user_id):
        with self._lock:
            self.drivers.append(
                {
                    "CarIdx": len(self.drivers),
                    "UserID": user_id,
                    "UserName": f"Driver {user_id}",
                    "CarPath": CAR,
                    "TeamID": 0,
                    "CarNumber": str(user_id),
                }
            )
            self.session_info_update += 1

    def change(self, **fields):
        with self._lock:
            for key, value in fields.items():
                setattr(self, key, value)
            self.session_info_update += 1

    def __getitem__(self, key):
        with self._lock:
            if key == "WeekendInfo":
                return {
                    "SessionID": self.session_id,
                    "SubSessionID": self.sub_session_id,
                    "TeamRacing": 0,
                    "SeriesID": 164,
                    "TrackName": "lanier dirt",
                    "WeekendOptions": {"TimeOfDay": self.time_of_day},
                }
            if key == "DriverInfo":
                return {"DriverCarIdx": 0, "DriverUserID": 1, "Drivers": [dict(d) for d in self.drivers]}
            if key == "LoadNumTextures":
                return False
            if key == "OkToReloadTextures":
                return True
            if key == "SessionInfoUpdate":
                return self.session_info_update
        raise KeyError(key)


def _wait_until(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def _session(user_ids, session_id=555, time_of_day="2:00 pm"):
    users = {APP.SessionUser(user_id=uid, directory=CAR, car_idx=index) for index, uid in enumerate(user_ids)}
    return APP.Session(
        session_id=APP.SessionId(session_id, 777),
        users=users,
        local_user_id=1,
        event_time_raw=time_of_day,
        series_id=164,
    )


class SessionIdentityFingerprintTests(unittest.TestCase):
    def test_a_driver_joining_keeps_the_identity(self):
        before = _session([1, 2, 3])
        after = _session([1, 2, 3, 4])
        self.assertNotEqual(before.fingerprint(), after.fingerprint())
        self.assertEqual(APP.session_identity_fingerprint(before), APP.session_identity_fingerprint(after))

    def test_a_driver_leaving_keeps_the_identity(self):
        self.assertEqual(
            APP.session_identity_fingerprint(_session([1, 2, 3])),
            APP.session_identity_fingerprint(_session([1, 3])),
        )

    def test_a_new_session_or_context_changes_the_identity(self):
        base = APP.session_identity_fingerprint(_session([1, 2]))
        self.assertNotEqual(base, APP.session_identity_fingerprint(_session([1, 2], session_id=556)))
        self.assertNotEqual(base, APP.session_identity_fingerprint(_session([1, 2], time_of_day="9:00 pm")))

    def test_the_full_fingerprint_still_tracks_the_roster(self):
        session = _session([1, 2])
        self.assertEqual(session.fingerprint(), (session.session_id, session.roster_fingerprint(), session.context_fingerprint()))
        self.assertEqual(session.identity_fingerprint(), (session.session_id, session.context_fingerprint()))


class SessionCancelMonitorTests(unittest.TestCase):
    def _start(self, sdk):
        reader = APP.IracingSdkReader(sdk=sdk)
        observed = APP.read_session_from_sdk(reader)[1]
        cancel_event = threading.Event()
        stop_event = threading.Event()
        monitor = APP.start_session_cancel_monitor(
            expected_fingerprint=APP.session_identity_fingerprint(observed),
            cancel_event=cancel_event,
            stop_event=stop_event,
            reader=reader,
            expected_session_info_update=reader.last_update,
            poll_seconds=0.05,
        )
        self.addCleanup(monitor.join, 2.0)
        self.addCleanup(stop_event.set)
        return cancel_event

    def test_a_driver_joining_does_not_cancel_the_pipeline(self):
        sdk = FakeSdk()
        for uid in (1, 2, 3):
            sdk.add_driver(uid)
        cancel_event = self._start(sdk)
        sdk.add_driver(4)
        sdk.add_driver(5)
        self.assertFalse(cancel_event.wait(1.0))

    def test_a_new_session_still_cancels_the_pipeline(self):
        sdk = FakeSdk()
        for uid in (1, 2, 3):
            sdk.add_driver(uid)
        cancel_event = self._start(sdk)
        sdk.change(sub_session_id=778)
        self.assertTrue(cancel_event.wait(2.0))

    def test_a_context_change_still_cancels_the_pipeline(self):
        sdk = FakeSdk()
        for uid in (1, 2, 3):
            sdk.add_driver(uid)
        cancel_event = self._start(sdk)
        sdk.change(time_of_day="9:00 pm")
        self.assertTrue(cancel_event.wait(2.0))


class ServiceLoopRosterChangeTests(unittest.TestCase):
    """Drive the real service loop against a fake SDK and a fake paint pipeline."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.sdk = FakeSdk()
        self.calls = []
        self.deleted = []
        self.processing = threading.Event()
        self.release = threading.Event()
        self.release.set()
        patches = {
            "default_paints_dir": lambda _cfg: self.tmp / "paint",
            "default_temp_dir": lambda: self.tmp / "temp",
            "default_replay_dir": lambda _cfg: self.tmp / "replay",
            "default_replay_packs_dir": lambda: self.tmp / "packs",
            "create_sdk_reader": lambda: APP.IracingSdkReader(sdk=self.sdk),
            "process_session": self._fake_process_session,
            "delete_saved": self._spy_delete_saved,
            "_read_replay_mode_active": lambda _reader: False,
            "iracing_ui_preview_protected_paths": lambda: set(),
        }
        self._real_delete_saved = APP.delete_saved
        for name, value in patches.items():
            original = getattr(APP, name)
            setattr(APP, name, value)
            self.addCleanup(setattr, APP, name, original)
        original_maintain = APP.DownloaderService._maintain_ui_previews
        APP.DownloaderService._maintain_ui_previews = lambda self, *a, **k: None
        self.addCleanup(setattr, APP.DownloaderService, "_maintain_ui_previews", original_maintain)
        config = APP.AppConfig(iracing_ui_car_previews=False, sync_ai_rosters_from_server=False, poll_seconds=0.2)
        self.service = APP.DownloaderService(config)
        self.addCleanup(self.service.stop, 5.0)

    def _fake_process_session(self, *, session, paints_dir, cancel_event=None, **_kwargs):
        ids = sorted(user.user_id for user in session.users)
        record = {"users": ids, "cancelled": False}
        self.calls.append(record)
        self.processing.set()
        while not self.release.wait(0.02):
            if cancel_event is not None and cancel_event.is_set():
                record["cancelled"] = True
                self.processing.clear()
                return [], APP.ThroughputMonitorSnapshot(), []
        saved = []
        for user in session.users:
            path = paints_dir / user.directory / f"car_{user.user_id}.tga"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"paint")
            saved.append(APP.SavedFile(session.session_id, APP.DownloadId(user.user_id, user.directory, APP.PaintType.CAR), path))
        self.processing.clear()
        return saved, APP.ThroughputMonitorSnapshot(), []

    def _spy_delete_saved(self, saved, *args, **kwargs):
        self.deleted.extend(item.download_id.user_id for item in saved)
        return self._real_delete_saved(saved, *args, **kwargs)

    def _finished_passes(self):
        return [call for call in self.calls if not call["cancelled"]]

    def test_a_driver_joining_mid_download_only_fetches_the_new_driver(self):
        for uid in range(1, 11):
            self.sdk.add_driver(uid)
        self.release.clear()
        self.service.start()
        self.assertTrue(self.processing.wait(5.0))
        self.sdk.add_driver(11)
        time.sleep(1.0)  # several cancel-monitor polls see the new driver
        self.release.set()
        self.assertTrue(_wait_until(lambda: len(self._finished_passes()) >= 2))
        time.sleep(0.6)
        self.assertEqual(self.calls, [
            {"users": list(range(1, 11)), "cancelled": False},
            {"users": [11], "cancelled": False},
        ])
        self.assertEqual(self.deleted, [])
        paint_dir = self.tmp / "paint" / CAR
        self.assertEqual(len(list(paint_dir.glob("car_*.tga"))), 11)

    def test_a_driver_joining_while_idle_only_fetches_the_new_driver(self):
        for uid in range(1, 6):
            self.sdk.add_driver(uid)
        self.service.start()
        self.assertTrue(_wait_until(lambda: len(self._finished_passes()) >= 1))
        self.sdk.add_driver(6)
        self.assertTrue(_wait_until(lambda: len(self._finished_passes()) >= 2))
        time.sleep(0.6)
        self.assertEqual([call["users"] for call in self.calls], [[1, 2, 3, 4, 5], [6]])
        self.assertEqual(self.deleted, [])

    def test_a_new_session_mid_download_still_restarts_the_pipeline(self):
        for uid in range(1, 4):
            self.sdk.add_driver(uid)
        self.release.clear()
        self.service.start()
        self.assertTrue(self.processing.wait(5.0))
        self.sdk.change(sub_session_id=999)
        self.assertTrue(_wait_until(lambda: any(call["cancelled"] for call in self.calls)))
        self.release.set()
        self.assertTrue(_wait_until(lambda: len(self._finished_passes()) >= 1))
        self.assertEqual(self.calls[0], {"users": [1, 2, 3], "cancelled": True})
        self.assertEqual(self._finished_passes()[0]["users"], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
