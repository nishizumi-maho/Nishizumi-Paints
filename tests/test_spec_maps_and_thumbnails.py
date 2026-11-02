import importlib.util
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_spec_maps_thumbnails_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


def make_session(local_user_id: int | None = None, local_team_id: int | None = None):
    return APP.Session(
        session_id=APP.SessionId(1, None),
        users=set(),
        local_user_id=local_user_id,
        local_team_id=local_team_id,
    )


def car_path(user_id, directory, *, team=False, number=False, paints_dir=None):
    return APP.save_path_for(
        APP.DownloadId(
            user_id=user_id,
            directory=directory,
            paint_type=APP.PaintType.CAR_NUMBER if number else APP.PaintType.CAR,
            is_team_paint=team,
        ),
        paints_dir,
    )


def spec_path(user_id, directory, *, team=False, paints_dir=None):
    return APP.save_path_for(
        APP.DownloadId(
            user_id=user_id,
            directory=directory,
            paint_type=APP.PaintType.CAR_SPEC,
            is_team_paint=team,
        ),
        paints_dir,
    )


class SpecMapTests(unittest.TestCase):
    def test_spec_map_applied_only_when_car_paint_exists_and_spec_is_missing(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paints = root / "paint"
            spec_dir = root / "SpecMaps"
            spec_dir.mkdir()
            (spec_dir / "stockcars2 chevy.mip").write_bytes(b"DEFAULTSPEC")
            with_car = APP.SessionUser(user_id=1, directory="stockcars2 chevy", display_name="Driver One")
            without_car = APP.SessionUser(user_id=2, directory="stockcars2 chevy", display_name="Driver Two")
            existing = APP.SessionUser(user_id=3, directory="stockcars2 chevy", display_name="Driver Three")
            car_path(1, "stockcars2 chevy", paints_dir=paints).parent.mkdir(parents=True, exist_ok=True)
            car_path(1, "stockcars2 chevy", paints_dir=paints).write_bytes(b"PAINT")
            car_path(3, "stockcars2 chevy", paints_dir=paints).write_bytes(b"PAINT")
            spec_path(3, "stockcars2 chevy", paints_dir=paints).write_bytes(b"MY OWN SPEC")

            written = APP.apply_default_spec_maps(
                make_session(1), [with_car, without_car, existing], paints, spec_dir=spec_dir
            )

            self.assertEqual(written, [spec_path(1, "stockcars2 chevy", paints_dir=paints)])
            self.assertEqual(spec_path(1, "stockcars2 chevy", paints_dir=paints).read_bytes(), b"DEFAULTSPEC")
            self.assertFalse(spec_path(2, "stockcars2 chevy", paints_dir=paints).exists())
            self.assertEqual(spec_path(3, "stockcars2 chevy", paints_dir=paints).read_bytes(), b"MY OWN SPEC")

    def test_spec_map_stem_match_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paints = root / "paint"
            spec_dir = root / "SpecMaps"
            spec_dir.mkdir()
            (spec_dir / "StockCars2 Chevy.MIP").write_bytes(b"SPEC")
            user = APP.SessionUser(user_id=1, directory="stockcars2 chevy")
            car_path(1, "stockcars2 chevy", paints_dir=paints).parent.mkdir(parents=True, exist_ok=True)
            car_path(1, "stockcars2 chevy", paints_dir=paints).write_bytes(b"PAINT")

            written = APP.apply_default_spec_maps(make_session(1), [user], paints, spec_dir=spec_dir)

            self.assertEqual(written, [spec_path(1, "stockcars2 chevy", paints_dir=paints)])

    def test_spec_map_can_come_from_the_number_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paints = root / "paint"
            spec_dir = root / "SpecMaps"
            spec_dir.mkdir()
            (spec_dir / "stockcars2 chevy.mip").write_bytes(b"SPEC")
            user = APP.SessionUser(user_id=1, directory="stockcars2 chevy")
            number_path = car_path(1, "stockcars2 chevy", number=True, paints_dir=paints)
            number_path.parent.mkdir(parents=True, exist_ok=True)
            number_path.write_bytes(b"NUMBER")

            written = APP.apply_default_spec_maps(make_session(1), [user], paints, spec_dir=spec_dir)

            self.assertEqual(written, [spec_path(1, "stockcars2 chevy", paints_dir=paints)])

    def test_spec_map_uses_the_team_path_for_team_targets(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paints = root / "paint"
            spec_dir = root / "SpecMaps"
            spec_dir.mkdir()
            (spec_dir / "stockcars2 chevy.mip").write_bytes(b"TEAMSPEC")
            user = APP.SessionUser(user_id=7, directory="stockcars2 chevy", team_id=99, display_name="Team Driver")
            team_car = car_path(99, "stockcars2 chevy", team=True, paints_dir=paints)
            team_car.parent.mkdir(parents=True, exist_ok=True)
            team_car.write_bytes(b"TEAM PAINT")

            written = APP.apply_default_spec_maps(make_session(local_team_id=99), [user], paints, spec_dir=spec_dir)

            expected = spec_path(99, "stockcars2 chevy", team=True, paints_dir=paints)
            self.assertEqual(written, [expected])
            self.assertEqual(expected.read_bytes(), b"TEAMSPEC")
            self.assertFalse(spec_path(7, "stockcars2 chevy", paints_dir=paints).exists())

    def test_spec_maps_are_skipped_when_the_setting_is_disabled(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paints = root / "paint"
            user = APP.SessionUser(user_id=1, directory="stockcars2 chevy")
            car_path(1, "stockcars2 chevy", paints_dir=paints).parent.mkdir(parents=True, exist_ok=True)
            car_path(1, "stockcars2 chevy", paints_dir=paints).write_bytes(b"PAINT")
            with mock.patch.object(APP, "load_league_library", return_value=[]), mock.patch.object(
                APP, "apply_default_spec_maps"
            ) as apply_specs:
                written = APP.apply_post_save_extras(
                    make_session(1), [user], paints, use_default_spec_maps=False
                )
            self.assertEqual(written, [])
            apply_specs.assert_not_called()


class OrderTests(unittest.TestCase):
    def test_post_save_extras_runs_league_library_before_default_spec_maps_order(self):
        calls = []

        def league(*_args, **_kwargs):
            calls.append("league")
            return []

        def specs(*_args, **_kwargs):
            calls.append("spec")
            return []

        with tempfile.TemporaryDirectory() as temp:
            with mock.patch.object(APP, "load_league_library", return_value=[]), mock.patch.object(
                APP, "apply_league_library", side_effect=league
            ), mock.patch.object(APP, "apply_default_spec_maps", side_effect=specs):
                APP.apply_post_save_extras(make_session(1), [], Path(temp))

        self.assertEqual(calls, ["league", "spec"])


class ThumbnailTests(unittest.TestCase):
    def test_thumbnail_names_for_own_and_other_drivers(self):
        own = APP.SessionUser(user_id=1, directory="stockcars2 chevy")
        other = APP.SessionUser(user_id=456, directory="stockcars2 chevy")

        self.assertEqual(APP.car_thumbnail_name(own, local=True), "stockcars2_chevy.png")
        self.assertEqual(APP.car_thumbnail_name(other, local=False), "456_stockcars2_chevy.png")

    def test_thumbnail_skipped_when_it_is_newer_than_the_car_tga(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paints = root / "paint"
            thumbnails = root / "Thumbnails"
            thumbnails.mkdir()
            user = APP.SessionUser(user_id=1, directory="stockcars2 chevy")
            tga = car_path(1, "stockcars2 chevy", paints_dir=paints)
            tga.parent.mkdir(parents=True, exist_ok=True)
            tga.write_bytes(b"PAINT")
            old = time.time() - 100
            os.utime(tga, (old, old))
            existing = thumbnails / "stockcars2_chevy.png"
            existing.write_bytes(b"THUMB")
            fetch = mock.Mock()

            written = APP.generate_car_thumbnails(
                make_session(1),
                [user],
                paints,
                create_own=True,
                thumbnails_dir=thumbnails,
                service_available=lambda: True,
                fetch_png=fetch,
            )

            self.assertEqual(written, [])
            fetch.assert_not_called()

    def test_thumbnail_skipped_when_the_render_service_is_unavailable(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paints = root / "paint"
            thumbnails = root / "Thumbnails"
            user = APP.SessionUser(user_id=1, directory="stockcars2 chevy")
            tga = car_path(1, "stockcars2 chevy", paints_dir=paints)
            tga.parent.mkdir(parents=True, exist_ok=True)
            tga.write_bytes(b"PAINT")
            fetch = mock.Mock()

            written = APP.generate_car_thumbnails(
                make_session(1),
                [user],
                paints,
                create_own=True,
                thumbnails_dir=thumbnails,
                service_available=lambda: False,
                fetch_png=fetch,
            )

            self.assertEqual(written, [])
            fetch.assert_not_called()
            self.assertFalse(thumbnails.exists())

    def test_thumbnails_for_own_and_session_drivers_skip_ai(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paints = root / "paint"
            thumbnails = root / "Thumbnails"
            own = APP.SessionUser(user_id=1, directory="stockcars2 chevy", number="7", car_design="0,1,2")
            other = APP.SessionUser(user_id=2, directory="stockcars2 chevy", number="9")
            ai = APP.SessionUser(user_id=3, directory="stockcars2 chevy", is_ai=True)
            for user in (own, other, ai):
                tga = car_path(user.user_id, user.directory, paints_dir=paints)
                tga.parent.mkdir(parents=True, exist_ok=True)
                tga.write_bytes(b"PAINT")

            urls = []
            fetched = []

            def fetch(url, destination):
                urls.append(url)
                fetched.append(Path(destination))
                Path(destination).write_bytes(b"PNG")
                return Path(destination)

            written = APP.generate_car_thumbnails(
                make_session(1),
                [own, other, ai],
                paints,
                create_own=True,
                create_session=True,
                thumbnails_dir=thumbnails,
                service_available=lambda: True,
                render_url=lambda *args, **kwargs: "https://render.test/car",
                fetch_png=fetch,
            )

            self.assertEqual(
                sorted(path.name for path in written),
                ["2_stockcars2_chevy.png", "stockcars2_chevy.png"],
            )
            self.assertEqual(len(urls), 2)
            self.assertNotIn("3_stockcars2_chevy.png", [path.name for path in fetched])

    def test_only_own_thumbnail_when_session_thumbnails_are_off(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            paints = root / "paint"
            thumbnails = root / "Thumbnails"
            own = APP.SessionUser(user_id=1, directory="stockcars2 chevy")
            other = APP.SessionUser(user_id=2, directory="stockcars2 chevy")
            for user in (own, other):
                tga = car_path(user.user_id, user.directory, paints_dir=paints)
                tga.parent.mkdir(parents=True, exist_ok=True)
                tga.write_bytes(b"PAINT")

            written = APP.generate_car_thumbnails(
                make_session(1),
                [own, other],
                paints,
                create_own=True,
                create_session=False,
                thumbnails_dir=thumbnails,
                service_available=lambda: True,
                render_url=lambda *args, **kwargs: "https://render.test/car",
                fetch_png=lambda url, destination: Path(destination),
            )

            self.assertEqual([path.name for path in written], ["stockcars2_chevy.png"])


class ConfigTests(unittest.TestCase):
    def test_config_defaults_for_spec_maps_and_thumbnails(self):
        config = APP.AppConfig()

        self.assertTrue(config.use_default_spec_maps)
        self.assertTrue(config.create_own_car_thumbnails)
        self.assertFalse(config.create_session_car_thumbnails)

    def test_config_round_trip_for_spec_maps_and_thumbnails(self):
        with tempfile.TemporaryDirectory() as temp:
            store = APP.ConfigStore()
            store.path = Path(temp) / "settings.json"
            config = APP.AppConfig(
                use_default_spec_maps=False,
                create_own_car_thumbnails=False,
                create_session_car_thumbnails=True,
            )

            store.save(config)
            loaded = store.load()

            self.assertFalse(loaded.use_default_spec_maps)
            self.assertFalse(loaded.create_own_car_thumbnails)
            self.assertTrue(loaded.create_session_car_thumbnails)

    def test_older_config_without_the_fields_uses_the_defaults(self):
        with tempfile.TemporaryDirectory() as temp:
            store = APP.ConfigStore()
            store.path = Path(temp) / "settings.json"
            store.path.write_text('{"auto_start": true, "ui_mode": "advanced"}', encoding="utf-8")

            loaded = store.load()

            self.assertTrue(loaded.use_default_spec_maps)
            self.assertTrue(loaded.create_own_car_thumbnails)
            self.assertFalse(loaded.create_session_car_thumbnails)


if __name__ == "__main__":
    unittest.main()
