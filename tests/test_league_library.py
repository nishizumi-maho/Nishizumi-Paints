"""League decal and paint library: naming, import routing, apply and pipeline hook."""
import bz2
import gc
import importlib.util
import io
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests
from PIL import Image


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_league_library_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)

CAR = "dirtlatemodel 350"


def setUpModule():
    gc.collect()


def _tga_bytes(colour, size=(4, 4), box=None):
    image = Image.new("RGBA", size, (0, 0, 0, 0))
    if box is None:
        box = (0, 0, size[0], size[1])
    image.paste((colour[0], colour[1], colour[2], 255), box)
    buffer = io.BytesIO()
    image.save(buffer, format="TGA")
    return buffer.getvalue()


def _library_entry(kind, league_id, car_class, member_id, car_folder, num_type="", ext="tga"):
    return APP.LeagueLibraryEntry(
        kind=kind,
        league_id=league_id,
        car_class=car_class,
        member_id=member_id,
        car_folder=car_folder,
        num_type=num_type,
        ext=ext,
    )


class _LeagueLibraryTemp(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="nishizumi-league-library-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        patcher = mock.patch.dict(os.environ, {"APPDATA": str(self.root / "appdata")})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.library = APP.default_league_library_dir()
        self.library.mkdir(parents=True)
        self.paints = self.root / "paint"
        self.paints.mkdir()
        self.session_id = APP.SessionId(1, None)

    def _write_library(self, entry, payload):
        path = self.library / APP.league_library_name(entry)
        path.write_bytes(payload)
        return path

    def _session(self, league_id, users, local_user_id=42):
        return APP.Session(
            session_id=self.session_id,
            users=set(users),
            local_user_id=local_user_id,
            league_id=league_id,
        )


class LeagueLibraryNameTests(_LeagueLibraryTemp):
    def test_name_round_trip_with_class_all_drivers_and_paint_kinds(self):
        entries = [
            _library_entry("decal", 12, "GT3", 0, CAR),
            _library_entry("decal", 12, "", 42, CAR),
            _library_entry("paint", 12, "", 42, CAR, "num", "tga"),
            _library_entry("paint", 12, "", 42, CAR, "sim", "tga"),
            _library_entry("paint", 12, "", 42, CAR, "sim", "mip"),
            _library_entry("paint", 12, "GT3", 42, CAR, "num", "tga"),
        ]
        for entry in entries:
            with self.subTest(entry=entry):
                name = APP.league_library_name(entry)
                self.assertEqual(APP.parse_league_library_name(name), entry)

    def test_legacy_all_drivers_decal_parses_and_formats_canonically(self):
        entry = APP.parse_league_library_name("12.car.decal.tga")
        self.assertIsNotNone(entry)
        self.assertEqual(entry.kind, "decal")
        self.assertEqual(entry.league_id, 12)
        self.assertEqual(entry.member_id, 0)
        self.assertEqual(entry.car_class, "")
        self.assertEqual(entry.car_folder, "car")
        self.assertEqual(APP.league_library_name(entry), "000012.0000000.car.decal.tga")

    def test_dotted_car_folder_keeps_every_middle_segment(self):
        entry = APP.parse_league_library_name("000012-GT3.0000042.weird.car.name.decal.tga")
        self.assertEqual(entry.car_folder, "weird.car.name")
        self.assertEqual(entry.car_class, "GT3")
        self.assertEqual(entry.member_id, 42)
        self.assertEqual(
            APP.league_library_name(entry),
            "000012-GT3.0000042.weird.car.name.decal.tga",
        )
        legacy = APP.parse_league_library_name("12.weird.car.name.decal.tga")
        self.assertEqual(legacy.car_folder, "weird.car.name")
        self.assertEqual(legacy.member_id, 0)

    def test_invalid_names_are_rejected(self):
        for name in (
            "",
            "garbage.tga",
            "000012.decal.tga",
            "12.car.decal.mip",
            "abc.car.decal.tga",
            "000012.0000042..decal.tga",
            "12.car.paint.other.tga",
            "12.car.paint.sim.jpg",
            "12.car.paint.tga",
            "0.car.decal.tga",
        ):
            with self.subTest(name=name):
                self.assertIsNone(APP.parse_league_library_name(name))

    def test_load_renames_valid_legacy_names_to_canonical(self):
        legacy = self.library / "12.car.decal.tga"
        legacy.write_bytes(b"legacy")
        entries = APP.load_league_library(self.library)
        canonical = self.library / "000012.0000000.car.decal.tga"
        self.assertFalse(legacy.exists())
        self.assertTrue(canonical.exists())
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].league_id, 12)


class LeagueLibraryImportTests(unittest.TestCase):
    def test_import_routing_and_member_parsing(self):
        cases = {
            "car_12345.tga": "000007.0012345.dirtlatemodel 350.paint.sim.tga",
            "car_num_12345.tga": "000007.0012345.dirtlatemodel 350.paint.num.tga",
            "car_decal_12345.tga": "000007.0012345.dirtlatemodel 350.decal.tga",
            "decal_12345.tga": "000007.0012345.dirtlatemodel 350.decal.tga",
            "car_spec_12345.mip": "000007.0012345.dirtlatemodel 350.paint.sim.mip",
            "car_team_12345.tga": "000007.0012345.dirtlatemodel 350.paint.sim.tga",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(
                    APP.league_library_import_name(source, 7, 0, CAR),
                    expected,
                )

    def test_import_uses_member_hint_and_car_class(self):
        self.assertEqual(
            APP.league_library_import_name("car_custompaint.tga", 7, 99, CAR, "GT3"),
            "000007-GT3.0000099.dirtlatemodel 350.paint.sim.tga",
        )

    def test_member_zero_paints_are_rejected_but_decal_is_allowed(self):
        self.assertIsNone(APP.league_library_import_name("car_0.tga", 7, 0, CAR))
        self.assertIsNone(APP.league_library_import_name("car_num_0.tga", 7, 0, CAR))
        self.assertIsNone(APP.league_library_import_name("car_custom.tga", 7, 0, CAR))
        self.assertEqual(
            APP.league_library_import_name("car_decal_0.tga", 7, 0, CAR),
            "000007.0000000.dirtlatemodel 350.decal.tga",
        )


class LeagueLibraryApplyPaintTests(_LeagueLibraryTemp):
    def test_apply_paint_num_beats_sim_and_league_mip_replaces_tp_spec(self):
        user = APP.SessionUser(user_id=42, directory=CAR, car_class="GT3")
        session = self._session(7, [user])
        self._write_library(_library_entry("paint", 7, "", 42, CAR, "num", "tga"), b"NUM")
        self._write_library(_library_entry("paint", 7, "", 42, CAR, "sim", "tga"), b"SIM")
        self._write_library(_library_entry("paint", 7, "", 42, CAR, "sim", "mip"), b"MIP")
        car_path = self.paints / CAR / "car_42.tga"
        spec_path = self.paints / CAR / "car_spec_42.mip"
        car_path.parent.mkdir(parents=True)
        car_path.write_bytes(b"TP CAR")
        spec_path.write_bytes(b"TP SPEC")

        library = APP.load_league_library(self.library)
        written = APP.apply_league_library(session, [user], self.paints, library)

        number_path = self.paints / CAR / "car_num_42.tga"
        self.assertEqual(number_path.read_bytes(), b"NUM")
        self.assertFalse(car_path.exists())
        self.assertEqual(spec_path.read_bytes(), b"MIP")
        self.assertEqual(set(written), {number_path, spec_path})

    def test_apply_paint_sim_copies_car_and_deletes_tp_spec_without_league_mip(self):
        user = APP.SessionUser(user_id=42, directory=CAR)
        session = self._session(7, [user])
        self._write_library(_library_entry("paint", 7, "", 42, CAR, "sim", "tga"), b"SIM")
        car_path = self.paints / CAR / "car_42.tga"
        spec_path = self.paints / CAR / "car_spec_42.mip"
        car_path.parent.mkdir(parents=True)
        car_path.write_bytes(b"TP CAR")
        spec_path.write_bytes(b"TP SPEC")

        library = APP.load_league_library(self.library)
        APP.apply_league_library(session, [user], self.paints, library)

        self.assertEqual(car_path.read_bytes(), b"SIM")
        self.assertFalse(spec_path.exists())


class LeagueLibraryApplyDecalTests(_LeagueLibraryTemp):
    def test_apply_decal_stacks_tp_then_all_then_driver(self):
        user = APP.SessionUser(user_id=42, directory=CAR, car_class="GT3")
        session = self._session(7, [user])
        self._write_library(_library_entry("decal", 7, "GT3", 0, CAR), _tga_bytes((0, 255, 0)))
        self._write_library(
            _library_entry("decal", 7, "GT3", 42, CAR),
            _tga_bytes((0, 0, 255), box=(0, 0, 2, 2)),
        )
        decal_path = self.paints / CAR / "car_decal_42.tga"
        decal_path.parent.mkdir(parents=True)
        decal_path.write_bytes(_tga_bytes((255, 0, 0)))

        library = APP.load_league_library(self.library)
        written = APP.apply_league_library(session, [user], self.paints, library)

        self.assertEqual(written, [decal_path])
        with Image.open(decal_path) as merged:
            merged = merged.convert("RGBA")
            self.assertEqual(merged.getpixel((0, 0)), (0, 0, 255, 255))
            self.assertEqual(merged.getpixel((3, 3)), (0, 255, 0, 255))

    def test_apply_decal_single_league_source_is_copied(self):
        user = APP.SessionUser(user_id=42, directory=CAR)
        session = self._session(7, [user])
        source_payload = _tga_bytes((0, 255, 0))
        self._write_library(_library_entry("decal", 7, "", 0, CAR), source_payload)

        library = APP.load_league_library(self.library)
        written = APP.apply_league_library(session, [user], self.paints, library)

        decal_path = self.paints / CAR / "car_decal_42.tga"
        self.assertEqual(written, [decal_path])
        self.assertEqual(decal_path.read_bytes(), source_payload)

    def test_apply_decal_tp_only_is_a_no_op(self):
        user = APP.SessionUser(user_id=42, directory=CAR)
        session = self._session(7, [user])
        decal_path = self.paints / CAR / "car_decal_42.tga"
        decal_path.parent.mkdir(parents=True)
        decal_path.write_bytes(_tga_bytes((255, 0, 0)))

        written = APP.apply_league_library(session, [user], self.paints, [])

        self.assertEqual(written, [])
        self.assertEqual(decal_path.read_bytes(), _tga_bytes((255, 0, 0)))

    def test_apply_decal_league_zero_is_a_no_op(self):
        user = APP.SessionUser(user_id=42, directory=CAR, car_class="GT3")
        session = self._session(0, [user])
        self._write_library(_library_entry("decal", 0, "GT3", 0, CAR), _tga_bytes((0, 255, 0)))
        self._write_library(_library_entry("paint", 0, "", 42, CAR, "sim", "tga"), b"SIM")
        # A zero league cannot be loaded from a canonical file name, so pass the entry directly.
        library = [_library_entry("decal", 0, "GT3", 0, CAR), _library_entry("paint", 0, "", 42, CAR, "sim", "tga")]

        written = APP.apply_league_library(session, [user], self.paints, library)

        self.assertEqual(written, [])
        self.assertFalse((self.paints / CAR / "car_decal_42.tga").exists())
        self.assertFalse((self.paints / CAR / "car_42.tga").exists())


class _Response:
    def __init__(self, status=200, text="", body=b""):
        self.status_code = status
        self.text = text
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def iter_content(self, chunk_size=None):
        yield self.body


class _FakeTradingPaints:
    def __init__(self):
        self.requests = []

    @staticmethod
    def _manifest(user_ids):
        cars = "".join(
            "<Car>"
            f"<carid>1</carid><userid>{uid}</userid><teamid>0</teamid><directory>{CAR}</directory><type>car</type>"
            f"<file>https://files.example.invalid/{uid}/car.tga.bz2</file>"
            "</Car>"
            for uid in user_ids
        )
        return f"<Response>{cars}</Response>"

    def post(self, url, data=None, timeout=None, **_kwargs):
        self.requests.append(("POST", url))
        listed = str((data or {}).get("list", ""))
        user_ids = [int(entry.split("=", 1)[0]) for entry in listed.split(",") if entry.split("=", 1)[0].isdigit()]
        return _Response(text=self._manifest(user_ids))

    def get(self, url, timeout=None, stream=False, headers=None, **_kwargs):
        self.requests.append(("GET", url))
        match = re.match(r"https://files\.example\.invalid/(\d+)/car\.tga\.bz2$", url)
        if match:
            return _Response(body=bz2.compress(f"car-{match.group(1)}".encode() * 512))
        return _Response(status=404)


class LeagueLibraryHookTests(_LeagueLibraryTemp):
    def test_hook_calls_post_save_extras_from_process_session(self):
        user = APP.SessionUser(user_id=1, directory=CAR, car_idx=0)
        session = self._session(7, [user], local_user_id=1)
        http = _FakeTradingPaints()
        calls = []

        def fake_extras(session_arg, users_arg, paints_dir_arg):
            calls.append((session_arg, list(users_arg), paints_dir_arg))
            return []

        with (
            mock.patch.object(APP, "get_thread_http_session", return_value=http),
            mock.patch.object(APP.time, "sleep"),
            mock.patch.object(APP, "compute_retry_delay", lambda _base, _attempt: 0.0),
            mock.patch.object(APP, "_fetch_tp_car_identity_doc", side_effect=RuntimeError("offline in tests")),
            mock.patch.object(APP, "apply_post_save_extras", side_effect=fake_extras),
        ):
            with APP._TP_FETCH_URL_DOWN_LOCK:
                APP._TP_FETCH_URL_DOWN_UNTIL.clear()
                APP._TP_FETCH_HOST_UNREACHABLE_UNTIL.clear()
            saved, _monitor, _drivers = APP.process_session(
                session=session,
                paints_dir=self.paints,
                temp_dir=self.root / "temp",
                ai_rosters_dir=None,
                max_concurrent_manifests=4,
                max_concurrent_downloads=4,
                download_workers_mode="manual",
                manual_manifest_workers=4,
                manual_download_workers=4,
                manual_save_workers=4,
                retries=2,
                retry_backoff_seconds=0.0,
                sync_my_livery_from_server=True,
                random_fallback_real_drivers=False,
                random_fallback_ai=False,
                random_helmets=False,
                random_suits=False,
                random_helmets_real_drivers=False,
                random_helmets_ai=False,
                random_suits_real_drivers=False,
                random_suits_ai=False,
                disable_random_in_team_events=True,
                disable_random_for_local_user=True,
                team_driver_personal_fallback_slots=(),
                ai_collection_skip_random_cars=True,
                ai_collection_skip_random_helmets=True,
                ai_collection_skip_random_suits=True,
                keep_tp_paints_in_random_pool=False,
                max_random_pool_gb=0.0,
                tp_fallback_mode="local",
            )

        self.assertTrue(saved)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][0].session_id, session.session_id)
        self.assertEqual(calls[0][1], [user])
        self.assertEqual(calls[0][2], self.paints)


if __name__ == "__main__":
    unittest.main()
