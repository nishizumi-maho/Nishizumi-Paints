import bz2
import importlib.util
import io
import shutil
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_downloads_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


class _StreamingResponse:
    def __init__(self, chunks, on_chunk=None):
        self.chunks = chunks
        self.on_chunk = on_chunk

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def raise_for_status(self):
        pass

    def iter_content(self, chunk_size=None):
        self.chunk_size = chunk_size
        for chunk in self.chunks:
            if self.on_chunk is not None:
                self.on_chunk()
            yield chunk


class DownloadCancelTests(unittest.TestCase):
    def test_a_cancel_mid_download_leaves_no_partial_file(self):
        temp_root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, temp_root, True)
        cancel = threading.Event()
        response = _StreamingResponse([b"a" * 10, b"b" * 10, b"c" * 10])
        calls = {"count": 0}

        def cancel_after_first_chunk():
            calls["count"] += 1
            if calls["count"] == 2:
                cancel.set()

        response.on_chunk = cancel_after_first_chunk
        http = mock.Mock()
        http.get.return_value = response
        item = APP.DownloadFile(
            download_id=APP.DownloadId(5, "mx5 mx52016", APP.PaintType.CAR),
            url="https://example.invalid/car_5.tga",
        )
        with mock.patch.object(APP, "get_thread_http_session", return_value=http):
            result = APP.download_file(APP.SessionId(1, 2), temp_root, item, 3, 0.1, cancel_event=cancel)
        self.assertIsNone(result)
        self.assertEqual([path for path in temp_root.rglob("*") if path.is_file()], [])
        self.assertLessEqual(response.chunk_size, 256 * 1024)


class Bz2LimitTests(unittest.TestCase):
    def test_a_bz2_that_expands_past_any_paint_size_is_refused(self):
        folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, folder, True)
        source = folder / "car.tga.bz2"
        source.write_bytes(bz2.compress(b"\0" * (3 * 1024 * 1024)))
        out = io.BytesIO()
        with self.assertRaises(RuntimeError):
            APP._copy_bz2_capped(source, out, limit=2 * 1024 * 1024)
        out = io.BytesIO()
        self.assertEqual(APP._copy_bz2_capped(source, out, limit=4 * 1024 * 1024), 3 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
