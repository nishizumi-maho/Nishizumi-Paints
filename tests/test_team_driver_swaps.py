import gc
import importlib.util
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_team_swap_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


def setUpModule():
    # Tk widgets left behind by other test modules must be collected on the main
    # thread; letting a worker thread started here collect them aborts Tcl.
    gc.collect()


CAR = "porsche963gtp"


class FakeTeamSdk:
    """A team race: one car per team, and the active driver of a car can change."""

    def __init__(self):
        self._lock = threading.Lock()
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

    def add_team(self, team_id, user_id):
        with self._lock:
            self.drivers.append(
                {
                    "CarIdx": len(self.drivers),
                    "UserID": user_id,
                    "UserName": f"Driver {user_id}",
                    "TeamID": team_id,
                    "TeamName": f"Team {team_id}",
                    "CarPath": CAR,
                    "CarNumber": str(team_id),
                }
            )
            self.session_info_update += 1

    def swap_driver(self, team_id, user_id):
        with self._lock:
            for driver in self.drivers:
                if driver["TeamID"] == team_id:
                    driver["UserID"] = user_id
                    driver["UserName"] = f"Driver {user_id}"
            self.session_info_update += 1

    def __getitem__(self, key):
        with self._lock:
            if key == "WeekendInfo":
                return {
                    "SessionID": 555,
                    "SubSessionID": 777,
                    "TeamRacing": 1,
                    "SeriesID": 286,
                    "TrackName": "spa",
                    "WeekendOptions": {"TimeOfDay": "10:55 am"},
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


class TeamDriverSwapServiceLoopTests(unittest.TestCase):
    """Drive the real service loop against a fake SDK and a fake paint pipeline."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.sdk = FakeTeamSdk()
        self.calls = []
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
            "_read_replay_mode_active": lambda _reader: False,
            "iracing_ui_preview_protected_paths": lambda: set(),
            # The first retry comes due quickly; the later ones stay out of the way.
            "TEAM_DRIVER_SWAP_RETRY_DELAYS_SECONDS": (0.3, 60.0, 60.0),
        }
        for name, value in patches.items():
            original = getattr(APP, name)
            setattr(APP, name, value)
            self.addCleanup(setattr, APP, name, original)
        original_maintain = APP.DownloaderService._maintain_ui_previews
        APP.DownloaderService._maintain_ui_previews = lambda self, *a, **k: None
        self.addCleanup(setattr, APP.DownloaderService, "_maintain_ui_previews", original_maintain)
        config = APP.AppConfig(
            iracing_ui_car_previews=False,
            sync_ai_rosters_from_server=False,
            preload_team_driver_personal_paints=False,
            poll_seconds=0.2,
        )
        self.service = APP.DownloaderService(config)
        self.addCleanup(self.service.stop, 5.0)

    def _fake_process_session(self, *, session, paints_dir, **_kwargs):
        self.calls.append(sorted(user.user_id for user in session.users))
        self.processing.set()
        self.release.wait(10.0)
        saved = []
        for user in session.users:
            path = paints_dir / user.directory / f"car_team_{user.team_id}.tga"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"paint")
            download_id = APP.DownloadId(user.team_id, user.directory, APP.PaintType.CAR, is_team_paint=True)
            saved.append(APP.SavedFile(session.session_id, download_id, path))
        self.processing.clear()
        return saved, APP.ThroughputMonitorSnapshot(), []

    def test_a_swap_is_not_starved_by_a_due_retry(self):
        # Seen live: team 333550 swapped while other teams' retries were due; its
        # paints were cleared, but the pass only fetched the retry's team, so the
        # car stayed unpainted until its own retry almost a minute later.
        self.sdk.add_team(101, 1)
        self.sdk.add_team(102, 2)
        self.sdk.add_team(103, 3)
        self.service.start()
        self.assertTrue(_wait_until(lambda: len(self.calls) >= 1 and not self.processing.is_set()))

        # Hold the swap pass for team 102 until its first retry is due, and swap team 103 meanwhile.
        self.release.clear()
        self.sdk.swap_driver(102, 12)
        self.assertTrue(_wait_until(lambda: len(self.calls) >= 2 and self.processing.is_set()))
        self.sdk.swap_driver(103, 13)
        time.sleep(0.6)
        self.release.set()

        self.assertTrue(_wait_until(lambda: len(self.calls) >= 4))
        time.sleep(0.4)
        self.assertEqual(self.calls[:2], [[1, 2, 3], [12]])
        self.assertEqual(self.calls[2], [13], "the new swap must be processed before the pending retry")
        self.assertEqual(self.calls[3], [12])
        paint = self.tmp / "paint" / CAR / "car_team_103.tga"
        self.assertTrue(paint.exists())


class UnprocessedTeamDriverSwapTests(unittest.TestCase):
    def _users(self, drivers):
        session = APP.Session(
            session_id=APP.SessionId(555, 777),
            users={APP.SessionUser(user_id=uid, directory=CAR, team_id=team) for team, uid in drivers.items()},
        )
        return session, APP._session_user_map(session)

    def test_detects_a_changed_team_driver(self):
        before, _ = self._users({101: 1, 102: 2})
        _, after = self._users({101: 1, 102: 12})
        self.assertTrue(APP._session_has_unprocessed_team_driver_swap(before, after))

    def test_ignores_joins_leaves_and_a_missing_previous_session(self):
        before, before_map = self._users({101: 1, 102: 2})
        _, joined = self._users({101: 1, 102: 2, 103: 3})
        _, left = self._users({101: 1})
        self.assertFalse(APP._session_has_unprocessed_team_driver_swap(before, before_map))
        self.assertFalse(APP._session_has_unprocessed_team_driver_swap(before, joined))
        self.assertFalse(APP._session_has_unprocessed_team_driver_swap(before, left))
        self.assertFalse(APP._session_has_unprocessed_team_driver_swap(None, joined))


if __name__ == "__main__":
    unittest.main()
