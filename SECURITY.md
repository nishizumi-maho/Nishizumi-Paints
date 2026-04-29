# Security Policy

## Supported versions

Only the latest published release is supported for security fixes.

## Reporting a vulnerability

Please do not open public issues for security-sensitive reports.

If GitHub private vulnerability reporting is enabled on the repository, use that channel. Otherwise, contact the maintainer privately and include:

- the affected version
- a short impact summary
- reproduction steps
- any logs or screenshots needed to understand the issue

## Sensitive data expectations

Nishizumi Paints should not require users to commit, share, or publish:

- Trading Paints browser profiles
- cookies
- tokens
- `settings.json`
- iRacing document contents
- local paint folders
- local RandomPool or collection-pool caches
- `.playwright-cli/` captures or other local browser/debug exports
- `FILES TO SEND/` or other staging/export folders prepared for manual sharing
- installer-built `dist/` or `build/` output
- stale installer output from `installer/output/`
- crash dumps, merge rejects, or backup files such as `*.dmp`, `*.orig`, `*.rej`, and `*.bak`
- session logs containing private local paths unless explicitly requested for support

## Repository hygiene

The repository intentionally excludes generated builds, installer output, local browser bundles, cache folders, scratch directories, staging/export folders, and local downloaded paint pools.

The no-browser public-showroom path in the current release does not require shipping an embedded browser, but local runtime data can still contain account-linked or machine-specific information and should not be committed.
