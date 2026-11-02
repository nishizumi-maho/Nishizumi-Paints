import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path

import requests


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_render_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


class _FakeResponse:
    def __init__(self, status_code=200, content=b""):
        self.status_code = status_code
        self.content = content


class _FakeSession:
    def __init__(self, response=None, error=None):
        self._response = response
        self._error = error
        self.requested_url = None
        self.requested_timeout = None

    def get(self, url, timeout=None, **_kwargs):
        self.requested_url = url
        self.requested_timeout = timeout
        if self._error is not None:
            raise self._error
        return self._response


def _save_tga(path, image, rle=False):
    image.save(path, format="TGA", compression="tga_rle" if rle else None)
    return path


class RenderUrlTests(unittest.TestCase):
    def test_car_url_fallback_design_uses_default_pattern_and_colours(self):
        paint_path = Path("paint dir/my car.tga")
        url = APP.iracing_render_url("car", paint_path, tick=123)
        self.assertIn("carPat=1&carCol=FF0000,00FF00,0000FF", url)
        self.assertIn("size=2&numShow=0&stampShow=0", url)
        self.assertIn("tick=123", url)
        self.assertIn(f"carCustPaint={str(paint_path).replace(' ', '%20')}", url)

    def test_car_url_uses_number_when_provided(self):
        url = APP.iracing_render_url("car", "car.tga", number="07", tick=5)
        self.assertIn("size=2&number=07&stampShow=0", url)

    def test_car_url_without_number_uses_num_show(self):
        url = APP.iracing_render_url("car", "car.tga", number=None, tick=5)
        self.assertIn("size=2&numShow=0&stampShow=0", url)

    def test_car_num_url_ignores_number(self):
        url = APP.iracing_render_url("car_num", "car.tga", number="07", tick=5)
        self.assertIn("size=2&numShow=0&stampShow=0", url)
        self.assertNotIn("&number=07", url)

    def test_car_url_splits_design_on_first_comma(self):
        url = APP.iracing_render_url("car", "car.tga", design="12,FF0000,00FF00,0000FF", tick=5)
        self.assertIn("carPat=12&carCol=FF0000,00FF00,0000FF", url)

    def test_car_url_turns_car_path_spaces_into_backslashes(self):
        url = APP.iracing_render_url("car", "car.tga", car_path="mx5 mx52016", tick=5)
        self.assertIn(r"carPath=mx5\mx52016", url)

    def test_suit_and_helmet_url_sizes(self):
        suit = APP.iracing_render_url("suit", "suit.tga", tick=9)
        helmet = APP.iracing_render_url("helmet", "helmet.tga", tick=9)
        self.assertTrue(suit.startswith(APP.IRACING_LOCAL_RENDER_URL + "pk_suit.png?size=3&tick=9"))
        self.assertTrue(helmet.startswith(APP.IRACING_LOCAL_RENDER_URL + "pk_helmet.png?size=2&tick=9"))
        self.assertIn("suitCustPaint=suit.tga", suit)
        self.assertIn("hlmtCustPaint=helmet.tga", helmet)

    def test_unknown_kind_returns_empty_url(self):
        self.assertEqual(APP.iracing_render_url("spec", "car.tga"), "")


class TgaDecodeTests(unittest.TestCase):
    def test_decode_rle_and_uncompressed_tgas_match(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            source = Image.new("RGBA", (5, 4))
            pixels = [
                ((x * 40) % 256, (y * 60) % 256, (x * y * 17) % 256, 255)
                for y in range(4)
                for x in range(5)
            ]
            source.putdata(pixels)
            rle_path = _save_tga(directory / "rle.tga", source, rle=True)
            plain_path = _save_tga(directory / "plain.tga", source, rle=False)

            rle_png = APP.tga_to_png_bytes(rle_path)
            plain_png = APP.tga_to_png_bytes(plain_path)

            self.assertIsNotNone(rle_png)
            self.assertIsNotNone(plain_png)
            rle_pixels = Image.open(io.BytesIO(rle_png)).convert("RGBA").tobytes()
            plain_pixels = Image.open(io.BytesIO(plain_png)).convert("RGBA").tobytes()
            self.assertEqual(rle_pixels, plain_pixels)
            self.assertEqual(rle_pixels, source.tobytes())

    def test_decode_missing_tga_returns_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self.assertIsNone(APP.tga_to_png_bytes(Path(temp_dir) / "missing.tga"))

    def test_decode_thumbnail_limits_size(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            path = _save_tga(Path(temp_dir) / "big.tga", Image.new("RGBA", (40, 20), (1, 2, 3, 255)))
            payload = APP.tga_to_png_bytes(path, max_size=10)
            self.assertIsNotNone(payload)
            self.assertEqual(Image.open(io.BytesIO(payload)).size, (10, 5))


class DecalMergeTests(unittest.TestCase):
    def _make_decal(self, path, alpha_left, alpha_right):
        from PIL import Image

        decal = Image.new("RGBA", (4, 4), (0, 0, 0, 0))
        decal.putdata(
            [(10, 200, 30, alpha_left) if x < 2 else (10, 200, 30, alpha_right) for y in range(4) for x in range(4)]
        )
        return _save_tga(path, decal, rle=True)

    def test_merge_decal_alpha_zero_keeps_car_and_full_alpha_replaces_it(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            car_path = _save_tga(directory / "car.tga", Image.new("RGBA", (4, 4), (200, 30, 40, 255)))
            decal_path = self._make_decal(directory / "decal.tga", 0, 255)
            destination = directory / "merged.tga"

            result = APP.merge_decal_onto_tga(car_path, decal_path, destination)

            self.assertEqual(result, destination)
            self.assertTrue(destination.exists())
            merged = Image.open(destination).convert("RGBA")
            self.assertEqual(merged.getpixel((0, 0)), (200, 30, 40, 255))
            self.assertEqual(merged.getpixel((3, 3)), (10, 200, 30, 255))

    def test_merge_missing_decal_copies_car_unchanged(self):
        from PIL import Image

        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            car_path = _save_tga(directory / "car.tga", Image.new("RGBA", (4, 4), (200, 30, 40, 255)), rle=True)
            destination = directory / "copied.tga"

            result = APP.merge_decal_onto_tga(car_path, directory / "missing.tga", destination)

            self.assertEqual(result, destination)
            self.assertEqual(destination.read_bytes(), car_path.read_bytes())

    def test_merge_missing_car_returns_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            directory = Path(temp_dir)
            decal_path = self._make_decal(directory / "decal.tga", 0, 255)
            self.assertIsNone(APP.merge_decal_onto_tga(directory / "missing.tga", decal_path, directory / "out.tga"))


class RenderFetchTests(unittest.TestCase):
    def test_fetch_connection_error_returns_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "render.png"
            session = _FakeSession(error=requests.ConnectionError("offline"))
            result = APP.fetch_iracing_render_png("http://example.invalid/render.png", destination, session=session)
            self.assertIsNone(result)
            self.assertFalse(destination.exists())

    def test_fetch_non_png_body_returns_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "render.png"
            session = _FakeSession(_FakeResponse(200, b"<html>not a png</html>"))
            result = APP.fetch_iracing_render_png("http://example.invalid/render.png", destination, session=session)
            self.assertIsNone(result)
            self.assertFalse(destination.exists())

    def test_fetch_png_body_writes_file(self):
        png = b"\x89PNG\r\n\x1a\n" + b"fake png body"
        with tempfile.TemporaryDirectory() as temp_dir:
            destination = Path(temp_dir) / "nested" / "render.png"
            session = _FakeSession(_FakeResponse(200, png))
            result = APP.fetch_iracing_render_png("http://example.invalid/render.png", destination, timeout=3.0, session=session)
            self.assertEqual(result, destination)
            self.assertTrue(destination.exists())
            self.assertEqual(destination.read_bytes(), png)
            self.assertEqual(session.requested_timeout, 3.0)

    def test_fetch_empty_url_returns_none(self):
        self.assertIsNone(APP.fetch_iracing_render_png("", Path("unused.png")))

    def test_render_service_available_accepts_any_response(self):
        session = _FakeSession(_FakeResponse(404, b""))
        self.assertTrue(APP.iracing_render_service_available(session=session))

    def test_render_service_unavailable_on_connection_error(self):
        session = _FakeSession(error=requests.ConnectionError("refused"))
        self.assertFalse(APP.iracing_render_service_available(session=session))


if __name__ == "__main__":
    unittest.main()
