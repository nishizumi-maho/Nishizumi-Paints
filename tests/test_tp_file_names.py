import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_tp_file_names_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


CAR = "mx5 mx52016"


def _download_id(paint_type, *, user_id=42, team=False, ext="", ss=False):
    return APP.DownloadId(
        user_id=user_id,
        directory=CAR,
        paint_type=paint_type,
        is_team_paint=team,
        is_superspeedway_variant=ss,
        ext=ext,
    )


class SavePathTests(unittest.TestCase):
    def setUp(self):
        self.paints = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.paints, True)

    def test_decal_uses_the_name_iracing_reads(self):
        path = APP.save_path_for(_download_id(APP.PaintType.CAR_DECAL), self.paints)
        self.assertEqual(path.name, "car_decal_42.tga")

    def test_team_decal_keeps_the_team_infix(self):
        path = APP.save_path_for(_download_id(APP.PaintType.CAR_DECAL, user_id=9, team=True), self.paints)
        self.assertEqual(path.name, "car_decal_team_9.tga")

    def test_custom_paint_extension_is_appended(self):
        cases = {
            APP.PaintType.CAR: "car_42_alt.tga",
            APP.PaintType.CAR_NUMBER: "car_num_42_alt.tga",
            APP.PaintType.CAR_SPEC: "car_spec_42_alt.mip",
            APP.PaintType.CAR_DECAL: "car_decal_42_alt.tga",
        }
        for paint_type, expected in cases.items():
            with self.subTest(paint_type=paint_type):
                path = APP.save_path_for(_download_id(paint_type, ext="alt"), self.paints)
                self.assertEqual(path.name, expected)

    def test_extension_and_superspeedway_suffixes_do_not_duplicate_ss(self):
        path = APP.save_path_for(_download_id(APP.PaintType.CAR, ss=True), self.paints)
        self.assertEqual(path.name, "car_42_ss.tga")
        path = APP.save_path_for(_download_id(APP.PaintType.CAR, ext="ss", ss=True), self.paints)
        self.assertEqual(path.name, "car_42_ss.tga")
        path = APP.save_path_for(_download_id(APP.PaintType.CAR, ext="alt", ss=True), self.paints)
        self.assertEqual(path.name, "car_42_alt_ss.tga")

    def test_team_helmet_has_no_team_infix_but_team_suit_does(self):
        helmet = APP.save_path_for(_download_id(APP.PaintType.HELMET, user_id=7, team=True), self.paints)
        suit = APP.save_path_for(_download_id(APP.PaintType.SUIT, user_id=9, team=True), self.paints)
        self.assertEqual(helmet.name, "helmet_7.tga")
        self.assertEqual(suit.name, "suit_team_9.tga")


class ParserTests(unittest.TestCase):
    def test_new_names_round_trip_through_save_path_for(self):
        cases = [
            _download_id(APP.PaintType.CAR),
            _download_id(APP.PaintType.CAR_NUMBER, ext="alt"),
            _download_id(APP.PaintType.CAR_SPEC, ext="alt", ss=True),
            _download_id(APP.PaintType.CAR_DECAL, ext="alt"),
            _download_id(APP.PaintType.CAR_DECAL, user_id=9, team=True),
            _download_id(APP.PaintType.HELMET, user_id=7),
            _download_id(APP.PaintType.SUIT, user_id=9, team=True),
        ]
        root = Path(r"C:\Users\me\Documents\iRacing\paint")
        for download_id in cases:
            with self.subTest(download_id=download_id):
                path = APP.save_path_for(download_id, root)
                parsed = APP._parse_saved_paint_filename(path, root)
                self.assertIsNotNone(parsed)
                paint_type, _directory, target_id, is_team, is_ss = parsed
                self.assertEqual(paint_type, download_id.paint_type)
                self.assertEqual(target_id, download_id.user_id)
                self.assertEqual(is_team, download_id.is_team_paint)
                self.assertEqual(is_ss, download_id.is_superspeedway_variant)

    def test_old_decal_name_is_still_recognised(self):
        root = Path(r"C:\Users\me\Documents\iRacing\paint")
        parsed = APP._parse_saved_paint_filename(root / CAR / "decal_42.tga", root)
        self.assertEqual(parsed[0], APP.PaintType.CAR_DECAL)
        self.assertEqual(parsed[2], 42)
        parsed = APP._parse_saved_paint_filename(root / CAR / "decal_team_9_ss.tga", root)
        self.assertEqual(parsed[0], APP.PaintType.CAR_DECAL)
        self.assertTrue(parsed[3])
        self.assertTrue(parsed[4])


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.paints = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.paints, True)
        self.folder = self.paints / CAR
        self.folder.mkdir()

    def test_old_decal_is_renamed_when_the_new_name_is_missing(self):
        old = self.folder / "decal_42.tga"
        old.write_bytes(b"paint")

        renamed, removed = APP.migrate_legacy_decal_filenames(self.paints)

        self.assertEqual((renamed, removed), (1, 0))
        self.assertFalse(old.exists())
        self.assertEqual((self.folder / "car_decal_42.tga").read_bytes(), b"paint")

    def test_old_decal_is_deleted_when_the_new_name_already_exists(self):
        old = self.folder / "decal_42.tga"
        old.write_bytes(b"old")
        new = self.folder / "car_decal_42.tga"
        new.write_bytes(b"new")

        renamed, removed = APP.migrate_legacy_decal_filenames(self.paints)

        self.assertEqual((renamed, removed), (0, 1))
        self.assertFalse(old.exists())
        self.assertEqual(new.read_bytes(), b"new")

    def test_team_decal_and_ss_variants_are_migrated(self):
        old = self.folder / "decal_team_9_ss.tga"
        old.write_bytes(b"paint")

        APP.migrate_legacy_decal_filenames(self.paints)

        self.assertTrue((self.folder / "car_decal_team_9_ss.tga").exists())
        self.assertFalse(old.exists())

    def test_hand_made_names_are_not_touched(self):
        handmade = self.folder / "decal_custom.tga"
        handmade.write_bytes(b"paint")

        APP.migrate_legacy_decal_filenames(self.paints)

        self.assertTrue(handmade.exists())


class NumberNormalisationTests(unittest.TestCase):
    def _sent_number(self, number):
        user = APP.SessionUser(user_id=42, directory=CAR, number=number)
        return user.trading_paints_list_value().split("=")[3]

    def test_only_digits_and_dots_survive(self):
        self.assertEqual(self._sent_number("A1"), "1")
        self.assertEqual(self._sent_number("12.5"), "12.5")
        self.assertEqual(self._sent_number("07"), "07")

    def test_context_payload_uses_the_same_number(self):
        payload = APP.tp_download_context_payload(
            42, 0, CAR, night="", series_id=0, league_id=0, custom_numbers=True, number="A1"
        )
        self.assertEqual(payload["list"].split("=")[3], "1")


class ManifestExtTests(unittest.TestCase):
    def test_manifest_ext_and_filesize_are_carried_into_the_download(self):
        xml = (
            "<Cars><Car>"
            "<file>https://example.invalid/car.tga.bz2</file>"
            f"<directory>{CAR}</directory>"
            "<type>car</type><userid>42</userid><teamid>0</teamid>"
            "<ext>alt</ext><filesize>1234</filesize>"
            "</Car></Cars>"
        )
        items = APP._parse_fetch_user_manifest_xml(42, xml)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].download_id.ext, "alt")
        self.assertEqual(items[0].expected_size, 1234)


if __name__ == "__main__":
    unittest.main()
