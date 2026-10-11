import argparse
import importlib.util
import re
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_showroom_lists_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


# Trading Paints lists the two Super Formula SF23 cars under showroom ID 268, but each has
# its own iRacing template (171 Toyota, 172 Honda). The three winged sprint cars under
# ID 170 share template 80.
CATALOG_ENTRIES = [
    {"mid": 268, "tp_name": "Super Formula SF23 - Honda", "tp_make_name": "Super Formula SF23",
     "directory": "superformulasf23 honda", "template_id": "172", "slug": "Super-Formula-SF23"},
    {"mid": 268, "tp_name": "Super Formula SF23 - Toyota", "tp_make_name": "Super Formula SF23",
     "directory": "superformulasf23 toyota", "template_id": "171", "slug": "Super-Formula-SF23"},
    {"mid": 170, "tp_name": "Dirt Sprint Car - 305", "tp_make_name": "Dirt Sprint Cars",
     "directory": "dirtsprint winged 305", "template_id": "80", "category": "Dirt"},
    {"mid": 170, "tp_name": "Dirt Sprint Car - 360", "tp_make_name": "Dirt Sprint Cars",
     "directory": "dirtsprint winged 360", "template_id": "80", "category": "Dirt"},
    {"mid": 170, "tp_name": "Dirt Sprint Car - 410", "tp_make_name": "Dirt Sprint Cars",
     "directory": "dirtsprint winged 410", "template_id": "80", "category": "Dirt"},
]

HONDA = "superformulasf23\\honda"
TOYOTA = "superformulasf23\\toyota"


def _item(scheme_id, car_make, name="Super Formula SF23"):
    return {"id": str(scheme_id), "title": f"paint {scheme_id}", "type": "paint", "hasnumber": "0",
            "pro_user": False, "car_make": str(car_make), "car_make_name": name}


class _CatalogMixin:
    def setUp(self):
        doc = APP._build_tp_car_identity_doc([dict(entry) for entry in CATALOG_ENTRIES])
        with APP._TP_CAR_IDENTITY_CACHE_LOCK:
            saved = (APP._TP_CAR_IDENTITY_CACHE_DOC, APP._TP_CAR_IDENTITY_CACHE_AT, APP._TP_CAR_IDENTITY_LAST_ATTEMPT_AT)
            APP._TP_CAR_IDENTITY_CACHE_DOC = doc
            APP._TP_CAR_IDENTITY_CACHE_AT = APP.time.monotonic()
            APP._TP_CAR_IDENTITY_LAST_ATTEMPT_AT = APP._TP_CAR_IDENTITY_CACHE_AT
        self.addCleanup(self._restore_catalog, saved)
        with APP._TP_FAMILY_CAR_MAKES_LOCK:
            APP._TP_FAMILY_CAR_MAKES.clear()
        self.addCleanup(APP._TP_FAMILY_CAR_MAKES.clear)
        self.doc = doc

    @staticmethod
    def _restore_catalog(saved):
        with APP._TP_CAR_IDENTITY_CACHE_LOCK:
            APP._TP_CAR_IDENTITY_CACHE_DOC, APP._TP_CAR_IDENTITY_CACHE_AT, APP._TP_CAR_IDENTITY_LAST_ATTEMPT_AT = saved


class CatalogTemplateTests(_CatalogMixin, unittest.TestCase):
    def test_the_template_of_each_directory_is_read_from_its_download_link(self):
        page = """
        <div id="car"><a href="https://ir-core-sites.iracing.com/members/member_images/cars/car_templates/172_template_SF23H.zip">
          <h3><span>Super Formula SF23 - Honda</span></h3>
          <div><span class="akkurat-mono">Documents/<span>iRacing/paint</span>/<span>superformulasf23 honda</span></span></div>
        </a></div>
        <div id="car"><a href="https://ir-core-sites.iracing.com/members/member_images/cars/car_templates/171_template_SF23T.zip">
          <h3><span>Super Formula SF23 - Toyota</span></h3>
          <div><span class="akkurat-mono">Documents/<span>iRacing/paint</span>/<span>superformulasf23 toyota</span></span></div>
        </a></div>
        """
        self.assertEqual(APP._parse_tp_car_template_ids(page), {HONDA: "172", TOYOTA: "171"})

    def test_only_a_list_of_cars_with_different_templates_is_marked(self):
        cars = self.doc["cars"]
        self.assertTrue(cars[HONDA]["mid_mixes_templates"])
        self.assertEqual({member["directory"] for member in cars[HONDA]["template_family"]}, {HONDA, TOYOTA})
        self.assertFalse(cars["dirtsprint\\winged\\360"].get("mid_mixes_templates"))


class ShowroomListNameTests(_CatalogMixin, unittest.TestCase):
    def test_the_name_of_a_list_of_cars_sharing_a_template_finds_one_of_them(self):
        matched = APP._tp_showroom_mapping_entry_for_name("Dirt Sprint Cars")
        self.assertIsNotNone(matched)
        self.assertTrue(matched[0].startswith("dirtsprint\\winged\\"))

    def test_the_name_of_a_list_mixing_templates_is_not_guessed(self):
        with mock.patch.object(APP, "_refresh_tp_car_identity_after_unknown", return_value=self.doc):
            self.assertIsNone(APP._tp_showroom_mapping_entry_for_name("Super Formula SF23"))
        self.assertEqual(APP._tp_showroom_mapping_entry_for_name("Super Formula SF23 - Toyota")[0], TOYOTA)


class SharedShowroomIdTests(_CatalogMixin, unittest.TestCase):
    def test_a_showroom_id_shared_by_different_templates_needs_the_paints_own_car(self):
        self.assertIsNone(APP._tp_showroom_mapping_entry_for_mid(268))
        named = APP._tp_showroom_mapping_entry_for_mid(268, car=_item(1, 263, "Super Formula SF23 - Toyota"))
        self.assertEqual(named[0], TOYOTA)
        # The per-car ID is remembered, so a paint that only shows the list's name is known too.
        self.assertEqual(APP._tp_showroom_mapping_entry_for_mid(268, car=_item(2, 263))[0], TOYOTA)
        self.assertIsNone(APP._tp_showroom_mapping_entry_for_mid(268, car=_item(3, 267)))

    def test_a_showroom_id_shared_by_one_template_still_resolves(self):
        self.assertTrue(APP._tp_showroom_mapping_entry_for_mid(170)[0].startswith("dirtsprint\\winged\\"))

    def _choose(self, directory, pages):
        def fake_page(*, page_index, **_kwargs):
            return [dict(item) for item in pages.get(int(page_index), [])]

        with mock.patch.object(APP, "_tp_fetch_showroom_page_batch_http", fake_page):
            return APP.choose_showroom_paint_direct(directory=directory, mapping_path=None, pages=3)

    def test_an_online_pick_only_takes_paints_made_for_this_car(self):
        page = [_item(10, 263), _item(11, 263), _item(12, 267), _item(13, 267), _item(14, 267, "Super Formula SF23 - Honda")]
        for _ in range(20):
            result = self._choose("superformulasf23 honda", {0: page})
            self.assertTrue(result.ok, result.message)
            self.assertIn(result.chosen_scheme_id, {"12", "13", "14"})
            self.assertEqual(len(result.showroom_cars), 5, "the whole list stays cached for the other cars")

    def test_an_online_pick_with_no_paint_known_for_this_car_picks_nothing(self):
        result = self._choose("superformulasf23 toyota", {0: [_item(10, 263), _item(12, 267)]})
        self.assertFalse(result.ok)
        self.assertIn("different paint template", result.message)

    def test_a_list_sharing_one_template_is_picked_from_as_before(self):
        page = [_item(20, 171, "Dirt Sprint Cars"), _item(21, 173, "Dirt Sprint Cars")]
        result = self._choose("dirtsprint winged 305", {0: page})
        self.assertTrue(result.ok, result.message)

    def test_collection_paints_follow_the_same_rule(self):
        link = "https://www.tradingpaints.com/showroom/Road/268/Super-Formula-SF23"
        items = [dict(_item(30, 263, "Super Formula SF23 - Toyota"), clink=link), dict(_item(31, 267), clink=link)]
        toyota = APP._tp_collection_candidates_for_car(items, "superformulasf23 toyota", None)
        honda = APP._tp_collection_candidates_for_car(items, "superformulasf23 honda", None)
        self.assertEqual([item["id"] for item in toyota], ["30"])
        self.assertEqual(honda, [])


class _Response:
    def __init__(self, cars, ok=True):
        self.ok = ok
        self._cars = cars

    def json(self):
        return {"output": {"cars": self._cars}}


class _OnePageShowroom:
    """A showroom with one page of paints."""

    def __init__(self):
        self.positions = []
        self.fail = False
        self._lock = threading.Lock()

    def get(self, url, headers=None, timeout=None):
        pos = int(re.search(r"[?&]pos=(\d+)", url).group(1))
        with self._lock:
            self.positions.append(pos)
        if self.fail and pos > 0:
            return _Response([], ok=False)
        if pos == 0:
            return _Response([{"id": str(500 + n), "title": f"scheme {n}", "type": "paint"} for n in range(3)])
        return _Response([])


class ShowroomEndTests(unittest.TestCase):
    def setUp(self):
        for cache in (APP._TP_SHOWROOM_PAGE_CACHE, APP._TP_SHOWROOM_PAGE_END):
            cache.clear()
            self.addCleanup(cache.clear)
        self.http = _OnePageShowroom()
        patcher = mock.patch.object(APP, "get_thread_http_session", return_value=self.http)
        patcher.start()
        self.addCleanup(patcher.stop)

    def _pool(self):
        return APP._fetch_tp_showroom_pool_http(mid=777, category="Road", slug="x", min_unused_count=50, max_pages=20)

    def test_pages_past_the_end_are_not_asked_for_again_by_the_next_pass(self):
        cars, _sampled = self._pool()
        self.assertEqual(len(cars), 3)
        first_pass = len(self.http.positions)
        self.assertLess(first_pass, 20)
        self._pool()
        self.assertEqual(len(self.http.positions), first_pass)

    def test_a_failed_page_is_not_taken_for_the_end(self):
        self.http.fail = True
        self._pool()
        failed_requests = len(self.http.positions)
        self.http.fail = False
        self._pool()
        self.assertGreater(len(self.http.positions), failed_requests)


class CommandLineTests(unittest.TestCase):
    def _parse(self, *argv):
        with mock.patch.object(sys, "argv", ["nishizumi", *argv]):
            return APP.parse_args()

    def test_the_documents_folder_flag_and_its_old_name_both_work(self):
        self.assertEqual(self._parse("--iracing-documents-dir", r"D:\iRacing").paints_dir, r"D:\iRacing")
        self.assertEqual(self._parse("--paints-dir", r"D:\iRacing\paint").paints_dir, r"D:\iRacing\paint")

    def test_retired_flags_still_start_the_app(self):
        args = self._parse("--watch", "--iracing-sdk", "--session-yaml", "x.yaml")
        with self.assertLogs(level="WARNING"):
            APP.apply_command_line_overrides(args)

    def test_the_temp_folder_flag_is_used_in_a_folder_of_its_own(self):
        self.addCleanup(setattr, APP, "_TEMP_DIR_OVERRIDE", None)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        APP.apply_command_line_overrides(argparse.Namespace(temp_dir=tmp.name))
        self.assertEqual(APP.default_temp_dir(), Path(tmp.name) / "NishizumiPaints")


if __name__ == "__main__":
    unittest.main()
