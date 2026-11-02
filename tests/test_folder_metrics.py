import importlib.util
import sys
import tempfile
import unittest
from collections import namedtuple
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_folder_metrics_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


_DiskUsage = namedtuple("_DiskUsage", "total used free")


class FolderSizeTests(unittest.TestCase):
    def test_size_sums_nested_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            nested = root / "nested" / "deeper"
            nested.mkdir(parents=True)
            (root / "root.bin").write_bytes(b"a" * 5)
            (nested / "nested.bin").write_bytes(b"b" * 7)
            self.assertEqual(APP.measure_folder_size(root), 12)

    def test_size_of_a_missing_folder_is_minus_one(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            missing = Path(temp_dir) / "does-not-exist"
            self.assertEqual(APP.measure_folder_size(missing), -1)

    def test_size_returns_minus_two_when_walking_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with mock.patch.object(APP.os, "scandir", side_effect=OSError("denied")):
                self.assertEqual(APP.measure_folder_size(Path(temp_dir)), -2)


class FolderMetricsTests(unittest.TestCase):
    def test_metrics_order_labels_and_extra_folders(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            documents = root / "iRacing"
            expected_sizes = {
                "airosters": 1,
                "paint": 2,
                "replay": 3,
                "telemetry": 4,
                "videos": 5,
            }
            for name, size in expected_sizes.items():
                folder = documents / name
                folder.mkdir(parents=True)
                (folder / "data.bin").write_bytes(b"x" * size)
            ai_liveries = root / "AiLiveries"
            ai_liveries.mkdir()
            (ai_liveries / "livery.bin").write_bytes(b"x" * 6)
            random_pool = root / "RandomPool"
            random_pool.mkdir()
            (random_pool / "paint.bin").write_bytes(b"x" * 7)
            extra = {"AI liveries": ai_liveries, "Random pool": random_pool}

            metrics = APP.iracing_folder_metrics(documents, extra)

            self.assertEqual(
                [label for label, _path, _size in metrics],
                ["airosters", "paint", "replay", "telemetry", "videos", "AI liveries", "Random pool"],
            )
            self.assertEqual(
                [size for _label, _path, size in metrics],
                [1, 2, 3, 4, 5, 6, 7],
            )
            self.assertEqual(metrics[0][1], documents / "airosters")
            self.assertEqual(metrics[-1][1], random_pool)


class FolderSizeFormatTests(unittest.TestCase):
    def test_format_size_boundaries(self):
        cases = {
            0: "0 B",
            1023: "1023 B",
            1024: "1.0 KB",
            1536 * 1024: "1.5 MB",
            1024 ** 3: "1.0 GB",
            1024 ** 4: "1.0 TB",
        }
        for size, expected in cases.items():
            with self.subTest(size=size):
                self.assertEqual(APP.format_folder_size(size), expected)

    def test_format_size_sentinels(self):
        self.assertEqual(APP.format_folder_size(-1), "N/A")
        self.assertEqual(APP.format_folder_size(-2), "Error")


class FreeSpaceTests(unittest.TestCase):
    def test_free_space_low_flag_at_nine_and_eleven_percent(self):
        with mock.patch.object(APP.shutil, "disk_usage", return_value=_DiskUsage(1000, 910, 90)):
            self.assertEqual(APP.free_space_info(Path(".")), (90, 1000, True))
        with mock.patch.object(APP.shutil, "disk_usage", return_value=_DiskUsage(1000, 890, 110)):
            self.assertEqual(APP.free_space_info(Path(".")), (110, 1000, False))

    def test_free_space_error_returns_none(self):
        with mock.patch.object(APP.shutil, "disk_usage", side_effect=OSError("unavailable")):
            self.assertIsNone(APP.free_space_info(Path(".")))


if __name__ == "__main__":
    unittest.main()
