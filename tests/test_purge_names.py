import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_purge_names_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


class PurgeNameTests(unittest.TestCase):
    def target(self, name):
        return APP._purge_paint_target(APP._purge_base_name(name))

    def test_current_decal_and_extension_names_are_purgeable(self):
        self.assertEqual(self.target("car_decal_42.tga"), (False, 42))
        self.assertEqual(self.target("car_decal_team_7_alt_ss.tga"), (True, 7))
        self.assertEqual(self.target("car_42_alt.tga"), (False, 42))
        self.assertEqual(self.target("car_spec_42_spec_alt.mip"), (False, 42))

    def test_pre_7_4_decal_name_is_still_purgeable(self):
        self.assertEqual(self.target("decal_42.tga"), (False, 42))

    def test_unrecognised_names_are_kept(self):
        self.assertIsNone(self.target("car_decal_x.tga"))
        self.assertIsNone(self.target("notes.tga"))


if __name__ == "__main__":
    unittest.main()
