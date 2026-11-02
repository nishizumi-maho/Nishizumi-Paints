import base64
import bz2
import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_tp_download_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)

_TINY_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


class _FakeResponse:
    def __init__(self, status_code=200, content=b"", text=""):
        self.status_code = status_code
        self.content = content
        self.text = text

    def raise_for_status(self):
        if self.status_code >= 400:
            raise APP.requests.HTTPError(f"HTTP {self.status_code}")


class _FakeSession:
    def __init__(self, *, get_responses=None, post_responses=None):
        self.get_responses = list(get_responses or [])
        self.post_responses = list(post_responses or [])
        self.get_urls = []
        self.post_urls = []
        self.post_payloads = []

    def get(self, url, **_kwargs):
        self.get_urls.append(url)
        if not self.get_responses:
            return _FakeResponse(404)
        return self.get_responses.pop(0)

    def post(self, url, data=None, **_kwargs):
        self.post_urls.append(url)
        self.post_payloads.append(data)
        if not self.post_responses:
            return _FakeResponse(404)
        return self.post_responses.pop(0)


def _download_file(directory: str, paint_type, url="https://example.invalid/paint", user_id=7, team_id=False):
    return APP.DownloadFile(
        download_id=APP.DownloadId(
            user_id=user_id,
            directory=directory,
            paint_type=paint_type,
            is_team_paint=team_id,
        ),
        url=url,
    )


def _manifest(*cars: str) -> str:
    return "<Manifest>" + "".join(cars) + "</Manifest>"


def _car(userid, teamid, directory, paint_type, url):
    return (
        "<Car>"
        f"<userid>{userid}</userid>"
        f"<teamid>{teamid}</teamid>"
        f"<directory>{directory}</directory>"
        f"<type>{paint_type}</type>"
        f"<file>{url}</file>"
        "</Car>"
    )


class CarGroupTests(unittest.TestCase):
    def test_groups_keep_car_types_with_a_directory_and_sort_by_directory(self):
        files = [
            _download_file("zcar", APP.PaintType.CAR),
            _download_file("Acar", APP.PaintType.CAR_DECAL),
            _download_file("zcar", APP.PaintType.CAR_SPEC),
            _download_file("Acar", APP.PaintType.CAR_NUMBER),
            _download_file("", APP.PaintType.CAR),
            _download_file("Acar", APP.PaintType.HELMET),
            _download_file("Acar", APP.PaintType.SUIT),
        ]

        groups = APP.tp_download_car_groups(files)

        self.assertEqual(list(groups), ["Acar", "zcar"])
        self.assertEqual(len(groups["Acar"]), 2)
        self.assertEqual(len(groups["zcar"]), 2)
        self.assertTrue(all(item.download_id.paint_type in {
            APP.PaintType.CAR,
            APP.PaintType.CAR_DECAL,
            APP.PaintType.CAR_SPEC,
            APP.PaintType.CAR_NUMBER,
        } for group in groups.values() for item in group))

    def test_groups_merge_directories_that_differ_only_in_case_and_keep_the_first_spelling(self):
        files = [
            _download_file("Mazda MX5", APP.PaintType.CAR),
            _download_file("mazda mx5", APP.PaintType.CAR_DECAL),
        ]

        groups = APP.tp_download_car_groups(files)

        self.assertEqual(list(groups), ["Mazda MX5"])
        self.assertEqual(len(groups["Mazda MX5"]), 2)

    def test_groups_sort_case_insensitive(self):
        files = [
            _download_file("Acar", APP.PaintType.CAR),
            _download_file("bcar", APP.PaintType.CAR),
            _download_file("Ccar", APP.PaintType.CAR),
        ]

        groups = APP.tp_download_car_groups(files)

        self.assertEqual(list(groups), ["Acar", "bcar", "Ccar"])


class PreviewItemPickTests(unittest.TestCase):
    def test_pick_preview_prefers_team(self):
        personal_car = _download_file("mx5 mx52016", APP.PaintType.CAR, user_id=7)
        personal_decal = _download_file("mx5 mx52016", APP.PaintType.CAR_DECAL, user_id=7)
        team_car = _download_file("mx5 mx52016", APP.PaintType.CAR, user_id=99, team_id=True)
        team_decal = _download_file("mx5 mx52016", APP.PaintType.CAR_DECAL, user_id=99, team_id=True)

        car, decal = APP.pick_tp_preview_items(
            [personal_car, personal_decal, team_car, team_decal], prefer_team=True
        )
        self.assertIs(car, team_car)
        self.assertIs(decal, team_decal)

        car, decal = APP.pick_tp_preview_items([personal_car, personal_decal], prefer_team=True)
        self.assertIs(car, personal_car)
        self.assertIs(decal, personal_decal)

        car, decal = APP.pick_tp_preview_items(
            [personal_car, personal_decal, team_car, team_decal], prefer_team=False
        )
        self.assertIs(car, personal_car)
        self.assertIs(decal, personal_decal)


class ContextPayloadTests(unittest.TestCase):
    def test_payload_for_a_member_uses_zero_team_and_custom_numbers(self):
        payload = APP.tp_download_context_payload(
            1234,
            0,
            "mx5 mx52016",
            night="",
            series_id=42,
            league_id=0,
            custom_numbers=True,
        )

        self.assertEqual(payload["team"], "0")
        self.assertEqual(payload["user"], "1234")
        self.assertEqual(payload["night"], "10:00 am")
        self.assertEqual(payload["series"], "42")
        self.assertEqual(payload["league"], "0")
        self.assertEqual(payload["numbers"], "True")
        self.assertEqual(payload["list"], "1234=mx5 mx52016=0=64=")

    def test_payload_for_a_team_uses_the_team_flag_and_false_numbers(self):
        payload = APP.tp_download_context_payload(
            1234,
            99,
            "mx5 mx52016",
            night="8:00 pm",
            series_id=1,
            league_id=2,
            custom_numbers=False,
            number="07",
            paint_ext="tga",
        )

        self.assertEqual(payload["team"], "1")
        self.assertEqual(payload["user"], "1234")
        self.assertEqual(payload["night"], "8:00 pm")
        self.assertEqual(payload["numbers"], "False")
        self.assertEqual(payload["list"], "1234=mx5 mx52016=99=07=tga")


class ContextFetchTests(unittest.TestCase):
    def _fetch(self, session, payload, member_id, team_id):
        with mock.patch.object(APP, "tp_fetch_context_urls", return_value=["https://one.invalid", "https://two.invalid"]), \
                mock.patch.object(APP, "get_thread_http_session", return_value=session):
            return APP.fetch_tp_download_context(payload, member_id, team_id)

    def test_context_fetch_falls_back_to_the_next_url_after_a_failure(self):
        xml = _manifest(_car(7, 0, "mx5 mx52016", "car", "https://example.invalid/car_7.tga"))
        session = _FakeSession(post_responses=[_FakeResponse(500, text=""), _FakeResponse(200, text=xml)])

        files = self._fetch(session, {"list": "7=mx5 mx52016=0=64="}, 7, 0)

        self.assertEqual(session.post_urls, ["https://one.invalid", "https://two.invalid"])
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].download_id.directory, "mx5 mx52016")
        self.assertEqual(files[0].download_id.paint_type, APP.PaintType.CAR)

    def test_context_fetch_acceptance_rules_for_member_and_team(self):
        xml = _manifest(
            _car(7, 0, "mx5 mx52016", "car", "https://example.invalid/car_7.tga"),
            _car(8, 99, "mx5 mx52016", "car_decal", "https://example.invalid/decal_99.tga"),
            _car(7, 55, "mx5 mx52016", "car", "https://example.invalid/wrong_team.tga"),
            _car(9, 0, "mx5 mx52016", "car", "https://example.invalid/wrong_user.tga"),
        )
        session = _FakeSession(post_responses=[_FakeResponse(200, text=xml)])

        member_files = self._fetch(session, {}, 7, 0)
        self.assertEqual([item.download_id.paint_type for item in member_files], [APP.PaintType.CAR])

        session = _FakeSession(post_responses=[_FakeResponse(200, text=xml)])
        team_files = self._fetch(session, {}, 7, 99)
        self.assertEqual(
            [item.download_id.paint_type for item in team_files],
            [APP.PaintType.CAR, APP.PaintType.CAR_DECAL, APP.PaintType.CAR],
        )

    def test_context_fetch_returns_empty_when_no_url_answers(self):
        session = _FakeSession(post_responses=[_FakeResponse(503), _FakeResponse(404)])

        self.assertEqual(self._fetch(session, {}, 7, 0), [])


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)

    def test_download_writes_bz2_decompressed_bytes_to_the_save_path(self):
        payload = b"TGA" * 100
        item = _download_file("mx5 mx52016", APP.PaintType.CAR, url="https://example.invalid/car_7.tga.bz2")
        session = _FakeSession(get_responses=[_FakeResponse(200, bz2.compress(payload))])

        with mock.patch.object(APP, "get_thread_http_session", return_value=session):
            saved = APP.download_tp_paint_to(item, self.folder, session=session)

        expected = APP.save_path_for(item.download_id, self.folder)
        self.assertEqual(saved, expected)
        self.assertEqual(expected.read_bytes(), payload)

    def test_download_403_returns_none_and_writes_nothing(self):
        item = _download_file("mx5 mx52016", APP.PaintType.CAR, url="https://example.invalid/car_7.tga")
        session = _FakeSession(get_responses=[_FakeResponse(403)])

        with mock.patch.object(APP, "get_thread_http_session", return_value=session):
            saved = APP.download_tp_paint_to(item, self.folder, session=session)

        self.assertIsNone(saved)
        self.assertEqual([path for path in self.folder.rglob("*") if path.is_file()], [])

    def test_download_empty_body_returns_none(self):
        item = _download_file("mx5 mx52016", APP.PaintType.CAR)
        session = _FakeSession(get_responses=[_FakeResponse(200, b"")])

        with mock.patch.object(APP, "get_thread_http_session", return_value=session):
            saved = APP.download_tp_paint_to(item, self.folder, session=session)

        self.assertIsNone(saved)
        self.assertEqual([path for path in self.folder.rglob("*") if path.is_file()], [])

    def test_download_unwritable_folder_returns_none(self):
        blocker = self.folder / "blocker"
        blocker.write_bytes(b"not a directory")
        item = _download_file("mx5 mx52016", APP.PaintType.CAR)
        session = _FakeSession(get_responses=[_FakeResponse(200, b"TGA")])

        with mock.patch.object(APP, "get_thread_http_session", return_value=session):
            saved = APP.download_tp_paint_to(item, blocker / "nested", session=session)

        self.assertIsNone(saved)


class TempTrackerTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)

    def test_temp_tracker_never_deletes_own_or_preexisting_files(self):
        existing = self.folder / "existing.tga"
        existing.write_bytes(b"old")
        own = self.folder / "own.tga"
        own.write_bytes(b"own")
        new = self.folder / "new.tga"
        new.write_bytes(b"new")
        tracker = APP.TpPreviewTempFiles()

        tracker.track(existing, existed_before=True, is_own=False)
        tracker.track(own, existed_before=False, is_own=True)
        tracker.track(new, existed_before=False, is_own=False)
        tracker.cleanup()

        self.assertTrue(existing.exists())
        self.assertTrue(own.exists())
        self.assertFalse(new.exists())
        tracker.cleanup()  # A second cleanup is harmless.

    def test_temp_tracker_untrack_directory_keeps_the_downloaded_car_files(self):
        car_dir = self.folder / "mx5 mx52016"
        car_dir.mkdir()
        car_file = car_dir / "car_7.tga"
        car_file.write_bytes(b"car")
        other_file = self.folder / "helmet_7.tga"
        other_file.write_bytes(b"helmet")
        tracker = APP.TpPreviewTempFiles()
        tracker.track(car_file, existed_before=False, is_own=False)
        tracker.track(other_file, existed_before=False, is_own=False)

        tracker.untrack_directory(car_dir)
        tracker.cleanup()

        self.assertTrue(car_file.exists())
        self.assertFalse(other_file.exists())


class PreviewPanelTests(unittest.TestCase):
    def _panel(self):
        panel = object.__new__(APP.PaintPreviewPanel)
        panel._version = 1
        panel._car_image = None
        panel._tga_car_image = None
        panel._tga_decal_image = None
        panel._car_label = mock.Mock()
        panel._tga_car_label = mock.Mock()
        panel._tga_decal_label = mock.Mock()
        panel._notebook = mock.Mock()
        panel._car_tab = object()
        panel._tga_tab = object()
        panel._set_car_text = lambda text: None
        return panel

    def test_a_stale_preview_version_is_discarded(self):
        panel = APP.PaintPreviewPanel.__new__(APP.PaintPreviewPanel)
        panel._version = 5
        applied = []
        panel._set_car_text = lambda text: applied.append(text)

        panel._apply_preview_result(
            4,
            render_png=None,
            car_png=None,
            decal_png=None,
            service_available=False,
            pillow_available=False,
            has_car=True,
        )

        self.assertEqual(applied, [])
        self.assertEqual(panel._version, 5)

    def test_apply_result_passes_png_bytes(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        render_png = folder / "render.png"
        render_png.write_bytes(_TINY_PNG)

        panel = self._panel()
        received = []
        panel._photo_image = lambda png: received.append(png) or object()
        panel._set_tga_image = lambda *args: None

        panel._apply_preview_result(
            1,
            render_png=render_png,
            car_png=b"car",
            decal_png=None,
            service_available=True,
            pillow_available=True,
            has_car=True,
        )

        self.assertEqual(len(received), 1)
        self.assertIsInstance(received[0], bytes)

        panel = self._panel()
        tga_calls = []

        def raise_on_car(_png):
            raise TypeError("not an image")

        panel._photo_image = raise_on_car
        panel._set_tga_image = lambda *args: tga_calls.append(args)

        panel._apply_preview_result(
            1,
            render_png=render_png,
            car_png=b"car",
            decal_png=b"decal",
            service_available=True,
            pillow_available=True,
            has_car=True,
        )

        self.assertEqual(len(tga_calls), 2)


if __name__ == "__main__":
    unittest.main()
