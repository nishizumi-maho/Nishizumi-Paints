import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_cloud_sync_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


ONEDRIVE_PATH = Path(r"C:\Users\test\AppData\Local\Microsoft\OneDrive\OneDrive.exe")
DROPBOX_PATH = Path(r"C:\Program Files\Dropbox\Dropbox.exe")


class _CompletedCommand:
    def __init__(self, returncode: int = 0, stdout: str = "") -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = ""


def _controller(running: dict[str, Path], run_calls: list) -> APP.CloudSyncController:
    def find_client(image_name: str) -> Path | None:
        return running.get(image_name)

    def run_process(command, **kwargs):
        run_calls.append((list(command), kwargs))
        return _CompletedCommand()

    return APP.CloudSyncController(find_client=find_client, run_process=run_process, start_process=lambda *a, **k: None)


class PauseTests(unittest.TestCase):
    def test_pause_stops_only_running_clients_and_remembers_them(self):
        run_calls = []
        controller = _controller({APP.CloudSyncController.ONEDRIVE: ONEDRIVE_PATH}, run_calls)

        controller.pause()

        self.assertEqual([call[0] for call in run_calls], [[str(ONEDRIVE_PATH), "/shutdown"]])
        resumed = []
        controller._start_process = lambda command, **kwargs: resumed.append((list(command), kwargs))
        controller.resume()
        self.assertEqual([command for command, _kwargs in resumed], [[str(ONEDRIVE_PATH), "/background"]])

    def test_pause_uses_shutdown_and_taskkill_without_force(self):
        run_calls = []
        controller = _controller(
            {
                APP.CloudSyncController.ONEDRIVE: ONEDRIVE_PATH,
                APP.CloudSyncController.DROPBOX: DROPBOX_PATH,
            },
            run_calls,
        )

        controller.pause()

        commands = [call[0] for call in run_calls]
        self.assertIn([str(ONEDRIVE_PATH), "/shutdown"], commands)
        taskkill = next(command for command in commands if command[0] == "taskkill")
        self.assertEqual(taskkill, ["taskkill", "/IM", "Dropbox.exe"])
        self.assertNotIn("/F", taskkill)


class ResumeTests(unittest.TestCase):
    def _paused_controller(self) -> tuple[APP.CloudSyncController, list]:
        started: list = []
        controller = _controller(
            {
                APP.CloudSyncController.ONEDRIVE: ONEDRIVE_PATH,
                APP.CloudSyncController.DROPBOX: DROPBOX_PATH,
            },
            [],
        )
        controller._start_process = lambda command, **kwargs: started.append((list(command), kwargs))
        controller.pause()
        return controller, started

    def test_resume_restarts_only_paused_clients_and_onedrive_uses_background(self):
        controller, started = self._paused_controller()

        controller.resume()

        self.assertEqual(
            [command for command, _kwargs in started],
            [[str(ONEDRIVE_PATH), "/background"], [str(DROPBOX_PATH)]],
        )
        flags = started[0][1]["creationflags"]
        self.assertTrue(flags & APP.subprocess.DETACHED_PROCESS)
        self.assertTrue(flags & APP.subprocess.CREATE_NEW_PROCESS_GROUP)
        self.assertTrue(started[0][1]["close_fds"])

    def test_a_second_resume_starts_nothing(self):
        controller, started = self._paused_controller()
        controller.resume()
        started_count = len(started)

        controller.resume()

        self.assertEqual(len(started), started_count)


class ErrorTests(unittest.TestCase):
    def test_pause_find_client_error_is_logged_and_swallowed(self):
        def find_client(_image_name: str) -> Path | None:
            raise RuntimeError("cannot list processes")

        controller = APP.CloudSyncController(
            find_client=find_client,
            run_process=lambda *a, **k: _CompletedCommand(),
            start_process=lambda *a, **k: None,
        )

        with self.assertLogs(level="ERROR") as captured:
            controller.pause()

        self.assertTrue(any("Cloud sync action failed" in line for line in captured.output))

    def test_pause_stop_error_is_logged_and_swallowed(self):
        def run_process(*_args, **_kwargs):
            raise OSError("cannot stop the client")

        controller = APP.CloudSyncController(
            find_client=lambda _image_name: ONEDRIVE_PATH,
            run_process=run_process,
            start_process=lambda *a, **k: None,
        )

        with self.assertLogs(level="ERROR") as captured:
            controller.pause()

        self.assertTrue(any("Cloud sync action failed" in line for line in captured.output))

    def test_resume_error_is_logged_and_swallowed(self):
        controller = _controller({APP.CloudSyncController.ONEDRIVE: ONEDRIVE_PATH}, [])
        controller.pause()

        def start_process(*_args, **_kwargs):
            raise OSError("cannot start the client")

        controller._start_process = start_process

        with self.assertLogs(level="ERROR") as captured:
            controller.resume()
            controller.resume()

        self.assertTrue(any("Cloud sync action failed" in line for line in captured.output))


class ConfigTests(unittest.TestCase):
    def _store(self, directory: str) -> APP.ConfigStore:
        store = APP.ConfigStore()
        store.path = Path(directory) / "settings.json"
        return store

    def test_config_defaults_to_false(self):
        self.assertFalse(APP.AppConfig().manage_cloud_sync)

    def test_config_round_trips_through_settings(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = self._store(tmp.name)
        config = APP.AppConfig()
        config.manage_cloud_sync = True
        store.save(config)
        self.assertTrue(store.load().manage_cloud_sync)

        config.manage_cloud_sync = False
        store.save(config)
        self.assertFalse(store.load().manage_cloud_sync)

    def test_old_config_without_the_key_loads_false(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = self._store(tmp.name)
        store.path.write_text(json.dumps({"auto_refresh_paints": False}), encoding="utf-8")

        self.assertFalse(store.load().manage_cloud_sync)


if __name__ == "__main__":
    unittest.main()
