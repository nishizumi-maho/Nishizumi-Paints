# Installation and Updating

## Install from release

1. Download the latest setup executable from the Releases page.
2. Run the installer.
3. Keep the startup option enabled if you want the app to launch when you sign in.
4. Finish the Quick Start wizard after first launch.

## Upgrade an existing installation

The installer uses the same app ID and install path, so you can install a new version over the previous one.

Typical update flow:

1. Download the newer setup executable.
2. Run it.
3. Let the installer replace the existing app files.
4. Launch the updated build.

## What the installer configures

- application files under `%LocalAppData%\Programs\Nishizumi Paints`
- optional desktop shortcut
- optional Windows sign-in startup entry

## Installer versus app settings

The installer can set the initial startup preference, but the app becomes the source of truth after the user starts saving settings inside the app.

## Run from source

```powershell
python .\Nishizumi_Paintsv6_nobrowser.py
```

## Build from source

```powershell
.\build_nobrowser_dir.bat
.\build_installer.bat
```
