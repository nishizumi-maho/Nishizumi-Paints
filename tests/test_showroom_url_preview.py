import bz2
import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_showroom_url_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


class _FakeResponse:
    def __init__(self, status_code=200, content=b""):
        self.status_code = status_code
        self.content = content


class _FakeSession:
    def __init__(self, responses=None):
        self.responses = list(responses or [])
        self.urls = []

    def get(self, url, **_kwargs):
        self.urls.append(url)
        if not self.responses:
            return _FakeResponse(404)
        return self.responses.pop(0)


class ShowroomUrlParseTests(unittest.TestCase):
    def test_parse_accepts_every_documented_url_form(self):
        for text in (
            "https://www.tradingpaints.com/showroom/view/123456/Some-Title",
            "https://tradingpaints.com/showroom/view/123456/Some-Title",
            "http://www.tradingpaints.com/showroom/view/123456",
            "www.tradingpaints.com/showroom/view/123456/Some-Title",
            "tradingpaints.com/showroom/view/123456/Some-Title",
            "  \"https://www.tradingpaints.com/showroom/view/123456/Some-Title\"  ",
            "https://www.tradingpaints.com/showroom/view/123456/Some-Title/",
            "https://www.tradingpaints.com/showroom/view/123456?from=showroom",
            "https://www.tradingpaints.com/showroom/view/123456/Some-Title?page=2#paint",
        ):
            with self.subTest(text=text):
                self.assertEqual(APP.parse_tp_showroom_asset_id(text), "123456")

    def test_parse_rejects_other_pages_and_text(self):
        for text in (
            "https://www.tradingpaints.com/showroom/collection/123456",
            "https://www.tradingpaints.com/showroom",
            "not a URL",
            "https://www.tradingpaints.com/showroom/view/not-a-number",
            "",
        ):
            with self.subTest(text=text):
                self.assertEqual(APP.parse_tp_showroom_asset_id(text), "")


class ShowroomAssetDownloadTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)

    def test_asset_tga_is_decompressed_and_a_missing_mip_is_optional(self):
        payload = b"TGA" * 100
        session = _FakeSession([_FakeResponse(200, bz2.compress(payload)), _FakeResponse(404)])

        tga, mip = APP.download_tp_showroom_asset("123456", self.folder, session=session)

        self.assertEqual(tga, self.folder / "123456.tga")
        self.assertEqual(tga.read_bytes(), payload)
        self.assertIsNone(mip)
        self.assertFalse((self.folder / "123456.mip").exists())
        self.assertEqual(len(session.urls), 2)

    def test_asset_tga_failure_writes_nothing_and_returns_no_paths(self):
        session = _FakeSession([_FakeResponse(404)])

        tga, mip = APP.download_tp_showroom_asset("123456", self.folder, session=session)

        self.assertIsNone(tga)
        self.assertIsNone(mip)
        self.assertEqual([path for path in self.folder.rglob("*") if path.is_file()], [])

    def test_asset_mip_is_saved_beside_the_tga(self):
        payload = b"TGA" * 20
        spec = b"MIP" * 20
        session = _FakeSession([_FakeResponse(200, bz2.compress(payload)), _FakeResponse(200, spec)])

        tga, mip = APP.download_tp_showroom_asset("123456", self.folder, session=session)

        self.assertEqual(tga, self.folder / "123456.tga")
        self.assertEqual(mip, self.folder / "123456.mip")
        self.assertEqual(mip.read_bytes(), spec)


class ShowroomInstallTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.paints = self.folder / "paint"
        self.paints.mkdir()
        self.tga = self.folder / "123456.tga"
        self.tga.write_bytes(b"new car paint")
        self.mip = self.folder / "123456.mip"
        self.mip.write_bytes(b"new spec map")
        self.decal_path = APP.save_path_for(
            APP.DownloadId(7, "mx5 mx52016", APP.PaintType.CAR_DECAL),
            self.paints,
        )
        self.decal_path.parent.mkdir(parents=True, exist_ok=True)
        self.decal_path.write_bytes(b"keep this decal")

    def test_install_writes_car_and_spec_and_keeps_the_decal(self):
        written = APP.install_showroom_paint(
            self.tga,
            self.mip,
            paints_dir=self.paints,
            car_directory="mx5 mx52016",
            member_id=7,
        )

        car_path = APP.save_path_for(APP.DownloadId(7, "mx5 mx52016", APP.PaintType.CAR), self.paints)
        spec_path = APP.save_path_for(APP.DownloadId(7, "mx5 mx52016", APP.PaintType.CAR_SPEC), self.paints)
        self.assertEqual(written, [car_path, spec_path])
        self.assertEqual(car_path.read_bytes(), b"new car paint")
        self.assertEqual(spec_path.read_bytes(), b"new spec map")
        self.assertEqual(self.decal_path.read_bytes(), b"keep this decal")

    def test_install_without_a_mip_removes_the_old_spec_and_keeps_the_decal(self):
        spec_path = APP.save_path_for(APP.DownloadId(7, "mx5 mx52016", APP.PaintType.CAR_SPEC), self.paints)
        spec_path.parent.mkdir(parents=True, exist_ok=True)
        spec_path.write_bytes(b"stale spec map")

        written = APP.install_showroom_paint(
            self.tga,
            None,
            paints_dir=self.paints,
            car_directory="mx5 mx52016",
            member_id=7,
        )

        car_path = APP.save_path_for(APP.DownloadId(7, "mx5 mx52016", APP.PaintType.CAR), self.paints)
        self.assertEqual(written, [car_path])
        self.assertFalse(spec_path.exists())
        self.assertEqual(self.decal_path.read_bytes(), b"keep this decal")


class ShowroomInstallAllowedTests(unittest.TestCase):
    def test_allowed_only_for_the_users_own_known_car_folder(self):
        self.assertTrue(APP.showroom_install_allowed(7, 7, "mx5 mx52016"))
        self.assertFalse(APP.showroom_install_allowed(8, 7, "mx5 mx52016"))
        self.assertFalse(APP.showroom_install_allowed(7, 0, "mx5 mx52016"))
        self.assertFalse(APP.showroom_install_allowed(0, 7, "mx5 mx52016"))
        self.assertFalse(APP.showroom_install_allowed(7, 7, ""))
        self.assertFalse(APP.showroom_install_allowed(7, 7, None))


if __name__ == "__main__":
    unittest.main()
