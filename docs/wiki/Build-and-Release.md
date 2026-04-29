# Build and Release

This page documents the repository layout and the local steps used to build and package the no-browser app.

## Current main entrypoint

The supported application script is:

- `Nishizumi_Paintsv6_nobrowser.py`

## Repository layout

Important top-level folders now include:

- `assets/icons/`
  bundled icon files used by the app and installer
- `data/`
  bundled data files such as the showroom mapping seed
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
- `data/tp_showroom_mapping.seed.json`

Those resources are resolved at runtime through the script’s bundled-resource helpers so the same code works from source and from PyInstaller output.

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
4. keep root-level repository noise low
5. avoid shipping local caches, tokens, browser profiles, Playwright captures, staging folders, or downloaded paint folders
6. upload only the freshly generated installer from the cleaned `installer/output/` folder
