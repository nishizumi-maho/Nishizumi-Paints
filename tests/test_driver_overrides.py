import importlib.util
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_driver_overrides_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


CAR = "ferrari296gt3"
SESSION_ID = APP.SessionId(555, 777)


class _Patching:
    def patch(self, name, value):
        original = getattr(APP, name)
        setattr(APP, name, value)
        self.addCleanup(setattr, APP, name, original)

    def make_tmp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        return tmp


def _entry(scheme_id, user_id=123):
    return {"user_id": user_id, "kind": "car", "directory": CAR, "scheme_id": str(scheme_id), "source": "manual"}


class CachedCarOverrideTests(_Patching, unittest.TestCase):
    def setUp(self):
        tmp = self.make_tmp()
        self.cache_root = tmp / "cache"
        self.paints = tmp / "paint"
        self.patch("remember_previous_paint_file", lambda *a, **k: False)
        cache_dir = APP._driver_paint_override_cache_dir(_entry(777), self.cache_root)
        cache_dir.mkdir(parents=True)
        (cache_dir / "car.tga").write_bytes(b"override car")
        car_dir = self.paints / CAR
        car_dir.mkdir(parents=True)
        # The driver's own Trading Paints paint, downloaded earlier in the pass.
        for name in ("car_123.tga", "car_spec_123.mip", "decal_123.tga", "car_num_123.tga", "car_123_ss.tga", "decal_123_ss.tga"):
            (car_dir / name).write_bytes(b"original " + name.encode())

    def _apply(self, superspeedway):
        user = APP.SessionUser(user_id=123, directory=CAR)
        session = APP.Session(session_id=SESSION_ID, users={user}, is_superspeedway_track=superspeedway)
        return APP._apply_cached_driver_paint_override_for_user(
            session=session, user=user, paints_dir=self.paints, entry=_entry(777), cache_root=self.cache_root
        )

    def test_the_original_spec_map_decal_and_number_do_not_stay_under_the_override(self):
        self._apply(superspeedway=False)
        car_dir = self.paints / CAR
        self.assertEqual((car_dir / "car_123.tga").read_bytes(), b"override car")
        for name in ("car_spec_123.mip", "decal_123.tga", "car_num_123.tga", "car_123_ss.tga", "decal_123_ss.tga"):
            self.assertFalse((car_dir / name).exists(), name)

    def test_a_superspeedway_track_gets_the_override_as_its_ss_paint(self):
        saved = self._apply(superspeedway=True)
        car_dir = self.paints / CAR
        self.assertEqual((car_dir / "car_123_ss.tga").read_bytes(), b"override car")
        self.assertFalse((car_dir / "decal_123_ss.tga").exists())
        self.assertIn(car_dir / "car_123_ss.tga", [item.file_path for item in saved])


class OverrideFileTests(_Patching, unittest.TestCase):
    def test_parallel_assignments_keep_every_override(self):
        path = self.make_tmp() / "overrides.json"
        errors = []

        def assign(user_id):
            try:
                for scheme in range(20):
                    APP.remember_driver_paint_override(_entry(f"{user_id}{scheme}", user_id=user_id), path)
            except Exception as exc:  # pragma: no cover - the failure being tested
                errors.append(exc)

        threads = [threading.Thread(target=assign, args=(user_id,)) for user_id in range(1, 9)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(len(APP.load_driver_paint_overrides(path)), 8)
        self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_reassigning_removes_the_previous_paints_cache(self):
        tmp = self.make_tmp()
        self.patch("default_driver_paint_overrides_path", lambda: tmp / "overrides.json")
        self.patch("default_driver_paint_override_cache_dir", lambda: tmp / "cache")
        first_cache = APP._driver_paint_override_cache_dir(_entry(1))
        first_cache.mkdir(parents=True)
        (first_cache / "car.tga").write_bytes(b"first")
        APP.remember_driver_paint_override(_entry(1))
        second_cache = APP._driver_paint_override_cache_dir(_entry(2))
        second_cache.mkdir(parents=True)
        (second_cache / "car.tga").write_bytes(b"second")
        APP.remember_driver_paint_override(_entry(2))
        self.assertFalse(first_cache.exists())
        self.assertTrue(second_cache.exists())


class CollectionDownloadTests(_Patching, unittest.TestCase):
    def test_collection_cars_use_the_repairing_download(self):
        calls = []
        self.patch("_download_and_save_with_auto_repair", lambda **kwargs: calls.append(kwargs) or [])
        user = APP.SessionUser(user_id=5, directory=CAR)
        session = APP.Session(session_id=SESSION_ID, users={user})
        item = APP.DownloadFile(download_id=APP.DownloadId(0, CAR, APP.PaintType.CAR), url="https://example.invalid/car.tga")
        result = APP.TPShowroomSyncResult(ok=True, chosen_scheme_id="9", direct_items=[item])
        APP._download_and_save_tp_collection_result(
            session=session, user=user, result=result, kind="car", temp_dir=self.make_tmp(), paints_dir=self.make_tmp(),
            retries=1, retry_backoff_seconds=0.1,
        )
        self.assertEqual(len(calls), 1)
        self.assertTrue(calls[0]["skip_car_extras_until_car"])


if __name__ == "__main__":
    unittest.main()
