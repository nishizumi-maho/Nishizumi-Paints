import argparse
import importlib.util
import json
import socket
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_launch_mode_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


NEWER_TAG = "v99.0.0"
ASSET_NAME = "NishizumiPaints-Setup-99.0.0.exe"
ASSET_URL = f"https://github.com/nishizumi-maho/Nishizumi-Paints/releases/download/{NEWER_TAG}/{ASSET_NAME}"


def _release(tag=NEWER_TAG, **overrides):
    payload = {
        "tag_name": tag,
        "html_url": f"https://github.com/nishizumi-maho/Nishizumi-Paints/releases/tag/{tag}",
        "asset_name": ASSET_NAME,
        "asset_download_url": ASSET_URL,
        "asset_size": 4,
        "asset_sha256": "a" * 64,
    }
    payload.update(overrides)
    return APP.GitHubReleaseInfo(**payload)


def _args(**overrides):
    values = {"gui": False, "nogui": False, "autostart_launched": False, "verbose": False}
    values.update(overrides)
    return argparse.Namespace(**values)


class _TempStoreMixin:
    def make_store(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        store = APP.ConfigStore()
        store.path = Path(tmp.name) / "settings.json"
        return store


class ConfigStoreLaunchModeTests(_TempStoreMixin, unittest.TestCase):
    def test_saving_the_startup_mode_keeps_every_other_setting(self):
        store = self.make_store()
        config = APP.AppConfig()
        config.poll_seconds = 2.5
        config.check_updates_automatically = False
        store.save(config)

        store.save_launch_mode_preference("headless")

        loaded = store.load()
        self.assertEqual(loaded.launch_mode_preference, "headless")
        self.assertEqual(loaded.poll_seconds, 2.5)
        self.assertFalse(loaded.check_updates_automatically)
        self.assertEqual(store.load_launch_mode_preference(), "headless")

    def test_startup_mode_can_be_saved_before_any_settings_exist(self):
        store = self.make_store()
        store.save_launch_mode_preference("gui")
        self.assertEqual(store.load().launch_mode_preference, "gui")

    def test_missing_settings_mean_ask(self):
        self.assertEqual(self.make_store().load_launch_mode_preference(), "ask")

    def test_unreadable_settings_are_not_overwritten_by_the_startup_mode(self):
        store = self.make_store()
        store.path.write_text("{ not json", encoding="utf-8")
        with mock.patch.object(APP, "CONFIG_IO_RETRY_SECONDS", 0.0):
            with self.assertRaises(RuntimeError):
                store.save_launch_mode_preference("gui")
        self.assertEqual(store.path.read_text(encoding="utf-8"), "{ not json")

    def test_a_running_copy_saving_stale_settings_does_not_undo_the_startup_mode(self):
        # The copy in the tray loaded its settings before the startup mode was chosen.
        store = self.make_store()
        store.save(APP.AppConfig())
        stale_in_memory = store.load()
        store.save_launch_mode_preference("headless")

        ui = mock.MagicMock()
        ui.config_store = store
        ui.config = stale_in_memory
        ui._normalize_random_pool_category_ui_values.return_value = (3.0, 1.0, 1.0)
        saved = APP.DownloaderUI._read_ui_config(ui)

        self.assertEqual(stale_in_memory.launch_mode_preference, "ask")
        self.assertEqual(saved.launch_mode_preference, "headless")

    def test_switching_mode_in_the_window_writes_only_the_startup_mode(self):
        store = self.make_store()
        config = APP.AppConfig()
        config.poll_seconds = 3.0
        store.save(config)
        ui = mock.MagicMock()
        ui.config_store = store
        ui.config = store.load()

        APP.DownloaderUI._persist_launch_mode_preference(ui, "headless")

        self.assertEqual(store.load_launch_mode_preference(), "headless")
        self.assertEqual(store.load().poll_seconds, 3.0)
        self.assertEqual(ui.config.launch_mode_preference, "headless")
        ui._apply_autostart.assert_called_once()

    def test_save_replaces_the_file_without_leaving_temporary_files(self):
        store = self.make_store()
        store.save(APP.AppConfig())
        store.save_launch_mode_preference("gui")
        self.assertEqual(sorted(p.name for p in store.path.parent.iterdir()), ["settings.json"])
        self.assertIsInstance(json.loads(store.path.read_text(encoding="utf-8")), dict)

    def test_a_read_during_a_replace_is_tried_again(self):
        store = self.make_store()
        store.path.write_text('{"launch_mode_preference": "gu', encoding="utf-8")

        def finish_write():
            time.sleep(0.1)
            store.path.write_text('{"launch_mode_preference": "gui"}', encoding="utf-8")

        writer = threading.Thread(target=finish_write)
        writer.start()
        self.addCleanup(writer.join)
        self.assertEqual(store.load().launch_mode_preference, "gui")


class ResolveLaunchModeTests(_TempStoreMixin, unittest.TestCase):
    def setUp(self):
        self.store = self.make_store()
        self.dialog = mock.Mock(return_value=("headless", True))
        patches = [
            mock.patch.object(APP, "show_launch_mode_dialog", self.dialog),
            mock.patch.object(APP, "is_shift_pressed_at_startup", return_value=False),
        ]
        for patcher in patches:
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_a_remembered_choice_starts_without_the_selector(self):
        self.store.save_launch_mode_preference("headless")
        self.assertEqual(APP.resolve_requested_launch_mode(_args(), self.store), "headless")
        self.dialog.assert_not_called()

    def test_the_remembered_choice_survives_the_next_launch(self):
        settings = APP.AppConfig()
        settings.poll_seconds = 1.7
        self.store.save(settings)
        self.assertEqual(APP.resolve_requested_launch_mode(_args(), self.store), "headless")
        self.dialog.assert_called_once()

        self.assertEqual(APP.resolve_requested_launch_mode(_args(), self.store), "headless")
        self.dialog.assert_called_once()
        self.assertEqual(self.store.load().poll_seconds, 1.7)

    def test_an_unremembered_choice_asks_again(self):
        self.dialog.return_value = ("gui", False)
        self.assertEqual(APP.resolve_requested_launch_mode(_args(), self.store), "gui")
        self.assertEqual(self.store.load_launch_mode_preference(), "ask")

    def test_no_selector_when_the_app_is_already_running(self):
        mode = APP.resolve_requested_launch_mode(_args(), self.store, another_instance_running=True)
        self.assertEqual(mode, APP.LAUNCH_MODE_RUNNING_INSTANCE)
        self.dialog.assert_not_called()

    def test_shift_still_opens_the_selector_while_the_app_is_running(self):
        self.store.save_launch_mode_preference("gui")
        with mock.patch.object(APP, "is_shift_pressed_at_startup", return_value=True):
            mode = APP.resolve_requested_launch_mode(_args(), self.store, another_instance_running=True)
        self.assertEqual(mode, "headless")
        self.dialog.assert_called_once_with("gui")

    def test_sign_in_launch_never_asks(self):
        with mock.patch.object(APP, "is_shift_pressed_at_startup", return_value=True):
            self.assertEqual(APP.resolve_requested_launch_mode(_args(autostart_launched=True), self.store), "gui")
            self.store.save_launch_mode_preference("headless")
            self.assertEqual(APP.resolve_requested_launch_mode(_args(autostart_launched=True), self.store), "headless")
        self.dialog.assert_not_called()

    def test_command_line_switches_win(self):
        self.store.save_launch_mode_preference("headless")
        self.assertEqual(APP.resolve_requested_launch_mode(_args(gui=True), self.store), "gui")
        self.assertEqual(APP.resolve_requested_launch_mode(_args(nogui=True), self.store), "headless")
        self.dialog.assert_not_called()

    def test_cancel_starts_nothing(self):
        self.dialog.return_value = None
        self.assertIsNone(APP.resolve_requested_launch_mode(_args(), self.store))


class _FakeLock:
    def __init__(self, acquired):
        self.acquired = acquired
        self.released = False

    def acquire(self):
        return self.acquired

    def release(self):
        self.released = True


class MainStartupTests(_TempStoreMixin, unittest.TestCase):
    def _run_main(self, *, acquired, saved_mode="ask", args=None, headless_running=False):
        store = self.make_store()
        if saved_mode != "ask":
            store.save_launch_mode_preference(saved_mode)
        lock = _FakeLock(acquired)
        dialog = mock.Mock(return_value=("gui", True))
        ui_class = mock.Mock()
        notify = mock.Mock(return_value=True)
        run_headless = mock.Mock(return_value=0)
        status = {"ok": True, "mode": "headless"} if headless_running else None
        with mock.patch.object(APP, "parse_args", return_value=args or _args()), \
             mock.patch.object(APP, "ConfigStore", return_value=store), \
             mock.patch.object(APP, "SingleInstanceLock", return_value=lock), \
             mock.patch.object(APP, "show_launch_mode_dialog", dialog), \
             mock.patch.object(APP, "is_shift_pressed_at_startup", return_value=False), \
             mock.patch.object(APP, "DownloaderUI", ui_class), \
             mock.patch.object(APP.SingleInstanceSignalServer, "notify_existing_instance", notify), \
             mock.patch.object(APP, "send_headless_control_command", return_value=status), \
             mock.patch.object(APP, "run_headless", run_headless):
            self.assertEqual(APP.main(), 0)
        return SimpleNamespace(lock=lock, dialog=dialog, ui_class=ui_class, notify=notify, run_headless=run_headless)

    def test_opening_the_app_again_brings_the_running_copy_forward_without_asking(self):
        result = self._run_main(acquired=False)
        result.dialog.assert_not_called()
        result.notify.assert_called_once()
        result.ui_class.assert_not_called()

    def test_first_launch_asks_once_and_starts_the_window(self):
        result = self._run_main(acquired=True)
        result.dialog.assert_called_once()
        result.ui_class.assert_called_once()
        self.assertTrue(result.lock.released)

    def test_headless_launch_reuses_the_lock_main_already_holds(self):
        result = self._run_main(acquired=True, saved_mode="headless")
        result.run_headless.assert_called_once()
        self.assertIs(result.run_headless.call_args.kwargs["instance_lock"], result.lock)
        result.dialog.assert_not_called()

    def test_window_attaches_to_a_running_headless_service(self):
        result = self._run_main(acquired=False, saved_mode="gui", headless_running=True)
        result.ui_class.assert_called_once()
        result.notify.assert_not_called()
        # The controller window does not own the lock; it has to take it later.
        self.assertIs(result.ui_class.call_args.kwargs["holds_instance_lock"], False)

    def test_headless_launch_while_the_window_runs_brings_the_window_forward(self):
        result = self._run_main(acquired=False, saved_mode="headless")
        result.run_headless.assert_not_called()
        result.notify.assert_called_once()


class SingleInstanceSignalTests(unittest.TestCase):
    """Ephemeral ports only: the real instance port belongs to the installed app."""

    def _start_server(self, on_activate):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            port = probe.getsockname()[1]
        server = APP.SingleInstanceSignalServer(on_activate, host="127.0.0.1", port=port)
        self.assertTrue(server.start())
        self.addCleanup(server.stop)
        return port

    def test_an_idle_connection_does_not_stop_the_next_launch_from_activating(self):
        activated = threading.Event()
        port = self._start_server(activated.set)
        idle = socket.create_connection(("127.0.0.1", port), timeout=2.0)
        self.addCleanup(idle.close)
        self.assertTrue(APP.SingleInstanceSignalServer.notify_existing_instance(port=port, attempts=1))
        self.assertTrue(activated.wait(4.0), "the SHOW request waited behind a connection that never sent anything")

    def test_a_connection_that_does_not_ask_to_show_does_not_activate(self):
        activated = threading.Event()
        port = self._start_server(activated.set)
        with socket.create_connection(("127.0.0.1", port), timeout=2.0) as client:
            client.sendall(b"GET / HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        self.assertFalse(activated.wait(1.5))
        self.assertTrue(APP.SingleInstanceSignalServer.notify_existing_instance(port=port, attempts=1))
        self.assertTrue(activated.wait(4.0))


class UpdateLauncherRelaunchTests(unittest.TestCase):
    def _script(self, relaunch_args):
        return APP.build_update_launcher_script(relaunch_args)

    def test_relaunches_in_the_mode_the_app_was_running_in(self):
        script = self._script(("--nogui",))
        self.assertIn('start "" "%NISHIZUMI_UPDATE_APP%" --nogui', script)

    def test_refuses_unsafe_relaunch_arguments(self):
        for bad in ("--gui & calc", "/S", '"--gui"', "--GUI", "--gui\r\nexit"):
            with self.assertRaises(RuntimeError, msg=bad):
                self._script((bad,))


class _FakeNotifier:
    def __init__(self):
        self.calls = []

    def notify(self, title, message, on_click=None):
        self.calls.append(SimpleNamespace(title=title, message=message, on_click=on_click))
        return True


class HeadlessUpdateManagerTests(_TempStoreMixin, unittest.TestCase):
    def setUp(self):
        self.store = self.make_store()
        self.notifier = _FakeNotifier()
        self.shutdown = mock.Mock()
        self.release = _release()
        self.fetch = mock.Mock(side_effect=lambda: self.release)
        self.download = mock.Mock(return_value=Path(r"C:\updates\NishizumiPaints-Setup-99.0.0.exe"))
        self.installer_started = threading.Event()
        self.start_installer = mock.Mock(side_effect=lambda *a, **k: self.installer_started.set())
        self.unsupported_reason = ""
        self.install_failure = None
        self.open_url = mock.Mock()
        title_patch = mock.patch.object(APP, "set_console_title")
        self.set_console_title = title_patch.start()
        self.addCleanup(title_patch.stop)

    def save_settings(self, **values):
        config = APP.AppConfig()
        for key, value in values.items():
            setattr(config, key, value)
        self.store.save(config)

    def make_manager(self, **overrides):
        options = dict(
            notifier=self.notifier,
            fetch_release=self.fetch,
            download_installer=self.download,
            start_installer=self.start_installer,
            clean_workspace=mock.Mock(),
            unsupported_reason=lambda: self.unsupported_reason,
            open_url=self.open_url,
            install_failure=lambda _release: self.install_failure,
            first_check_delay=0.0,
            check_interval=3600.0,
            retry_delay=3600.0,
        )
        options.update(overrides)
        manager = APP.HeadlessUpdateManager(self.store, self.shutdown, **options)
        self.addCleanup(manager.stop)
        return manager

    def test_a_check_during_an_install_leaves_the_install_state_alone(self):
        self.save_settings(auto_install_updates=False)
        release_download = threading.Event()
        downloading = threading.Event()

        def slow_download(*_args, progress_cb=None, **_kwargs):
            downloading.set()
            release_download.wait(5.0)
            return Path(r"C:\updates\NishizumiPaints-Setup-99.0.0.exe")

        self.download.side_effect = slow_download
        manager = self.make_manager()
        self.addCleanup(release_download.set)
        self.assertTrue(manager.install_available_update()[0])
        self.assertTrue(downloading.wait(5.0))
        self.assertEqual(manager.status()["update_state"], "downloading")
        self.assertTrue(manager.check_now())
        self.assertEqual(manager.status()["update_state"], "downloading")
        release_download.set()
        self.assertTrue(self.installer_started.wait(5.0))

    def test_stopping_during_the_download_does_not_launch_the_installer(self):
        self.save_settings(auto_install_updates=False)
        manager = self.make_manager()
        finished = threading.Event()

        def download_then_stop(*_args, progress_cb=None, **_kwargs):
            manager._stop_event.set()
            return Path(r"C:\updates\NishizumiPaints-Setup-99.0.0.exe")

        self.download.side_effect = download_then_stop
        original_release = manager._release_install
        manager._release_install = lambda: (original_release(), finished.set())
        self.assertTrue(manager.install_available_update()[0])
        self.assertTrue(finished.wait(5.0))
        self.start_installer.assert_not_called()
        self.shutdown.assert_not_called()
        self.assertIn("stopping", manager.status()["update_message"])

    def test_a_version_whose_installer_just_failed_is_announced_instead_of_reinstalled(self):
        # The update script relaunches the old version after a failed install and
        # records the failure; the relaunched service must not install it again at once.
        self.save_settings(auto_install_updates=True)
        self.install_failure = "5"
        manager = self.make_manager()
        with self.assertLogs(level="WARNING") as logs:
            manager.check_now()
        self.download.assert_not_called()
        self.shutdown.assert_not_called()
        self.assertIn("exit code 5", "\n".join(logs.output))
        self.assertIn("Click here to install", self.notifier.calls[-1].message)

    def test_a_new_version_is_announced_once_with_a_notification(self):
        self.save_settings(auto_install_updates=False)
        manager = self.make_manager()
        with self.assertLogs(level="WARNING") as logs:
            self.assertTrue(manager.check_now())
        self.assertIn(NEWER_TAG, "\n".join(logs.output))
        self.assertEqual(len(self.notifier.calls), 1)
        self.assertIn(NEWER_TAG, self.notifier.calls[0].message)
        self.set_console_title.assert_called_once()
        status = manager.status()
        self.assertTrue(status["update_available"])
        self.assertEqual(status["latest_release_tag"], NEWER_TAG)
        self.assertEqual(status["update_state"], "available")
        self.download.assert_not_called()

        manager.check_now()
        self.assertEqual(len(self.notifier.calls), 1)
        manager.check_now(manual=True)
        self.assertEqual(len(self.notifier.calls), 2)

    def test_clicking_the_notification_installs_the_update(self):
        self.save_settings(auto_install_updates=False)
        manager = self.make_manager()
        manager.check_now()
        self.notifier.calls[0].on_click()
        self.assertTrue(self.installer_started.wait(5))
        self.assertEqual(self.start_installer.call_args.kwargs["relaunch_args"], ("--nogui",))
        self._wait_for(lambda: self.shutdown.called)

    def test_installs_by_itself_when_automatic_install_is_on(self):
        self.save_settings(auto_install_updates=True)
        manager = self.make_manager()
        self.assertTrue(manager.check_now())
        self.download.assert_called_once()
        self.start_installer.assert_called_once()
        self.assertEqual(self.start_installer.call_args.kwargs["relaunch_args"], ("--nogui",))
        self.shutdown.assert_called_once()
        self.assertEqual(manager.status()["update_state"], "installing")
        self.assertEqual(self.notifier.calls, [])

    def test_a_failed_automatic_install_is_reported_and_not_repeated(self):
        self.save_settings(auto_install_updates=True)
        self.download.side_effect = RuntimeError("digest mismatch")
        manager = self.make_manager()
        with self.assertLogs(level="ERROR"):
            manager.check_now()
        self.shutdown.assert_not_called()
        self.assertEqual(manager.status()["update_state"], "failed")
        self.assertIn("could not be installed", self.notifier.calls[-1].message)

        manager.check_now()
        self.download.assert_called_once()
        self.assertIn("Click here to install", self.notifier.calls[-1].message)

    def test_builds_that_cannot_install_point_to_the_download_page(self):
        self.save_settings(auto_install_updates=True)
        self.unsupported_reason = "Automatic installation is only available in the packaged .exe build."
        manager = self.make_manager()
        manager.check_now()
        self.download.assert_not_called()
        self.assertIn("download page", self.notifier.calls[0].message)
        self.notifier.calls[0].on_click()
        self.open_url.assert_called_once_with(self.release.html_url)
        self.assertEqual(manager.install_available_update(), (False, self.unsupported_reason))

    def test_up_to_date_is_quiet(self):
        self.release = _release(tag=f"v{APP.APP_VERSION}")
        manager = self.make_manager()
        self.assertTrue(manager.check_now())
        self.assertEqual(self.notifier.calls, [])
        self.assertFalse(manager.status()["update_available"])
        self.assertEqual(manager.status()["update_state"], "up_to_date")

    def test_a_failed_check_is_reported_as_failed(self):
        self.fetch.side_effect = RuntimeError("offline")
        manager = self.make_manager()
        with self.assertLogs(level="WARNING"):
            self.assertFalse(manager.check_now())
        self.assertEqual(manager.status()["update_state"], "failed")
        self.assertEqual(self.notifier.calls, [])

    def test_the_service_checks_on_its_own_after_starting(self):
        self.save_settings(check_updates_automatically=True, auto_install_updates=False)
        manager = self.make_manager(first_check_delay=0.05)
        manager.start()
        self._wait_for(lambda: self.notifier.calls)
        self.fetch.assert_called_once()

    def test_no_automatic_check_when_checks_are_off_but_a_request_still_checks(self):
        self.save_settings(check_updates_automatically=False)
        manager = self.make_manager(first_check_delay=0.0)
        manager.start()
        time.sleep(0.2)
        self.fetch.assert_not_called()
        manager.request_check()
        self._wait_for(lambda: self.fetch.called)

    def test_turning_checks_on_checks_right_away(self):
        self.save_settings(check_updates_automatically=False)
        manager = self.make_manager(first_check_delay=0.0)
        manager.start()
        time.sleep(0.2)
        self.fetch.assert_not_called()
        self.save_settings(check_updates_automatically=True)
        manager.config_changed()
        self._wait_for(lambda: self.fetch.called)

    def test_a_failed_check_is_retried_sooner(self):
        self.save_settings(check_updates_automatically=True)
        self.fetch.side_effect = [RuntimeError("offline"), self.release]
        manager = self.make_manager(first_check_delay=0.0, retry_delay=1.0, check_interval=3600.0)
        with self.assertLogs(level="WARNING"):
            manager.start()
            self._wait_for(lambda: self.fetch.call_count >= 2, timeout=5)

    def test_install_request_fetches_the_release_when_none_is_known(self):
        manager = self.make_manager()
        started, _message = manager.install_available_update()
        self.assertTrue(started)
        self.assertTrue(self.installer_started.wait(5))
        self.fetch.assert_called_once()

    def test_only_one_install_runs_at_a_time(self):
        release_download = threading.Event()
        self.download.side_effect = lambda *a, **k: (release_download.wait(5), Path(r"C:\updates\setup.exe"))[1]
        manager = self.make_manager()
        manager.check_now()
        self.assertTrue(manager.install_available_update()[0])
        started, message = manager.install_available_update()
        self.assertFalse(started)
        self.assertIn("already in progress", message)
        release_download.set()
        self.assertTrue(self.installer_started.wait(5))

    def _wait_for(self, condition, timeout=3.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if condition():
                return
            time.sleep(0.02)
        self.fail("condition was not met in time")


class _FakeService:
    def get_runtime_snapshot(self):
        return SimpleNamespace(current_session=None, session_rows=[], replay_mode_active=False)

    def get_ui_preview_status(self):
        return SimpleNamespace(state="ready", message="", member_id=0, car_directories=0)

    def is_running(self):
        return True

    def get_status(self):
        return "Watching"

    def update_config(self, config):
        self.config = config


class HeadlessControlUpdateCommandTests(_TempStoreMixin, unittest.TestCase):
    def setUp(self):
        self.store = self.make_store()
        self.manager = mock.Mock()
        self.manager.status.return_value = {"update_state": "available", "latest_release_tag": NEWER_TAG, "update_available": True}
        self.manager.install_available_update.return_value = (True, "started")
        self.server = APP.HeadlessControlServer(_FakeService(), self.store, mock.Mock(), update_manager=self.manager)

    def test_status_reports_the_update_state(self):
        response = self.server._handle_command({"command": "status"})
        self.assertTrue(response["ok"])
        self.assertEqual(response["latest_release_tag"], NEWER_TAG)
        self.assertTrue(response["update_available"])

    def test_check_and_install_commands(self):
        self.assertTrue(self.server._handle_command({"command": "check_updates"})["ok"])
        self.manager.request_check.assert_called_once()
        response = self.server._handle_command({"command": "install_update"})
        self.assertTrue(response["started"])
        self.manager.install_available_update.return_value = (False, "busy")
        response = self.server._handle_command({"command": "install_update"})
        self.assertFalse(response["ok"])
        self.assertEqual(response["error"], "busy")

    def test_reloading_settings_wakes_the_update_checks(self):
        self.server._handle_command({"command": "reload_config"})
        self.manager.config_changed.assert_called_once()


class ControllerWindowUpdateTests(unittest.TestCase):
    def _controller(self, status):
        ui = mock.MagicMock()
        ui._headless_controller_mode = True
        ui._last_headless_status_response = status
        ui._headless_service_handles_updates = lambda: APP.DownloaderUI._headless_service_handles_updates(ui)
        return ui

    def test_the_window_leaves_automatic_installs_to_the_headless_service(self):
        ui = self._controller({"ok": True, "update_state": "idle"})
        ui.auto_install_updates_var.get.return_value = True
        ui._update_install_in_progress = False
        ui._exiting = False
        self.assertFalse(APP.DownloaderUI._should_auto_install(ui, _release()))

    def test_install_from_the_window_is_handed_to_the_headless_service(self):
        ui = self._controller({"ok": True, "update_state": "available"})
        ui._update_install_in_progress = False
        release = _release()
        APP.DownloaderUI.start_update_install(ui, release, manual=True)
        ui._hand_update_install_to_headless.assert_called_once_with(release)
        self.assertFalse(ui._update_install_in_progress)

        with mock.patch.object(APP, "send_headless_control_command", return_value={"ok": True, "started": True}) as send:
            APP.DownloaderUI._hand_update_install_to_headless(ui, release)
        send.assert_called_once_with("install_update")
        ui.request_exit_for_update.assert_called_once()

    def test_a_refused_hand_off_keeps_the_window_open(self):
        ui = self._controller({"ok": True, "update_state": "available"})
        with mock.patch.object(APP, "send_headless_control_command", return_value={"ok": False, "error": "busy"}):
            APP.DownloaderUI._hand_update_install_to_headless(ui, _release())
        ui.request_exit_for_update.assert_not_called()
        ui.messagebox.showerror.assert_called_once()

    def test_an_embedded_window_still_installs_by_itself(self):
        ui = mock.MagicMock()
        ui._headless_controller_mode = False
        ui._update_install_in_progress = False
        ui._headless_service_handles_updates = lambda: APP.DownloaderUI._headless_service_handles_updates(ui)
        with mock.patch.object(APP.threading, "Thread") as thread_class:
            APP.DownloaderUI.start_update_install(ui, _release(), manual=True)
        ui._hand_update_install_to_headless.assert_not_called()
        thread_class.return_value.start.assert_called_once()

    def test_the_window_closes_when_the_headless_service_leaves_to_install(self):
        ui = self._controller({"ok": True, "update_state": "downloading"})
        with mock.patch.object(APP, "send_headless_control_command", return_value=None):
            APP.DownloaderUI._poll_service(ui)
        ui.request_exit_for_update.assert_called_once()
        ui.service.start.assert_not_called()

    def test_losing_an_idle_headless_service_still_falls_back_to_the_window(self):
        ui = self._controller({"ok": True, "update_state": "idle"})
        ui._exiting = False
        ui.service.is_running.return_value = False
        with mock.patch.object(APP, "send_headless_control_command", return_value=None):
            APP.DownloaderUI._poll_service(ui)
        ui.request_exit_for_update.assert_not_called()
        ui.service.start.assert_called()

    def test_a_window_that_cannot_take_the_lock_does_not_start_a_second_downloader(self):
        # The headless console closed and another full copy of the app took over:
        # starting the embedded service here would run two downloaders at once.
        ui = self._controller({"ok": True, "update_state": "idle"})
        ui._exiting = False
        ui._holds_instance_lock = False
        ui._instance_blocked_logged = False
        ui.service.is_running.return_value = False
        ui._claim_single_instance = lambda: APP.DownloaderUI._claim_single_instance(ui)
        ui._attach_to_existing_headless_if_available.return_value = False
        with mock.patch.object(APP, "send_headless_control_command", return_value=None), \
             mock.patch.object(APP, "SingleInstanceLock", return_value=_FakeLock(False)):
            APP.DownloaderUI._poll_service(ui)
        ui.service.start.assert_not_called()

    def test_taking_over_from_a_lost_headless_service_takes_the_lock_first(self):
        ui = self._controller({"ok": True, "update_state": "idle"})
        ui._exiting = False
        ui._holds_instance_lock = False
        ui.service.is_running.return_value = False
        ui._claim_single_instance = lambda: APP.DownloaderUI._claim_single_instance(ui)
        lock = _FakeLock(True)
        with mock.patch.object(APP, "send_headless_control_command", return_value=None), \
             mock.patch.object(APP, "SingleInstanceLock", return_value=lock):
            APP.DownloaderUI._poll_service(ui)
        self.assertIs(ui._owned_instance_lock, lock)
        ui.instance_signal_server.start.assert_called()
        ui.service.update_config.assert_called()
        ui.service.start.assert_called()

    def test_the_controller_panel_follows_the_current_session(self):
        ui = self._controller({"ok": True, "update_state": "idle", "latest_release_tag": "v1", "current_session": "A"})
        status = {"ok": True, "update_state": "idle", "latest_release_tag": "v1", "current_session": "B"}
        with mock.patch.object(APP, "send_headless_control_command", return_value=status):
            APP.DownloaderUI._poll_service(ui)
        ui._update_headless_ui.assert_called_with(status)

    def test_a_failed_automatic_download_offers_the_update_again(self):
        ui = mock.MagicMock()
        ui._exiting = False
        release = _release()
        APP.DownloaderUI._finish_update_install(ui, release, None, "network down", manual=False)
        ui._prompt_for_update.assert_called_once_with(release)


class ConsoleCloseHandlerTests(unittest.TestCase):
    class _Kernel32:
        def __init__(self):
            self.callback = None

        def SetConsoleCtrlHandler(self, callback, add):
            self.callback = callback
            return 1

    def test_closing_the_console_runs_the_shutdown(self):
        kernel32 = self._Kernel32()
        closed = mock.Mock()
        handler = APP.install_console_close_handler(closed, kernel32=kernel32)
        self.assertIsNotNone(handler)
        for event in (2, 5, 6):  # close, logoff, shutdown
            self.assertTrue(kernel32.callback(event))
        self.assertEqual(closed.call_count, 3)

    def test_ctrl_c_is_left_to_python(self):
        kernel32 = self._Kernel32()
        closed = mock.Mock()
        APP.install_console_close_handler(closed, kernel32=kernel32)
        self.assertFalse(kernel32.callback(0))
        self.assertFalse(kernel32.callback(1))
        closed.assert_not_called()


if __name__ == "__main__":
    unittest.main()
