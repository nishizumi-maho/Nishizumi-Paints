# QA handoff

- Branch: `qa/campaign` (base `origin/main` 6dedd45). Commit per group.
- Phase: G0-G4 and G6 done; G5 partial (L2, L5 passed live). Campaign complete except live rows L3, L4, L6-L8.
- Last verified: `python -m unittest discover -s tests` -> 352 tests OK, two consecutive runs (~36 s, ~80 s wall).
- Plan and rules: `docs/qa/QA_PLAN.md`. Findings and final assessment: `docs/qa/QA_LOG.md` (F-001..F-012). PR text draft: `docs/qa/PR_DRAFT.md` (not published).
- Next action: when the user can, run the remaining live rows below; then push `qa/campaign` and open the PR only with the user's OK.

## G5 live checklist

Before: close any installed copy of Nishizumi Paints (tray too); back up `Documents\iRacing\paint`.
Run from the repo on `qa/campaign`, output to a file:
`python -u Nishizumi_Paintsv6_nobrowser.py --verbose *> "$env:TEMP\nishizumi_live.log"` (PowerShell)

| # | Scenario | Pass if |
| --- | --- | --- |
| L1 | App starts, settings kept | window opens, settings as before |
| L2 | Join an online practice | other cars show TP paints within ~1 min |
| L3 | A driver joins mid-session | only that driver is fetched (log), paint shows |
| L4 | Practice -> qualify/race in the same event | no full re-download (log), paints stay |
| L5 | Leave the session | session paints cleared, your own livery files untouched |
| L6 | AI session + "Randomize active AI roster" | AI cars get random paints, no error |
| L7 | Close the app during downloads, reopen | no crash, no 0-byte `.tga` in paint folder, resumes |
| L8 | (if possible) team race with a driver swap | new driver's paint applied |

After: send the log path + what you saw per row. Analyse with grep (WARNING/ERROR/Traceback, "Downloading", "Saved"), not by reading the whole log.

## Notes

- `H:\New folder (5)\PAINTS-bugsweep` still holds the original uncommitted copy of the G0 fixes (git says "dubious ownership"; use `git -c safe.directory=*`). Safe to delete once `qa/campaign` is pushed.
- Line endings: the module has CRLF in places; match `\r\n` when patching it from scripts.
