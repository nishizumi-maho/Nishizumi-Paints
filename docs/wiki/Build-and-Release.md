# Build and Release

## Main source file

The current main no-browser release script is:

- `Nishizumi_Paintsv6_nobrowser.py`

## Local build steps

1. Build the application directory:

   ```powershell
   .\build_nobrowser_dir.bat
   ```

2. Build the installer:

   ```powershell
   .\build_installer.bat
   ```

## Installer output

The Inno Setup build writes the release setup executable into:

- `installer/output`

## Repository hygiene

Generated folders and local runtime caches are intentionally ignored:

- `build/`
- `dist/`
- `installer/output/`
- `embedded_browser/`
- `nishizumi_paints_showroom_downloads/`

## Release notes source

`CHANGELOG.md` is the canonical user-facing change history used for release notes.
