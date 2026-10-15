# QA handoff

- State: the campaign is merged (PR #56, merge commit 8894ab0) and released as **v7.3.6** (final, "Latest", 2026-10-15, installer with SHA-256 digest). Work from `main`.
- Phase: G0-G4 and G6 done; G5 partial (L2, L5 passed live). Open: live rows L3, L4, L6-L8.
- Last verified: `python -m unittest discover -s tests` -> 352 tests OK, two consecutive local runs; CI and the release workflow's test step passed.
- Plan and rules: `docs/qa/QA_PLAN.md`. Findings and final assessment: `docs/qa/QA_LOG.md` (F-001..F-012). PR text: `docs/qa/PR_DRAFT.md` (used for PR #56).
- Next action: when the user can, run the remaining live rows below. A defect found there goes into `QA_LOG.md` with a regression test, on a new branch from `main`, and ships as 7.3.7.

## G5 live checklist

Before: close any installed copy of Nishizumi Paints (tray too); back up `Documents\iRacing\paint`.
Run from the repo on `main`, output to a file:
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

- Line endings: the module has CRLF in places; match `\r\n` when patching it from scripts.
- Known open risks (low): see "Residual risks" in `QA_LOG.md`.
- Cleanup done 2026-10-15: the `PAINTS-bugsweep` worktree was removed after checking its uncommitted diff matched commit 6eed12e; merged local branches deleted; `refactor/split-into-package` kept (one commit not in `main`).
