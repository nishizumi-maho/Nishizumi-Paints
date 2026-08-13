# Build and Release

This page documents the repository layout and the local steps used to build and package the no-browser app.

## Current main entrypoint

The supported application script is:

- `Nishizumi_Paintsv6_nobrowser.py`

## Repository layout

Important top-level folders now include:

- `assets/icons/`
  bundled icon files used by the app and installer
- `scripts/`
  local build helpers
- `installer/`
  Inno Setup script and output folder
- `docs/wiki/`
  versioned manual
- `archive/`
  historical scripts and legacy helpers

## Local build steps

Build the app directory:

```powershell
.\scripts\build_nobrowser_dir.bat
```

Build the installer:

```powershell
.\scripts\build_installer.bat
```

The installer helper clears the previous `installer/output/` folder before compiling so the release folder only contains fresh artifacts for the current version.

## Installer output

The Inno Setup build writes release installers into:

- `installer/output/`

## Bundled resources in the build

The current build packages:

- `assets/icons/nishizumi_paints_icon.ico`
- `assets/icons/nishizumi_paints_icon.png`

Car identity is not bundled. It is loaded automatically from the live Trading Paints template catalog.

## Building and publishing from GitHub

The `Release installer` workflow (`.github/workflows/release.yml`) does the same build on a `windows-latest` runner and publishes the result. Start it from `Actions > Release installer > Run workflow`, on the branch the release should be cut from.

One input, `tag_suffix`, which decides both the tag and the kind of release:

| `tag_suffix` | Result |
| --- | --- |
| empty | `v<version>`, published as a normal release. The in-app updater offers it. |
| `beta.1`, `rc.1`, ... | `v<version>-<suffix>`, published as a pre-release. The app asks GitHub for the *latest* release and GitHub never answers with a pre-release, so it is never offered by the updater: people download and run it themselves. |

The suffix alone decides, so a beta tag can never be published as a final release, or the other way round. Note that a `workflow_dispatch` input sent as an empty string falls back to its declared default, which is why the default here is empty rather than a suffix.

The run reads `APP_VERSION` from the script, so the version is never typed twice. It then compiles the app, checks the syntax, runs the unit tests, compiles the installer with the same Inno Setup script used locally, and publishes the release with:

- the installer from `installer/output/` as the only asset
- `docs/release-notes/<version>.md` as the release body, with a beta banner in front when the run is a pre-release
- the installer's SHA-256 appended in the format the in-app updater parses, so a full release can be installed from inside the app

A run fails instead of publishing when `APP_VERSION` is not a plain version number, when the tag suffix is not a valid tag fragment, when PyInstaller or Inno Setup produce nothing, or when the tag already exists.

## Ignored local output

Generated artifacts and local scratch areas are intentionally ignored:

- `build/`
- `dist/`
- `installer/output/`
- `.playwright-cli/`
- `wiki_tmp/`
- `FILES TO SEND/`
- `*.bak`, `*.orig`, `*.rej`, `*.dmp`, and `*.stackdump`
- downloaded paint pools and local browser bundles

## Release hygiene

Before publishing a release:

1. verify the script compiles
2. verify the onedir build works
3. verify the installer build works
4. run a tracked-file secret and privacy scan
5. keep root-level repository noise low
6. avoid shipping local caches, tokens, browser profiles, Playwright captures, staging folders, or downloaded paint folders
7. upload only the freshly generated installer from the cleaned `installer/output/` folder
