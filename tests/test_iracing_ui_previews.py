import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_ui_preview_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


MEMBER_ID = 654321
OTHER_MEMBER_ID = 111222


def _car_item(directory, paint_type, url, user_id=MEMBER_ID, is_team_paint=False, superspeedway=False):
    return APP.DownloadFile(
        download_id=APP.DownloadId(
            user_id=user_id,
            directory=directory,
            paint_type=paint_type,
            is_team_paint=is_team_paint,
            is_superspeedway_variant=superspeedway,
        ),
        url=url,
    )


class IracingUiPreviewManifestSelectionTests(unittest.TestCase):
    def test_only_the_local_drivers_personal_assets_are_previewed(self):
        items = [
            _car_item("ferrari296gt3", APP.PaintType.CAR, "https://example.test/1700000000.tga"),
            _car_item("ferrari296gt3", APP.PaintType.CAR, "https://example.test/1600000000.tga", user_id=OTHER_MEMBER_ID),
            _car_item("ferrari296gt3", APP.PaintType.CAR, "https://example.test/1650000000.tga", user_id=999, is_team_paint=True),
        ]
        selected = APP.iracing_ui_preview_manifest_items(items, MEMBER_ID)
        self.assertEqual([item.url for item in selected], ["https://example.test/1700000000.tga"])

    def test_superspeedway_variants_are_never_used_for_the_ui_viewer(self):
        items = [
            _car_item("stockcars2 chevyc8rvi", APP.PaintType.CAR, "https://example.test/1700000000.tga"),
            _car_item("stockcars2 chevyc8rvi", APP.PaintType.CAR, "https://example.test/1800000000_ss.tga", superspeedway=True),
        ]
        selected = APP.iracing_ui_preview_manifest_items(items, MEMBER_ID)
        self.assertEqual([item.url for item in selected], ["https://example.test/1700000000.tga"])

    def test_the_freshest_asset_of_each_type_wins(self):
        items = [
            _car_item("mx5 mx52016", APP.PaintType.CAR, "https://example.test/1500000000.tga"),
            _car_item("mx5 mx52016", APP.PaintType.CAR, "https://example.test/1900000000.tga"),
            _car_item("mx5 mx52016", APP.PaintType.CAR_NUMBER, "https://example.test/1900000001.tga"),
        ]
        selected = APP.iracing_ui_preview_manifest_items(items, MEMBER_ID)
        self.assertEqual(
            {item.download_id.paint_type: item.url for item in selected},
            {
                APP.PaintType.CAR: "https://example.test/1900000000.tga",
                APP.PaintType.CAR_NUMBER: "https://example.test/1900000001.tga",
            },
        )

    def test_helmet_and_suit_assets_are_included(self):
        items = [
            _car_item("", APP.PaintType.HELMET, "https://example.test/helmet_1700000000.tga"),
            _car_item("", APP.PaintType.SUIT, "https://example.test/suit_1700000000.tga"),
        ]
        selected = APP.iracing_ui_preview_manifest_items(items, MEMBER_ID)
        self.assertEqual(
            {item.download_id.paint_type for item in selected},
            {APP.PaintType.HELMET, APP.PaintType.SUIT},
        )

    def test_an_unknown_member_id_selects_nothing(self):
        items = [_car_item("ferrari296gt3", APP.PaintType.CAR, "https://example.test/1700000000.tga")]
        self.assertEqual(APP.iracing_ui_preview_manifest_items(items, 0), [])


class IracingUiPreviewMemberIdTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="nishizumi-ui-preview-id-"))
        self.state_path = self.temp_dir / "state.json"
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self._original_read_login = APP.read_tp_login_status
        APP.read_tp_login_status = lambda *_args, **_kwargs: {"ok": False, "member_id": 0}
        self.addCleanup(setattr, APP, "read_tp_login_status", self._original_read_login)

    def test_a_manual_customer_id_beats_every_automatic_source(self):
        config = APP.AppConfig(iracing_ui_preview_member_id=MEMBER_ID, tp_manifest_member_id_override=OTHER_MEMBER_ID)
        member_id, source = APP.resolve_iracing_ui_preview_member_id(config, live_member_id=OTHER_MEMBER_ID)
        self.assertEqual(member_id, MEMBER_ID)
        self.assertEqual(source, "manual")

    def test_a_live_session_id_is_preferred_over_stored_overrides(self):
        config = APP.AppConfig(tp_manifest_member_id_override=OTHER_MEMBER_ID)
        member_id, source = APP.resolve_iracing_ui_preview_member_id(config, live_member_id=MEMBER_ID)
        self.assertEqual(member_id, MEMBER_ID)
        self.assertEqual(source, "iRacing session")

    def test_the_trading_paints_login_id_is_used_when_nothing_else_is_known(self):
        APP.read_tp_login_status = lambda *_args, **_kwargs: {"ok": True, "member_id": MEMBER_ID}
        member_id, source = APP.resolve_iracing_ui_preview_member_id(APP.AppConfig(), live_member_id=0)
        self.assertEqual(member_id, MEMBER_ID)
        self.assertEqual(source, "Trading Paints login")

    def test_the_previous_run_id_keeps_previews_working_before_iracing_starts(self):
        APP.remember_iracing_ui_preview_member_id(MEMBER_ID, "iRacing session", self.state_path)
        member_id, source = APP.resolve_iracing_ui_preview_member_id(
            APP.AppConfig(),
            live_member_id=0,
            state_path=self.state_path,
        )
        self.assertEqual(member_id, MEMBER_ID)
        self.assertEqual(source, "saved from a previous run")

    def test_no_known_source_reports_no_customer_id(self):
        member_id, source = APP.resolve_iracing_ui_preview_member_id(
            APP.AppConfig(),
            live_member_id=0,
            state_path=self.state_path,
        )
        self.assertEqual(member_id, 0)
        self.assertEqual(source, "")


class IracingHideCarNumbersTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="nishizumi-ui-preview-ini-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, True)

    def _write_ini(self, text):
        (self.temp_dir / APP.IRACING_APP_INI_FILENAME).write_text(text, encoding="utf-8")

    def test_hide_car_numbers_is_read_from_the_graphics_section(self):
        self._write_ini("[Graphics]\nhideCarNum=1\t; Hide car numbers\n")
        self.assertIs(APP.read_iracing_hide_car_numbers(self.temp_dir), True)

    def test_disabled_hide_car_numbers_is_reported(self):
        self._write_ini("[Graphics]\nhideCarNum=0\n")
        self.assertIs(APP.read_iracing_hide_car_numbers(self.temp_dir), False)

    def test_the_key_is_ignored_outside_the_graphics_section(self):
        self._write_ini("[Force Feedback]\nhideCarNum=1\n")
        self.assertIsNone(APP.read_iracing_hide_car_numbers(self.temp_dir))

    def test_a_missing_app_ini_is_reported_as_unknown(self):
        self.assertIsNone(APP.read_iracing_hide_car_numbers(self.temp_dir))


class IracingUiPreviewInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="nishizumi-ui-preview-install-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.paints_dir = self.temp_dir / "paint"
        self.cache_dir = self.temp_dir / "cache"
        self.state_path = self.temp_dir / "state.json"
        self.paints_dir.mkdir(parents=True, exist_ok=True)
        cache_root = self.cache_dir / str(MEMBER_ID)
        (cache_root / "ferrari296gt3").mkdir(parents=True, exist_ok=True)
        (cache_root / f"ferrari296gt3/car_{MEMBER_ID}.tga").write_bytes(b"my-car-paint")
        (cache_root / f"helmet_{MEMBER_ID}.tga").write_bytes(b"my-helmet")
        APP.save_iracing_ui_preview_state(
            {
                "member_id": MEMBER_ID,
                "member_id_source": "test",
                "entries": {
                    f"ferrari296gt3\\car_{MEMBER_ID}.tga": {
                        "url": "https://example.test/car.tga",
                        "cache": f"ferrari296gt3\\car_{MEMBER_ID}.tga",
                    },
                    f"helmet_{MEMBER_ID}.tga": {
                        "url": "https://example.test/helmet.tga",
                        "cache": f"helmet_{MEMBER_ID}.tga",
                    },
                },
            },
            self.state_path,
        )

    def _install(self):
        return APP.install_iracing_ui_car_previews(
            member_id=MEMBER_ID,
            paints_dir=self.paints_dir,
            cache_dir=self.cache_dir,
            state_path=self.state_path,
        )

    def test_previews_are_written_into_the_iracing_paint_folder(self):
        installed, present = self._install()
        self.assertEqual((installed, present), (2, 2))
        self.assertEqual((self.paints_dir / "ferrari296gt3" / f"car_{MEMBER_ID}.tga").read_bytes(), b"my-car-paint")
        self.assertEqual((self.paints_dir / f"helmet_{MEMBER_ID}.tga").read_bytes(), b"my-helmet")

    def test_a_second_pass_does_not_rewrite_untouched_files(self):
        self._install()
        self.assertEqual(self._install(), (0, 2))

    def test_a_deleted_preview_is_restored(self):
        self._install()
        (self.paints_dir / "ferrari296gt3" / f"car_{MEMBER_ID}.tga").unlink()
        installed, present = self._install()
        self.assertEqual((installed, present), (1, 2))
        self.assertEqual((self.paints_dir / "ferrari296gt3" / f"car_{MEMBER_ID}.tga").read_bytes(), b"my-car-paint")

    def test_a_paint_replaced_by_the_session_pipeline_is_restored(self):
        self._install()
        (self.paints_dir / "ferrari296gt3" / f"car_{MEMBER_ID}.tga").write_bytes(b"session-paint")
        self._install()
        self.assertEqual((self.paints_dir / "ferrari296gt3" / f"car_{MEMBER_ID}.tga").read_bytes(), b"my-car-paint")

    def test_installed_previews_are_published_as_protected_paths(self):
        self._install()
        protected = APP.iracing_ui_preview_protected_paths()
        self.assertIn(str(self.paints_dir / "ferrari296gt3" / f"car_{MEMBER_ID}.tga").lower(), protected)

    def test_a_different_customer_id_installs_nothing(self):
        self.assertEqual(
            APP.install_iracing_ui_car_previews(
                member_id=OTHER_MEMBER_ID,
                paints_dir=self.paints_dir,
                cache_dir=self.cache_dir,
                state_path=self.state_path,
            ),
            (0, 0),
        )

    def test_turning_previews_off_removes_only_the_files_the_app_installed(self):
        self._install()
        foreign = self.paints_dir / "ferrari296gt3" / f"car_{OTHER_MEMBER_ID}.tga"
        foreign.write_bytes(b"another-driver")
        (self.paints_dir / f"helmet_{MEMBER_ID}.tga").write_bytes(b"edited-by-hand")
        removed_installed, removed_cached = APP.clear_iracing_ui_car_previews(
            paints_dir=self.paints_dir,
            cache_dir=self.cache_dir,
            state_path=self.state_path,
            remove_cache=False,
        )
        self.assertEqual(removed_installed, 1)
        self.assertEqual(removed_cached, 0)
        self.assertFalse((self.paints_dir / "ferrari296gt3" / f"car_{MEMBER_ID}.tga").exists())
        self.assertTrue(foreign.exists())
        self.assertTrue((self.paints_dir / f"helmet_{MEMBER_ID}.tga").exists())


class IracingUiPreviewCleanupProtectionTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="nishizumi-ui-preview-cleanup-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, True)

    def test_protected_preview_files_survive_session_cleanup(self):
        paints_dir = self.temp_dir / "paint"
        (paints_dir / "ferrari296gt3").mkdir(parents=True, exist_ok=True)
        preview_path = paints_dir / "ferrari296gt3" / f"car_{MEMBER_ID}.tga"
        other_path = paints_dir / "ferrari296gt3" / f"car_{OTHER_MEMBER_ID}.tga"
        preview_path.write_bytes(b"my-car-paint")
        other_path.write_bytes(b"another-driver")
        saved = [
            APP.SavedFile(
                session_id=APP.SessionId(1, 1),
                download_id=APP.DownloadId(user_id=MEMBER_ID, directory="ferrari296gt3", paint_type=APP.PaintType.CAR),
                file_path=preview_path,
            ),
            APP.SavedFile(
                session_id=APP.SessionId(1, 1),
                download_id=APP.DownloadId(user_id=OTHER_MEMBER_ID, directory="ferrari296gt3", paint_type=APP.PaintType.CAR),
                file_path=other_path,
            ),
        ]
        kept = APP.delete_saved(
            saved,
            keep_targets=set(),
            paints_root=paints_dir,
            protected_paths={str(preview_path).lower()},
        )
        self.assertEqual([item.file_path for item in kept], [preview_path])
        self.assertTrue(preview_path.exists())
        self.assertFalse(other_path.exists())


class IracingUiPreviewSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="nishizumi-ui-preview-sync-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.paints_dir = self.temp_dir / "paint"
        self.cache_dir = self.temp_dir / "cache"
        self.state_path = self.temp_dir / "state.json"
        self.download_dir = self.temp_dir / "downloads"
        self.download_dir.mkdir(parents=True, exist_ok=True)
        self.manifest = []
        self.downloaded_urls = []
        self._original_fetch = APP.fetch_user_files
        self._original_download = APP.download_file
        APP.fetch_user_files = lambda *_args, **_kwargs: list(self.manifest)
        APP.download_file = self._fake_download_file
        self.addCleanup(setattr, APP, "fetch_user_files", self._original_fetch)
        self.addCleanup(setattr, APP, "download_file", self._original_download)

    def _fake_download_file(self, session_id, temp_root, item, *_args, **_kwargs):
        self.downloaded_urls.append(item.url)
        payload = f"payload::{item.url}".encode("utf-8")
        temp_file = self.download_dir / f"{len(self.downloaded_urls)}_{item.download_id.paint_type.value}.tga"
        temp_file.write_bytes(payload)
        return APP.DownloadedFile(session_id=session_id, download_id=item.download_id, file_path=temp_file)

    def _sync(self, force=False):
        return APP.sync_iracing_ui_car_previews(
            member_id=MEMBER_ID,
            member_id_source="test",
            paints_dir=self.paints_dir,
            cache_dir=self.cache_dir,
            state_path=self.state_path,
            retries=1,
            retry_backoff_seconds=0.1,
            force=force,
        )

    def test_a_first_sync_installs_the_paints_the_iracing_ui_reads(self):
        self.manifest = [
            _car_item("ferrari296gt3", APP.PaintType.CAR, "https://example.test/1700000000.tga"),
            _car_item("", APP.PaintType.HELMET, "https://example.test/1700000001.tga"),
        ]
        result = self._sync()
        self.assertTrue(result.ok)
        self.assertEqual(result.manifest_items, 2)
        self.assertEqual(result.car_directories, 1)
        car_path = self.paints_dir / "ferrari296gt3" / f"car_{MEMBER_ID}.tga"
        self.assertEqual(car_path.read_bytes(), b"payload::https://example.test/1700000000.tga")
        self.assertTrue((self.paints_dir / f"helmet_{MEMBER_ID}.tga").exists())

    def test_unchanged_manifest_urls_are_not_downloaded_again(self):
        self.manifest = [_car_item("ferrari296gt3", APP.PaintType.CAR, "https://example.test/1700000000.tga")]
        self._sync()
        self.downloaded_urls.clear()
        result = self._sync()
        self.assertTrue(result.ok)
        self.assertEqual(self.downloaded_urls, [])
        self.assertEqual(result.downloaded, 0)

    def test_a_new_manifest_url_replaces_the_installed_preview(self):
        self.manifest = [_car_item("ferrari296gt3", APP.PaintType.CAR, "https://example.test/1700000000.tga")]
        self._sync()
        self.manifest = [_car_item("ferrari296gt3", APP.PaintType.CAR, "https://example.test/1800000000.tga")]
        self._sync()
        car_path = self.paints_dir / "ferrari296gt3" / f"car_{MEMBER_ID}.tga"
        self.assertEqual(car_path.read_bytes(), b"payload::https://example.test/1800000000.tga")

    def test_a_paint_removed_from_trading_paints_stops_being_previewed(self):
        self.manifest = [
            _car_item("ferrari296gt3", APP.PaintType.CAR, "https://example.test/1700000000.tga"),
            _car_item("mx5 mx52016", APP.PaintType.CAR, "https://example.test/1700000002.tga"),
        ]
        self._sync()
        dropped = self.paints_dir / "mx5 mx52016" / f"car_{MEMBER_ID}.tga"
        self.assertTrue(dropped.exists())
        self.manifest = [_car_item("ferrari296gt3", APP.PaintType.CAR, "https://example.test/1700000000.tga")]
        result = self._sync()
        self.assertEqual(result.removed, 1)
        self.assertFalse(dropped.exists())
        self.assertTrue((self.paints_dir / "ferrari296gt3" / f"car_{MEMBER_ID}.tga").exists())

    def test_an_empty_manifest_is_reported_without_failing(self):
        self.manifest = []
        result = self._sync()
        self.assertTrue(result.ok)
        self.assertEqual(result.manifest_items, 0)
        self.assertIn("no personal paints", result.message)

    def test_a_manifest_failure_is_reported_as_an_error(self):
        def _raise(*_args, **_kwargs):
            raise RuntimeError("network down")

        APP.fetch_user_files = _raise
        result = self._sync()
        self.assertFalse(result.ok)
        self.assertIn("network down", result.message)

    def test_a_custom_number_paint_warns_when_hide_car_numbers_is_off(self):
        (self.temp_dir / APP.IRACING_APP_INI_FILENAME).write_text("[Graphics]\nhideCarNum=0\n", encoding="utf-8")
        self.manifest = [
            _car_item("ferrari296gt3", APP.PaintType.CAR, "https://example.test/1700000000.tga"),
            _car_item("ferrari296gt3", APP.PaintType.CAR_NUMBER, "https://example.test/1700000003.tga"),
        ]
        result = self._sync()
        self.assertTrue(result.ok)
        self.assertEqual(result.custom_number_cars, 1)
        self.assertIs(result.hide_car_numbers, False)
        self.assertTrue(any("Hide car numbers" in line for line in result.logs))

    def test_a_partially_downloaded_manifest_is_reported_as_incomplete(self):
        self.manifest = [
            _car_item("ferrari296gt3", APP.PaintType.CAR, "https://example.test/1700000000.tga"),
            _car_item("mx5 mx52016", APP.PaintType.CAR, "https://example.test/unavailable.tga"),
        ]
        original_download = APP.download_file

        def _download_with_one_failure(session_id, temp_root, item, *args, **kwargs):
            if item.url.endswith("unavailable.tga"):
                return None
            return original_download(session_id, temp_root, item, *args, **kwargs)

        APP.download_file = _download_with_one_failure
        result = self._sync()
        self.assertFalse(result.ok)
        self.assertEqual(result.manifest_items, 2)
        self.assertEqual(result.files_in_place, 1)
        self.assertIn("Only 1 of 2", result.message)
        self.assertTrue((self.paints_dir / "ferrari296gt3" / f"car_{MEMBER_ID}.tga").exists())

    def test_a_complete_sync_reports_every_file_in_place(self):
        self.manifest = [
            _car_item("ferrari296gt3", APP.PaintType.CAR, "https://example.test/1700000000.tga"),
            _car_item("ferrari296gt3", APP.PaintType.CAR_SPEC, "https://example.test/1700000004.mip"),
        ]
        result = self._sync()
        self.assertTrue(result.ok)
        self.assertEqual(result.files_in_place, 2)
        self.assertTrue((self.paints_dir / "ferrari296gt3" / f"car_spec_{MEMBER_ID}.mip").exists())

    def test_switching_customer_id_rebuilds_the_previews(self):
        self.manifest = [_car_item("ferrari296gt3", APP.PaintType.CAR, "https://example.test/1700000000.tga")]
        self._sync()
        old_path = self.paints_dir / "ferrari296gt3" / f"car_{MEMBER_ID}.tga"
        self.assertTrue(old_path.exists())
        self.manifest = [
            _car_item("ferrari296gt3", APP.PaintType.CAR, "https://example.test/1700000005.tga", user_id=OTHER_MEMBER_ID)
        ]
        result = APP.sync_iracing_ui_car_previews(
            member_id=OTHER_MEMBER_ID,
            paints_dir=self.paints_dir,
            cache_dir=self.cache_dir,
            state_path=self.state_path,
            retries=1,
            retry_backoff_seconds=0.1,
        )
        self.assertTrue(result.ok)
        self.assertFalse(old_path.exists())
        self.assertTrue((self.paints_dir / "ferrari296gt3" / f"car_{OTHER_MEMBER_ID}.tga").exists())
        self.assertFalse((self.cache_dir / str(MEMBER_ID)).exists())

    def test_the_download_scratch_folder_is_cleaned_up(self):
        scratch = APP.default_temp_dir() / "UiPreviewDownloads"
        before = {child.name for child in scratch.iterdir()} if scratch.exists() else set()
        self.manifest = [_car_item("ferrari296gt3", APP.PaintType.CAR, "https://example.test/1700000000.tga")]
        self._sync()
        after = {child.name for child in scratch.iterdir()} if scratch.exists() else set()
        self.assertEqual(after - before, set())

    def test_an_unknown_customer_id_is_refused(self):
        result = APP.sync_iracing_ui_car_previews(
            member_id=0,
            paints_dir=self.paints_dir,
            cache_dir=self.cache_dir,
            state_path=self.state_path,
        )
        self.assertFalse(result.ok)
        self.assertIn("customer ID", result.message)


class IracingUiPreviewServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="nishizumi-ui-preview-service-"))
        self.addCleanup(shutil.rmtree, self.temp_dir, True)
        self.paints_dir = self.temp_dir / "paint"
        self.paints_dir.mkdir(parents=True, exist_ok=True)
        self.sync_calls = []
        self.install_calls = []
        self.clear_calls = []
        self._originals = {
            "sync_iracing_ui_car_previews": APP.sync_iracing_ui_car_previews,
            "install_iracing_ui_car_previews": APP.install_iracing_ui_car_previews,
            "clear_iracing_ui_car_previews": APP.clear_iracing_ui_car_previews,
            "remember_iracing_ui_preview_member_id": APP.remember_iracing_ui_preview_member_id,
            "resolve_iracing_ui_preview_member_id": APP.resolve_iracing_ui_preview_member_id,
        }
        for name, value in self._originals.items():
            self.addCleanup(setattr, APP, name, value)
        APP.sync_iracing_ui_car_previews = self._fake_sync
        APP.install_iracing_ui_car_previews = self._fake_install
        APP.clear_iracing_ui_car_previews = self._fake_clear
        APP.remember_iracing_ui_preview_member_id = lambda *_args, **_kwargs: MEMBER_ID
        APP.resolve_iracing_ui_preview_member_id = lambda *_args, **_kwargs: (MEMBER_ID, "iRacing session")

    def _fake_sync(self, **kwargs):
        self.sync_calls.append(kwargs)
        return APP.IracingUiPreviewSyncResult(
            ok=True,
            member_id=MEMBER_ID,
            manifest_items=3,
            car_directories=2,
            message="ready",
        )

    def _fake_install(self, **kwargs):
        self.install_calls.append(kwargs)
        return 0, 0

    def _fake_clear(self, **kwargs):
        self.clear_calls.append(kwargs)
        return 0, 0

    def _wait_for_worker(self, service, timeout=5.0):
        deadline = APP.time.monotonic() + timeout
        while APP.time.monotonic() < deadline:
            with service._lock:
                if not service._ui_preview_worker_active:
                    return True
            APP.time.sleep(0.01)
        return False

    def test_an_idle_service_syncs_the_previews(self):
        service = APP.DownloaderService(APP.AppConfig(iracing_ui_car_previews=True))
        service._maintain_ui_previews(service.get_config(), self.paints_dir, live_member_id=MEMBER_ID, session_active=False)
        self.assertTrue(self._wait_for_worker(service))
        self.assertEqual(len(self.sync_calls), 1)
        status = service.get_ui_preview_status()
        self.assertEqual(status.state, "ok")
        self.assertEqual(status.car_directories, 2)

    def test_a_live_session_is_never_interrupted(self):
        service = APP.DownloaderService(APP.AppConfig(iracing_ui_car_previews=True))
        service._maintain_ui_previews(service.get_config(), self.paints_dir, live_member_id=MEMBER_ID, session_active=True)
        self.assertEqual(self.sync_calls, [])
        self.assertEqual(self.install_calls, [])

    def test_turning_previews_off_clears_the_installed_files_once(self):
        service = APP.DownloaderService(APP.AppConfig(iracing_ui_car_previews=False))
        config = service.get_config()
        service._maintain_ui_previews(config, self.paints_dir, live_member_id=MEMBER_ID, session_active=False)
        service._maintain_ui_previews(config, self.paints_dir, live_member_id=MEMBER_ID, session_active=False)
        self.assertEqual(len(self.clear_calls), 1)
        self.assertEqual(service.get_ui_preview_status().state, "disabled")
        self.assertEqual(self.sync_calls, [])

    def test_session_cleanup_keeps_preview_files_and_restores_them(self):
        preview_path = self.paints_dir / "ferrari296gt3" / f"car_{MEMBER_ID}.tga"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview_path.write_bytes(b"my-car-paint")
        APP._set_iracing_ui_preview_protected_paths([preview_path])
        self.addCleanup(APP._set_iracing_ui_preview_protected_paths, [])
        service = APP.DownloaderService(APP.AppConfig(iracing_ui_car_previews=True))
        service._ui_preview_member_id = MEMBER_ID
        saved = [
            APP.SavedFile(
                session_id=APP.SessionId(1, 1),
                download_id=APP.DownloadId(user_id=MEMBER_ID, directory="ferrari296gt3", paint_type=APP.PaintType.CAR),
                file_path=preview_path,
            )
        ]
        kept = service._cleanup_saved(
            saved=saved,
            keep_my_livery_locally=False,
            preserve_targets=set(),
            reason="test cleanup",
            paints_root=self.paints_dir,
        )
        self.assertEqual([item.file_path for item in kept], [preview_path])
        self.assertTrue(preview_path.exists())
        self.assertEqual(len(self.install_calls), 1)


if __name__ == "__main__":
    unittest.main()
