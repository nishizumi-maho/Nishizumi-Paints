"""Paint theme tags and iRating/SR warning decals."""
import importlib.util
import io
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from PIL import Image


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_tags_warnings_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


CAR = "dirtlatemodel 350"


def _tga_bytes(colour, size=(4, 4)):
    image = Image.new("RGBA", size, (colour[0], colour[1], colour[2], 255))
    buffer = io.BytesIO()
    image.save(buffer, format="TGA")
    return buffer.getvalue()


class _TempFolder(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="nishizumi-tags-"))
        self.addCleanup(shutil.rmtree, self.root, True)


class TagThemeParseTests(unittest.TestCase):
    def test_theme_parse_generic_and_car_specific_names(self):
        generic = APP.parse_tag_theme_file("Neon.car.tga")
        self.assertIsNotNone(generic)
        self.assertEqual(generic.theme, "Neon")
        self.assertEqual(generic.car_folder, "")
        self.assertEqual(generic.file_type, "car")
        self.assertEqual(generic.path.name, "Neon.car.tga")

        spaced = APP.parse_tag_theme_file("Neon.dirtlatemodel 350.num.tga")
        self.assertIsNotNone(spaced)
        self.assertEqual(spaced.theme, "Neon")
        self.assertEqual(spaced.car_folder, CAR)
        self.assertEqual(spaced.file_type, "num")

        dotted = APP.parse_tag_theme_file("Neon.weird.car.name.decal.tga")
        self.assertIsNotNone(dotted)
        self.assertEqual(dotted.theme, "Neon")
        self.assertEqual(dotted.car_folder, "weird.car.name")
        self.assertEqual(dotted.file_type, "decal")

    def test_theme_parse_extensions_and_rejects(self):
        self.assertEqual(APP.parse_tag_theme_file("Neon.spec.mip").file_type, "spec")
        for name in (
            "",
            "garbage.tga",
            "Neon.paint.tga",
            "Neon.car.jpg",
            "Neon.spec.tga",
            "Neon.car.mip",
            ".car.tga",
        ):
            with self.subTest(name=name):
                self.assertIsNone(APP.parse_tag_theme_file(name))

    def test_theme_parse_load_and_specific_selection(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        (folder / "Neon.car.tga").write_bytes(b"generic car")
        (folder / "NEON.dirtlatemodel 350.car.tga").write_bytes(b"specific car")
        (folder / "neon.dirtlatemodel 350.decal.tga").write_bytes(b"specific decal")
        (folder / "Neon.Other .helmet.tga").write_bytes(b"other helmet")
        (folder / "not-a-theme.txt").write_bytes(b"ignore")

        themes = APP.load_tag_themes(folder)
        self.assertEqual(len(themes), 1)
        theme_name = next(iter(themes))
        self.assertEqual(theme_name, "Neon")

        files = APP.tag_theme_files_for(themes[theme_name], CAR.upper())
        self.assertEqual(files["car"].read_bytes(), b"specific car")
        self.assertEqual(files["decal"].read_bytes(), b"specific decal")
        self.assertNotIn("helmet", files)

        files = APP.tag_theme_files_for(themes[theme_name], "other car")
        self.assertEqual(files["car"].read_bytes(), b"generic car")


class TagsStorageTests(_TempFolder):
    def test_tags_storage_keeps_other_people_keys_and_round_trips(self):
        path = self.root / ".nishizumi_people.json"
        data = {
            "version": 1,
            "friends": {"7": "Driver Seven"},
            "driver_aliases": {"7": "Seven"},
            "team_aliases": {"42": "Team Forty-Two"},
            "tags": {"8": "Neon"},
        }
        APP.save_people(data, path)
        self.assertEqual(APP.load_people(path), data)

        APP.set_tag(9, "Glow", path)
        people = APP.load_people(path)
        self.assertEqual(people["friends"], {"7": "Driver Seven"})
        self.assertEqual(people["driver_aliases"], {"7": "Seven"})
        self.assertEqual(people["team_aliases"], {"42": "Team Forty-Two"})
        self.assertEqual(people["tags"], {"8": "Neon", "9": "Glow"})

        APP.set_tag(9, "", path)
        self.assertEqual(APP.load_people(path)["tags"], {"8": "Neon"})

    def test_tags_storage_without_the_key_loads_empty(self):
        path = self.root / "old.json"
        path.write_text(json.dumps({"version": 1, "friends": {"7": "Seven"}}), encoding="utf-8")
        people = APP.load_people(path)
        self.assertEqual(APP.tags_from_people(people), {})
        self.assertEqual(people["friends"], {"7": "Seven"})

    def test_tags_storage_clipboard_export_import_format(self):
        text = APP.format_tags_clipboard({"42": "Glow", "7": "Neon"}, {"7": "Seven", "42": "Forty-Two"})
        self.assertEqual(text, "Tags(7=Neon,Seven|42=Glow,Forty-Two)")
        self.assertEqual(APP.parse_tags_clipboard(text), {"7": "Neon", "42": "Glow"})
        self.assertEqual(APP.parse_tags_clipboard("Tags(7=Neon,Seven,With Comma|42=Glow,)"), {"7": "Neon", "42": "Glow"})
        self.assertEqual(APP.parse_tags_clipboard("nonsense"), {})


class ThemeApplyTests(_TempFolder):
    def setUp(self):
        super().setUp()
        self.themes_dir = self.root / "themes"
        self.themes_dir.mkdir()
        self.paints = self.root / "paint"
        self.paints.mkdir()
        self.session = APP.Session(
            session_id=APP.SessionId(1, None),
            users=set(),
            local_user_id=99,
        )

    def _apply(self, user, assignments):
        return APP.apply_tag_themes(
            self.session,
            [user],
            self.paints,
            APP.load_tag_themes(self.themes_dir),
            assignments,
        )

    def test_theme_apply_car_replaces_paint_and_drops_decal_and_spec(self):
        (self.themes_dir / f"Neon.{CAR}.car.tga").write_bytes(b"THEME CAR")
        user = APP.SessionUser(user_id=42, directory=CAR)
        folder = self.paints / CAR
        folder.mkdir()
        (folder / "car_42.tga").write_bytes(b"TP CAR")
        (folder / "car_num_42.tga").write_bytes(b"TP NUM")
        (folder / "decal_42.tga").write_bytes(b"TP DECAL")
        (folder / "car_spec_42.mip").write_bytes(b"TP SPEC")

        written = self._apply(user, {"42": "neon"})

        self.assertEqual((folder / "car_42.tga").read_bytes(), b"THEME CAR")
        self.assertFalse((folder / "car_num_42.tga").exists())
        self.assertFalse((folder / "decal_42.tga").exists())
        self.assertFalse((folder / "car_spec_42.mip").exists())
        self.assertEqual(set(written), {folder / "car_42.tga"})

    def test_theme_apply_num_replaces_number_and_keeps_supplied_extras(self):
        (self.themes_dir / "Neon.num.tga").write_bytes(b"THEME NUM")
        (self.themes_dir / f"Neon.{CAR}.spec.mip").write_bytes(b"THEME SPEC")
        (self.themes_dir / f"Neon.{CAR}.decal.tga").write_bytes(b"THEME DECAL")
        (self.themes_dir / "Neon.helmet.tga").write_bytes(b"THEME HELMET")
        (self.themes_dir / "Neon.suit.tga").write_bytes(b"THEME SUIT")
        user = APP.SessionUser(user_id=42, directory=CAR)
        folder = self.paints / CAR
        folder.mkdir()
        (folder / "car_42.tga").write_bytes(b"TP CAR")
        (folder / "car_num_42.tga").write_bytes(b"TP NUM")

        written = self._apply(user, {"42": "Neon"})

        self.assertFalse((folder / "car_42.tga").exists())
        self.assertEqual((folder / "car_num_42.tga").read_bytes(), b"THEME NUM")
        self.assertEqual((folder / "car_spec_42.mip").read_bytes(), b"THEME SPEC")
        self.assertEqual((folder / "decal_42.tga").read_bytes(), b"THEME DECAL")
        self.assertEqual((self.paints / "helmet_42.tga").read_bytes(), b"THEME HELMET")
        self.assertEqual((self.paints / "suit_42.tga").read_bytes(), b"THEME SUIT")
        self.assertEqual(len(written), 5)

    def test_theme_apply_local_user_is_untouched(self):
        (self.themes_dir / f"Neon.{CAR}.car.tga").write_bytes(b"THEME CAR")
        local = APP.SessionUser(user_id=99, directory=CAR)
        folder = self.paints / CAR
        folder.mkdir()
        (folder / "car_99.tga").write_bytes(b"MY CAR")
        (folder / "decal_99.tga").write_bytes(b"MY DECAL")

        written = self._apply(local, {"99": "Neon"})

        self.assertEqual(written, [])
        self.assertEqual((folder / "car_99.tga").read_bytes(), b"MY CAR")
        self.assertEqual((folder / "decal_99.tga").read_bytes(), b"MY DECAL")


class WarningRuleTests(unittest.TestCase):
    def _user(self, **kwargs):
        values = {
            "user_id": 42,
            "directory": CAR,
            "irating": 1400,
            "license_label": "A",
            "safety_rating": "3.45",
        }
        values.update(kwargs)
        return APP.SessionUser(**values)

    def test_warning_rule_table(self):
        cases = [
            ("off is always false", self._user(), "off", 1500, 2.0, False),
            ("and both match", self._user(irating=1000, safety_rating="1.50"), "and", 1500, 2.0, True),
            ("and irating fails", self._user(irating=2000, safety_rating="1.50"), "and", 1500, 2.0, False),
            ("and safety fails", self._user(irating=1000, safety_rating="3.00"), "and", 1500, 2.0, False),
            ("or irating matches", self._user(irating=1000, safety_rating="3.00"), "or", 1500, 2.0, True),
            ("or safety matches", self._user(irating=2000, safety_rating="1.00"), "or", 1500, 2.0, True),
            ("or neither matches", self._user(irating=2000, safety_rating="3.00"), "or", 1500, 2.0, False),
            ("rookies are excluded", self._user(license_label="R", irating=500, safety_rating="0.50"), "or", 1500, 2.0, False),
            ("missing licence is excluded", self._user(license_label="-"), "or", 1500, 2.0, False),
            ("AI is excluded", self._user(is_ai=True, irating=500, safety_rating="0.50"), "or", 1500, 2.0, False),
            ("unparsable SR is excluded", self._user(safety_rating="-"), "or", 1500, 2.0, False),
            ("None irating cannot match and", self._user(irating=None, safety_rating="1.00"), "and", 1500, 2.0, False),
            ("None irating can still match or", self._user(irating=None, safety_rating="1.00"), "or", 1500, 2.0, True),
            ("licence label carrying SR parses", self._user(license_label="A 1.25", safety_rating="-"), "and", 1500, 2.0, True),
        ]
        for label, user, mode, irating_limit, safety_limit, expected in cases:
            with self.subTest(label):
                self.assertEqual(
                    APP.warning_decal_applies(user, mode, irating_limit, safety_limit),
                    expected,
                )


class WarningApplyTests(_TempFolder):
    def setUp(self):
        super().setUp()
        self.themes_dir = self.root / "themes"
        self.themes_dir.mkdir()
        self.paints = self.root / "paint"
        self.paints.mkdir()
        self.session = APP.Session(
            session_id=APP.SessionId(1, None),
            users=set(),
            local_user_id=99,
        )

    def _eligible_user(self, user_id=42):
        return APP.SessionUser(
            user_id=user_id,
            directory=CAR,
            irating=1000,
            license_label="A",
            safety_rating="1.00",
        )

    def test_warning_apply_composites_on_top_of_existing_decal(self):
        (self.themes_dir / f"Warning.{CAR}.decal.tga").write_bytes(_tga_bytes((0, 255, 0)))
        folder = self.paints / CAR
        folder.mkdir()
        decal = folder / "decal_42.tga"
        decal.write_bytes(_tga_bytes((255, 0, 0)))

        written = APP.apply_warning_decals(
            self.session,
            [self._eligible_user()],
            self.paints,
            "and",
            1500,
            2.0,
            self.themes_dir,
        )

        self.assertEqual(written, [decal])
        with Image.open(decal) as image:
            self.assertEqual(image.convert("RGBA").getpixel((0, 0)), (0, 255, 0, 255))

    def test_warning_apply_copies_when_no_decal_exists(self):
        payload = _tga_bytes((0, 0, 255))
        (self.themes_dir / "Warning.decal.tga").write_bytes(payload)

        written = APP.apply_warning_decals(
            self.session,
            [self._eligible_user()],
            self.paints,
            "or",
            1500,
            2.0,
            self.themes_dir,
        )

        decal = self.paints / CAR / "decal_42.tga"
        self.assertEqual(written, [decal])
        self.assertEqual(decal.read_bytes(), payload)

    def test_warning_apply_skips_ineligible_and_local_users(self):
        (self.themes_dir / "Warning.decal.tga").write_bytes(_tga_bytes((0, 0, 255)))
        ineligible = APP.SessionUser(user_id=42, directory=CAR, irating=9000, license_label="A", safety_rating="4.00")
        local = self._eligible_user(user_id=99)

        written = APP.apply_warning_decals(
            self.session,
            [ineligible, local],
            self.paints,
            "and",
            1500,
            2.0,
            self.themes_dir,
        )

        self.assertEqual(written, [])
        self.assertFalse((self.paints / CAR / "decal_42.tga").exists())
        self.assertFalse((self.paints / CAR / "decal_99.tga").exists())


class PostSaveOrderTests(_TempFolder):
    def test_order_league_then_tags_then_warnings(self):
        calls = []
        session = APP.Session(session_id=APP.SessionId(1, None), users=set())

        def record(name):
            def _inner(*_args, **_kwargs):
                calls.append(name)
                return []
            return _inner

        with (
            mock.patch.object(APP, "load_league_library", return_value=[]),
            mock.patch.object(APP, "apply_league_library", side_effect=record("league")),
            mock.patch.object(APP, "apply_tag_themes", side_effect=record("tags")),
            mock.patch.object(APP, "apply_warning_decals", side_effect=record("warnings")),
            mock.patch.object(APP, "ConfigStore", return_value=mock.Mock(load=lambda: APP.AppConfig())),
        ):
            written = APP.apply_post_save_extras(session, [], self.root)

        self.assertEqual(calls, ["league", "tags", "warnings"])
        self.assertEqual(written, [])


if __name__ == "__main__":
    unittest.main()
