# QA log

## Progress

| Group | Result | Tests (suite) | Commit |
| --- | --- | --- | --- |
| G0 | Rescued 6 uncommitted fixes; 4 broken controller tests fixed; 6 tests added; 8/8 mutations killed | 326 pass, 0 fail (30 s) | 6eed12e |
| G1 | `test_download_install_safety.py` (13 tests): good install, truncated/empty bz2, empty tga, dropped stream, 404 no retry, retry budget, permanent/short lock, disk full, history snapshot, path escape, team/user names. F-008 fixed | 339 pass, 0 fail | dac127c |
| G2 | Gap tests on the real service loop: repeated update with no change, driver leaves (others keep paints), driver returns (not refetched), new session (new roster fetched, old cleared); cancel after download installs nothing. No defects; 3/3 repeat runs stable | 344 pass | 1f4a86c |
| G3 | Existing coverage of hosts/outage/recovery/paging/pool was already dense. Added: well-formed HTML from primary, malformed HTML from every host. F-010 fixed | 346 pass | 43b49bb |
| G4 | Updater/launch/single-instance already covered (~95 tests). Added: non-object settings.json, out-of-range numbers clamped. No defects | 348 pass | see git log |

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
| F-009 | Downloads | Low | A 200 reply with an HTML/error page for a raw `.tga` URL would be installed (no content check for uncompressed paints). Most paint URLs are `.bz2`, which fail to decompress | hypothesis, not fixed | - |

F-001..F-007 were found and fixed in an earlier session (uncommitted in `H:\New folder (5)\PAINTS-bugsweep`); G0 verified them.

## Residual risks

- AI roster assets and team preload copies write without the empty-file check; low risk (roster assets never overwrite a non-empty file; preload copies come from already-installed paints).

- A crash between writing `car_X.tga.tmp` and `os.replace` leaves the `.tmp` in the paint folder until that target is downloaded again (harmless to iRacing; no startup sweep).
- The real manifest root tag is not documented; F-010 only rejects `<html>`, it does not require a specific root.
- Session transitions are tested on the fingerprint (SessionID, SubSessionID, time of day). Practice -> qualify -> race inside one event is expected to start no new download; verify live (G5).

## Environment limits

- Windows 11, Python 3.13.11. No iRacing in automated runs: SDK, real paint folder and Trading Paints are mocked.
- Installer (`installer/NishizumiPaints.iss`) not built or run.
