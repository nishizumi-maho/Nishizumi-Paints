# QA log

## Progress

| Group | Result | Tests (suite) | Commit |
| --- | --- | --- | --- |
| G0 | Rescued 6 uncommitted fixes; 4 broken controller tests fixed; 6 tests added; 8/8 mutations killed | 326 pass, 0 fail (30 s) | 6eed12e |

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

F-001..F-007 were found and fixed in an earlier session (uncommitted in `H:\New folder (5)\PAINTS-bugsweep`); G0 verified them.

## Environment limits

- Windows 11, Python 3.13.11. No iRacing in automated runs: SDK, real paint folder and Trading Paints are mocked.
- Installer (`installer/NishizumiPaints.iss`) not built or run.
