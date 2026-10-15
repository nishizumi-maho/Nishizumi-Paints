import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_verification_round_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


def _user(user_id, team_id):
    return APP.SessionUser(user_id=user_id, directory="bmwlmdh", team_id=team_id, display_name=f"Driver {user_id}")


class TeamSwapConfirmationTests(unittest.TestCase):
    def test_two_swaps_one_poll_apart_are_both_confirmed(self):
        service = APP.DownloaderService(APP.AppConfig())
        team_a, team_b = ("team", 1, "bmwlmdh"), ("team", 2, "bmwlmdh")
        before = {team_a: _user(10, 1), team_b: _user(20, 2)}
        after_a = {team_a: _user(11, 1), team_b: _user(20, 2)}
        after_both = {team_a: _user(11, 1), team_b: _user(21, 2)}
        # Poll 1: team A changes. Poll 2: team B changes too. Nothing is processed while
        # a swap is pending, so the previous roster stays the one from before both.
        confirmed, pending = service._confirm_team_driver_swap_candidates([team_a], before, after_a)
        self.assertEqual((confirmed, pending), ([], [team_a]))
        confirmed, pending = service._confirm_team_driver_swap_candidates([team_a, team_b], before, after_both)
        self.assertEqual((confirmed, pending), ([team_a], [team_b]))
        confirmed, pending = service._confirm_team_driver_swap_candidates([team_a, team_b], before, after_both)
        self.assertEqual((sorted(confirmed), pending), ([team_a, team_b], []))


class DamagedSettingsTests(unittest.TestCase):
    def test_wrongly_typed_values_fall_back_to_defaults(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = APP.ConfigStore()
        store.path = Path(tmp.name) / "settings.json"
        store.path.write_text(json.dumps({
            "retries": None,
            "poll_seconds": "fast",
            "retry_backoff_seconds": "nan",
            "verbose": "yes",
            "tp_manual_max_lanes": "4",
            "max_pool_gb": 2.5,
            "delete_downloaded_livery": False,
        }), encoding="utf-8")
        config = store.load()
        defaults = APP.AppConfig()
        self.assertEqual(config.retries, defaults.retries)
        self.assertEqual(config.poll_seconds, max(0.2, defaults.poll_seconds))
        self.assertEqual(config.retry_backoff_seconds, max(0.1, defaults.retry_backoff_seconds))
        self.assertEqual(config.verbose, defaults.verbose)
        self.assertEqual(config.tp_manual_max_lanes, 4)
        self.assertFalse(config.delete_downloaded_livery)
        if hasattr(defaults, "max_pool_gb"):
            self.assertEqual(config.max_pool_gb, 2.5)


class SettingsShapeTests(unittest.TestCase):
    def _load(self, text):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = APP.ConfigStore()
        store.path = Path(tmp.name) / "settings.json"
        store.path.write_text(text, encoding="utf-8")
        return store.load()

    def test_a_settings_file_that_is_not_an_object_starts_with_defaults(self):
        defaults = APP.AppConfig()
        for text in ("[]", "null", '"text"', "42", ""):
            with self.subTest(text=text):
                config = self._load(text)
                self.assertEqual(config.retries, defaults.retries)
                self.assertEqual(config.poll_seconds, max(0.2, defaults.poll_seconds))

    def test_out_of_range_numbers_are_clamped_to_something_that_still_works(self):
        config = self._load(json.dumps({"retries": -3, "poll_seconds": 0, "retry_backoff_seconds": -1}))
        self.assertGreaterEqual(config.retries, 1)
        self.assertGreater(config.poll_seconds, 0)
        self.assertGreater(config.retry_backoff_seconds, 0)


class TargetCleanupTests(unittest.TestCase):
    def test_a_preserved_override_stays_tracked_and_on_disk(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        paints = Path(tmp.name)
        session = APP.Session(session_id=APP.SessionId(1, 2), users={_user(10, 1)}, local_user_id=99, team_racing=True)
        override = paints / "bmwlmdh" / "car_team_1.tga"
        override.parent.mkdir(parents=True)
        override.write_bytes(b"override")
        saved = [APP.SavedFile(session.session_id, APP.DownloadId(1, "bmwlmdh", APP.PaintType.CAR, is_team_paint=True, preserve_on_cleanup=True), override)]
        kept, deleted = APP.clear_session_target_files(
            session=session, saved=saved, paints_dir=paints, target_keys=[("team", 1, "bmwlmdh")]
        )
        self.assertTrue(override.exists())
        self.assertEqual([item.file_path for item in kept], [override])
        self.assertEqual(deleted, 0)


if __name__ == "__main__":
    unittest.main()
