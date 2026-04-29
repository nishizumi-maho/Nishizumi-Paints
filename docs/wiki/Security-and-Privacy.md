# Security and Privacy

This page summarizes what the app stores locally, what should not be committed, and how the repository is kept clean.

## What the app stores locally

The app can store:

- settings
- recent-scheme state
- driver override memory
- showroom mapping overrides
- RandomPool content
- collection-pool content
- AI roster metadata
- manually downloaded team paint files

These are runtime files and are not intended for source control.

## What should not be committed

Do not commit:

- local downloaded paint pools
- browser profiles
- tokens or cookies
- `settings.json`
- installer output
- `.playwright-cli/` captures
- `FILES TO SEND/` or other manual staging/export folders
- crash dumps and merge/backup artifacts such as `*.dmp`, `*.orig`, `*.rej`, and `*.bak`
- local temp folders
- logs containing private local paths unless a support workflow explicitly asks for them

## Repository hygiene

The repository intentionally keeps:

- bundled resources in `assets/` and `data/`
- build helpers in `scripts/`
- user docs in `docs/wiki/`
- historical material in `archive/`

It intentionally ignores:

- build output
- installer output
- scratch directories
- imported staging folders

## Current release posture

The main online fallback path uses public showroom direct downloads. That reduces the need to package or ship browser automation just to make public fallback work.

The 6.2.0 manual team downloader also stays browserless. It sends the entered Team ID, resolved car directory, optional requesting/driver member IDs, and car number to Trading Paints manifest endpoints. It does not store Trading Paints passwords, cookies, or tokens.

## Responsible debugging

When reporting problems, try to share:

- the relevant log excerpt
- the affected release version
- the exact action that triggered the problem

Avoid sharing full local profile data unless the issue specifically requires it.
