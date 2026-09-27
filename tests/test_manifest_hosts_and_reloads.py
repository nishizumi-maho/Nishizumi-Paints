import gc
import importlib.util
import sys
import threading
import time
import unittest
from pathlib import Path

import requests


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_hosts_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


def setUpModule():
    # Tk widgets left behind by other test modules must be collected on the main
    # thread; letting a worker thread started here collect them aborts Tcl.
    gc.collect()


CAR = "dirtlatemodel 350"
BROKEN, HEALTHY = APP.TRADING_PAINTS_FETCH_CONTEXT_URLS


def _manifest(user_id):
    return (
        "<Response><Car>"
        f"<carid>1</carid><userid>{user_id}</userid><teamid>0</teamid>"
        f"<file>https://example.invalid/{user_id}.tga</file><type>car</type><directory>{CAR}</directory>"
        "</Car></Response>"
    )


class _Response:
    def __init__(self, text):
        self.text = text

    def raise_for_status(self):
        pass


class _HttpSession:
    def __init__(self, failures):
        self.failures = failures
        self.calls = []

    def post(self, url, data=None, timeout=None):
        self.calls.append(url)
        failure = self.failures.get(url)
        if failure is not None:
            raise failure
        user_id = str(data["list"]).split("=", 1)[0]
        return _Response(_manifest(user_id))


class ManifestHostFallbackTests(unittest.TestCase):
    def setUp(self):
        with APP._TP_FETCH_URL_DOWN_LOCK:
            APP._TP_FETCH_URL_DOWN_UNTIL.clear()
        self.addCleanup(APP._TP_FETCH_URL_DOWN_UNTIL.clear)
        original = APP.get_thread_http_session
        self.addCleanup(setattr, APP, "get_thread_http_session", original)
        self.user = APP.SessionUser(user_id=42, directory=CAR)
        self.session = APP.Session(
            session_id=APP.SessionId(1, 2),
            users={self.user},
            local_user_id=42,
            series_id=164,
        )

    def _use(self, http):
        APP.get_thread_http_session = lambda: http

    def _fetch(self):
        return APP.fetch_context_files(self.session, self.user, retries=3, retry_backoff_seconds=5.0)

    def test_general_session_manifest_uses_the_healthy_alternative_after_tls_failure(self):
        http = _HttpSession({BROKEN: requests.exceptions.SSLError("handshake failure")})
        self._use(http)
        started = time.monotonic()
        files = self._fetch()
        self.assertLess(time.monotonic() - started, 1.0, "no backoff should be spent on the broken host")
        self.assertEqual(http.calls, [BROKEN, HEALTHY])
        self.assertEqual([item.download_id.user_id for item in files], [42])

    def test_later_fetches_start_with_the_host_that_works(self):
        http = _HttpSession({BROKEN: requests.exceptions.SSLError("handshake failure")})
        self._use(http)
        self._fetch()
        http.calls.clear()
        self._fetch()
        self.assertEqual(http.calls, [HEALTHY])
        self.assertEqual(APP.tp_fetch_context_urls(), [HEALTHY, BROKEN])

    def test_a_host_that_answers_again_is_trusted_again(self):
        APP._note_tp_fetch_url_result(BROKEN, requests.exceptions.ConnectionError("refused"))
        self.assertEqual(APP.tp_fetch_context_urls(), [HEALTHY, BROKEN])
        APP._note_tp_fetch_url_result(BROKEN, None)
        self.assertEqual(APP.tp_fetch_context_urls(), [BROKEN, HEALTHY])

    def test_http_errors_keep_the_normal_retries(self):
        self.assertFalse(APP._note_tp_fetch_url_result(BROKEN, requests.exceptions.HTTPError("503")))
        self.assertFalse(APP._note_tp_fetch_url_result(BROKEN, requests.exceptions.ReadTimeout("slow")))
        self.assertEqual(APP.tp_fetch_context_urls(), [BROKEN, HEALTHY])

    def test_the_last_host_left_still_gets_its_retries(self):
        error = requests.exceptions.ConnectionError("down")
        http = _HttpSession({BROKEN: error, HEALTHY: error})
        self._use(http)
        original_delay = APP.compute_retry_delay
        APP.compute_retry_delay = lambda _base, _attempt: 0.0
        self.addCleanup(setattr, APP, "compute_retry_delay", original_delay)
        with self.assertRaises(requests.exceptions.ConnectionError):
            self._fetch()
        self.assertEqual(http.calls, [BROKEN, HEALTHY, HEALTHY, HEALTHY])

    def test_team_manifest_uses_the_healthy_alternative_after_tls_failure(self):
        http = _HttpSession({BROKEN: requests.exceptions.SSLError("handshake failure")})
        self._use(http)
        target = APP.TPTeamPaintTarget(0, "Ferrari 296 GT3", (CAR,), 264, "Ferrari-296-GT3")
        APP.fetch_tp_team_paint_files(target, request_member_id=42, retries=3, retry_backoff_seconds=0.0)
        self.assertEqual(http.calls[:2], [BROKEN, HEALTHY])


class _ReloadSdk:
    is_initialized = True
    is_connected = True

    def __init__(self):
        self.reloads = []
        self._lock = threading.Lock()

    def startup(self):
        return True

    def freeze_var_buffer_latest(self):
        pass

    def reload_texture(self, car_idx):
        with self._lock:
            self.reloads.append(car_idx)

    def __getitem__(self, key):
        if key == "OkToReloadTextures":
            return True
        raise KeyError(key)


class TextureReloadDebounceTests(unittest.TestCase):
    def test_files_of_one_car_arriving_apart_reload_it_once(self):
        sdk = _ReloadSdk()
        user = APP.SessionUser(user_id=7, directory=CAR, car_idx=5)
        session = APP.Session(session_id=APP.SessionId(1, 2), users={user})
        debouncer = APP.TextureReloadDebouncer(
            APP.IracingSdkReader(sdk=sdk),
            session,
            debounce_seconds=APP.TEXTURE_RELOAD_DEBOUNCE_SECONDS,
        )
        for paint_type in (APP.PaintType.CAR, APP.PaintType.CAR_SPEC, APP.PaintType.HELMET, APP.PaintType.SUIT):
            saved = APP.SavedFile(session.session_id, APP.DownloadId(7, CAR, paint_type), Path("x"))
            debouncer.request_saved_items([saved])
            time.sleep(0.3)
        time.sleep(APP.TEXTURE_RELOAD_DEBOUNCE_SECONDS + 0.5)
        self.assertEqual(sdk.reloads, [5])


class _ShowroomResponse:
    ok = True

    def __init__(self, cars):
        self._cars = cars

    def json(self):
        return {"output": {"cars": self._cars}}


class _ShowroomHttp:
    def __init__(self, empty=False):
        self.urls = []
        self.empty = empty
        self._lock = threading.Lock()

    def get(self, url, headers=None, timeout=None):
        with self._lock:
            self.urls.append(url)
            serial = len(self.urls)
        if self.empty:
            return _ShowroomResponse([])
        return _ShowroomResponse([{"id": str(900000 + serial * 10 + n), "title": f"scheme {n}"} for n in range(3)])


class ShowroomPageCacheTests(unittest.TestCase):
    def setUp(self):
        with APP._TP_SHOWROOM_PAGE_CACHE_LOCK:
            APP._TP_SHOWROOM_PAGE_CACHE.clear()
        self.addCleanup(APP._TP_SHOWROOM_PAGE_CACHE.clear)
        original = APP.get_thread_http_session
        self.addCleanup(setattr, APP, "get_thread_http_session", original)
        self.http = _ShowroomHttp()
        APP.get_thread_http_session = lambda: self.http

    def _page(self, source="trending", page_index=0, mid=118):
        return APP._tp_fetch_showroom_page_batch_http(
            mid=mid, category="Driver", slug="Helmets", page_index=page_index, showroom_source=source
        )

    def test_a_page_is_fetched_once_per_session(self):
        first = self._page()
        second = self._page()
        self.assertEqual(len(self.http.urls), 1)
        self.assertEqual(first, second)

    def test_callers_cannot_change_the_cached_page(self):
        self._page()[0]["id"] = "changed"
        self.assertNotEqual(self._page()[0]["id"], "changed")

    def test_each_source_page_and_pool_is_its_own_entry(self):
        self._page(source="trending")
        self._page(source="newest")
        self._page(page_index=1)
        self._page(mid=119)
        self.assertEqual(len(self.http.urls), 4)

    def test_an_expired_page_is_fetched_again(self):
        self._page()
        with APP._TP_SHOWROOM_PAGE_CACHE_LOCK:
            for key, (_fetched_at, cars) in list(APP._TP_SHOWROOM_PAGE_CACHE.items()):
                APP._TP_SHOWROOM_PAGE_CACHE[key] = (time.monotonic() - APP.TP_SHOWROOM_PAGE_CACHE_SECONDS - 1, cars)
        self._page()
        self.assertEqual(len(self.http.urls), 2)

    def test_an_empty_answer_is_not_cached(self):
        self.http.empty = True
        self.assertEqual(self._page(), [])
        self.http.empty = False
        self.assertTrue(self._page())
        self.assertEqual(len(self.http.urls), 2)

    def test_prefetch_warms_every_source_so_picks_need_no_request(self):
        sources = APP.TP_SHOWROOM_DEFAULT_SOURCES
        pools = {(118, "Driver", "Helmets"), (119, "Driver", "Suits")}
        fetched = APP.prefetch_tp_showroom_first_pages(pools, sources)
        source_count = len(APP.tp_showroom_sources_list(sources))
        self.assertEqual(fetched, 2 * source_count)
        self.assertEqual(len(self.http.urls), 2 * source_count)
        for kind in ("helmet", "suit"):
            result = APP.choose_showroom_accessory_direct(
                accessory_kind=kind,
                showroom_sources=sources,
                minimum_unused_choices=1,
                allow_reuse_existing_scheme=False,
            )
            self.assertTrue(result.ok, result.message)
        self.assertEqual(len(self.http.urls), 2 * source_count)

    def test_prefetch_stops_when_the_session_is_cancelled(self):
        cancel_event = threading.Event()
        cancel_event.set()
        self.assertEqual(APP.prefetch_tp_showroom_first_pages({(118, "Driver", "Helmets")}, "trending", cancel_event), 0)
        self.assertEqual(self.http.urls, [])


if __name__ == "__main__":
    unittest.main()
