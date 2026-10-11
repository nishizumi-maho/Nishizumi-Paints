import importlib.util
import itertools
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_fallback_lanes_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


SESSION_ID = APP.SessionId(555, 777)
FAVORITE = "4242"


class _FakeShowroom:
    """Stands in for the Trading Paints showroom and the downloads.

    Every pick sleeps a little so overlapping lanes are visible, and records which
    thread made it and how many picks were running at the same time.
    """

    def __init__(self, pick_seconds=0.15, failing_downloads=()):
        self.lock = threading.Lock()
        self.ids = itertools.count(1000)
        self.pick_seconds = pick_seconds
        self.failing_downloads = set(failing_downloads)
        self.running = 0
        self.max_running = 0
        self.max_running_by_kind = {}
        self.running_by_kind = {}
        self.picks = []  # (kind, directory, forced scheme, thread name, start, end)

    def _pick(self, kind, directory, forced):
        with self.lock:
            self.running += 1
            self.max_running = max(self.max_running, self.running)
            self.running_by_kind[kind] = self.running_by_kind.get(kind, 0) + 1
            self.max_running_by_kind[kind] = max(self.max_running_by_kind.get(kind, 0), self.running_by_kind[kind])
        started = time.monotonic()
        time.sleep(self.pick_seconds)
        with self.lock:
            self.running -= 1
            self.running_by_kind[kind] -= 1
            self.picks.append((kind, directory, forced, threading.current_thread().name, started, time.monotonic()))
            scheme_id = forced or str(next(self.ids))
        return APP.TPShowroomSyncResult(ok=True, chosen_scheme_id=scheme_id, chosen_title=f"paint {scheme_id}")

    def choose_car(self, *, directory, forced_scheme_id="", **_kwargs):
        return self._pick("car", directory, forced_scheme_id)

    def choose_accessory(self, *, accessory_kind, forced_scheme_id="", **_kwargs):
        return self._pick(accessory_kind, "", forced_scheme_id)

    def _saved(self, user, result, paint_type, paints_dir):
        if (user.user_id, paint_type) in self.failing_downloads:
            return []
        download_id = APP.DownloadId(
            user.user_id,
            user.directory,
            paint_type,
            tp_scheme_id=result.chosen_scheme_id,
            tp_source="fallback_online",
        )
        return [APP.SavedFile(SESSION_ID, download_id, Path(paints_dir) / f"{paint_type.value}_{user.user_id}.tga")]

    def download_car(self, *, user, result, paints_dir, **_kwargs):
        return self._saved(user, result, APP.PaintType.CAR, paints_dir)

    def download_accessory(self, *, user, result, accessory_kind, paints_dir, **_kwargs):
        paint_type = APP.PaintType.HELMET if accessory_kind == "helmet" else APP.PaintType.SUIT
        return self._saved(user, result, paint_type, paints_dir)


class _FallbackTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.preferences = APP._empty_random_paint_preferences()
        self.local_calls = []
        for name in ("choose_showroom_paint_direct", "choose_showroom_accessory_direct",
                     "_download_and_save_direct_showroom_car_result", "_download_and_save_direct_showroom_accessory_result"):
            self.addCleanup(setattr, APP, name, getattr(APP, name))
        self.use_showroom(_FakeShowroom())
        patches = {
            "_tp_showroom_mapping_entry_for_directory": lambda *_a, **_k: None,
            "prefetch_tp_showroom_first_pages": lambda *_a, **_k: 0,
            "load_tp_recent_schemes": lambda: {},
            "save_tp_recent_schemes": lambda *_a, **_k: None,
            "load_random_paint_preferences": lambda *_a, **_k: self.preferences,
            "default_random_pool_dir": lambda: self.tmp / "pool",
            "default_ai_livery_dir": lambda: self.tmp / "ai",
            "default_temp_dir": lambda: self.tmp / "temp",
            "_apply_local_tp_random_fallback_assets_for_user": self._fake_local,
        }
        for name, value in patches.items():
            self.patch(name, value)

    def patch(self, name, value):
        original = getattr(APP, name)
        setattr(APP, name, value)
        self.addCleanup(setattr, APP, name, original)

    def use_showroom(self, showroom):
        self.showroom = showroom
        APP.choose_showroom_paint_direct = showroom.choose_car
        APP.choose_showroom_accessory_direct = showroom.choose_accessory
        APP._download_and_save_direct_showroom_car_result = showroom.download_car
        APP._download_and_save_direct_showroom_accessory_result = showroom.download_accessory

    def _fake_local(self, *, user, need_car, need_helmet, need_suit, **_kwargs):
        self.local_calls.append((user.user_id, need_car, need_helmet, need_suit))
        return [], [], False

    def run_fallback(self, users, *, helmets=False, saved=(), **options):
        session = APP.Session(session_id=SESSION_ID, users=set(users))
        return APP.apply_tp_showroom_fallbacks_public(
            session=session,
            saved=list(saved),
            paints_dir=self.tmp / "paint",
            enable_real_drivers=True,
            enable_ai=True,
            sync_my_livery_from_server=True,
            random_helmets=helmets,
            random_helmets_ai=helmets,
            **options,
        )


def _ai(user_id, directory):
    return APP.SessionUser(user_id=user_id, directory=directory, is_ai=True, display_name=f"AI {user_id}")


THREE_CARS = [_ai(1, "porsche963gtp"), _ai(2, "porsche963gtp"), _ai(3, "ferrari296gt3"), _ai(4, "mx5 mx52016")]


class LaneTests(_FallbackTestCase):
    def setUp(self):
        super().setUp()
        self.use_showroom(_FakeShowroom())

    def test_safe_mode_works_on_one_car_group_at_a_time(self):
        saved, _logs, summary = self.run_fallback(THREE_CARS, tp_fallback_lanes_mode="safe")
        self.assertEqual(self.showroom.max_running, 1)
        self.assertEqual(len(saved), 4)
        self.assertEqual(summary.applied_targets, 4)

    def test_session_total_runs_every_car_group_at_once(self):
        self.run_fallback(THREE_CARS, tp_fallback_lanes_mode="session_total")
        self.assertEqual(self.showroom.max_running, 3)
        threads_by_directory = {}
        for kind, directory, _forced, thread_name, _start, _end in self.showroom.picks:
            threads_by_directory.setdefault(directory, set()).add(thread_name)
        # Drivers of the same car stay in one lane, one after the other.
        self.assertEqual(len(threads_by_directory["porsche963gtp"]), 1)

    def test_manual_mode_caps_the_lanes(self):
        self.run_fallback(THREE_CARS, tp_fallback_lanes_mode="manual", tp_manual_max_lanes=2)
        self.assertEqual(self.showroom.max_running, 2)

    def test_lane_count(self):
        self.assertEqual(APP.resolve_tp_fallback_lane_count("safe", 9, 5), 1)
        self.assertEqual(APP.resolve_tp_fallback_lane_count("Manual", 3, 5), 3)
        self.assertEqual(APP.resolve_tp_fallback_lane_count("manual", 9, 2), 2)
        self.assertEqual(APP.resolve_tp_fallback_lane_count("Session Total", 1, 5), 5)
        self.assertEqual(APP.resolve_tp_fallback_lane_count("session_total", 1, 0), 0)

    def test_helmets_run_alongside_the_cars_only_when_processing_together(self):
        users = [_ai(1, "porsche963gtp"), _ai(2, "porsche963gtp")]
        self.run_fallback(users, helmets=True, tp_fallback_lanes_mode="safe", process_all_together=True)
        cars = [pick for pick in self.showroom.picks if pick[0] == "car"]
        helmets = [pick for pick in self.showroom.picks if pick[0] == "helmet"]
        self.assertEqual(len(helmets), 2)
        self.assertLess(min(pick[4] for pick in helmets), max(pick[5] for pick in cars), "helmets waited for the cars")

        self.use_showroom(_FakeShowroom())
        self.run_fallback(users, helmets=True, tp_fallback_lanes_mode="safe", process_all_together=False)
        cars = [pick for pick in self.showroom.picks if pick[0] == "car"]
        helmets = [pick for pick in self.showroom.picks if pick[0] == "helmet"]
        self.assertGreaterEqual(min(pick[4] for pick in helmets), max(pick[5] for pick in cars))

    def test_a_failed_download_gets_one_final_online_try_only_when_enabled(self):
        users = [_ai(1, "porsche963gtp")]
        self.use_showroom(_FakeShowroom(pick_seconds=0.0, failing_downloads={(1, APP.PaintType.CAR)}))
        self.run_fallback(users, retry_failed_online_once=False)
        self.assertEqual(len(self.showroom.picks), 4)
        self.assertEqual(self.local_calls, [(1, True, False, False)])

        self.local_calls.clear()
        self.use_showroom(_FakeShowroom(pick_seconds=0.0, failing_downloads={(1, APP.PaintType.CAR)}))
        _saved, logs, _summary = self.run_fallback(users, retry_failed_online_once=True)
        self.assertEqual(len(self.showroom.picks), 5)
        self.assertTrue(any("one final online try" in line for line in logs))
        self.assertEqual(self.local_calls, [(1, True, False, False)])

    def test_a_car_miss_counts_even_when_the_helmet_was_applied(self):
        users = [_ai(1, "porsche963gtp")]
        self.use_showroom(_FakeShowroom(pick_seconds=0.0, failing_downloads={(1, APP.PaintType.CAR)}))
        _saved, _logs, summary = self.run_fallback(users, helmets=True)
        self.assertEqual((summary.attempted_targets, summary.applied_targets, summary.missing_source_targets), (1, 0, 1))


class OnlineFavoriteTests(_FallbackTestCase):
    def setUp(self):
        super().setUp()
        self.use_showroom(_FakeShowroom(pick_seconds=0.0))
        self.preferences["favorites"] = {
            "fav": {
                "key": "fav",
                "kind": "car",
                "directory": "porsche963gtp",
                "source_type": "online",
                "scheme_id": FAVORITE,
                "source_id": FAVORITE,
                "title": "My favorite",
            }
        }

    def _forced(self):
        return [pick[2] for pick in self.showroom.picks if pick[2]]

    def test_the_favorite_goes_to_one_driver_per_session(self):
        users = [_ai(user_id, "porsche963gtp") for user_id in (1, 2, 3)]
        saved, _logs, _summary = self.run_fallback(users)
        self.assertEqual(self._forced(), [FAVORITE])
        schemes = [item.download_id.tp_scheme_id for item in saved]
        self.assertEqual(schemes.count(FAVORITE), 1)
        self.assertEqual(len(set(schemes)), 3)

    def test_a_favorite_used_in_an_earlier_pass_is_not_used_again(self):
        earlier = APP.SavedFile(
            SESSION_ID,
            APP.DownloadId(9, "porsche963gtp", APP.PaintType.CAR, tp_scheme_id=FAVORITE, tp_source="fallback_online"),
            self.tmp / "car_9.tga",
        )
        self.run_fallback([_ai(1, "porsche963gtp")], session_saved=[earlier])
        self.assertEqual(self._forced(), [])


class LocalFavoriteTests(unittest.TestCase):
    def setUp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        self.pool = tmp / "pool"
        bucket = self.pool / APP._safe_random_pool_bucket("porsche963gtp")
        for name in ("fav", "a", "b", "c"):
            (bucket / name).mkdir(parents=True)
            (bucket / name / "car.tga").write_bytes(name.encode())
        self.favorite_id = "pool:porsche963gtp:fav"
        self.preferences = APP._empty_random_paint_preferences()
        self.preferences["favorites"] = {
            "fav": {"key": "fav", "kind": "car", "directory": "porsche963gtp", "source_type": "local", "source_id": self.favorite_id}
        }
        self.cache = APP.RandomPoolPassCache(self.pool, tmp / "ai", self.preferences)

    def _pick(self, used, seed):
        entry, _reused = APP._choose_random_pool_entry("porsche963gtp", self.pool, self.pool, used, seed, pool_cache=self.cache)
        return entry.source_id if entry is not None else None

    def test_the_favorite_is_picked_first_and_then_never_again(self):
        used = set()
        picks = [self._pick(used, f"driver {index}") for index in range(4)]
        self.assertEqual(picks[0], self.favorite_id)
        self.assertEqual(len(set(picks)), 4)
        self.assertIsNone(self._pick(used, "driver 5"))

    def test_a_favorite_already_in_the_session_counts_as_used(self):
        earlier = APP.SavedFile(
            SESSION_ID,
            APP.DownloadId(9, "porsche963gtp", APP.PaintType.CAR, tp_scheme_id=self.favorite_id, tp_source="random_pool"),
            Path("car_9.tga"),
        )
        used = APP.random_favorites_used_in_session([earlier], self.preferences)
        self.assertEqual(used, {self.favorite_id})
        self.assertNotEqual(self._pick(used, "driver 1"), self.favorite_id)


if __name__ == "__main__":
    unittest.main()
