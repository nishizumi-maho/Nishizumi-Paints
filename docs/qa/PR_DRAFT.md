# QA campaign: verified fixes and regression tests

## Summary

A QA pass over 7.3.6 on `qa/campaign`. It rescues an uncommitted round of fixes, adds 30 tests, and fixes four more defects found while testing. No version bump or release notes.

## Fixes

- **Rescued (F-001..F-007).** These were uncommitted on top of 7.3.6. Each is now verified by a test that fails when the fix is reverted:
  - The car catalog fetch no longer holds the lock the window reads.
  - A preserved driver override survives session cleanup.
  - Damaged settings values fall back to defaults.
  - Two team swaps one poll apart are both handled.
  - The window's service poll survives exceptions.
  - A failed automatic update download is retried.
- **F-008:** an empty HTTP 200 for a `.tga` no longer replaces an installed paint with a zero-byte file.
- **F-010:** a well-formed HTML page from Trading Paints counts as a failed manifest, so retry and backup-host failover run. Before, it read as "no paint". The same applies to the AI roster list.
- **F-011:** fixes a lock-order deadlock in the car catalog, between an unknown car and a first catalog download. The F-001 change introduced it, and an independent review found it.
- **F-012:** an integer too large for a float in settings.json no longer stops the app from starting.

## Tests

The suite went from 316 to 352 tests, all passing.

- **New:**
  - Download-to-install safety: truncated or empty archives, dropped streams, retry budgets, locked targets, full disk, history snapshots.
  - Real `process_session` integration against a fake Trading Paints.
  - Service-loop session cases: repeated updates, a driver leaving or returning, a new session.
  - HTML manifests.
  - Settings shapes.
  - The deadlock.
- **Fixed:** controller-window tests that ran against a `MagicMock`.

## Verification

- Full suite: 352 OK, two consecutive runs. Python 3.13, Windows 11.
- Live: spectating one online race with 38 drivers.
  - 87/87 Trading Paints files installed.
  - 22 random fallbacks with 0 misses.
  - Session paints cleared on exit, and the user's own livery kept.
- Not verified live: a join mid-session, practice -> race, AI randomize, team swap, closing during a download, the installer.

Details: `docs/qa/QA_LOG.md`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
