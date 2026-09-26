import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_randomize_ai_roster_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


CAR = "dallarap217"
ROSTER = "Test Roster"
RANDOM_ROSTER = f"{ROSTER}{APP.AI_RANDOM_ROSTER_SUFFIX}"


def _driver(number, name, car_tga=None):
    return {
        "driverName": name,
        "carNumber": str(number),
        "carId": 128,
        "carClassId": 0,
        "carPath": CAR,
        "carTgaName": car_tga,
        "helmetTgaName": None,
        "suitTgaName": None,
    }


class RandomizeActiveAiRosterTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="nishizumi_random_roster_"))
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.rosters = self.root / "airosters"
        self.pool = self.root / "RandomPool"
        self.livery = self.root / "ailiveries"
        # Keep the user's real favorites/blocked list out of the picks.
        patcher = mock.patch.object(APP, "load_random_paint_preferences", return_value=APP._empty_random_paint_preferences())
        patcher.start()
        self.addCleanup(patcher.stop)

        self.source_dir = self.rosters / ROSTER
        self.source_dir.mkdir(parents=True)
        (self.source_dir / "car_111.tga").write_bytes(b"original car")
        drivers = [_driver(1, "Alpha", "car_111.tga"), _driver(2, "Bravo"), _driver(3, "Charlie")]
        (self.source_dir / "roster.json").write_text(json.dumps({"drivers": drivers}), encoding="utf-8")

        self.session = APP.Session(
            session_id=APP.SessionId(main_session_id=1, sub_session_id=2),
            users=set(),
            ai_driver_count=3,
            ai_roster_id="42",
            ai_roster_name=ROSTER,
        )

    def _add_pool_set(self, name, *, helmet=False, suit=False):
        set_dir = self.pool / APP._safe_random_pool_bucket(CAR) / name
        set_dir.mkdir(parents=True)
        (set_dir / "car.tga").write_bytes(f"{name} car".encode())
        (set_dir / "car_spec.mip").write_bytes(f"{name} spec".encode())
        if helmet:
            (set_dir / "helmet.tga").write_bytes(f"{name} helmet".encode())
        if suit:
            (set_dir / "suit.tga").write_bytes(f"{name} suit".encode())

    def _randomize(self, session=None, seed="test"):
        return APP.randomize_active_ai_roster_from_pool(
            session or self.session,
            self.rosters,
            self.pool,
            self.livery,
            seed=seed,
        )

    def _read_drivers(self, roster_dir):
        return json.loads((roster_dir / "roster.json").read_text(encoding="utf-8"))["drivers"]

    def test_builds_local_roster_with_random_pool_paints(self):
        self._add_pool_set("set_a", helmet=True)
        self._add_pool_set("set_b", suit=True)

        ok, message = self._randomize()

        self.assertTrue(ok, message)
        target = self.rosters / RANDOM_ROSTER
        drivers = self._read_drivers(target)
        self.assertEqual([d["driverName"] for d in drivers], ["Alpha", "Bravo", "Charlie"])
        pool_cars = {b"set_a car", b"set_b car"}
        for row, driver in enumerate(drivers, start=1):
            self.assertEqual(driver["carTgaName"], f"car_{row}.tga")
            self.assertIn((target / driver["carTgaName"]).read_bytes(), pool_cars)
            self.assertTrue((target / f"car_{row}_spec.mip").exists())
            self.assertEqual(driver["helmetTgaName"], f"helmet_{row}.tga")
            self.assertEqual(driver["suitTgaName"], f"suit_{row}.tga")
            self.assertTrue((target / driver["helmetTgaName"]).exists())
            self.assertTrue((target / driver["suitTgaName"]).exists())
        # Two distinct paints for three drivers: the first two never repeat.
        self.assertNotEqual((target / "car_1.tga").read_bytes(), (target / "car_2.tga").read_bytes())

        meta = json.loads((target / APP.AI_ROSTER_META_FILENAME).read_text(encoding="utf-8"))
        self.assertTrue(meta["is_local"])
        self.assertEqual(meta["name"], RANDOM_ROSTER)
        self.assertEqual(meta["source_roster_id"], "42")
        self.assertTrue(APP._ai_roster_dir_is_local(target))
        self.assertFalse(APP._ai_roster_dir_is_generated_random(target))

        # The synced Trading Paints roster is left untouched.
        self.assertEqual(self._read_drivers(self.source_dir)[0]["carTgaName"], "car_111.tga")
        self.assertEqual((self.source_dir / "car_111.tga").read_bytes(), b"original car")

    def test_running_again_replaces_the_randomized_roster(self):
        self._add_pool_set("set_a")
        self.assertTrue(self._randomize(seed="first")[0])
        stale = self.rosters / RANDOM_ROSTER / "stale.tga"
        stale.write_bytes(b"old")

        ok, message = self._randomize(seed="second")

        self.assertTrue(ok, message)
        self.assertFalse(stale.exists())
        self.assertFalse((self.rosters / f"{RANDOM_ROSTER}.building").exists())

    def test_randomizing_the_randomized_roster_rebuilds_it_in_place(self):
        self._add_pool_set("set_a")
        self.assertTrue(self._randomize()[0])
        active_random = APP.Session(
            session_id=self.session.session_id,
            users=set(),
            ai_driver_count=3,
            ai_roster_name=RANDOM_ROSTER,
        )

        ok, message = self._randomize(session=active_random, seed="again")

        self.assertTrue(ok, message)
        self.assertEqual(sorted(p.name for p in self.rosters.iterdir()), sorted([ROSTER, RANDOM_ROSTER]))
        self.assertEqual(len(self._read_drivers(self.rosters / RANDOM_ROSTER)), 3)

    def test_empty_pool_keeps_the_previous_randomized_roster(self):
        self._add_pool_set("set_a")
        self.assertTrue(self._randomize()[0])
        shutil.rmtree(self.pool)

        ok, message = self._randomize(seed="empty")

        self.assertFalse(ok)
        self.assertIn("RandomPool has no paints", message)
        self.assertTrue((self.rosters / RANDOM_ROSTER / "car_1.tga").exists())

    def test_driver_without_pool_car_keeps_original_paint(self):
        # Only an accessory is available, so car paints fall back to the source roster.
        helmet_dir = self.pool / "other_car" / "set_h"
        helmet_dir.mkdir(parents=True)
        (helmet_dir / "helmet.tga").write_bytes(b"helmet")

        ok, message = self._randomize()

        self.assertTrue(ok, message)
        target = self.rosters / RANDOM_ROSTER
        drivers = self._read_drivers(target)
        self.assertEqual(drivers[0]["carTgaName"], "car_111.tga")
        self.assertEqual((target / "car_111.tga").read_bytes(), b"original car")
        self.assertIsNone(drivers[1]["carTgaName"])
        self.assertEqual(drivers[1]["helmetTgaName"], "helmet_2.tga")

    def test_reports_missing_session_or_roster(self):
        ok, message = APP.randomize_active_ai_roster_from_pool(None, self.rosters, self.pool, self.livery)
        self.assertFalse(ok)
        self.assertIn("No current iRacing session", message)
        no_roster = APP.Session(session_id=self.session.session_id, users=set())
        ok, message = self._randomize(session=no_roster)
        self.assertFalse(ok)
        self.assertIn("does not report an active AI roster", message)

    def test_ui_button_handler_calls_defined_function(self):
        # Without the function behind it the button raised NameError.
        ui = mock.Mock()
        ui.service.get_runtime_snapshot.return_value = mock.Mock(current_session=self.session)
        with mock.patch.object(APP, "default_ai_rosters_dir", return_value=self.rosters), \
             mock.patch.object(APP, "default_random_pool_dir", return_value=self.pool), \
             mock.patch.object(APP, "default_ai_livery_dir", return_value=self.livery):
            self._add_pool_set("set_a")
            APP.DownloaderUI.randomize_active_ai_roster(ui)
        ui._append_log.assert_called_once()
        self.assertIn("Created randomized AI roster", ui._append_log.call_args[0][0])
        ui.status_var.set.assert_called_once_with("Random AI roster created")


if __name__ == "__main__":
    unittest.main()
