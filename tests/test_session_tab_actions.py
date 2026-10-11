import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_session_tab_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


CAR = "ferrari296gt3"
SESSION_ID = APP.SessionId(555, 777)


def _row(user_id, **overrides):
    values = dict(
        iracing_id=user_id,
        display_name=f"Driver {user_id}",
        directory=CAR,
        status_code="downloaded",
        car_status_code="downloaded",
        helmet_status_code="",
        suit_status_code="",
    )
    values.update(overrides)
    return mock.Mock(**values)


class SessionActionStateTests(unittest.TestCase):
    def test_an_unchanged_selection_does_not_reread_the_paint_files(self):
        user = APP.SessionUser(user_id=7, directory=CAR)
        session = APP.Session(session_id=SESSION_ID, users={user})
        snapshot = mock.Mock(current_session=session, last_saved=[])
        ui = mock.MagicMock()
        ui._selected_session_contexts.return_value = (snapshot, [(_row(7), user)])
        ui._session_snapshot_signature.return_value = ("session", "rows")
        ui._session_row_iid.side_effect = lambda row: f"row-{row.iracing_id}"
        ui._driver_override_assignment_in_progress = set()
        ui._driver_restore_in_progress = set()
        ui._session_action_state_key = lambda s, c: APP.DownloaderUI._session_action_state_key(ui, s, c)
        ui.__dict__.pop("_last_session_action_state_key", None)
        with mock.patch.object(APP, "load_driver_paint_overrides", return_value={}) as load_overrides, \
             mock.patch.object(APP, "_load_paint_history_index", return_value={"entries": []}) as load_history:
            APP.DownloaderUI._update_session_action_state(ui)
            APP.DownloaderUI._update_session_action_state(ui)
            APP.DownloaderUI._update_session_action_state(ui)
            self.assertEqual(load_overrides.call_count, 1)
            self.assertEqual(load_history.call_count, 1)
            ui._driver_restore_in_progress = {"busy"}
            APP.DownloaderUI._update_session_action_state(ui)
            self.assertEqual(load_overrides.call_count, 2)


class ForgetTests(unittest.TestCase):
    def test_forgetting_many_drivers_restores_them_in_one_worker(self):
        user_rows = [(APP.SessionUser(user_id=uid, directory=CAR), _row(uid)) for uid in (1, 2, 3)]
        session = APP.Session(session_id=SESSION_ID, users={user for user, _row in user_rows})
        ui = mock.MagicMock()
        ui._driver_action_key.side_effect = lambda _session, user, kind: (user.user_id, kind)
        ui.__dict__["_driver_restore_in_progress"] = set()
        with mock.patch.object(APP.threading, "Thread") as thread_class:
            APP.DownloaderUI._restore_original_driver_paints_after_forget(ui, session, user_rows, "car")
            self.assertEqual(thread_class.call_count, 1)
            self.assertEqual(ui.__dict__["_driver_restore_in_progress"], {(1, "car"), (2, "car"), (3, "car")})
            # A second Forget for a driver still being restored does not start another download.
            APP.DownloaderUI._restore_original_driver_paints_after_forget(ui, session, user_rows[:1], "car")
            self.assertEqual(thread_class.call_count, 1)


class AssignCurrentTests(unittest.TestCase):
    def test_assign_current_copies_the_files_off_the_tk_thread(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        paint = folder / CAR / "car_7.tga"
        paint.parent.mkdir(parents=True)
        paint.write_bytes(b"paint")
        user = APP.SessionUser(user_id=7, directory=CAR)
        session = APP.Session(session_id=SESSION_ID, users={user})
        saved = [APP.SavedFile(SESSION_ID, APP.DownloadId(7, CAR, APP.PaintType.CAR), paint)]
        snapshot = mock.Mock(current_session=session, last_saved=saved)
        ui = mock.MagicMock()
        ui._require_selected_session_drivers.return_value = (snapshot, [(_row(7), user)])
        ui._driver_action_key.side_effect = lambda _session, user, kind: (user.user_id, kind)
        ui.__dict__["_driver_override_assignment_in_progress"] = set()
        with mock.patch.object(APP, "cache_saved_driver_paint_override") as cache:
            APP.DownloaderUI.assign_current_driver_paint(ui, "car")
            cache.assert_not_called()
        ui._run_ui_task.assert_called_once()
        self.assertEqual(ui.__dict__["_driver_override_assignment_in_progress"], {(7, "car")})


if __name__ == "__main__":
    unittest.main()
