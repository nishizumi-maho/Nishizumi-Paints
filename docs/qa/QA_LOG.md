# QA log

## Progress

| Group | Result | Tests (suite) | Commit |
| --- | --- | --- | --- |
| G0 | Rescued 6 uncommitted fixes; 4 broken controller tests fixed; 6 tests added; 8/8 mutations killed | 326 pass, 0 fail (30 s) | 6eed12e |
| G1 | `test_download_install_safety.py` (13 tests): good install, truncated/empty bz2, empty tga, dropped stream, 404 no retry, retry budget, permanent/short lock, disk full, history snapshot, path escape, team/user names. F-008 fixed | 339 pass, 0 fail | dac127c |
| G2 | Gap tests on the real service loop: repeated update with no change, driver leaves (others keep paints), driver returns (not refetched), new session (new roster fetched, old cleared); cancel after download installs nothing. No defects; 3/3 repeat runs stable | 344 pass | 1f4a86c |
| G3 | Existing coverage of hosts/outage/recovery/paging/pool was already dense. Added: well-formed HTML from primary, malformed HTML from every host. F-010 fixed | 346 pass | 43b49bb |
| G4 | Updater/launch/single-instance already covered (~95 tests). Added: non-object settings.json, out-of-range numbers clamped. No defects | 348 pass | 7ded441 |
| G5 (partial) | Live, 2026-10-14, spectating an online NASCAR Next Gen race (38 drivers, headless mode, `--verbose`). L2 passed: 38 manifests, 87/87 TP files downloaded and saved in ~15 s, online random fallback filled 22 targets (54 files, 0 misses), local driver skipped as configured, 0 WARNING/ERROR/Traceback in 1431 log lines. Paint folder after: 141 files written this session, no 0-byte paint, no `.tmp`. L1 partly (started headless, settings kept). L5 passed after the game closed: session paints cleared (248 -> 110 files, the pre-session UI-preview baseline), 3 local livery files kept, no 0-byte/.tmp. L3, L4, L6-L8 not run | - | 1f11ed6 |
| G6 | Branch coverage measured (below). `process_session` had 0%: 3 integration tests added (real orchestrator, fake Trading Paints). One independent review (Sonnet) of the app diff: F-011 (High, deadlock) confirmed and fixed, F-012 fixed, rest recorded. Harness: integration module collects Tk garbage on the main thread (Tcl abort otherwise) | 352 pass, 2 consecutive full runs | 24b9d4d |

Baseline before G0: `origin/main` + rescued diff = 321 tests, 4 failures (test harness: tests called `_poll_service` on a `MagicMock`, so the new `_poll_service_once` was never run).

## Findings

Status: `fixed` (with regression test), `open`, `hypothesis` (not reproduced).

| ID | Area | Sev | Summary | Status | Test |
| --- | --- | --- | --- | --- | --- |
| F-001 | Car catalog | Med | Catalog fetch (up to ~1 min) held the cache lock the window reads, freezing the UI | fixed (G0) | `test_the_catalog_lock_is_free_while_the_catalog_downloads` |
| F-002 | Car catalog | Low | A weeks-old catalog read from disk counted as fresh for a full 6 h TTL | fixed (G0) | `test_a_catalog_from_disk_is_replaced_once_the_retry_pause_ends` |
| F-003 | Cleanup | High | `clear_session_target_files` deleted a preserved driver override in its second sweep | fixed (G0) | `test_a_preserved_override_stays_tracked_and_on_disk` |
| F-004 | Config | High | A wrongly typed value in settings.json stopped the app from starting | fixed (G0) | `test_wrongly_typed_values_fall_back_to_defaults` |
| F-005 | Team swaps | Med | Two team swaps one poll apart were never processed | fixed (G0) | `test_two_swaps_one_poll_apart_are_both_confirmed` |
| F-006 | UI | Med | One exception in `_poll_service` stopped the window's polling for good; one missed status reply during an update download closed the window | fixed (G0) | `test_a_failing_poll_keeps_polling`, `test_the_window_closes_when_the_headless_service_leaves_to_install` |
| F-007 | Updater | Low | A failed automatic update download blocked automatic installs until restart | fixed (G0) | `test_a_failed_download_is_installed_automatically_again_later` |

| F-008 | Downloads | High | An empty HTTP 200 body for a `.tga` replaced a good paint with a zero-byte file (`move_or_extract` had no size check; empty `.bz2` was already refused) | fixed (G1); test failed before the fix | `test_an_empty_tga_body_keeps_the_old_paint` |
| F-010 | Manifests | Med | Well-formed HTML (proxy/challenge page) with HTTP 200 parsed as an empty manifest: driver treated as having no paint, backup host never asked. Same for the AI roster list (would read as "no rosters") | fixed (G3): `_parse_tp_manifest_xml` raises a parse error for an `<html>` root; test failed before the fix | `test_an_html_page_from_the_primary_moves_to_the_backup` |
| F-011 | Car catalog | High | Introduced by the F-001 fix: `_refresh_tp_car_identity_after_unknown` held the cache lock and called `_load_tp_showroom_mapping` (fetch lock, then cache lock). With a first catalog download running, an unknown car deadlocked both threads and froze the window. Found by the G6 review | fixed (G6); test hung/failed before the fix | `test_an_unknown_car_during_a_catalog_download_does_not_deadlock` |
| F-012 | Config | Low | An integer too large for a float in settings.json raised OverflowError at start | fixed (G6) | `test_out_of_range_numbers_are_clamped_to_something_that_still_works` |
| O-001 | Texture reload | Info | Live: some cars got 2-3 SDK texture reloads (car files spread over >1 s debounce, then fallback helmet/suit). Cosmetic cost only | observation, not changed | - |
| F-009 | Downloads | Low | A 200 reply with an HTML/error page for a raw `.tga` URL would be installed (no content check for uncompressed paints). Most paint URLs are `.bz2`, which fail to decompress | hypothesis, not fixed | - |

F-001..F-007 were found and fixed in an earlier session (uncommitted in `H:\New folder (5)\PAINTS-bugsweep`); G0 verified them.

## Residual risks

- AI roster assets and team preload copies write without the empty-file check; low risk (roster assets never overwrite a non-empty file; preload copies come from already-installed paints).

- A crash between writing `car_X.tga.tmp` and `os.replace` leaves the `.tmp` in the paint folder until that target is downloaded again (harmless to iRacing; no startup sweep).
- The real manifest root tag is not documented; F-010 only rejects `<html>`, it does not require a specific root.
- Session transitions are tested on the fingerprint (SessionID, SubSessionID, time of day). Practice -> qualify -> race inside one event is expected to start no new download; verify live (G5).

- A permanently failing automatic update download (e.g. digest mismatch) is retried hourly and notifies each time (F-007 side effect).
- If the headless service dies while downloading an update, the controller window closes after 3 missed replies instead of falling back to its own service (F-006 side effect; plausible, not reproduced).
- A refused (empty) download leaves its temp source until the same URL is downloaded again or temp cleanup runs.

## Coverage (G6, branch, before the process_session tests)

Whole module 36% (UI is ~4.2k of 19.3k statements at 9%). `DownloaderService` 59%, `ConfigStore` 88%, `HeadlessUpdateManager` 82%.
Critical paths: `download_file` 80, `move_or_extract` 75, `clear_session_target_files` 100, `delete_saved` 88, `fetch_context_files` 75, `_load_tp_showroom_mapping` 88, `fetch_tp_team_paint_files` 89, `download_release_installer` 90.
0% and still unit-untested: online showroom fallback lanes (`_process_tp_showroom_fallback_lane`, accessory targets, ~1k lines; exercised live in G5 with 22 targets, 0 misses), `run_headless`, `SingleInstanceLock.acquire` (Windows mutex), `fetch_user_files` legacy path. `process_session` now has 3 integration tests (not re-measured).

## Final assessment

- Verified live (one session, spectating): manifests, downloads, installs, online random fallback, local-driver exclusion, cleanup at session end, user livery kept.
- Verified by automated tests only (simulated): file safety, failure/recovery paths, host failover, session joins/leaves/new sessions, config damage, updater, single-instance hand-off logic.
- Unverified: L3 join live, L4 practice -> race transition live, AI roster randomize live, close during download live, team swaps live, installer build/install, CI run of this branch (not pushed).
- Not claimed: the app is not bug-free; UI behaviour is mostly untested by automation.

## Environment limits

- Windows 11, Python 3.13.11. No iRacing in automated runs: SDK, real paint folder and Trading Paints are mocked.
- Installer (`installer/NishizumiPaints.iss`) not built or run.
