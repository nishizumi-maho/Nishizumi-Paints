import importlib.util
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import requests


MODULE_PATH = Path(__file__).resolve().parents[1] / "Nishizumi_Paintsv6_nobrowser.py"
SPEC = importlib.util.spec_from_file_location("nishizumi_paints_download_speed_test_module", MODULE_PATH)
APP = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = APP
SPEC.loader.exec_module(APP)


CAR = "dirtlatemodel 350"
TEAM_CAR = "dirtlatemodel 350 team"
FILES = "https://files.example.invalid"


def _session(users, local_user_id=1, superspeedway=False):
    return APP.Session(
        session_id=APP.SessionId(7, 9),
        users=set(users),
        local_user_id=local_user_id,
        event_time_raw="2:00 pm",
        series_id=164,
        is_superspeedway_track=superspeedway,
    )


def _car(
    user_id,
    *,
    team_id=0,
    directory=CAR,
    paint_type="car",
    car_id=1,
    file_url=None,
    ext="",
):
    url = file_url or f"{FILES}/{user_id}/{paint_type}.tga.bz2"
    ext_xml = f"<ext>{ext}</ext>" if ext else ""
    return (
        "<Car>"
        f"<carid>{car_id}</carid><userid>{user_id}</userid><teamid>{team_id}</teamid>"
        f"<directory>{directory}</directory><type>{paint_type}</type>"
        f"<file>{url}</file>{ext_xml}"
        "</Car>"
    )


def _manifest(*cars):
    return f"<Response>{''.join(cars)}</Response>"


class _Response:
    def __init__(self, text="", status=200, body=b""):
        self.text = text
        self.status_code = status
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def iter_content(self, chunk_size=None):
        yield self.body


class _ManifestHttp:
    """Answers fetch.php for whatever list of users the request contains."""

    def __init__(self, omit_from_batch=()):
        self.omit_from_batch = set(omit_from_batch)
        self.calls = []

    def post(self, url, data=None, timeout=None):
        payload = dict(data or {})
        self.calls.append((url, payload))
        entries = [entry for entry in str(payload.get("list", "")).split(",") if entry]
        user_ids = [int(entry.split("=", 1)[0]) for entry in entries if entry.split("=", 1)[0].isdigit()]
        cars = []
        for user_id in user_ids:
            if len(user_ids) > 1 and user_id in self.omit_from_batch:
                continue
            cars.append(_car(user_id))
        return _Response(text=_manifest(*cars))


class BatchPayloadTests(unittest.TestCase):
    def test_batch_payload_is_one_comma_separated_list(self):
        users = [
            APP.SessionUser(user_id=10, directory=CAR, team_id=None, number="7", paint_ext="alt"),
            APP.SessionUser(user_id=11, directory=TEAM_CAR, team_id=500, number="12"),
        ]
        session = _session(users, local_user_id=10)
        payload = APP._build_fetch_context_payload_batch(session, users)
        self.assertEqual(payload["list"], ",".join(user.trading_paints_list_value() for user in users))
        self.assertEqual(payload["user"], "10")
        self.assertNotIn("ss", payload)

    def test_batch_superspeedway_flag_matches_the_per_driver_request(self):
        user = APP.SessionUser(user_id=10, directory=CAR)
        session = _session([user], local_user_id=10, superspeedway=True)
        self.assertEqual(APP._build_fetch_context_payload_batch(session, [user], superspeedway_variant=True)["ss"], "1")
        self.assertNotIn("ss", APP._build_fetch_context_payload_batch(session, [user], superspeedway_variant=False))

    def test_batch_drivers_are_split_into_chunks_of_64(self):
        users = [APP.SessionUser(user_id=1000 + index, directory=CAR) for index in range(130)]
        self.assertEqual([len(chunk) for chunk in APP._chunk_session_users(users)], [64, 64, 2])

    def test_a_large_batch_field_costs_one_request_per_chunk(self):
        users = [APP.SessionUser(user_id=1000 + index, directory=CAR) for index in range(130)]
        http = _ManifestHttp()
        self._http(http)
        result = APP.fetch_context_files_batch(_session(users, local_user_id=1000), users, 1, 0.0)
        self.assertEqual([len(str(payload["list"]).split(",")) for _url, payload in http.calls], [64, 64, 2])
        self.assertEqual(len(result), 130)

    def _http(self, http):
        patcher = mock.patch.object(APP, "get_thread_http_session", return_value=http)
        patcher.start()
        self.addCleanup(patcher.stop)
        return patcher


class BatchAssignmentTests(unittest.TestCase):
    def setUp(self):
        with APP._TP_FETCH_URL_DOWN_LOCK:
            APP._TP_FETCH_URL_DOWN_UNTIL.clear()
            APP._TP_FETCH_HOST_UNREACHABLE_UNTIL.clear()
        self.addCleanup(APP._TP_FETCH_URL_DOWN_UNTIL.clear)
        self.addCleanup(APP._TP_FETCH_HOST_UNREACHABLE_UNTIL.clear)

    def _fetch(self, session, users, cars):
        http = _ManifestHttp()
        http.post = lambda url, data=None, timeout=None: http.calls.append((url, dict(data or {}))) or _Response(
            text=_manifest(*cars)
        )
        patcher = mock.patch.object(APP, "get_thread_http_session", return_value=http)
        patcher.start()
        self.addCleanup(patcher.stop)
        return APP.fetch_context_files_batch(session, users, 1, 0.0)

    def test_batch_assigns_member_and_team_entries_to_their_own_driver(self):
        member = APP.SessionUser(user_id=10, directory=CAR)
        team = APP.SessionUser(user_id=20, directory=TEAM_CAR, team_id=500)
        session = _session([member, team], local_user_id=10)
        result = self._fetch(
            session,
            [member, team],
            [
                _car(10, directory=CAR),
                _car(20, directory=CAR),
                _car(999, team_id=500, directory=TEAM_CAR),
                _car(999, directory=CAR),
            ],
        )

        member_files = result[member.effective_target_key()]
        self.assertEqual([(item.download_id.user_id, item.download_id.is_team_paint) for item in member_files], [(10, False)])

        team_files = result[team.effective_target_key()]
        self.assertEqual(
            sorted((item.download_id.user_id, item.download_id.is_team_paint) for item in team_files),
            [(20, False), (500, True)],
        )
        self.assertTrue(all(item.download_id.directory in {CAR, TEAM_CAR} for item in team_files))

    def test_batch_member_does_not_receive_another_teams_entry(self):
        member = APP.SessionUser(user_id=10, directory=CAR)
        session = _session([member], local_user_id=10)
        result = self._fetch(session, [member], [_car(999, team_id=500, directory=TEAM_CAR)])
        self.assertEqual(result, {})


class BatchFallbackTests(unittest.TestCase):
    def setUp(self):
        with APP._TP_FETCH_URL_DOWN_LOCK:
            APP._TP_FETCH_URL_DOWN_UNTIL.clear()
            APP._TP_FETCH_HOST_UNREACHABLE_UNTIL.clear()
        self.addCleanup(APP._TP_FETCH_URL_DOWN_UNTIL.clear)
        self.addCleanup(APP._TP_FETCH_HOST_UNREACHABLE_UNTIL.clear)

    def test_only_the_driver_without_a_batch_entry_uses_the_per_driver_path(self):
        users = [
            APP.SessionUser(user_id=10, directory=CAR),
            APP.SessionUser(user_id=20, directory=CAR),
            APP.SessionUser(user_id=30, directory=CAR),
        ]
        session = _session(users, local_user_id=10)
        http = _ManifestHttp(omit_from_batch={20})
        with mock.patch.object(APP, "get_thread_http_session", return_value=http):
            wanted = APP._collect_wanted_downloads(
                session=session,
                manifest_workers=4,
                retries=1,
                retry_backoff_seconds=0.0,
                sync_my_livery_from_server=True,
                team_driver_personal_fallback_slots=(),
                ai_rosters_dir=None,
                cancel_event=None,
            )

        self.assertEqual(len(http.calls), 2)
        self.assertEqual(len(str(http.calls[0][1]["list"]).split(",")), 3)
        self.assertEqual(
            str(http.calls[1][1]["list"]),
            users[1].trading_paints_list_value(),
            "the per-driver fallback was not limited to the unanswered driver",
        )
        self.assertEqual(sorted(item.download_id.user_id for item in wanted), [10, 20, 30])


class TrackOrderTests(unittest.TestCase):
    def test_on_track_drivers_go_first_and_local_targets_go_last(self):
        users = [
            APP.SessionUser(user_id=1, directory=CAR, car_idx=0),
            APP.SessionUser(user_id=2, directory=CAR, car_idx=1),
            APP.SessionUser(user_id=3, directory=CAR, car_idx=2),
            APP.SessionUser(user_id=4, directory=CAR, car_idx=3),
        ]
        ordered = APP.order_session_targets(
            users,
            on_track_car_idxs={1, 3},
            local_keys={users[0].effective_target_key(), users[2].effective_target_key()},
        )
        self.assertEqual([user.user_id for user in ordered], [2, 4, 1, 3])

    def test_without_telemetry_only_the_local_targets_move(self):
        users = [
            APP.SessionUser(user_id=1, directory=CAR, car_idx=0),
            APP.SessionUser(user_id=2, directory=CAR, car_idx=1),
            APP.SessionUser(user_id=3, directory=CAR, car_idx=2),
            APP.SessionUser(user_id=4, directory=CAR, car_idx=3),
        ]
        ordered = APP.order_session_targets(users, set(), {users[1].effective_target_key()})
        self.assertEqual([user.user_id for user in ordered], [1, 3, 4, 2])

    def test_telemetry_marks_the_cars_in_the_world(self):
        class _Sdk:
            def freeze_var_buffer_latest(self):
                return None

            def __getitem__(self, key):
                if key == "CarIdxTrackSurface":
                    return [-1, 0, None, 3]
                raise KeyError(key)

        self.assertEqual(APP.read_on_track_car_idxs(APP.IracingSdkReader(sdk=_Sdk())), {1, 3})


class AlternateAssetUrlTests(unittest.TestCase):
    def test_the_trading_paints_asset_host_is_moved_to_the_alternate_cdn(self):
        self.assertEqual(
            APP.alternate_tp_asset_url("https://dl.tradingpaints.gg/path/car.tga.bz2?x=1"),
            "https://dl1.tradingpaints.gg/path/car.tga.bz2?x=1",
        )

    def test_the_alternate_host_and_non_asset_hosts_are_left_alone(self):
        for url in (
            "https://dl1.tradingpaints.gg/path/car.tga.bz2",
            "https://fetch.tradingpaints.gg/fetch.php",
            "https://www.tradingpaints.gg/page",
            "https://example.invalid/car.tga",
            "not a URL",
            "",
        ):
            with self.subTest(url=url):
                self.assertIsNone(APP.alternate_tp_asset_url(url))


class AlternateAssetRetryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix="nishizumi-download-speed-"))
        self.addCleanup(shutil.rmtree, self.root, True)
        self.item = APP.DownloadFile(
            download_id=APP.DownloadId(5, CAR, APP.PaintType.CAR),
            url="https://dl.tradingpaints.gg/car_5.tga",
        )

    def _download(self, http, retries=2):
        with mock.patch.object(APP, "get_thread_http_session", return_value=http):
            return APP.download_file(APP.SessionId(1, 2), self.root, self.item, retries, 0.0)

    def test_a_missing_asset_is_tried_once_on_the_alternate_host(self):
        class _Http:
            def __init__(self):
                self.urls = []

            def get(self, url, timeout=None, stream=False):
                self.urls.append(url)
                return _Response(status=404 if "dl.tradingpaints" in url and "dl1." not in url else 200, body=b"paint")

        http = _Http()
        downloaded = self._download(http)
        self.assertIsNotNone(downloaded)
        self.assertEqual(
            http.urls,
            ["https://dl.tradingpaints.gg/car_5.tga", "https://dl1.tradingpaints.gg/car_5.tga"],
        )

    def test_a_server_error_is_retried_normally_then_on_the_alternate_host(self):
        class _Http:
            def __init__(self):
                self.urls = []

            def get(self, url, timeout=None, stream=False):
                self.urls.append(url)
                return _Response(status=503 if "dl.tradingpaints" in url and "dl1." not in url else 200, body=b"paint")

        http = _Http()
        self.assertIsNotNone(self._download(http))
        self.assertEqual(
            http.urls,
            [
                "https://dl.tradingpaints.gg/car_5.tga",
                "https://dl.tradingpaints.gg/car_5.tga",
                "https://dl1.tradingpaints.gg/car_5.tga",
            ],
        )

    def test_a_non_trading_paints_url_never_uses_the_alternate_host(self):
        class _Http:
            def __init__(self):
                self.urls = []

            def get(self, url, timeout=None, stream=False):
                self.urls.append(url)
                return _Response(status=404)

        item = APP.DownloadFile(
            download_id=APP.DownloadId(5, CAR, APP.PaintType.CAR),
            url="https://example.invalid/car_5.tga",
        )
        http = _Http()
        with mock.patch.object(APP, "get_thread_http_session", return_value=http):
            self.assertIsNone(APP.download_file(APP.SessionId(1, 2), self.root, item, 2, 0.0))
        self.assertEqual(http.urls, ["https://example.invalid/car_5.tga"])


if __name__ == "__main__":
    unittest.main()
