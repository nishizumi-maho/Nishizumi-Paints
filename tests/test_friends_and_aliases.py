import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_friends_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


def _download_file(directory: str, paint_type=APP.PaintType.CAR, user_id: int = 7):
    return APP.DownloadFile(
        download_id=APP.DownloadId(user_id=user_id, directory=directory, paint_type=paint_type),
        url=f"https://example.invalid/{directory}.tga",
    )


class PeopleStorageTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)
        self.path = self.folder / ".nishizumi_people.json"

    def test_storage_round_trip_keeps_every_bucket(self):
        data = {
            "version": 1,
            "friends": {"7": "Driver Seven"},
            "driver_aliases": {"7": "Seven"},
            "team_aliases": {"42": "Team Forty-Two"},
        }

        APP.save_people(data, self.path)

        self.assertEqual(APP.load_people(self.path), data)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["version"], 1)

    def test_storage_set_and_remove_friend(self):
        APP.set_friend(7, "Driver Seven", True, self.path)
        self.assertEqual(APP.load_people(self.path)["friends"], {"7": "Driver Seven"})

        APP.set_friend(7, "Driver Seven", False, self.path)
        self.assertEqual(APP.load_people(self.path)["friends"], {})

    def test_storage_set_and_remove_alias(self):
        APP.set_alias("driver", 7, "Seven", self.path)
        APP.set_alias("team", 42, "Forty-Two", self.path)

        people = APP.load_people(self.path)
        self.assertEqual(people["driver_aliases"], {"7": "Seven"})
        self.assertEqual(people["team_aliases"], {"42": "Forty-Two"})

        APP.set_alias("driver", 7, "", self.path)
        APP.set_alias("team", 42, "  ", self.path)

        people = APP.load_people(self.path)
        self.assertEqual(people["driver_aliases"], {})
        self.assertEqual(people["team_aliases"], {})

    def test_storage_corrupt_file_loads_empty(self):
        self.path.write_text("{not valid json", encoding="utf-8")
        self.assertEqual(APP.load_people(self.path), APP._empty_people())

        self.path.write_text(json.dumps(["a", "list"]), encoding="utf-8")
        self.assertEqual(APP.load_people(self.path), APP._empty_people())


class AliasDisplayTests(unittest.TestCase):
    def test_display_driver_alias(self):
        people = {
            "version": 1,
            "friends": {},
            "driver_aliases": {"7": "Seven"},
            "team_aliases": {"42": "Team Forty-Two"},
        }

        self.assertEqual(APP.display_name_with_alias("Driver Seven", 7, 0, people), "Seven (Driver Seven)")

    def test_display_team_alias_on_team_rows(self):
        people = {
            "version": 1,
            "friends": {},
            "driver_aliases": {"7": "Seven"},
            "team_aliases": {"42": "Team Forty-Two"},
        }

        self.assertEqual(
            APP.display_name_with_alias("Driver Seven", 7, 42, people),
            "Team Forty-Two (Driver Seven)",
        )
        # A user row passes no team id, so the driver alias applies.
        self.assertEqual(APP.display_name_with_alias("Driver Seven", 7, None, people), "Seven (Driver Seven)")

    def test_display_no_alias(self):
        people = {"version": 1, "friends": {}, "driver_aliases": {}, "team_aliases": {}}

        self.assertEqual(APP.display_name_with_alias("Driver Seven", 7, 42, people), "Driver Seven")
        self.assertEqual(APP.display_name_with_alias("Driver Seven", None, None, None), "Driver Seven")


class FriendsDownloadTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.folder, True)

    def test_friends_download_downloads_every_friends_grouped_files(self):
        manifests = {
            1: [_download_file("car-a"), _download_file("car-a", APP.PaintType.CAR_DECAL)],
            2: [_download_file("car-b")],
            3: [],
        }
        fetched = []
        downloaded = []

        def fetch(member_id):
            fetched.append(member_id)
            return manifests[member_id]

        def download(item, destination):
            downloaded.append((item.download_id.directory, destination))
            return destination / f"{item.download_id.directory}.tga"

        progress = []
        result = APP.download_friends_paints(
            [1, 2, 3],
            fetch,
            download,
            self.folder,
            progress=lambda done, total, files: progress.append((done, total, files)),
        )

        self.assertEqual(fetched, [1, 2, 3])
        self.assertEqual(len(downloaded), 3)
        self.assertTrue(all(destination == self.folder for _directory, destination in downloaded))
        self.assertEqual(result["friends_total"], 3)
        self.assertEqual(result["friends_done"], 3)
        self.assertEqual(result["files"], 3)
        self.assertEqual(result["failed"], [])
        self.assertEqual(progress, [(1, 3, 2), (2, 3, 3), (3, 3, 3)])

    def test_friends_download_one_failing_friend_does_not_stop_the_rest(self):
        downloaded = []

        def fetch(member_id):
            if member_id == 2:
                raise RuntimeError("network down")
            return [_download_file(f"car-{member_id}")]

        def download(item, destination):
            downloaded.append(item.download_id.directory)
            return destination / item.download_id.directory

        result = APP.download_friends_paints([1, 2, 3], fetch, download, self.folder)

        self.assertEqual(downloaded, ["car-1", "car-3"])
        self.assertEqual(result["friends_done"], 3)
        self.assertEqual(result["files"], 2)
        self.assertEqual(result["failed"], [2])


if __name__ == "__main__":
    unittest.main()
