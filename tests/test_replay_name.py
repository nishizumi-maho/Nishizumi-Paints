import importlib.util
import json
import sys
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_replay_name_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


class RenderReplayNameTests(unittest.TestCase):
    def test_render_tokens_are_case_insensitive(self):
        self.assertEqual(
            APP.render_replay_name("{SERIES}-{Season}-{CATEGORY}", {"series": "9", "season": "2", "category": "Formula"}),
            "9-2-Formula",
        )

    def test_render_keeps_unknown_tokens_verbatim(self):
        self.assertEqual(APP.render_replay_name("{series} {unknown}", {"series": "9"}), "9 {unknown}")

    def test_render_empty_template_is_empty(self):
        self.assertEqual(APP.render_replay_name("", {"series": "9"}), "")

    def test_render_removes_invalid_filename_characters(self):
        self.assertEqual(APP.render_replay_name('A<>:"/\\|?*B', {}), "AB")
        self.assertEqual(APP.render_replay_name("{series}", {"series": 'Mo<n>t:r"e/a\\l|?*'}), "Montreal")

    def test_render_collapses_spaces_and_strips(self):
        self.assertEqual(APP.render_replay_name("  A   {series}    B  ", {"series": "9"}), "A 9 B")


class ReplayNameValueTests(unittest.TestCase):
    def _session(self, **weekend_overrides):
        weekend = {
            "SessionID": 123456,
            "SubSessionID": 654321,
            "SeriesID": 123,
            "SeasonID": 2,
            "LeagueID": 121,
            "RaceWeek": 3,
            "Category": "Formula",
            "EventDate": "2024-01-01",
            "EventTimeRaw": "6:30 pm",
            "TrackDisplayName": "Circuit Gilles Villeneuve",
            "TrackDisplayShortName": "Montreal",
        }
        weekend.update(weekend_overrides)
        driver_info = {
            "DriverUserID": 42,
            "DriverCarIdx": 1,
            "Drivers": [
                {
                    "UserID": 42,
                    "CarIdx": 1,
                    "CarPath": "fia f4",
                    "CarScreenName": "FIA F4",
                    "CarScreenNameShort": "FIA F4",
                }
            ],
        }
        return APP._build_session_from_parts(weekend, driver_info)

    def test_values_read_from_a_parsed_session(self):
        values = APP.replay_name_values(self._session())
        self.assertEqual(values["series"], "123")
        self.assertEqual(values["series_id"], "123")
        self.assertEqual(values["season"], "2")
        self.assertEqual(values["season_id"], "2")
        self.assertEqual(values["league_id"], "121")
        self.assertEqual(values["raceweek"], "3")
        self.assertEqual(values["session"], "123456")
        self.assertEqual(values["subsession"], "654321")
        self.assertEqual(values["category"], "Formula")
        self.assertEqual(values["simdate"], "2024-01-01")
        self.assertEqual(values["simtime"], "18:30")
        self.assertEqual(values["track"], "Montreal")
        self.assertEqual(values["car"], "FIA F4")

    def test_values_turn_zero_ids_into_empty_strings(self):
        session = self._session(SeriesID=0, SeasonID=0, LeagueID=0, RaceWeek=0, SubSessionID=0)
        values = APP.replay_name_values(session)
        for token in ("series", "series_id", "season", "season_id", "league_id", "raceweek", "subsession"):
            self.assertEqual(values[token], "", token)

    def test_values_keep_an_unparsable_sim_time_and_fall_back_to_the_display_name(self):
        session = self._session(EventTimeRaw="not a time", TrackDisplayShortName="")
        values = APP.replay_name_values(session)
        self.assertEqual(values["simtime"], "not a time")
        self.assertEqual(values["track"], "Circuit Gilles Villeneuve")
        self.assertRegex(values["localdate"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertRegex(values["localtime"], r"^\d{2}:\d{2}$")


class ReplayNameLatchTests(unittest.TestCase):
    CHECKERED = APP.REPLAY_NAME_CHECKERED_FLAG
    GREEN = APP.REPLAY_NAME_GREEN_FLAG

    def test_latch_checkered_copies_once_and_repeated_checkered_does_nothing(self):
        latch = APP.ReplayNameLatch()
        self.assertTrue(latch.update("1_2", self.CHECKERED))
        self.assertFalse(latch.update("1_2", self.CHECKERED))
        self.assertFalse(latch.update("1_2", self.CHECKERED))

    def test_latch_green_resets_the_checkered_catch(self):
        latch = APP.ReplayNameLatch()
        self.assertTrue(latch.update("1_2", self.CHECKERED))
        self.assertFalse(latch.update("1_2", self.GREEN))
        self.assertTrue(latch.update("1_2", self.CHECKERED))

    def test_latch_new_session_resets_the_checkered_catch(self):
        latch = APP.ReplayNameLatch()
        self.assertTrue(latch.update("1_2", self.CHECKERED))
        self.assertTrue(latch.update("3_4", self.CHECKERED))

    def test_latch_no_session_clears_the_catch(self):
        latch = APP.ReplayNameLatch()
        self.assertTrue(latch.update("1_2", self.CHECKERED))
        self.assertFalse(latch.update(None, 0))
        self.assertTrue(latch.update("1_2", self.CHECKERED))


class ReplayNameConfigTests(unittest.TestCase):
    def _store(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = APP.ConfigStore()
        store.path = Path(tmp.name) / "settings.json"
        return store

    def test_config_defaults_and_round_trip(self):
        config = APP.AppConfig()
        self.assertEqual(config.replay_name_template, "Series{series} S{season} Week{raceweek}")
        self.assertFalse(config.copy_replay_name_on_finish)
        store = self._store()
        store.save(replace(config, replay_name_template="Series{series} {track}", copy_replay_name_on_finish=True))
        loaded = store.load()
        self.assertEqual(loaded.replay_name_template, "Series{series} {track}")
        self.assertTrue(loaded.copy_replay_name_on_finish)

    def test_config_older_settings_without_the_replay_fields_use_defaults(self):
        store = self._store()
        store.path.write_text(json.dumps({"poll_seconds": 1.0}), encoding="utf-8")
        loaded = store.load()
        self.assertEqual(loaded.replay_name_template, "Series{series} S{season} Week{raceweek}")
        self.assertFalse(loaded.copy_replay_name_on_finish)


if __name__ == "__main__":
    unittest.main()
