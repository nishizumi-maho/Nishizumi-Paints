import hashlib
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


ASSET_NAME = "NishizumiPaints-Setup-7.3.3.exe"
ASSET_URL = f"https://github.com/nishizumi-maho/Nishizumi-Paints/releases/download/v7.3.3/{ASSET_NAME}"


class _FakeResponse:
    def __init__(self, payload: bytes, status_code: int = 200, headers=None, url: str = ASSET_URL, history=()):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers if headers is not None else {"Content-Length": str(len(payload))}
        self.url = url
        self.history = list(history)

    def iter_content(self, chunk_size=1):
        for start in range(0, len(self._payload), chunk_size):
            yield self._payload[start:start + chunk_size]

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False


class _FakeSession:
    def __init__(self, response):
        self._response = response
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return self._response


def _release(**overrides):
    payload = {
        "tag_name": "v7.3.3",
        "html_url": "https://github.com/nishizumi-maho/Nishizumi-Paints/releases/tag/v7.3.3",
        "asset_name": ASSET_NAME,
        "asset_download_url": ASSET_URL,
        "asset_size": 4,
        "asset_sha256": "a" * 64,
    }
    payload.update(overrides)
    return APP.GitHubReleaseInfo(**payload)


class TrustedAssetUrlTests(unittest.TestCase):
    def test_accepts_github_release_hosts(self):
        for url in (
            ASSET_URL,
            "https://objects.githubusercontent.com/github-production-release-asset/1/2",
            "https://release-assets.githubusercontent.com/github-production-release-asset/1/2",
        ):
            self.assertTrue(APP.is_trusted_release_asset_url(url), url)

    def test_rejects_untrusted_or_insecure_urls(self):
        for url in (
            "",
            None,
            "http://github.com/x/y/releases/download/v1/app.exe",
            "https://github.com.evil.test/x/y.exe",
            "https://evil.test/github.com/y.exe",
            "https://raw.githubusercontent.com/x/y/main/app.exe",
            "ftp://github.com/x.exe",
        ):
            self.assertFalse(APP.is_trusted_release_asset_url(url), url)


class ReleaseDigestParsingTests(unittest.TestCase):
    def test_reads_digest_from_asset_field(self):
        digest = "b" * 64
        info = APP._extract_release_info(
            {
                "tag_name": "v7.3.3",
                "html_url": "https://github.com/x/y/releases/tag/v7.3.3",
                "assets": [{"name": ASSET_NAME, "browser_download_url": ASSET_URL, "size": 123, "digest": f"sha256:{digest}"}],
            }
        )
        self.assertEqual(info.asset_sha256, digest)
        self.assertEqual(info.asset_size, 123)
        self.assertTrue(info.installer_is_verifiable())

    def test_falls_back_to_the_release_notes(self):
        digest = "c" * 64
        for body in (
            f"## Checksums\n\n```\n{digest}  {ASSET_NAME}\n```\n",
            f"SHA-256 for {ASSET_NAME}: {digest}\n",
            f"| {ASSET_NAME} | `{digest}` |\n",
        ):
            info = APP._extract_release_info(
                {
                    "tag_name": "v7.3.3",
                    "html_url": "https://github.com/x/y/releases/tag/v7.3.3",
                    "body": body,
                    "assets": [{"name": ASSET_NAME, "browser_download_url": ASSET_URL, "size": 123}],
                }
            )
            self.assertEqual(info.asset_sha256, digest, body)

    def test_ignores_a_digest_published_for_a_different_asset(self):
        body = f"{'d' * 64}  SomeOtherApp-Setup-1.0.exe\n"
        self.assertIsNone(APP.parse_release_body_sha256(body, ASSET_NAME))

    def test_release_without_a_digest_is_not_verifiable(self):
        info = APP._extract_release_info(
            {
                "tag_name": "v7.3.3",
                "html_url": "https://github.com/x/y/releases/tag/v7.3.3",
                "assets": [{"name": ASSET_NAME, "browser_download_url": ASSET_URL, "size": 123}],
            }
        )
        self.assertIsNone(info.asset_sha256)
        self.assertFalse(info.installer_is_verifiable())

    def test_non_exe_asset_is_not_verifiable(self):
        info = _release(asset_name="notes.txt", asset_sha256="e" * 64)
        self.assertFalse(info.installer_is_verifiable())

    def test_asset_on_an_untrusted_host_is_not_verifiable(self):
        info = _release(asset_download_url="https://evil.test/NishizumiPaints-Setup-7.3.3.exe")
        self.assertFalse(info.installer_is_verifiable())


class DownloadReleaseInstallerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dest = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def test_downloads_and_keeps_a_matching_installer(self):
        payload = b"installer-bytes"
        digest = hashlib.sha256(payload).hexdigest()
        session = _FakeSession(_FakeResponse(payload))
        result = APP.download_release_installer(
            _release(asset_sha256=digest, asset_size=len(payload)),
            dest_dir=self.dest,
            session=session,
        )
        self.assertEqual(result, self.dest / ASSET_NAME)
        self.assertEqual(result.read_bytes(), payload)
        self.assertEqual(list(self.dest.glob("*.part")), [])

    def test_reports_progress_while_downloading(self):
        payload = b"x" * 1024
        digest = hashlib.sha256(payload).hexdigest()
        seen = []
        APP.download_release_installer(
            _release(asset_sha256=digest, asset_size=len(payload)),
            dest_dir=self.dest,
            progress_cb=lambda done, total: seen.append((done, total)),
            session=_FakeSession(_FakeResponse(payload)),
        )
        self.assertTrue(seen)
        self.assertEqual(seen[-1], (len(payload), len(payload)))

    def test_discards_a_download_that_fails_the_digest(self):
        payload = b"tampered-installer"
        session = _FakeSession(_FakeResponse(payload))
        with self.assertRaises(RuntimeError) as caught:
            APP.download_release_installer(
                _release(asset_sha256=hashlib.sha256(b"expected").hexdigest(), asset_size=len(payload)),
                dest_dir=self.dest,
                session=session,
            )
        self.assertIn("SHA-256", str(caught.exception))
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_refuses_a_release_without_a_digest(self):
        with self.assertRaises(RuntimeError):
            APP.download_release_installer(
                _release(asset_sha256=None),
                dest_dir=self.dest,
                session=_FakeSession(_FakeResponse(b"x")),
            )

    def test_refuses_an_untrusted_download_host(self):
        with self.assertRaises(RuntimeError):
            APP.download_release_installer(
                _release(asset_download_url="https://evil.test/app.exe", asset_sha256="f" * 64),
                dest_dir=self.dest,
                session=_FakeSession(_FakeResponse(b"x")),
            )

    def test_refuses_a_redirect_off_github(self):
        payload = b"redirected"
        digest = hashlib.sha256(payload).hexdigest()
        response = _FakeResponse(payload, url="https://evil.test/app.exe")
        with self.assertRaises(RuntimeError) as caught:
            APP.download_release_installer(
                _release(asset_sha256=digest, asset_size=len(payload)),
                dest_dir=self.dest,
                session=_FakeSession(response),
            )
        self.assertIn("redirected", str(caught.exception))

    def test_refuses_an_oversized_declared_asset(self):
        with self.assertRaises(RuntimeError):
            APP.download_release_installer(
                _release(asset_sha256="a" * 64, asset_size=APP.UPDATE_INSTALLER_MAX_BYTES + 1),
                dest_dir=self.dest,
                session=_FakeSession(_FakeResponse(b"x")),
            )

    def test_stops_a_body_that_grows_past_the_cap(self):
        original_cap = APP.UPDATE_INSTALLER_MAX_BYTES
        APP.UPDATE_INSTALLER_MAX_BYTES = 16
        self.addCleanup(setattr, APP, "UPDATE_INSTALLER_MAX_BYTES", original_cap)
        payload = b"y" * 64
        response = _FakeResponse(payload, headers={})
        with self.assertRaises(RuntimeError):
            APP.download_release_installer(
                _release(asset_sha256=hashlib.sha256(payload).hexdigest(), asset_size=0),
                dest_dir=self.dest,
                session=_FakeSession(response),
            )
        self.assertEqual(list(self.dest.iterdir()), [])

    def test_refuses_an_unsafe_asset_filename(self):
        for name in ("../evil.exe", "evil.exe.bat", r"sub\evil.exe", "evil.cmd"):
            with self.assertRaises(RuntimeError, msg=name):
                APP.download_release_installer(
                    _release(asset_name=name, asset_sha256="a" * 64),
                    dest_dir=self.dest,
                    session=_FakeSession(_FakeResponse(b"x")),
                )

    def test_http_error_is_reported(self):
        with self.assertRaises(RuntimeError) as caught:
            APP.download_release_installer(
                _release(asset_sha256="a" * 64),
                dest_dir=self.dest,
                session=_FakeSession(_FakeResponse(b"", status_code=404)),
            )
        self.assertIn("404", str(caught.exception))


class UpdateLauncherScriptTests(unittest.TestCase):
    def test_runs_the_installer_silently_then_relaunches_the_app(self):
        script = APP.build_update_launcher_script(
            Path(r"C:\Users\me\AppData\Roaming\NishizumiPaints\updates\NishizumiPaints-Setup-7.3.3.exe"),
            Path(r"C:\Users\me\AppData\Local\Programs\Nishizumi Paints\NishizumiPaints.exe"),
            Path(r"C:\Users\me\AppData\Roaming\NishizumiPaints\updates\install.log"),
        )
        self.assertIn("/SILENT", script)
        self.assertIn("/NORESTART", script)
        self.assertIn("/CLOSEAPPLICATIONS", script)
        self.assertIn("if errorlevel 1 exit /b", script)
        installer_line = next(line for line in script.splitlines() if "Setup-7.3.3.exe" in line)
        launch_line = next(line for line in script.splitlines() if line.startswith("start "))
        self.assertLess(script.index(installer_line), script.index(launch_line))
        self.assertIn('start "" "C:\\Users\\me\\AppData\\Local\\Programs\\Nishizumi Paints\\NishizumiPaints.exe"', script)

    def test_quotes_the_paths_so_spaces_survive(self):
        script = APP.build_update_launcher_script(
            Path(r"C:\dir with spaces\setup.exe"),
            Path(r"C:\other dir\app.exe"),
            Path(r"C:\dir with spaces\install.log"),
        )
        self.assertIn(r'"C:\dir with spaces\setup.exe"', script)
        self.assertIn(r'/LOG="C:\dir with spaces\install.log"', script)

    def test_refuses_paths_that_could_break_out_of_the_script(self):
        safe = Path(r"C:\updates\setup.exe")
        for bad in (Path('C:\\updates\\ev"il.exe'), Path("C:\\updates\\%PATH%.exe")):
            with self.assertRaises(RuntimeError, msg=str(bad)):
                APP.build_update_launcher_script(bad, safe, Path(r"C:\updates\install.log"))


class UpdateWorkspaceTests(unittest.TestCase):
    def test_cleanup_removes_stale_files_but_keeps_the_new_installer(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        workspace = Path(tmp.name) / "updates"
        workspace.mkdir()
        original = APP.update_workspace_dir
        APP.update_workspace_dir = lambda: workspace
        self.addCleanup(setattr, APP, "update_workspace_dir", original)

        keeper = workspace / "NishizumiPaints-Setup-7.3.3.exe"
        keeper.write_bytes(b"new")
        stale_file = workspace / "NishizumiPaints-Setup-7.3.2.exe"
        stale_file.write_bytes(b"old")
        stale_dir = workspace / "leftover"
        stale_dir.mkdir()
        (stale_dir / "inner.txt").write_text("x", encoding="utf-8")

        APP.clean_update_workspace(keep=keeper)

        self.assertTrue(keeper.is_file())
        self.assertFalse(stale_file.exists())
        self.assertFalse(stale_dir.exists())

    def test_cleanup_is_a_no_op_when_the_directory_is_missing(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        missing = Path(tmp.name) / "nope"
        original = APP.update_workspace_dir
        APP.update_workspace_dir = lambda: missing
        self.addCleanup(setattr, APP, "update_workspace_dir", original)
        APP.clean_update_workspace()


class AutoInstallSupportTests(unittest.TestCase):
    def test_source_checkouts_cannot_self_install(self):
        # The tests always run from source, never from the frozen .exe.
        self.assertTrue(APP.auto_install_unsupported_reason())

    def test_start_update_installer_refuses_when_unsupported(self):
        with self.assertRaises(RuntimeError):
            APP.start_update_installer(Path(r"C:\updates\setup.exe"))


class VersionTests(unittest.TestCase):
    def test_app_version_matches_the_installer_script(self):
        iss = (Path(__file__).resolve().parents[1] / "installer" / "NishizumiPaints.iss").read_text(encoding="utf-8")
        self.assertIn(f'#define AppVersion "{APP.APP_VERSION}"', iss)
        self.assertIn(f'#define AppVersionInfo "{APP.APP_VERSION}.0"', iss)


if __name__ == "__main__":
    unittest.main()
