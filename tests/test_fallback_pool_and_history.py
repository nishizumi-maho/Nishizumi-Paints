import importlib.util
import json
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_pool_history_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


CAR = "ferrari296gt3"
SESSION_ID = APP.SessionId(555, 777)


class _Patching:
    def patch(self, name, value, owner=None):
        target = APP if owner is None else owner
        original = getattr(target, name)
        setattr(target, name, value)
        self.addCleanup(setattr, target, name, original)

    def make_tmp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        return tmp


def _scheme(scheme_id):
    return {"id": str(scheme_id), "title": f"Paint {scheme_id}", "type": "paint", "hasnumber": "0", "pro_user": False}


class ShowroomPoolTests(_Patching, unittest.TestCase):
    def setUp(self):
        self.page_requests = []

        def fake_page(*, page_index, **_kwargs):
            self.page_requests.append(page_index)
            return [_scheme(1), _scheme(2), _scheme(3)] if page_index == 0 else []

        self.patch("_tp_fetch_showroom_page_batch_http", fake_page)
        self.patch(
            "_tp_showroom_mapping_entry_for_directory",
            lambda directory, mapping_path=None: (CAR, {"mid": 264, "category": "Road", "slug": "Ferrari-296-GT3"}),
        )

    def test_the_walk_stops_at_the_first_empty_page(self):
        cars, sampled = APP._fetch_tp_showroom_pool_http(
            mid=264,
            category="Road",
            slug="Ferrari-296-GT3",
            min_unused_count=10,
            max_pages=20,
        )
        self.assertEqual(len(cars), 3)
        # Page 0 and one random page past the end, instead of all 19 empty pages.
        self.assertEqual(len(self.page_requests), 2)
        self.assertEqual(len(sampled), 2)

    def test_a_forced_favorite_hands_the_fetched_pool_back_unchanged(self):
        pool = [_scheme(1), _scheme(2), _scheme(3)]
        result = APP.choose_showroom_paint_direct(
            directory=CAR,
            mapping_path=None,
            showroom_cars=pool,
            showroom_sampled_pages={0},
            forced_scheme_id="999",
            forced_scheme_title="My favorite",
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.chosen_scheme_id, "999")
        self.assertEqual([car["id"] for car in result.showroom_cars], ["1", "2", "3"])
        self.assertEqual(result.showroom_sampled_pages, [0])
        self.assertEqual(self.page_requests, [])


class UnknownCarCatalogRefreshTests(_Patching, unittest.TestCase):
    def setUp(self):
        tmp = self.make_tmp()
        self.patch("default_tp_car_identity_cache_path", lambda: tmp / "car_identity.json")
        self.fetches = 0
        doc = APP._build_tp_car_identity_doc([{"mid": 264, "tp_name": "Ferrari 296 GT3", "directory": CAR}])

        def fake_fetch(*_args, **_kwargs):
            self.fetches += 1
            return doc

        self.patch("_fetch_tp_car_identity_doc", fake_fetch)
        with APP._TP_CAR_IDENTITY_CACHE_LOCK:
            APP._TP_CAR_IDENTITY_CACHE_DOC = None
            APP._TP_CAR_IDENTITY_CACHE_AT = 0.0
            APP._TP_CAR_IDENTITY_LAST_ATTEMPT_AT = 0.0
            APP._TP_CAR_IDENTITY_LAST_UNKNOWN_REFRESH_AT = 0.0
        self.addCleanup(setattr, APP, "_TP_CAR_IDENTITY_CACHE_DOC", None)

    def test_an_unknown_car_right_after_a_fetch_does_not_fetch_again(self):
        self.assertIsNone(APP._tp_showroom_mapping_entry_for_name("Some Car Trading Paints Does Not List"))
        self.assertEqual(self.fetches, 1)
        self.assertIsNone(APP._tp_showroom_mapping_entry_for_name("Another Unlisted Car"))
        self.assertEqual(self.fetches, 1)

    def test_an_empty_name_never_fetches(self):
        self.assertIsNone(APP._tp_showroom_mapping_entry_for_name(""))
        self.assertEqual(self.fetches, 0)

    def test_learning_an_alias_does_not_change_a_cars_map_someone_is_iterating(self):
        doc = APP._load_tp_showroom_mapping()
        cars_before = doc["cars"]
        snapshot = dict(cars_before)
        with APP._IRACING_OBSERVED_CAR_IDENTITIES_LOCK:
            APP._IRACING_OBSERVED_CAR_IDENTITIES["ferrari296gt3evo"] = {"car_name": "Ferrari 296 GT3"}
        self.addCleanup(APP._IRACING_OBSERVED_CAR_IDENTITIES.pop, "ferrari296gt3evo", None)
        learned = APP._tp_learn_observed_iracing_alias("ferrari296gt3evo", doc)
        self.assertIsNotNone(learned)
        self.assertEqual(cars_before, snapshot, "the alias was inserted into the dict readers iterate")
        self.assertIn("ferrari296gt3evo", doc["cars"])


class RandomPoolLimitTests(_Patching, unittest.TestCase):
    def test_a_trim_by_the_car_cap_alone_reports_what_it_freed(self):
        pool = self.make_tmp() / "pool"
        for index in range(3):
            set_dir = pool / CAR / f"set{index}"
            set_dir.mkdir(parents=True)
            (set_dir / "car.tga").write_bytes(b"x" * 1000)
            (set_dir / "helmet.tga").write_bytes(b"h" * 10)
        remaining, freed = APP.enforce_random_pool_limit(pool, 10.0, max_car_gb=0.0)
        self.assertEqual(list(pool.rglob("car.tga")), [])
        self.assertGreaterEqual(freed, 3000)
        self.assertGreater(remaining, 0)


class RebuildRandomPoolTests(_Patching, unittest.TestCase):
    def test_each_car_folder_becomes_its_own_pool_bucket(self):
        tmp = self.make_tmp()
        paints = tmp / "paint"
        for directory in ("dirtlatemodel", "ferrari296gt3"):
            (paints / directory).mkdir(parents=True)
            (paints / directory / "car_1.tga").write_bytes(directory.encode() * 50)
        (paints / "helmet_1.tga").write_bytes(b"helmet")
        pool = tmp / "pool"
        APP.rebuild_random_pool_from_paints_root(paints, pool, 10.0)
        buckets = {path.parent.parent.name for path in pool.rglob("car.tga")}
        self.assertEqual(buckets, {APP._safe_random_pool_bucket("dirtlatemodel"), APP._safe_random_pool_bucket("ferrari296gt3")})

    def test_a_nested_car_folder_keeps_its_full_directory(self):
        root = Path(r"C:\Users\me\Documents\iRacing\paint")
        parsed = APP._parse_saved_paint_filename(root / "stockcars2" / "chevy" / "car_7.tga", root)
        self.assertEqual(parsed[1], "stockcars2\\chevy")
        self.assertEqual(APP._parse_saved_paint_filename(root / "helmet_7.tga", root)[1], "__accessories__")


class PaintHistoryTests(_Patching, unittest.TestCase):
    def setUp(self):
        self.history = self.make_tmp() / "history"
        self.patch("default_paint_history_dir", lambda: self.history)
        self.patch("default_paint_history_index_path", lambda: self.history / "index.json")
        self.paints = self.make_tmp()

    def _index_entries(self):
        return json.loads((self.history / "index.json").read_text(encoding="utf-8"))["entries"]

    def test_parallel_saves_keep_every_history_entry(self):
        targets = []
        for user_id in range(24):
            path = self.paints / CAR / f"car_{user_id}.tga"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"old paint")
            targets.append((path, APP.DownloadId(user_id, CAR, APP.PaintType.CAR)))
        threads = [
            threading.Thread(target=APP.remember_previous_paint_file, args=(path, SESSION_ID, download_id))
            for path, download_id in targets
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        entries = self._index_entries()
        self.assertEqual(len(entries), 24)
        backups = {str(path) for path in (self.history / "files").rglob("*") if path.is_file()}
        self.assertEqual(backups, {entry["backup_path"] for entry in entries})

    def test_a_locked_save_that_is_retried_snapshots_the_old_file_once(self):
        destination = self.paints / CAR / "car_5.tga"
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"old paint")
        source = self.paints / "download.tga"
        source.write_bytes(b"new paint")
        downloaded = APP.DownloadedFile(SESSION_ID, APP.DownloadId(5, CAR, APP.PaintType.CAR), source)
        real_replace = APP.os.replace
        attempts = []

        def flaky_replace(src, dst):
            if Path(dst) == destination:
                attempts.append(dst)
                if len(attempts) < 3:
                    raise PermissionError(13, "locked")
            return real_replace(src, dst)

        with mock.patch.object(APP.os, "replace", side_effect=flaky_replace):
            saved = APP.move_or_extract(downloaded, self.paints, retries=3, retry_backoff_seconds=0.05)
        self.assertIsNotNone(saved)
        self.assertEqual(destination.read_bytes(), b"new paint")
        self.assertEqual(len(self._index_entries()), 1)


class ServiceRestartTests(unittest.TestCase):
    def test_start_after_a_timed_out_stop_never_runs_two_loops(self):
        service = APP.DownloaderService(APP.AppConfig())
        release = threading.Event()

        def slow_loop():
            # A step that does not watch the stop event, like a large download.
            release.wait(5.0)

        service._run_forever = slow_loop
        self.addCleanup(release.set)
        service.start()
        first = service._thread
        service.stop(join_timeout=0.1)
        self.assertTrue(first.is_alive())
        service.start()
        self.assertIs(service._thread, first, "a second loop started next to the one still stopping")
        self.assertTrue(service._stop_event.is_set())
        release.set()
        first.join(2.0)
        service.start()
        self.assertIsNot(service._thread, first)
        service._thread.join(6.0)


if __name__ == "__main__":
    unittest.main()
