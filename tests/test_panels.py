"""Status, conditions, purge, manager tables and league preview helpers."""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_panels_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


class StrengthOfFieldTests(unittest.TestCase):
    def test_no_drivers_has_no_sof(self):
        self.assertEqual(APP.strength_of_field([]), 0)

    def test_one_driver_is_their_own_rating(self):
        self.assertEqual(APP.strength_of_field([2000]), 2000)

    def test_equal_ratings_stay_that_rating(self):
        self.assertEqual(APP.strength_of_field([1600, 1600, 1600]), 1600)

    def test_two_hand_computed_ratings(self):
        # 1600/ln(2) * ln(2 / (2^(-2000/1600) + 2^(-1000/1600))) = 1446.03
        self.assertEqual(APP.strength_of_field([2000, 1000]), 1446)

    def test_three_hand_computed_ratings(self):
        # 1600/ln(2) * ln(3 / (2^(-3000/1600) + 2^(-1500/1600) + 2^(-1000/1600))) = 1689.23
        self.assertEqual(APP.strength_of_field([3000, 1500, 1000]), 1689)

    def test_unknown_or_ai_ratings_are_not_counted(self):
        session = APP.Session(
            session_id=APP.SessionId(1, None),
            users={
                APP.SessionUser(user_id=1, directory="gt3", irating=2000),
                APP.SessionUser(user_id=2, directory="gt3", irating=1000),
                APP.SessionUser(user_id=3, directory="gt3", irating=5000, is_ai=True),
                APP.SessionUser(user_id=4, directory="gt3", irating=None),
            },
        )
        self.assertEqual(APP.session_strength_of_field(session), 1446)


class SessionConditionsTests(unittest.TestCase):
    def test_missing_values_use_the_dash_marker(self):
        session = APP.Session(session_id=APP.SessionId(1, None), users=set())
        values = dict(APP.session_condition_rows(session))
        self.assertEqual(values["Sim date"], "—")
        self.assertEqual(values["Air temperature"], "—")
        self.assertEqual(values["Pit speed limit"], "—")
        self.assertEqual(len(values), len(APP.SESSION_CONDITION_FIELDS))

    def test_values_keep_the_units_iracing_gives(self):
        session = APP.Session(
            session_id=APP.SessionId(1, None),
            users=set(),
            sim_date="2026-05-01",
            sim_time="14:30",
            air_temp="24.00 C",
            track_temp="38.00 C",
            humidity="55.00 %",
            wind_speed="2.00 m/s",
            wind_direction="45.00 rad",
            fog="0.00 %",
            skies="Clear",
            rain="0.00 %",
            track_length="3.70 km",
            turns="12",
            altitude="120.00 m",
            city="Monza",
            country="Italy",
            pit_speed_limit="60.00 kph",
            pace_speed_limit="45.00 kph",
        )
        values = dict(APP.session_condition_rows(session))
        self.assertEqual(values["Sim date"], "2026-05-01")
        self.assertEqual(values["Air temperature"], "24.00 C")
        self.assertEqual(values["Wind direction"], "45.00 rad")
        self.assertEqual(values["Track length"], "3.70 km")
        self.assertEqual(values["Turns"], "12")
        self.assertEqual(values["Pit speed limit"], "60.00 kph")
        self.assertEqual(values["Pace speed limit"], "45.00 kph")

    def test_session_from_weekend_info_reads_conditions(self):
        weekend = {
            "SessionID": 12,
            "TrackName": "monza",
            "Date": "2026-05-01",
            "EventTime": "14:30",
            "TrackAirTemp": "24.00 C",
            "TrackSurfaceTemp": "38.00 C",
            "TrackRelativeHumidity": "55.00 %",
            "TrackWindVel": "2.00 m/s",
            "TrackWindDir": "45.00 rad",
            "TrackFogLevel": "0.00 %",
            "TrackSkies": "Clear",
            "TrackPrecipitation": "0.00 %",
            "TrackLength": "3.70 km",
            "TrackNumTurns": 12,
            "TrackAltitude": "120.00 m",
            "TrackCity": "Monza",
            "TrackCountry": "Italy",
            "TrackPitSpeedLimit": "60.00 kph",
            "TrackPaceSpeed": "45.00 kph",
        }
        session = APP._build_session_from_parts(weekend, {"Drivers": []})
        self.assertIsNotNone(session)
        assert session is not None
        self.assertEqual(session.air_temp, "24.00 C")
        self.assertEqual(session.track_length, "3.70 km")
        self.assertEqual(session.turns, "12")
        self.assertEqual(session.city, "Monza")
        self.assertEqual(session.pace_speed_limit, "45.00 kph")


class PurgeSelectionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="nishizumi-purge-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.paint = self.root / "paint"
        self.car = self.paint / "gt3"
        self.car.mkdir(parents=True)

    def _touch(self, path: Path, size: int = 4) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)
        return path

    def test_purge_selects_only_app_owned_other_target_files(self):
        expected = {
            self._touch(self.car / "car_1001.tga"),
            self._touch(self.car / "car_1001_ss.tga"),
            self._touch(self.car / "car_num_1001.tga"),
            self._touch(self.car / "decal_1001.tga"),
            self._touch(self.car / "car_spec_1001.mip"),
            self._touch(self.car / "car_spec_1001_spec_ss.mip"),
            self._touch(self.car / "car_team_8.tga"),
            self._touch(self.paint / "helmet_1001.tga"),
            self._touch(self.paint / "suit_1001.tga"),
            self._touch(self.paint / "car_2002.tga.bz2"),
            self._touch(self.paint / f"car_2003.tga.{'a' * 32}.tmp"),
        }
        self._touch(self.car / "car_42.tga")
        self._touch(self.car / "car_team_7.tga")
        self._touch(self.paint / "helmet_42.tga")
        self._touch(self.paint / "not_a_paint.tga")
        self._touch(self.paint / "notes.txt")
        self._touch(self.paint / "unknown.tmp")
        preview = self._touch(self.paint / "car_1005.tga")

        selected = APP.select_purge_files(
            self.paint,
            own_member_id=42,
            own_team_id=7,
            protected_paths=[preview],
        )

        self.assertEqual({path.name for path in selected}, {path.name for path in expected})

    def test_purge_stats_count_selected_files_and_bytes(self):
        first = self._touch(self.paint / "car_1.tga", size=10)
        second = self._touch(self.paint / "helmet_1.tga", size=5)
        count, size = APP.purge_file_stats([first, second])
        self.assertEqual(count, 2)
        self.assertEqual(size, 15)


class ManagerTablesTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="nishizumi-manager-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        patcher = mock.patch.dict(os.environ, {"APPDATA": str(self.root / "appdata")})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_tables_are_assembled_from_the_stored_files(self):
        APP.save_people(
            {
                "tags": {"42": "Red"},
                "driver_aliases": {"42": "Alice"},
                "friends": {},
                "team_aliases": {},
            }
        )
        themes_dir = APP.default_tag_themes_dir()
        themes_dir.mkdir(parents=True, exist_ok=True)
        (themes_dir / "Red.car.tga").write_bytes(b"red")
        (themes_dir / "Blue.gt3.decal.tga").write_bytes(b"blue")
        APP.set_tp_paint_forbidden("user", 42, "car", "gt3", "Alice", True)

        tag_rows, theme_rows, forbidden_rows = APP.build_manager_tables(
            APP.load_people(),
            APP.load_tag_themes(),
            APP.load_forbidden_tp_paints(),
        )

        self.assertEqual(len(tag_rows), 1)
        self.assertEqual((tag_rows[0].member_id, tag_rows[0].name, tag_rows[0].theme), (42, "Alice", "Red"))
        self.assertEqual({(row.theme, row.car_folder, row.file_type) for row in theme_rows}, {
            ("Red", "", "car"),
            ("Blue", "gt3", "decal"),
        })
        self.assertEqual(len(forbidden_rows), 1)
        row = forbidden_rows[0]
        self.assertEqual((row.target_kind, row.target_id, row.kind, row.directory), ("user", 42, "car", "gt3"))
        self.assertEqual(row.display_name, "Alice")

    def test_unusable_people_entries_are_ignored(self):
        tag_rows, theme_rows, forbidden_rows = APP.build_manager_tables(
            {"tags": {"abc": "Red"}, "driver_aliases": {}},
            {},
            {"entries": {"broken": {"target_id": 1}}},
        )
        self.assertEqual(tag_rows, [])
        self.assertEqual(theme_rows, [])
        self.assertEqual(forbidden_rows, [])


class LeaguePreviewTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="nishizumi-league-preview-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.library = self.root / "league"
        self.library.mkdir()

    def _entry(self, kind, member_id, car_folder, car_class="GT3", num_type="", ext="tga"):
        return APP.LeagueLibraryEntry(
            kind=kind,
            league_id=121,
            car_class=car_class,
            member_id=member_id,
            car_folder=car_folder,
            num_type=num_type,
            ext=ext,
        )

    def _write(self, entry: APP.LeagueLibraryEntry, payload: bytes = b"x") -> Path:
        path = self.library / APP.league_library_name(entry)
        path.write_bytes(payload)
        return path

    def test_driver_decal_wins_and_library_paint_is_selected(self):
        all_decal = self._entry(APP.LEAGUE_LIBRARY_DECAL_KIND, 0, "gt3")
        driver_decal = self._entry(APP.LEAGUE_LIBRARY_DECAL_KIND, 42, "gt3")
        paint = self._entry(APP.LEAGUE_LIBRARY_PAINT_KIND, 42, "gt3", num_type="sim")
        self._write(all_decal)
        driver_path = self._write(driver_decal)
        paint_path = self._write(paint)

        selection = APP.league_preview_selection(
            [all_decal, driver_decal, paint],
            121,
            "gt3",
            car_class="GT3",
            member_id=42,
            library_dir=self.library,
        )

        self.assertEqual(selection.decal_path, driver_path)
        self.assertEqual(selection.paint_path, paint_path)
        self.assertEqual(selection.member_id, 42)

    def test_all_driver_decal_is_the_fallback(self):
        all_decal = self._entry(APP.LEAGUE_LIBRARY_DECAL_KIND, 0, "gt3")
        decal_path = self._write(all_decal)

        selection = APP.league_preview_selection(
            [all_decal],
            121,
            "gt3",
            car_class="GT3",
            member_id=42,
            library_dir=self.library,
        )

        self.assertEqual(selection.decal_path, decal_path)
        self.assertIsNone(selection.paint_path)

    def test_chosen_paint_tga_overrides_the_library_paint(self):
        decal = self._entry(APP.LEAGUE_LIBRARY_DECAL_KIND, 0, "gt3")
        paint = self._entry(APP.LEAGUE_LIBRARY_PAINT_KIND, 42, "gt3", num_type="sim")
        self._write(decal)
        self._write(paint)
        chosen = self.root / "chosen.tga"
        chosen.write_bytes(b"chosen")

        selection = APP.league_preview_selection(
            [decal, paint],
            121,
            "gt3",
            car_class="GT3",
            member_id=42,
            paint_path=chosen,
            library_dir=self.library,
        )

        self.assertEqual(selection.paint_path, chosen)

    def test_export_jobs_need_a_paint_and_a_decal(self):
        decal = self._entry(APP.LEAGUE_LIBRARY_DECAL_KIND, 0, "gt3")
        paint = self._entry(APP.LEAGUE_LIBRARY_PAINT_KIND, 42, "gt3", num_type="sim")
        self._write(decal)
        self._write(paint)

        jobs = APP.league_export_jobs([decal, paint], league_id=121, library_dir=self.library)

        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].member_id, 42)
        self.assertEqual(jobs[0].car_folder, "gt3")
        self.assertTrue(jobs[0].file_name.endswith(".png"))
        self.assertIsNotNone(jobs[0].decal_path)


if __name__ == "__main__":
    unittest.main()
