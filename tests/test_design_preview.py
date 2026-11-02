import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_design_preview_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


def _driver(**overrides):
    driver = {
        "UserID": 42,
        "CarPath": "mx5 mx52016",
        "CarID": 10,
        "CarScreenName": "Mazda MX-5",
        "CarNumber": "7",
        "UserName": "Test Driver",
        "CarIsAI": 0,
        "IRating": 1500,
        "LicString": "A 4.99",
        "CarDesignStr": "12,ABCDEF,123456,FFFFFF",
        "HelmetDesignStr": "5,111111,222222,333333",
        "SuitDesignStr": "6,AAAAAA,BBBBBB,CCCCCC",
    }
    driver.update(overrides)
    return driver


def _session(*drivers):
    weekend = {
        "SessionID": 123,
        "SubSessionID": 456,
        "TeamRacing": False,
        "EventTime": "10:00 am",
        "TrackName": "test track",
    }
    return APP._build_session_from_parts(weekend, {"DriverCarIdx": 0, "Drivers": list(drivers)})


class DesignFieldTests(unittest.TestCase):
    def test_design_fields_are_parsed_from_driver_info(self):
        session = _session(_driver())

        self.assertIsNotNone(session)
        user = next(iter(session.users))
        self.assertEqual(user.car_design, "12,ABCDEF,123456,FFFFFF")
        self.assertEqual(user.helmet_design, "5,111111,222222,333333")
        self.assertEqual(user.suit_design, "6,AAAAAA,BBBBBB,CCCCCC")

    def test_design_fields_are_not_part_of_identity_or_fingerprint(self):
        plain = APP.SessionUser(user_id=42, directory="mx5 mx52016")
        styled = APP.SessionUser(
            user_id=42,
            directory="mx5 mx52016",
            car_design="12,ABCDEF,123456,FFFFFF",
            helmet_design="5,111111,222222,333333",
            suit_design="6,AAAAAA,BBBBBB,CCCCCC",
        )

        self.assertEqual(plain, styled)
        self.assertEqual(hash(plain), hash(styled))
        self.assertEqual(len({plain, styled}), 1)

        plain_session = APP.Session(session_id=APP.SessionId(1, 2), users={plain})
        styled_session = APP.Session(session_id=APP.SessionId(1, 2), users={styled})
        self.assertEqual(plain_session.identity_fingerprint(), styled_session.identity_fingerprint())
        self.assertEqual(APP._session_fingerprint_key(plain_session), APP._session_fingerprint_key(styled_session))

    def test_missing_design_strings_keep_the_empty_defaults(self):
        session = _session(_driver(CarDesignStr=None, HelmetDesignStr="", SuitDesignStr=None))

        user = next(iter(session.users))
        self.assertEqual(user.car_design, "")
        self.assertEqual(user.helmet_design, "")
        self.assertEqual(user.suit_design, "")


class PreviewInputTests(unittest.TestCase):
    def setUp(self):
        self.paints = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.paints, True)
        self.car_dir = self.paints / "mx5 mx52016"
        self.car_dir.mkdir()

    def _user(self, **kwargs):
        values = {
            "user_id": 42,
            "directory": "mx5 mx52016",
            "number": "7",
            "car_design": "12,ABCDEF,123456,FFFFFF",
            "helmet_design": "5,111111,222222,333333",
            "suit_design": "6,AAAAAA,BBBBBB,CCCCCC",
        }
        values.update(kwargs)
        return APP.SessionUser(**values)

    def test_inputs_prefer_the_installed_car_paint(self):
        car_tga = self.car_dir / "car_42.tga"
        car_tga.write_bytes(b"car")
        decal_tga = self.car_dir / "decal_42.tga"
        decal_tga.write_bytes(b"decal")
        (self.paints / "helmet_42.tga").write_bytes(b"helmet")
        (self.paints / "suit_42.tga").write_bytes(b"suit")

        inputs = APP.session_preview_inputs(self._user(), self.paints)

        self.assertEqual(inputs["car_tga"], car_tga)
        self.assertEqual(inputs["decal_tga"], decal_tga)
        self.assertEqual(inputs["helmet_tga"], self.paints / "helmet_42.tga")
        self.assertEqual(inputs["suit_tga"], self.paints / "suit_42.tga")
        self.assertEqual(inputs["car_path"], "mx5 mx52016")
        self.assertEqual(inputs["design"], "12,ABCDEF,123456,FFFFFF")
        self.assertEqual(inputs["number"], "7")
        self.assertFalse(inputs["uses_design"])

    def test_inputs_without_a_car_paint_use_the_iracing_design(self):
        inputs = APP.session_preview_inputs(self._user(), self.paints)

        self.assertIsNone(inputs["car_tga"])
        self.assertIsNone(inputs["decal_tga"])
        self.assertIsNone(inputs["helmet_tga"])
        self.assertIsNone(inputs["suit_tga"])
        self.assertTrue(inputs["uses_design"])

    def test_inputs_use_the_team_variant_path_for_a_team_driver(self):
        (self.car_dir / "car_42.tga").write_bytes(b"personal")
        team_car = self.car_dir / "car_team_55.tga"
        team_car.write_bytes(b"team")

        inputs = APP.session_preview_inputs(self._user(team_id=55), self.paints)

        self.assertEqual(inputs["car_tga"], team_car)
        self.assertFalse(inputs["uses_design"])

    def test_inputs_turn_a_zero_number_into_none(self):
        for raw, expected in (("0", None), ("", None), ("007", "007"), (" 12 ", "12")):
            with self.subTest(number=raw):
                inputs = APP.session_preview_inputs(self._user(number=raw), self.paints)
                self.assertEqual(inputs["number"], expected)


class DesignUrlTests(unittest.TestCase):
    def test_design_url_has_the_pattern_colours_and_no_custom_paint(self):
        url = APP.iracing_render_url(
            "car",
            "",
            car_path="mx5 mx52016",
            design="12,ABCDEF,123456,FFFFFF",
            number="7",
            tick=1,
        )

        self.assertIn("carPat=12", url)
        self.assertIn("carCol=ABCDEF,123456,FFFFFF", url)
        self.assertIn("&number=7", url)
        self.assertTrue(url.endswith("carCustPaint="))


class ExportNameTests(unittest.TestCase):
    def test_export_names_use_the_member_and_car_folder(self):
        names = APP.preview_export_names(1234, "NASCAR Cup Series Ford Mustang")

        self.assertEqual(
            names,
            {
                "car": "1234_NASCAR_Cup_Series_Ford_Mustang.png",
                "helmet": "1234_helmet.png",
                "suit": "1234_suit.png",
            },
        )

    def test_export_names_fall_back_to_a_generic_car_name(self):
        names = APP.preview_export_names(0, "")

        self.assertEqual(names["car"], "0_car.png")
        self.assertEqual(names["helmet"], "0_helmet.png")
        self.assertEqual(names["suit"], "0_suit.png")


if __name__ == "__main__":
    unittest.main()
