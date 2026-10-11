import importlib.util
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_sdk_settings_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


class LocalDriverIdentityTests(unittest.TestCase):
    def test_a_teammate_driving_the_car_does_not_become_the_local_user(self):
        driver_info = {"DriverUserID": 111, "DriverCarIdx": 5}
        drivers = [{"CarIdx": 5, "UserID": 222, "TeamID": 777}]
        self.assertEqual(APP._resolve_local_driver_identity(driver_info, drivers, 5), (111, 777))

    def test_the_local_users_own_entry_still_wins(self):
        driver_info = {"DriverUserID": 111, "DriverCarIdx": 5}
        drivers = [{"CarIdx": 5, "UserID": 222, "TeamID": 777}, {"CarIdx": 9, "UserID": 111, "TeamID": 888}]
        self.assertEqual(APP._resolve_local_driver_identity(driver_info, drivers, 5), (111, 888))

    def test_without_a_driver_user_id_the_car_index_decides(self):
        self.assertEqual(APP._resolve_local_driver_identity({}, [{"CarIdx": 5, "UserID": 222, "TeamID": 0}], 5), (222, None))


class _Sdk:
    def __init__(self, values):
        self.values = values
        self.is_initialized = True
        self.is_connected = True

    def startup(self):
        return True

    def freeze_var_buffer_latest(self):
        pass

    def __getitem__(self, key):
        return self.values[key]


class ReplayDetectionTests(unittest.TestCase):
    LIVE_RACE = {"IsReplayPlaying": True, "ReplayFrameNum": 54000, "ReplayFrameNumEnd": 1, "ReplaySessionNum": 2, "ReplaySessionTime": 900.0}

    def _active(self, values):
        return APP._read_replay_mode_active(APP.IracingSdkReader(sdk=_Sdk(values)))

    def test_a_live_race_is_not_a_replay(self):
        self.assertFalse(self._active(dict(self.LIVE_RACE, WeekendInfo={"SimMode": "full"})))

    def test_a_saved_replay_is_a_replay(self):
        self.assertTrue(self._active(dict(self.LIVE_RACE, WeekendInfo={"SimMode": "replay"})))

    def test_without_sim_mode_only_a_replay_behind_the_live_edge_counts(self):
        self.assertFalse(self._active(dict(self.LIVE_RACE, WeekendInfo={})))
        self.assertTrue(self._active(dict(self.LIVE_RACE, WeekendInfo={}, ReplayFrameNumEnd=3000)))


class TextureReloadDebouncerTests(unittest.TestCase):
    def test_a_firing_timer_keeps_the_newer_timer_for_the_same_car(self):
        debouncer = APP.TextureReloadDebouncer(reader=mock.Mock(), session=mock.Mock(), debounce_seconds=60.0)
        newer = threading.Timer(60.0, lambda: None)
        debouncer._timers[3] = newer
        with mock.patch.object(APP, "trigger_texture_reload") as reload:
            debouncer._fire(3)  # the older timer, firing on another thread
            self.assertIs(debouncer._timers.get(3), newer)
            debouncer.flush(force=True)
        self.assertEqual([call.kwargs["car_idx"] for call in reload.call_args_list], [3, 3])


class DocumentsFolderTests(unittest.TestCase):
    def test_the_documents_folder_is_not_searched_on_every_call(self):
        APP._IRACING_DOCUMENTS_DIR_CACHE = None
        self.addCleanup(setattr, APP, "_IRACING_DOCUMENTS_DIR_CACHE", None)
        with mock.patch.object(APP, "auto_detect_iracing_documents_dir", return_value=Path(r"C:\Docs\iRacing")) as detect:
            for _ in range(5):
                self.assertEqual(APP.default_iracing_documents_dir(), Path(r"C:\Docs\iRacing"))
        self.assertEqual(detect.call_count, 1)


class UnreadableSettingsTests(unittest.TestCase):
    def test_an_unreadable_settings_file_is_kept_before_defaults_replace_it(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = APP.ConfigStore()
        store.path = Path(tmp.name) / "settings.json"
        store.path.write_text('{"poll_seconds": 3.0, "delete_downloaded_livery": fal', encoding="utf-8")
        with mock.patch.object(APP, "CONFIG_IO_RETRY_SECONDS", 0.0):
            config = store.load()
            store.load()
        self.assertIsInstance(config, APP.AppConfig)
        backups = list(Path(tmp.name).glob("settings.json.unreadable-*"))
        self.assertEqual(len(backups), 1)
        self.assertIn("delete_downloaded_livery", backups[0].read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
