import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_forbid_tp_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


CAR = "ferrari296gt3"
OTHER_CAR = "mazda mx-5 2019"
SESSION_ID = APP.SessionId(555, 777)


def _item(user_id, paint_type, directory=CAR, *, is_team_paint=False, **download_id_overrides):
    download_id = APP.DownloadId(
        user_id=user_id,
        directory=directory,
        paint_type=paint_type,
        is_team_paint=is_team_paint,
        **download_id_overrides,
    )
    return APP.DownloadFile(
        download_id=download_id,
        url=f"https://example.invalid/{paint_type.value}/{user_id}/{directory}/paint.tga",
    )


def _key(target_kind, target_id, kind, directory=""):
    return APP.forbidden_tp_paint_key(target_kind, target_id, kind, directory)


def _forbidden(*keys):
    return {"version": 1, "entries": {key: {"key": key} for key in keys}}


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.path = self.folder / "forbidden.json"

    def test_storage_round_trip_toggle_states_and_corrupt_file_is_empty(self):
        self.assertEqual(APP.load_forbidden_tp_paints(self.path), {"version": 1, "entries": {}})
        self.assertEqual(_key("user", 7, "car", CAR.upper()), f"user:7:car:{CAR}")

        self.assertTrue(
            APP.set_tp_paint_forbidden("user", 7, "car", CAR, "Driver 7", True, self.path)
        )
        loaded = APP.load_forbidden_tp_paints(self.path)
        entry = loaded["entries"][f"user:7:car:{CAR}"]
        self.assertEqual(entry["target_kind"], "user")
        self.assertEqual(entry["target_id"], 7)
        self.assertEqual(entry["kind"], "car")
        self.assertEqual(entry["directory"], CAR)
        self.assertEqual(entry["display_name"], "Driver 7")
        self.assertTrue(APP.is_tp_paint_forbidden("user", 7, "car", CAR, path=self.path))
        self.assertFalse(APP.is_tp_paint_forbidden("user", 8, "car", CAR, path=self.path))

        self.assertFalse(
            APP.set_tp_paint_forbidden("user", 7, "car", CAR, "Driver 7", False, self.path)
        )
        self.assertEqual(APP.load_forbidden_tp_paints(self.path)["entries"], {})

        self.path.write_text("{ this is not json", encoding="utf-8")
        self.assertEqual(APP.load_forbidden_tp_paints(self.path), {"version": 1, "entries": {}})


class FilterTests(unittest.TestCase):
    def test_filter_drops_car_files_for_the_forbidden_member_and_directory_only(self):
        forbidden = _forbidden(_key("user", 7, "car", CAR), _key("team", 99, "car", CAR))
        items = [
            _item(7, APP.PaintType.CAR),
            _item(7, APP.PaintType.CAR_DECAL),
            _item(7, APP.PaintType.CAR_NUMBER),
            _item(7, APP.PaintType.CAR_SPEC),
            _item(8, APP.PaintType.CAR),
            _item(7, APP.PaintType.CAR, OTHER_CAR),
            _item(99, APP.PaintType.CAR, is_team_paint=True),
            _item(99, APP.PaintType.CAR),
        ]

        kept = APP.filter_forbidden_tp_items(items, forbidden)

        self.assertEqual(
            [item.download_id.paint_type for item in kept[:2]],
            [APP.PaintType.CAR, APP.PaintType.CAR],
        )
        self.assertEqual(
            [(item.download_id.user_id, item.download_id.directory, item.download_id.is_team_paint) for item in kept],
            [
                (8, CAR, False),
                (7, OTHER_CAR, False),
                (99, CAR, False),
            ],
        )


class FallbackTests(unittest.TestCase):
    def test_helmet_suit_and_random_collection_fallbacks_are_handled(self):
        forbidden = _forbidden(
            _key("user", 7, "helmet"),
            _key("user", 7, "suit"),
        )
        items = [
            _item(7, APP.PaintType.HELMET),
            _item(8, APP.PaintType.HELMET),
            _item(7, APP.PaintType.SUIT),
            _item(7, APP.PaintType.HELMET, tp_source="random_pool"),
            _item(7, APP.PaintType.SUIT, tp_source="collection"),
            _item(7, APP.PaintType.HELMET, preserve_on_cleanup=True),
            _item(7, APP.PaintType.CAR),
        ]

        kept = APP.filter_forbidden_tp_items(items, forbidden)

        self.assertEqual(
            [(item.download_id.paint_type, item.download_id.user_id) for item in kept],
            [
                (APP.PaintType.HELMET, 8),
                (APP.PaintType.HELMET, 7),
                (APP.PaintType.SUIT, 7),
                (APP.PaintType.HELMET, 7),
                (APP.PaintType.CAR, 7),
            ],
        )


class SelectManifestTests(unittest.TestCase):
    def test_select_manifest_variants_applies_the_forbidden_filter(self):
        self.addCleanup(setattr, APP, "_FORBIDDEN_TP_PAINTS_CACHE", APP._FORBIDDEN_TP_PAINTS_CACHE)
        APP._FORBIDDEN_TP_PAINTS_CACHE = None
        forbidden = _forbidden(_key("user", 7, "car", CAR), _key("user", 7, "helmet"))
        items = [
            _item(7, APP.PaintType.CAR),
            _item(8, APP.PaintType.CAR),
            _item(7, APP.PaintType.HELMET),
        ]
        session = APP.Session(session_id=SESSION_ID, users=set())

        with mock.patch.object(APP, "load_forbidden_tp_paints", return_value=forbidden):
            selected = APP._select_manifest_variants_for_session(session, items)

        self.assertEqual(
            [(item.download_id.paint_type, item.download_id.user_id) for item in selected],
            [(APP.PaintType.CAR, 8)],
        )


if __name__ == "__main__":
    unittest.main()
