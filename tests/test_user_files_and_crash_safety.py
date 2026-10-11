import gc
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
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_user_files_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


def setUpModule():
    # Tk widgets left behind by other test modules must be collected on the main
    # thread; letting a worker thread started here collect them aborts Tcl.
    gc.collect()


CAR = "dirtlatemodel 350"
SESSION_ID = APP.SessionId(555, 777)


class _TempDirMixin:
    def make_tmp(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, True)
        return tmp

    def patch(self, name, value, owner=None):
        target = APP if owner is None else owner
        original = getattr(target, name)
        setattr(target, name, value)
        self.addCleanup(setattr, target, name, original)


class _FakeSdk:
    """Just enough of pyirsdk for the service loop: one local driver, user 1."""

    def __init__(self):
        self.is_initialized = True
        self.is_connected = True
        self.session_info_update = 1
        self.drivers = [
            {"CarIdx": index, "UserID": uid, "UserName": f"Driver {uid}", "CarPath": CAR, "TeamID": 0, "CarNumber": str(uid)}
            for index, uid in enumerate((1, 2))
        ]

    def startup(self):
        return True

    def shutdown(self):
        pass

    def freeze_var_buffer_latest(self):
        pass

    def reload_texture(self, _car_idx):
        pass

    def __getitem__(self, key):
        if key == "WeekendInfo":
            return {
                "SessionID": 555,
                "SubSessionID": 777,
                "TeamRacing": 0,
                "SeriesID": 164,
                "TrackName": "lanier dirt",
                "WeekendOptions": {"TimeOfDay": "2:00 pm"},
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


class ServiceExitKeepsOwnLiveryTests(_TempDirMixin, unittest.TestCase):
    def setUp(self):
        self.tmp = self.make_tmp()
        self.sdk = _FakeSdk()
        self.passes = 0
        self.paint_dir = self.tmp / "paint" / CAR
        for name, value in {
            "default_paints_dir": lambda _cfg: self.tmp / "paint",
            "default_temp_dir": lambda: self.tmp / "temp",
            "default_replay_dir": lambda _cfg: self.tmp / "replay",
            "default_replay_packs_dir": lambda: self.tmp / "packs",
            "create_sdk_reader": lambda: APP.IracingSdkReader(sdk=self.sdk),
            "process_session": self._fake_process_session,
            "_read_replay_mode_active": lambda _reader: False,
            "iracing_ui_preview_protected_paths": lambda: set(),
        }.items():
            self.patch(name, value)
        self.patch("_maintain_ui_previews", lambda self, *a, **k: None, owner=APP.DownloaderService)
        config = APP.AppConfig(iracing_ui_car_previews=False, sync_ai_rosters_from_server=False, poll_seconds=0.2)
        self.service = APP.DownloaderService(config)
        self.addCleanup(self.service.stop, 5.0)

    def _fake_process_session(self, *, session, paints_dir, cancel_event=None, **_kwargs):
        saved = []
        for user in session.users:
            path = paints_dir / user.directory / f"car_{user.user_id}.tga"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"paint")
            saved.append(APP.SavedFile(session.session_id, APP.DownloadId(user.user_id, user.directory, APP.PaintType.CAR), path))
        self.passes += 1
        return saved, APP.ThroughputMonitorSnapshot(), []

    def test_closing_the_app_after_leaving_the_session_keeps_the_users_own_livery(self):
        self.service.start()
        self.assertTrue(_wait_until(lambda: self.passes >= 1))
        self.assertTrue(_wait_until(lambda: (self.paint_dir / "car_2.tga").exists()))
        self.sdk.is_connected = False
        # Leaving the session deletes the other driver's paint and keeps the user's own.
        self.assertTrue(_wait_until(lambda: not (self.paint_dir / "car_2.tga").exists()))
        self.assertTrue((self.paint_dir / "car_1.tga").exists())
        self.service.stop(5.0)
        self.assertTrue((self.paint_dir / "car_1.tga").exists(), "the exit cleanup deleted the user's own livery")


class SessionCancelOnStopTests(unittest.TestCase):
    def test_stopping_the_service_cancels_the_running_pass(self):
        sdk = _FakeSdk()
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
        self.assertFalse(cancel_event.wait(0.3))
        stop_event.set()
        self.assertTrue(cancel_event.wait(2.0), "a stopping service left the pass running")


def _team_session(*, local_user_id=5, local_team_id=99):
    driver = APP.SessionUser(user_id=local_user_id, directory=CAR, team_id=local_team_id, display_name="Me")
    other = APP.SessionUser(user_id=7, directory=CAR, team_id=42, display_name="Other")
    return APP.Session(
        session_id=SESSION_ID,
        users={driver, other},
        local_user_id=local_user_id,
        local_team_id=local_team_id,
        team_racing=True,
    )


class LocalTargetFilesWithSyncOffTests(_TempDirMixin, unittest.TestCase):
    def setUp(self):
        self.paints = self.make_tmp() / "paint"
        self.own_car = self.paints / CAR / "car_team_99.tga"
        self.own_helmet = self.paints / "helmet_team_99.tga"
        for path in (self.own_car, self.own_helmet):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"MY OWN LIVERY")

    def _clear(self, sync):
        return APP.clear_session_target_files(
            session=_team_session(),
            saved=[],
            paints_dir=self.paints,
            target_keys=[("team", 99, CAR)],
            sync_my_livery_from_server=sync,
        )

    def test_a_swap_or_force_refresh_keeps_the_users_own_team_files_with_sync_off(self):
        _kept, cleared = self._clear(sync=False)
        self.assertEqual(cleared, 0)
        self.assertEqual(self.own_car.read_bytes(), b"MY OWN LIVERY")
        self.assertTrue(self.own_helmet.exists())

    def test_with_sync_on_the_target_files_are_still_cleared_for_the_new_download(self):
        _kept, cleared = self._clear(sync=True)
        self.assertEqual(cleared, 2)
        self.assertFalse(self.own_car.exists())

    def test_the_preload_fallback_leaves_the_users_own_team_alone_with_sync_off(self):
        copied_for = []

        def fake_copy(session, user, slot, cache_root, paints_dir):
            copied_for.append((user.user_id, slot))
            return []

        self.patch("_copy_preloaded_team_driver_slot", fake_copy)
        for sync in (False, True):
            copied_for.clear()
            APP.apply_preloaded_team_driver_personal_fallbacks(
                session=_team_session(),
                saved=[],
                paints_dir=self.paints,
                enabled_slots=["car"],
                cache_root=self.paints.parent / "cache",
                sync_my_livery_from_server=sync,
            )
            users = {user_id for user_id, _slot in copied_for}
            if sync:
                self.assertIn(5, users)
            else:
                self.assertNotIn(5, users)
            self.assertIn(7, users)


class UiPreviewsWithSyncOffTests(_TempDirMixin, unittest.TestCase):
    def test_previews_never_replace_the_users_paint_while_sync_is_off(self):
        installs = []
        self.patch("install_iracing_ui_car_previews", lambda **kwargs: installs.append(kwargs) or (0, 0))
        self.patch("sync_iracing_ui_car_previews", lambda **kwargs: installs.append(kwargs))
        service = APP.DownloaderService(APP.AppConfig(sync_my_livery_from_server=False))
        config = service.get_config()
        paints = self.make_tmp()
        service._maintain_ui_previews(config, paints, live_member_id=123)
        service._reassert_ui_previews_now(config, paints)
        time.sleep(0.2)
        self.assertEqual(installs, [])
        self.assertEqual(service.get_ui_preview_status().state, "paused")


class AiRosterFolderTests(_TempDirMixin, unittest.TestCase):
    def test_a_server_provided_name_cannot_leave_the_airosters_folder(self):
        for name in ("..\\..\\escaped", "Team\\Sub", "../up", "..", "CON", "nul.txt", "a\x00b"):
            cleaned = APP._safe_ai_roster_folder_name(name, "fallback")
            self.assertNotIn("\\", cleaned, name)
            self.assertNotIn("/", cleaned, name)
            self.assertNotIn("\x00", cleaned, name)
            self.assertNotIn(cleaned.strip(". "), {"", ".."}, name)
        self.assertEqual(APP._safe_ai_roster_folder_name("CON", "fallback"), "fallback")
        self.assertEqual(APP._safe_ai_roster_folder_name("My Roster", "fallback"), "My Roster")

    def test_cleanup_only_removes_folders_this_app_made(self):
        root = self.make_tmp()
        users_backup = root / "Backups" / "Old roster"
        users_backup.mkdir(parents=True)
        (users_backup / "roster.json").write_text("{}", encoding="utf-8")
        broken_sync = root / "Half synced"
        broken_sync.mkdir()
        (broken_sync / APP.AI_ROSTER_META_FILENAME).write_text("{}", encoding="utf-8")
        empty = root / "Empty"
        empty.mkdir()
        good = root / "Good"
        good.mkdir()
        (good / "roster.json").write_text("{}", encoding="utf-8")
        APP._cleanup_ai_roster_dirs(root)
        self.assertTrue(users_backup.exists())
        self.assertFalse(broken_sync.exists())
        self.assertFalse(empty.exists())
        self.assertTrue(good.exists())

    def test_cloning_a_roster_only_copies_files_from_inside_it(self):
        root = self.make_tmp()
        source = root / "My Roster"
        source.mkdir()
        (root / "outside.tga").write_bytes(b"not part of the roster")
        (source / "car_1.tga").write_bytes(b"roster car")
        drivers = [
            {"driverName": "A", "carNumber": "1", "carTgaName": "car_1.tga"},
            {"driverName": "B", "carNumber": "2", "carTgaName": "..\\outside.tga"},
        ]
        (source / "roster.json").write_text(json.dumps({"drivers": drivers}), encoding="utf-8")
        session = APP.Session(session_id=SESSION_ID, users=set(), ai_roster_name="My Roster")
        ok, message = APP.clone_active_ai_roster_to_local(session, root)
        self.assertTrue(ok, message)
        clone = root / f"My Roster{APP.AI_LOCAL_ROSTER_SUFFIX}"
        self.assertEqual((clone / "car_1.tga").read_bytes(), b"roster car")
        self.assertFalse((clone / "outside.tga").exists())
        self.assertEqual((root / "outside.tga").read_bytes(), b"not part of the roster")


class CopyHelperTests(_TempDirMixin, unittest.TestCase):
    def setUp(self):
        self.patch("remember_previous_paint_file", lambda *a, **k: False)
        self.patch("time", mock.Mock(wraps=time, sleep=lambda _s: None))
        tmp = self.make_tmp()
        self.source = tmp / "source.tga"
        self.source.write_bytes(b"paint")
        self.paints = tmp / "paint"
        self.download_id = APP.DownloadId(5, CAR, APP.PaintType.CAR)

    def _copy(self):
        return APP._copy_source_file_to_saved_targets(self.source, SESSION_ID, self.download_id, self.paints)

    def test_a_file_iracing_keeps_locked_is_skipped_instead_of_ending_the_pass(self):
        locked = PermissionError(13, "The process cannot access the file because it is being used by another process")
        with mock.patch.object(APP.os, "replace", side_effect=locked):
            self.assertEqual(self._copy(), [])
        self.assertEqual(list(self.paints.rglob("*.tmp")), [])

    def test_a_short_lock_is_retried(self):
        real_replace = APP.os.replace
        calls = []

        def flaky_replace(src, dst):
            calls.append(dst)
            if len(calls) == 1:
                raise PermissionError(13, "locked")
            return real_replace(src, dst)

        with mock.patch.object(APP.os, "replace", side_effect=flaky_replace):
            saved = self._copy()
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].file_path.read_bytes(), b"paint")


class RandomPoolArchiveTests(_TempDirMixin, unittest.TestCase):
    def setUp(self):
        tmp = self.make_tmp()
        self.pool = tmp / "pool"
        car = tmp / "paint" / CAR / "car_5.tga"
        car.parent.mkdir(parents=True)
        car.write_bytes(b"x" * 5000)
        self.saved = [APP.SavedFile(SESSION_ID, APP.DownloadId(5, CAR, APP.PaintType.CAR), car)]

    def _archive(self):
        return APP.archive_saved_tp_sets_to_random_pool(self.saved, self.pool, 10.0)

    def test_a_copy_cut_short_never_leaves_a_truncated_paint_in_the_pool(self):
        def partial_copy(src, dst, *a, **k):
            Path(dst).write_bytes(b"x" * 100)
            raise OSError(28, "No space left on device")

        with mock.patch.object(APP.shutil, "copy2", side_effect=partial_copy):
            self._archive()
        self.assertEqual([p for p in self.pool.rglob("car.tga")], [])
        self.assertEqual([p for p in self.pool.rglob("*.tmp")], [])
        self._archive()
        cars = list(self.pool.rglob("car.tga"))
        self.assertEqual(len(cars), 1)
        self.assertEqual(cars[0].stat().st_size, 5000)


class DamagedSettingsFilesTests(_TempDirMixin, unittest.TestCase):
    def test_a_bad_timestamp_in_the_overrides_file_keeps_the_override(self):
        path = self.make_tmp() / "driver_paint_overrides.json"
        entry = {"user_id": 123, "kind": "car", "directory": CAR, "scheme_id": "777", "assigned_at": "n/a"}
        path.write_text(json.dumps({"overrides": {"x": entry}}), encoding="utf-8")
        overrides = APP.load_driver_paint_overrides(path)
        self.assertEqual(len(overrides), 1)
        self.assertIsInstance(next(iter(overrides.values()))["assigned_at"], float)

    def test_bad_numbers_in_the_preferences_file_do_not_raise(self):
        entry = {"kind": "car", "directory": CAR, "source_id": "pool:x:y", "created_at": "soon", "use_count": "many", "last_used_at": float("nan")}
        normalized = APP._normalize_random_paint_preference_entry(entry)
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized["use_count"], 0)
        self.assertEqual(normalized["last_used_at"], 0.0)


class LocalRandomPoolTests(_TempDirMixin, unittest.TestCase):
    def setUp(self):
        tmp = self.make_tmp()
        self.pool = tmp / "pool"
        self.ai_root = tmp / "ai"
        self.paints = tmp / "paint"
        self.set_dir = self.pool / APP._safe_random_pool_bucket(CAR) / "aaaa"
        self.set_dir.mkdir(parents=True)
        (self.set_dir / "car.tga").write_bytes(b"pool car")
        (self.set_dir / "helmet.tga").write_bytes(b"pool helmet")
        self.preferences = APP._empty_random_paint_preferences()
        self.patch("load_random_paint_preferences", lambda *a, **k: self.preferences)
        self.patch("remember_previous_paint_file", lambda *a, **k: False)
        self.session = APP.Session(session_id=SESSION_ID, users=set())

    def _apply(self, user_id, *, need_car, need_helmet, used):
        saved, _logs, _reused = APP._apply_local_tp_random_fallback_assets_for_user(
            session=self.session,
            user=APP.SessionUser(user_id=user_id, directory=CAR, is_ai=True),
            paints_dir=self.paints,
            random_pool_dir=self.pool,
            ai_livery_root=self.ai_root,
            used_source_ids=used,
            need_car=need_car,
            need_helmet=need_helmet,
            need_suit=False,
        )
        return {item.download_id.paint_type for item in saved}

    def test_a_driver_who_only_needs_a_helmet_leaves_the_car_set_for_the_next_driver(self):
        used = set()
        self.assertEqual(self._apply(1, need_car=False, need_helmet=True, used=used), {APP.PaintType.HELMET})
        self.assertIn(APP.PaintType.CAR, self._apply(2, need_car=True, need_helmet=False, used=used))

    def test_a_blocked_helmet_from_a_pool_set_is_not_applied_again(self):
        blocked_id = f"pool:{CAR}:aaaa"
        self.preferences["blocked"] = {
            "b": {"kind": "helmet", "directory": "driver", "source_type": "local", "source_id": blocked_id, "key": "b"}
        }
        self.assertIn(blocked_id, APP.random_paint_blocked_source_ids("helmet", "", self.preferences))
        types = self._apply(1, need_car=True, need_helmet=True, used=set())
        self.assertIn(APP.PaintType.CAR, types)
        self.assertNotIn(APP.PaintType.HELMET, types)


class RestartTests(unittest.TestCase):
    def test_restart_passes_each_argument_intact_even_with_spaces_in_the_path(self):
        ui = mock.MagicMock()
        ui._headless_controller_mode = False
        exe = r"C:\Users\me\AppData\Local\Programs\Nishizumi Paints\NishizumiPaints.exe"

        class _Exited(Exception):
            pass

        with mock.patch.object(APP, "build_self_launch_command", return_value=[exe, "--gui"]), mock.patch.object(
            APP.subprocess, "Popen"
        ) as popen, mock.patch.object(APP.os, "_exit", side_effect=_Exited), mock.patch.object(APP.os, "execv") as execv:
            with self.assertRaises(_Exited):
                APP.DownloaderUI.restart_app(ui, save_current=False)
        execv.assert_not_called()
        self.assertEqual(popen.call_args.args[0], [exe, "--gui"])

    def test_no_status_update_waits_on_tk_while_the_window_exits(self):
        ui = mock.MagicMock()
        ui._exiting = True
        APP.DownloaderUI._on_service_status(ui, "Stopped")
        ui.root.after.assert_not_called()
        ui._exiting = False
        APP.DownloaderUI._on_service_status(ui, "Watching")
        ui.root.after.assert_called_once()


if __name__ == "__main__":
    unittest.main()
