import importlib.util
import logging
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

import yaml


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_robustness_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


class LogTrimmingTests(unittest.TestCase):
    def test_old_records_and_continuation_lines_are_dropped(self):
        now = time.time()
        old = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 40 * 86400))
        recent = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now - 60))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "app.log"
            path.write_text(
                f"{old} ERROR old failure\nTraceback (most recent call last):\n  old.py\n"
                f"{recent} INFO still here\n",
                encoding="utf-8",
            )
            APP.trim_log_file(path, max_bytes=1024 * 1024, max_age_days=31, now=now)
            text = path.read_text(encoding="utf-8")
        self.assertNotIn("old failure", text)
        self.assertNotIn("old.py", text)
        self.assertIn("still here", text)

    def test_the_file_is_capped_at_the_newest_bytes(self):
        now = time.time()
        stamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "app.log"
            path.write_text(
                "".join(f"{stamp} INFO line {index:02d} {'x' * 40}\n" for index in range(20)),
                encoding="utf-8",
            )
            APP.trim_log_file(path, max_bytes=300, max_age_days=31, now=now)
            text = path.read_text(encoding="utf-8")
        self.assertLessEqual(len(text.encode("utf-8")), 300)
        self.assertIn("line 19", text)


class ExceptionHookTests(unittest.TestCase):
    def test_the_excepthook_writes_a_traceback(self):
        old_sys_hook = sys.excepthook
        old_thread_hook = threading.excepthook
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "hook.log"
            handler = logging.FileHandler(path, encoding="utf-8")
            handler.setFormatter(logging.Formatter("%(levelname)s %(message)s"))
            root = logging.getLogger()
            root.addHandler(handler)
            try:
                APP.install_exception_hooks()
                try:
                    raise RuntimeError("hook boom")
                except RuntimeError:
                    sys.excepthook(*sys.exc_info())
                handler.flush()
            finally:
                root.removeHandler(handler)
                handler.close()
                sys.excepthook = old_sys_hook
                threading.excepthook = old_thread_hook
            text = path.read_text(encoding="utf-8")
        self.assertIn("CRITICAL", text)
        self.assertIn("Traceback (most recent call last)", text)
        self.assertIn("RuntimeError: hook boom", text)


class SettingsRoundTripTests(unittest.TestCase):
    def _store(self, directory: Path):
        store = APP.ConfigStore.__new__(APP.ConfigStore)
        store.path = directory / "settings.json"
        return store

    def test_the_dont_ask_flag_round_trips_and_old_files_use_the_default(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            store = self._store(directory)
            store.path.write_text('{"ui_mode": "advanced"}', encoding="utf-8")
            self.assertFalse(store.load().trading_paints_warning_dont_ask)

            config = APP.AppConfig()
            config.trading_paints_warning_dont_ask = True
            store.save(config)
            self.assertTrue(store.load().trading_paints_warning_dont_ask)


class TradingPaintsCoexistenceTests(unittest.TestCase):
    def test_the_decision_uses_the_injected_process_list(self):
        self.assertTrue(APP.should_warn_about_trading_paints(["chrome.exe", "Trading Paints.exe"]))
        self.assertFalse(APP.should_warn_about_trading_paints(["chrome.exe"]))
        self.assertFalse(APP.should_warn_about_trading_paints([]))
        self.assertFalse(APP.should_warn_about_trading_paints(["trading paints.exe"], dont_ask_again=True))

    def test_process_names_are_matched_without_case_or_quotes(self):
        self.assertIsNotNone(APP.find_named_process(['"TRADING PAINTS.EXE"'], "Trading Paints.exe"))
        self.assertIsNone(APP.find_named_process(["TradingPaints.exe"], "Trading Paints.exe"))

    def test_iracing_process_detection(self):
        self.assertTrue(APP.iracing_is_running(["iRacingSim64DX11.exe"]))
        self.assertFalse(APP.iracing_is_running(["notepad.exe"]))


class IracingAppIniTests(unittest.TestCase):
    def _write_ini(self, directory: Path, value: str) -> Path:
        path = directory / "app.ini"
        path.write_text(f"[Graphics]\nhideCarNum=0\n\n[Misc]\nirsdkEnableMem={value}\n", encoding="utf-8")
        return path

    def test_the_setting_is_read_from_the_misc_section(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            self._write_ini(directory, "0")
            self.assertFalse(APP.read_iracing_sdk_memory_enabled(directory))
            self._write_ini(directory, "1")
            self.assertTrue(APP.read_iracing_sdk_memory_enabled(directory))

    def test_the_fix_refuses_while_iracing_is_running(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            path = self._write_ini(directory, "0")
            original = path.read_text(encoding="utf-8")
            changed, message = APP.fix_iracing_sdk_memory_setting(directory, iracing_running=True)
            self.assertFalse(changed)
            self.assertIn("Close iRacing", message)
            self.assertEqual(path.read_text(encoding="utf-8"), original)
            self.assertFalse((directory / "app.ini.bak").exists())

    def test_the_fix_backs_up_then_enables_memory(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            path = self._write_ini(directory, "0")
            changed, _message = APP.fix_iracing_sdk_memory_setting(directory, iracing_running=False)
            self.assertTrue(changed)
            self.assertIn("irsdkEnableMem=1", path.read_text(encoding="utf-8"))
            backup = directory / "app.ini.bak"
            self.assertTrue(backup.exists())
            self.assertIn("irsdkEnableMem=0", backup.read_text(encoding="utf-8"))


class SessionYamlCleanupTests(unittest.TestCase):
    BAD_YAML = """SessionInfo:
  Sessions:
  - SessionNum: 0
    SessionType: Race
  DriverInfo:
    Drivers:
    - UserName: 山田:太郎
      TeamName: 田中 #1
      AbbrevName: *Star
      Initials: !AB
      CarDesignStr:
      HelmetDesignStr:
      SuitDesignStr:
      CarNumberDesignStr:
"""

    def test_known_bad_values_become_parseable_yaml(self):
        cleaned = APP.clean_session_yaml(self.BAD_YAML)
        parsed = yaml.safe_load(cleaned)
        driver = parsed["SessionInfo"]["DriverInfo"]["Drivers"][0]
        self.assertEqual(driver["UserName"], "山田:太郎")
        self.assertEqual(driver["TeamName"], "田中 #1")
        self.assertEqual(driver["AbbrevName"], "*Star")
        self.assertEqual(driver["Initials"], "!AB")
        self.assertEqual(driver["CarDesignStr"], "")
        self.assertEqual(driver["HelmetDesignStr"], "")
        self.assertEqual(driver["SuitDesignStr"], "")
        self.assertEqual(driver["CarNumberDesignStr"], "")

    def test_a_clean_value_is_left_alone(self):
        text = "SessionInfo:\n  DriverInfo:\n    Drivers:\n    - UserName: Jose Alonso\n"
        self.assertEqual(APP.clean_session_yaml(text), text)

    def test_the_recovery_returns_the_session_info_mapping(self):
        recovered = APP.recover_session_info_yaml(self.BAD_YAML)
        self.assertIsInstance(recovered, dict)
        self.assertIn("DriverInfo", recovered)

    def test_the_raw_yaml_is_dumped_once_per_session_and_old_dumps_are_purged(self):
        now = time.time()
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            dumped = set()
            first = APP.dump_failed_session_yaml("bad: yaml", 123, dump_dir=directory, dumped_session_ids=dumped, now=now)
            second = APP.dump_failed_session_yaml("bad: yaml", 123, dump_dir=directory, dumped_session_ids=dumped, now=now)
            self.assertIsNotNone(first)
            self.assertIsNone(second)
            self.assertEqual(len(list(directory.glob("*.yaml"))), 1)
            old = directory / "old.yaml"
            old.write_text("old", encoding="utf-8")
            os.utime(old, (now - 31 * 86400, now - 31 * 86400))
            removed = APP.purge_yaml_dumps(directory, now=now)
            self.assertEqual(removed, 1)
            self.assertFalse(old.exists())


class SessionYamlSdkRecoveryTests(unittest.TestCase):
    class _BadYamlSdk:
        is_initialized = True
        is_connected = True
        is_session_info_utf8 = True

        def __init__(self, raw_yaml):
            self.raw_yaml = raw_yaml

        def freeze_var_buffer_latest(self):
            return None

        def _get_session_info_binary(self, key):
            return self.raw_yaml.encode("utf-8")

        def __getitem__(self, key):
            if key == "WeekendInfo":
                return {"SessionID": 456, "SubSessionID": 789, "TrackName": "Test Track"}
            if key == "DriverInfo":
                return {"Drivers": []}
            if key == "SessionInfo":
                raise ValueError("invalid YAML")
            raise KeyError(key)

    def test_the_sdk_reader_retries_with_the_cleaned_yaml(self):
        raw = SessionYamlCleanupTests.BAD_YAML.replace("SessionInfo:\n", "SessionInfo:\n", 1)
        reader = APP.IracingSdkReader(sdk=self._BadYamlSdk(raw))
        state, session = APP.read_session_from_sdk(reader)
        self.assertEqual(state, APP.SdkPollState.SESSION)
        self.assertIsNotNone(session)
        self.assertEqual(session.session_id.main_session_id, 456)


class AiRosterSanityTests(unittest.TestCase):
    def test_duplicates_and_illegal_file_name_characters_are_reported(self):
        drivers = [
            {"driverName": "Alex: Smith", "carNumber": "5"},
            {"driverName": "Alex: Smith", "carNumber": "05"},
            {"driverName": "Jamie", "carNumber": "7"},
            {"driverName": "Taylor?", "carNumber": "8"},
        ]
        problems = APP.ai_roster_sanity_problems(drivers)
        joined = "\n".join(problems)
        self.assertIn("duplicate driver name", joined)
        self.assertIn("duplicate car number", joined)
        self.assertIn("characters Windows file names cannot hold", joined)
        self.assertEqual(len([line for line in problems if "duplicate driver name" in line]), 1)
        self.assertEqual(len([line for line in problems if "duplicate car number" in line]), 1)

    def test_a_clean_roster_has_no_problems(self):
        drivers = [
            {"driverName": "José Álvarez", "carNumber": "5"},
            {"driverName": "Jamie Lee", "carNumber": "7"},
        ]
        self.assertEqual(APP.ai_roster_sanity_problems(drivers), [])

    def test_file_name_sanitising_keeps_clean_names_identical(self):
        self.assertEqual(APP.sanitize_ai_roster_driver_name("José Álvarez"), "José Álvarez")
        self.assertEqual(APP.sanitize_ai_roster_driver_name("A:B|C?D"), "ABCD")
        self.assertEqual(
            APP._normalize_ai_match_text("José Álvarez"),
            APP._normalize_ai_match_text("José Álvarez"),
        )


if __name__ == "__main__":
    unittest.main()
