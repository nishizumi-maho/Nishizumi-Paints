import importlib.util
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_team_preload_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


CAR = "stockcars2 camaro2019"
DRIVER = APP.SessionUser(user_id=7, directory=CAR, team_id=42, display_name="Teammate")


def _session(superspeedway=False):
    return APP.Session(
        session_id=APP.SessionId(555, 777),
        users={DRIVER},
        local_user_id=1,
        local_team_id=99,
        team_racing=True,
        is_superspeedway_track=superspeedway,
    )


class _TmpMixin:
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.cache = self.tmp / "cache"
        self.paints = self.tmp / "paint"
        APP._TEAM_DRIVER_PRELOAD_FAILED_SLOT_RETRY_AFTER.clear()
        APP._TEAM_DRIVER_PERSONAL_MANIFEST_CACHE.clear()

    def patch(self, name, value):
        original = getattr(APP, name)
        setattr(APP, name, value)
        self.addCleanup(setattr, APP, name, original)

    def cache_file(self, name, content):
        path = self.cache / CAR / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
        return path


class PreloadTrackVariantTests(_TmpMixin, unittest.TestCase):
    def _copy(self, superspeedway):
        return APP._copy_preloaded_team_driver_slot(_session(superspeedway), DRIVER, "car", self.cache, self.paints)

    def test_a_superspeedway_paint_does_not_count_at_another_track(self):
        self.cache_file("car_7_ss.tga", b"daytona")
        self.assertFalse(APP._team_driver_preloaded_slot_available(_session(False), DRIVER, "car", self.cache))
        self.assertEqual(self._copy(False), [])
        self.assertFalse((self.paints / CAR).exists())

    def test_a_superspeedway_prefers_the_ss_paint(self):
        self.cache_file("car_7_ss.tga", b"daytona")
        self.cache_file("car_7.tga", b"road")
        saved = self._copy(True)
        self.assertEqual({item.file_path.name for item in saved}, {"car_team_42_ss.tga"})
        self.assertEqual((self.paints / CAR / "car_team_42_ss.tga").read_bytes(), b"daytona")

    def test_a_superspeedway_without_an_ss_paint_uses_the_normal_one_for_both_files(self):
        self.cache_file("car_7.tga", b"road")
        saved = self._copy(True)
        self.assertEqual({item.file_path.name for item in saved}, {"car_team_42.tga", "car_team_42_ss.tga"})

    def test_another_track_copies_only_the_normal_paint(self):
        self.cache_file("car_7_ss.tga", b"daytona")
        self.cache_file("car_7.tga", b"road")
        saved = self._copy(False)
        self.assertEqual({item.file_path.name for item in saved}, {"car_team_42.tga"})


class PreloadFolderTests(_TmpMixin, unittest.TestCase):
    def test_a_preload_is_found_when_trading_paints_spells_the_car_folder_differently(self):
        manifest = [
            APP.DownloadFile(
                download_id=APP.DownloadId(user_id=7, directory="stockcars2_camaro2019", paint_type=APP.PaintType.CAR),
                url="https://example.invalid/car_7.tga.bz2",
            )
        ]
        self.patch("default_team_driver_preload_cache_dir", lambda: self.cache)
        self.patch("_fetch_team_driver_personal_manifest", lambda *_a, **_k: list(manifest))
        self.patch("_download_items_parallel", lambda *, items, **_k: (list(items), None))

        def fake_save(*, downloads, paints_dir, **_kwargs):
            saved = []
            for item in downloads:
                path = APP.save_path_for(item.download_id, paints_dir)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"paint")
                saved.append(APP.SavedFile(APP.SessionId(555, 777), item.download_id, path))
            return saved, None

        self.patch("_save_downloads_parallel", fake_save)
        session = _session(False)
        APP.start_team_driver_personal_paint_preload(
            session=session,
            temp_dir=self.tmp / "temp",
            manifest_workers=1,
            retries=0,
            retry_backoff_seconds=0.0,
            enabled_slots=["car"],
        )
        for thread in threading.enumerate():
            if thread.name == "NishizumiTeamDriverPreload":
                thread.join(5.0)
        self.assertTrue(APP._team_driver_preloaded_slot_available(session, DRIVER, "car", self.cache))
        saved = APP._copy_preloaded_team_driver_slot(session, DRIVER, "car", self.cache, self.paints)
        self.assertEqual([item.file_path.name for item in saved], ["car_team_42.tga"])


if __name__ == "__main__":
    unittest.main()
