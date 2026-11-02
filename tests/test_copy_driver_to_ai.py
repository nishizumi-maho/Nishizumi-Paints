import configparser
import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_copy_driver_ai_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


CAR = "ferrari296gt3"
SESSION_ID = APP.SessionId(555, 777)


def _saved_file(root, user_id, *, is_team=False, tp_title="", tp_source_link="", tp_source=""):
    folder = root / "saved" / CAR
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"car_{user_id}{'_team' if is_team else ''}.tga"
    path.write_bytes(b"paint")
    download_id = APP.DownloadId(
        user_id=user_id,
        directory=CAR,
        paint_type=APP.PaintType.CAR,
        is_team_paint=is_team,
        tp_title=tp_title,
        tp_source_link=tp_source_link,
        tp_source=tp_source,
    )
    return APP.SavedFile(SESSION_ID, download_id, path)


class TargetKeyFilterTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_target_keys_filter_groups_and_none_copies_all(self):
        saved = [_saved_file(self.tmp, 1), _saved_file(self.tmp, 2)]

        everything_root = self.tmp / "everything"
        self.assertEqual(APP.import_saved_paint_groups_to_ai_livery(saved, None, everything_root), (2, 2))
        self.assertTrue((everything_root / CAR / "car_1.tga").exists())
        self.assertTrue((everything_root / CAR / "car_2.tga").exists())

        selected_root = self.tmp / "selected"
        copied_sets, copied_files, paths = APP.import_selected_paint_groups_to_ai_livery(
            saved, None, selected_root, target_keys={(1, False)}
        )
        self.assertEqual((copied_sets, copied_files), (1, 1))
        self.assertEqual([path.name for path in paths], ["car_1.tga"])
        self.assertTrue((selected_root / CAR / "car_1.tga").exists())
        self.assertFalse((selected_root / CAR / "car_2.tga").exists())

    def test_target_keys_keep_team_and_driver_groups_apart(self):
        saved = [
            _saved_file(self.tmp, 7),
            _saved_file(self.tmp, 42, is_team=True),
        ]
        ai_root = self.tmp / "ai"
        copied_sets, _copied_files, paths = APP.import_selected_paint_groups_to_ai_livery(
            saved, None, ai_root, target_keys={(42, True)}
        )
        self.assertEqual(copied_sets, 1)
        self.assertEqual([path.name for path in paths], ["car_1.tga"])

    def test_session_users_map_to_their_effective_saved_target(self):
        driver = APP.SessionUser(user_id=7, directory=CAR)
        team_driver = APP.SessionUser(user_id=8, directory=CAR, team_id=42)
        ai_driver = APP.SessionUser(user_id=9, directory=CAR, team_id=42, is_ai=True)
        self.assertEqual(APP.session_user_saved_target_key(driver), (7, False))
        self.assertEqual(APP.session_user_saved_target_key(team_driver), (42, True))
        self.assertEqual(APP.session_user_saved_target_key(ai_driver), (9, False))


class SourceNoteTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_note_ini_written_with_metadata_and_absent_otherwise(self):
        saved = [
            _saved_file(
                self.tmp,
                7,
                tp_title="Nice Paint",
                tp_source_link="https://www.tradingpaints.com/showroom/view/123/Nice-Paint",
                tp_source="showroom",
            )
        ]
        session = APP.Session(
            session_id=SESSION_ID,
            users={APP.SessionUser(user_id=7, directory=CAR, display_name="Driver Seven")},
        )
        ai_root = self.tmp / "ai"
        APP.import_saved_paint_groups_to_ai_livery(saved, session, ai_root)

        note_path = ai_root / CAR / "car_1.ini"
        self.assertTrue(note_path.exists())
        parser = configparser.ConfigParser()
        parser.read(note_path, encoding="utf-8")
        self.assertTrue(parser.has_section("TradingPaints"))
        self.assertEqual(parser.get("TradingPaints", "Url"), "https://www.tradingpaints.com/showroom/view/123/Nice-Paint")
        self.assertEqual(parser.get("TradingPaints", "Title"), "Nice Paint")
        self.assertEqual(parser.get("TradingPaints", "Source"), "showroom")
        self.assertEqual(parser.get("TradingPaints", "CopiedFrom"), "Driver Seven")
        self.assertEqual([item.name for item in (ai_root / CAR).glob("*.tmp")], [])

        plain = [_saved_file(self.tmp, 8)]
        plain_root = self.tmp / "plain"
        APP.import_saved_paint_groups_to_ai_livery(plain, None, plain_root)
        self.assertEqual([item.name for item in (plain_root / CAR).glob("*.ini")], [])


class CacheIdCollisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_new_ids_do_not_collide_with_existing_car_tga_files(self):
        ai_root = self.tmp / "ai"
        car_dir = ai_root / CAR
        car_dir.mkdir(parents=True)
        for existing in ("car_1.tga", "car_5.tga", "car_5.ini"):
            (car_dir / existing).write_bytes(b"existing")
        saved = [_saved_file(self.tmp, 7)]
        copied_sets, _copied_files, paths = APP.import_selected_paint_groups_to_ai_livery(
            saved, None, ai_root, target_keys={(7, False)}
        )
        self.assertEqual(copied_sets, 1)
        self.assertEqual([path.name for path in paths], ["car_6.tga"])
        self.assertEqual((car_dir / "car_1.tga").read_bytes(), b"existing")
        self.assertEqual((car_dir / "car_5.tga").read_bytes(), b"existing")


class SelectedCopyUiTests(unittest.TestCase):
    def test_selected_copy_passes_effective_targets_and_logs_the_names(self):
        user = APP.SessionUser(user_id=7, directory=CAR, display_name="Driver Seven")
        session = APP.Session(session_id=SESSION_ID, users={user})
        row = mock.Mock(display_name="Driver Seven")
        snapshot = mock.Mock(current_session=session, last_saved=[])
        ui = mock.MagicMock()
        ui._require_selected_session_drivers.return_value = (snapshot, [(row, user)])
        ai_root = Path("ai-livery")
        with mock.patch.object(APP, "default_ai_livery_dir", return_value=ai_root), \
             mock.patch.object(APP, "import_selected_paint_groups_to_ai_livery", return_value=(1, 1, [Path("car_1.tga")])) as copy:
            APP.DownloaderUI.copy_selected_drivers_to_ai(ui)
            work = ui._run_ui_task.call_args[0][2]
            self.assertEqual(work(), (1, [Path("car_1.tga")]))
            copy.assert_called_once_with([], session, ai_root, {(7, False)})
        done = ui._run_ui_task.call_args[0][3]
        done((1, [Path("car_1.tga")]), None)
        ui._append_log.assert_called_with("Copied 1 car set(s) for Driver Seven into the AI livery folder.")
        done((0, []), None)
        ui._append_log.assert_called_with("No downloaded car paint to copy for Driver Seven.")


if __name__ == "__main__":
    unittest.main()
