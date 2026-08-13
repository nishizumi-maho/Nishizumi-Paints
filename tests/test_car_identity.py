import importlib.util
import shutil
import sys
import tempfile
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

    def test_template_catalog_joins_directory_with_the_showroom_make_id(self):
        page = """
        <div id="car" class="bg-white br3 grow">
          <a href="https://ir-core-sites.iracing.com/members/member_images/cars/car_templates/198_template.zip">
            <h3 class="ma0 f5 b"><span>Ferrari 296 GT3</span></h3>
            <div class="o-50 f7 flex items-center mt2">
              <img src="/folder-open.svg" class="h1 mr1 v-mid">
              <span class="akkurat-mono">Documents/<span>iRacing/paint</span>/<span>ferrari296gt3</span></span>
            </div>
          </a>
        </div>
        """
        index = {264: {"category": "Road", "name": "Ferrari 296 GT3"}}
        entries = APP._parse_tp_car_templates_html(page, index)
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

    def test_template_catalog_reads_both_directory_markup_shapes(self):
        # The page emits two different nested <span> shapes for the same path.
        page = """
        <div id="car" class="grow">
          <a href="/a.zip"><h3><span>ARCA Chevrolet SS</span></h3>
            <div class="o-50">
              <span class="akkurat-mono">Documents/<span>iRacing/paint</span>/<span>stockcars2 arcachevy25</span></span>
            </div>
          </a>
        </div>
        <div id="car" class="grow">
          <a href="/b.zip"><h3><span>Acura ARX-06 GTP</span></h3>
            <div class="o-50">
              <span class="akkurat-mono"><span>Documents</span>/<span>iRacing</span><span>/</span>paint/<span>acuraarx06gtp</span></span>
            </div>
          </a>
        </div>
        """
        rows = APP._parse_tp_car_template_rows(page)
        self.assertEqual(
            rows,
            [
                ("ARCA Chevrolet SS", "stockcars2\\arcachevy25"),
                ("Acura ARX-06 GTP", "acuraarx06gtp"),
            ],
        )

    def test_showroom_index_reads_make_links_and_skips_non_make_paths(self):
        page = """
        <a href="https://www.tradingpaints.com/showroom/Oval/170/Dirt-Sprint-Cars">a</a>
        <a href="https://www.tradingpaints.com/showroom/Road/264/Ferrari-296-GT3">b</a>
        <a href="https://www.tradingpaints.com/showroom/view/1188280/Some-Paint">c</a>
        <a href="https://www.tradingpaints.com/showroom/hof/2026/08">d</a>
        """
        index = APP._parse_tp_showroom_make_index(page)
        self.assertEqual(
            index,
            {
                170: {"category": "Oval", "name": "Dirt Sprint Cars"},
                264: {"category": "Road", "name": "Ferrari 296 GT3"},
            },
        )

    def test_grouped_make_prefers_the_most_specific_vehicle(self):
        # One "Dirt Sprint Cars" make covers several iRacing directories, but a
        # micro sprint must not be swallowed by the broader sprint car make.
        index = {
            170: {"category": "Oval", "name": "Dirt Sprint Cars"},
            176: {"category": "Oval", "name": "Dirt Sprint Cars  NonWinged"},
            276: {"category": "Oval", "name": "Dirt Micro Sprint Cars  Winged"},
            277: {"category": "Oval", "name": "Dirt Micro Sprint Cars  NonWinged"},
        }
        cases = {
            ("Dirt Sprint Car - 410", "dirtsprint\\winged\\410"): 170,
            ("Dirt Sprint Car - 360 Non-Winged", "dirtsprint\\nonwinged\\360"): 176,
            ("Dirt Micro Sprint Car", "dirtmicrosprint\\winged"): 276,
            ("Dirt Micro Sprint Car - Non-Winged", "dirtmicrosprint\\nonwinged"): 277,
        }
        for (name, directory), expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(
                    APP._select_tp_make_for_template(name, directory, index, set()), expected
                )

    def test_grouped_make_ignores_a_make_already_claimed_by_an_exact_name(self):
        index = {
            166: {"category": "Oval", "name": "Dirt Late Models"},
            225: {"category": "Oval", "name": "Super Late Model"},
        }
        self.assertEqual(
            APP._select_tp_make_for_template(
                "Dirt Late Model - Super", "dirtlatemodel\\438", index, {225}
            ),
            166,
        )

    def test_template_without_any_matching_make_is_dropped(self):
        page = """
        <div id="car"><a href="/a.zip"><h3><span>Totally Unknown Car</span></h3>
          <div><span class="akkurat-mono">Documents/iRacing/paint/unknowncar</span></div>
        </a></div>
        """
        index = {264: {"category": "Road", "name": "Ferrari 296 GT3"}}
        self.assertEqual(APP._parse_tp_car_templates_html(page, index), [])

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


class TradingPaintsCarIdentityDiskCacheTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="nishizumi-car-identity-cache-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.cache_path = self.temp_dir / "car_identity.json"
        original_path_getter = APP.default_tp_car_identity_cache_path
        APP.default_tp_car_identity_cache_path = lambda: self.cache_path
        self.addCleanup(setattr, APP, "default_tp_car_identity_cache_path", original_path_getter)
        with APP._TP_CAR_IDENTITY_CACHE_LOCK:
            APP._TP_CAR_IDENTITY_CACHE_DOC = None
            APP._TP_CAR_IDENTITY_CACHE_AT = 0.0
            APP._TP_CAR_IDENTITY_LAST_ATTEMPT_AT = 0.0
            APP._TP_CAR_IDENTITY_LAST_ERROR = ""

    def _doc(self):
        return APP._build_tp_car_identity_doc(
            [{"mid": 264, "tp_name": "Ferrari 296 GT3", "directory": "ferrari296gt3"}]
        )

    def _install_fetch(self, result):
        original_fetch = APP._fetch_tp_car_identity_doc

        def fake_fetch(*_args, **_kwargs):
            if isinstance(result, Exception):
                raise result
            return result

        APP._fetch_tp_car_identity_doc = fake_fetch
        self.addCleanup(setattr, APP, "_fetch_tp_car_identity_doc", original_fetch)

    def test_saved_catalog_is_read_back(self):
        doc = self._doc()
        APP.save_tp_car_identity_cache(doc)
        self.assertTrue(self.cache_path.is_file())
        self.assertEqual(APP.load_tp_car_identity_cache(), doc)

    def test_empty_catalog_is_never_written_over_a_good_one(self):
        APP.save_tp_car_identity_cache(self._doc())
        APP.save_tp_car_identity_cache({"schema_version": 2, "cars": {}})
        self.assertIn("ferrari296gt3", APP.load_tp_car_identity_cache()["cars"])

    def test_cache_from_another_layout_version_is_ignored(self):
        APP.save_tp_car_identity_cache(self._doc())
        payload = APP.json.loads(self.cache_path.read_text(encoding="utf-8"))
        payload["version"] = APP.TP_CAR_IDENTITY_DISK_CACHE_VERSION + 1
        self.cache_path.write_text(APP.json.dumps(payload), encoding="utf-8")
        self.assertIsNone(APP.load_tp_car_identity_cache())

    def test_expired_cache_is_ignored(self):
        APP.save_tp_car_identity_cache(self._doc())
        payload = APP.json.loads(self.cache_path.read_text(encoding="utf-8"))
        payload["saved_at"] = APP.time.time() - APP.TP_CAR_IDENTITY_DISK_CACHE_MAX_AGE_SECONDS - 60
        self.cache_path.write_text(APP.json.dumps(payload), encoding="utf-8")
        self.assertIsNone(APP.load_tp_car_identity_cache())

    def test_damaged_cache_file_is_ignored(self):
        self.cache_path.write_text("{ not json", encoding="utf-8")
        self.assertIsNone(APP.load_tp_car_identity_cache())

    def test_a_successful_refresh_persists_the_catalog(self):
        self._install_fetch(self._doc())
        APP._load_tp_showroom_mapping(force_refresh=True)
        self.assertIn("ferrari296gt3", (APP.load_tp_car_identity_cache() or {})["cars"])

    def test_a_failed_refresh_falls_back_to_the_catalog_on_disk(self):
        APP.save_tp_car_identity_cache(self._doc())
        self._install_fetch(RuntimeError("Trading Paints changed the page again"))
        doc = APP._load_tp_showroom_mapping(force_refresh=True)
        self.assertIn("ferrari296gt3", doc.get("cars") or {})
        self.assertIn("changed the page again", APP.tp_car_identity_catalog_status()["last_error"])

    def test_a_failed_refresh_without_a_disk_cache_returns_an_empty_catalog(self):
        self._install_fetch(RuntimeError("Trading Paints is unreachable"))
        self.assertEqual(APP._load_tp_showroom_mapping(force_refresh=True).get("cars"), {})


if __name__ == "__main__":
    unittest.main()
