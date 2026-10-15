# QA handoff

- Branch: `qa/campaign` (base `origin/main` 6dedd45). Commit per group.
- Phase: G0, G1 done. Next: **G2 session sync**.
- Last verified: `python -m unittest discover -s tests` -> 339 tests OK (~30 s, ~75 s wall).
- Plan and rules: `docs/qa/QA_PLAN.md`. Findings: `docs/qa/QA_LOG.md` (F-001..F-009).
- Mutation-check helper pattern: replace the fix's code in the module, run the test module, restore (keep a backup copy).

## Next action

G2: list what the roster, swap, preload, randomize and ai_roster_sync tests cover (test names only), then read the
`DownloaderService` pass that reacts to a session change (grep `cancel_event`, `_on_session_change`, `RuntimeSnapshot`).
Add tests only for gaps: session changes while downloads run (old pass cancelled, no paint for the old session
installed after), the same roster seen twice (no second download), a driver who leaves and comes back.

## Notes

- `H:\New folder (5)\PAINTS-bugsweep` still holds the original uncommitted copy of the G0 fixes (git says "dubious ownership"; use `git -c safe.directory=*`). Safe to delete once `qa/campaign` is pushed.
- Line endings: the module has CRLF in places; match `\r\n` when patching it from scripts.
