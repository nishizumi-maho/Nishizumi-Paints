# QA handoff

- Branch: `qa/campaign` (base `origin/main` 6dedd45). Commit per group.
- Phase: G0 done. Next: **G1 file safety**.
- Last verified: `python -m unittest discover -s tests` -> 326 tests OK (~30 s, ~75 s wall).
- Plan and rules: `docs/qa/QA_PLAN.md`. Findings: `docs/qa/QA_LOG.md`.
- Mutation-check helper pattern: replace the fix's code in the module, run the test module, restore (keep a backup copy).

## Next action

G1: read `download_file` (~line 18236) and the save path right after it (`save_path_for`, temp `.tmp` handling ~18430),
plus `_download_and_save_with_auto_repair` / `_cleanup_partial_download_save_files` (~7930-8020) and `delete_saved`.
List what `tests/test_downloads.py` and `tests/test_user_files_and_crash_safety.py` already cover, then add tests for:
truncated/corrupt body not installed, failed write leaves the old paint, `.tmp` cleaned, locked target, user's own files untouched.

## Notes

- `H:\New folder (5)\PAINTS-bugsweep` still holds the original uncommitted copy of the G0 fixes (git says "dubious ownership"; use `git -c safe.directory=*`). Safe to delete once `qa/campaign` is pushed.
- Line endings: the module has CRLF in places; match `\r\n` when patching it from scripts.
