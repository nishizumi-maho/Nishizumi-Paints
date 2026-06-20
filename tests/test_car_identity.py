import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


class TradingPaintsCarIdentityTests(unittest.TestCase):
    def setUp(self):
        with APP._TP_CAR_IDENTITY_CACHE_LOCK:
            APP._TP_CAR_IDENTITY_CACHE_DOC = None
            APP._TP_CAR_IDENTITY_CACHE_AT = 0.0
            APP._TP_CAR_IDENTITY_LAST_ATTEMPT_AT = 0.0
            APP._TP_CAR_IDENTITY_LAST_ERROR = ""
            APP._TP_CAR_IDENTITY_LAST_UNKNOWN_REFRESH_AT = 0.0
        with APP._IRACING_OBSERVED_CAR_IDENTITIES_LOCK:
            APP._IRACING_OBSERVED_CAR_IDENTITIES.clear()
        with APP._TP_MANIFEST_OBSERVED_DIRECTORIES_LOCK:
            APP._TP_MANIFEST_OBSERVED_DIRECTORIES.clear()

    def _install_catalog(self, entries):
        doc = APP._build_tp_car_identity_doc(entries)
        with APP._TP_CAR_IDENTITY_CACHE_LOCK:
            APP._TP_CAR_IDENTITY_CACHE_DOC = doc
            APP._TP_CAR_IDENTITY_CACHE_AT = APP.time.monotonic()
            APP._TP_CAR_IDENTITY_LAST_ATTEMPT_AT = APP._TP_CAR_IDENTITY_CACHE_AT
        return doc

    def test_template_catalog_parses_mid_name_and_iracing_directory(self):
        page = """
        <div id="car_264" class="car">
          <a href="/template.zip">
            <h3>Ferrari 296 GT3</h3>
            <span>Documents/iRacing/paint/ferrari296gt3</span>
          </a>
        </div>
        """
        entries = APP._parse_tp_car_templates_html(page)
        self.assertEqual(
            entries,
            [
                {
                    "mid": 264,
                    "tp_name": "Ferrari 296 GT3",
                    "iracing_name": "Ferrari 296 GT3",
                    "directory": "ferrari296gt3",
                    "slug": "Ferrari-296-GT3",
                    "category": "Road",
                    "is_superspeedway_variant": False,
                    "source": "trading_paints_cartemplates",
                }
            ],
        )

    def test_duplicate_template_directory_is_kept_as_vehicle_variants(self):
        doc = APP._build_tp_car_identity_doc(
            [
                {
                    "mid": 297,
                    "tp_name": "Gen 4 Chevrolet Monte Carlo - 2003",
                    "directory": "stockcars chevymontecarlo03",
                },
                {
                    "mid": 298,
                    "tp_name": "Gen 4 Chevrolet Monte Carlo - 2003 SS",
                    "directory": "stockcars chevymontecarlo03",
                    "is_superspeedway_variant": True,
                },
            ]
        )
        entry = doc["cars"]["stockcars\\chevymontecarlo03"]
        self.assertEqual(entry["mid"], 297)
        self.assertEqual([variant["mid"] for variant in entry["variants"]], [297, 298])
        self.assertEqual(entry["alternate_mids"], [298])

    def test_vehicle_name_ending_in_ss_is_not_a_superspeedway_variant_by_itself(self):
        doc = APP._build_tp_car_identity_doc(
            [
                {
                    "mid": 294,
                    "tp_name": "ARCA Chevrolet SS",
                    "directory": "stockcars2 arcachevy25",
                    "is_superspeedway_variant": True,
                }
            ]
        )
        entry = doc["cars"]["stockcars2\\arcachevy25"]
        self.assertFalse(entry["is_superspeedway_variant"])
        self.assertFalse(entry["variants"][0]["is_superspeedway_variant"])

    def test_iracing_sdk_name_learns_an_unlisted_directory_alias(self):
        self._install_catalog(
            [
                {
                    "mid": 401,
                    "tp_name": "Example GT3 2027",
                    "iracing_name": "Example GT3 2027",
                    "directory": "examplegt3",
                    "slug": "Example-GT3-2027",
                }
            ]
        )
        APP._observe_iracing_car_identity("manufacturer examplegt3-2027", "Example GT3 2027", 9001)
        resolved = APP._tp_showroom_mapping_entry_for_directory("manufacturer examplegt3-2027")
        self.assertIsNotNone(resolved)
        directory, entry = resolved
        self.assertEqual(directory, "manufacturer\\examplegt3-2027")
        self.assertEqual(entry["mid"], 401)
        self.assertEqual(entry["source"], "iracing_sdk_plus_trading_paints_cartemplates")

    def test_iracing_sdk_alias_tolerates_a_unique_minor_name_difference(self):
        self._install_catalog(
            [
                {
                    "mid": 401,
                    "tp_name": "Example GT3 Evo 2027",
                    "directory": "examplegt3",
                },
                {
                    "mid": 402,
                    "tp_name": "Unrelated Formula Car",
                    "directory": "unrelatedformula",
                },
            ]
        )
        APP._observe_iracing_car_identity("manufacturer examplegt3-2027", "Example GT3 EVO", 9001)
        resolved = APP._tp_showroom_mapping_entry_for_directory("manufacturer examplegt3-2027")
        self.assertIsNotNone(resolved)
        self.assertEqual(resolved[1]["mid"], 401)

    def test_manifest_carid_is_asset_id_not_vehicle_mid(self):
        self._install_catalog(
            [
                {
                    "mid": 401,
                    "tp_name": "Example GT3 2027",
                    "directory": "examplegt3",
                }
            ]
        )
        manifest = """
        <TPXML>
          <Cars>
            <Car>
              <carid>987654321</carid>
              <file>https://dl.tradingpaints.gg/compressed/987654321.tga.bz2</file>
              <userid>42</userid>
              <directory>examplegt3</directory>
              <type>car</type>
              <teamid>0</teamid>
            </Car>
          </Cars>
        </TPXML>
        """
        files = APP._parse_fetch_user_manifest_xml(42, manifest)
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].download_id.directory, "examplegt3")
        self.assertIn("examplegt3", APP._TP_MANIFEST_OBSERVED_DIRECTORIES)
        resolved = APP._tp_showroom_mapping_entry_for_directory("examplegt3")
        self.assertEqual(resolved[1]["mid"], 401)
        self.assertNotEqual(resolved[1]["mid"], 987654321)


if __name__ == "__main__":
    unittest.main()
