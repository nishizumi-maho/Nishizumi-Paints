# QA plan

Lean QA campaign for Nishizumi Paints on branch `qa/campaign` (from `origin/main` 6dedd45, 7.3.6).
Progress and findings: [QA_LOG.md](QA_LOG.md). Resuming: [QA_HANDOFF.md](QA_HANDOFF.md).

## Architecture (short)

One module, `Nishizumi_Paintsv6_nobrowser.py` (~30.6k lines, Tkinter + `requests` + `pyirsdk`).
Tests import it as `APP` and run with `python -m unittest discover -s tests` (CI: windows-latest, Python 3.13).

| Area | Main entry points |
| --- | --- |
| Service loop / sync | `DownloaderService`, `IracingSdkReader`, `SdkPollState`, `RuntimeSnapshot` |
| Manifests / hosts | `fetch_context_files`, `fetch_best_manifest_files`, `fetch_user_files` |
| Downloads / install | `download_file`, `save_path_for`, `_download_and_save_with_auto_repair`, `_cleanup_partial_download_save_files` |
| Cleanup / user files | `delete_saved`, `clear_session_target_files`, `_hard_delete_file`, `cleanup_stale_temp_dirs` |
| Random pool / fallback | `RandomPoolEntry`, `download_*_to_random_pool`, `fetch_tp_collection_pool`, `clear_random_pool` |
| AI rosters | `fetch_active_ai_roster_collection_files`, `_write_ai_roster_files`, `_download_ai_roster_asset` |
| Team paints / swaps | `fetch_tp_team_paint_files`, `TeamDriverSwapCandidate`, `TeamDriverSwapRetry`, `cleanup_team_driver_preload_cache` |
| Car catalog | `_load_tp_showroom_mapping`, `_fetch_tp_car_identity_doc`, `save/load_tp_car_identity_cache` |
| Config / lifecycle | `AppConfig`, `ConfigStore`, `SingleInstanceLock`, `HeadlessControlServer` |
| Updater | `HeadlessUpdateManager`, `fetch_latest_github_release`, `download_release_installer` |
| UI | `DownloaderUI`, `WindowsTrayIcon` |

## Rules (token budget)

- Never read the big module whole: grep the function, read its range.
- Focused test modules while working; full suite once at the end of a group.
- Gap analysis first: list what existing tests cover, write only what a real risk needs.
- Regression tests for fixed bugs get a mutation check (revert the fix, the test must fail).
- One independent review at the end (G6), on the diff of G1-G3, not one per group.
- Network is always mocked in the suite; live behaviour is only claimed after G5.

## Groups (by risk)

| ID | Scope | Risk | Existing tests | Status |
| --- | --- | --- | --- | --- |
| G0 | Rescue uncommitted 7.3.6 verification round, baseline | lost work | - | done |
| G1 | File safety: download -> validate -> atomic install, user files, cleanup, disk/lock errors | data loss, wrong paint | `test_downloads` (2), `test_user_files_and_crash_safety` (18) | done |
| G2 | Session sync: transitions, joins/leaves, duplicates, overlap with active downloads, team swaps, AI roster | wrong/missing paints, redownloads | roster, swaps, preload, randomize, ai_roster_sync | done |
| G3 | Network: gg primary -> backup host, outages, showroom paging, pool exhaustion, retry/backoff, history | stuck downloads, request storms | manifest_hosts, fallback_pool, online_fallback_lanes, showroom_lists | done |
| G4 | Lifecycle: first run, bad config, shutdown/restart, single instance, updater | app won't start, two downloaders | auto_update, launch_mode, sdk_and_settings | done |
| G5 | Live check in iRacing (user runs the game), checklist in QA_HANDOFF | real-world gaps | manual | partial (L2, L5) |
| G6 | Coverage once, one independent review, CI check, final report, PR text (not published) | - | - | done |

UI (`DownloaderUI`) is covered only where logic is testable with mocks; real UI behaviour is checked in G5.

## Out of scope (recorded only)

Stale branches/worktrees (`refactor/split-into-package`, prunable worktrees on `K:`), dependabot PR #52, untracked `.kiro/`.
No version bump, tags, releases, merges to `main` or published PRs without explicit approval.
