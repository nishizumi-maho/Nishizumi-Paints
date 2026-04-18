# Installation and Updating

## Install from a release

1. Download the latest setup executable from the Releases page.
2. Run the installer.
3. Leave the startup option enabled if you want the app to launch when you sign in.
4. Leave the background option enabled inside the app if you want monitoring to continue when the main window is closed.
5. Finish the Quick Start wizard after first launch.

## What the installer does

The installer writes the application into:

- `%LocalAppData%\Programs\Nishizumi Paints`

It can also configure:

- a desktop shortcut
- a `Run` entry in `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`

The installer and the app now cooperate on the same autostart entry. That matters because:

- a new install can set the initial default
- a later change inside the app updates the same Windows startup slot
- upgrades do not create duplicate startup entries

## Upgrade an existing installation

The installer uses the same app ID and install path, so a newer setup executable can be installed over the existing version.

Typical flow:

1. download the new setup executable
2. run it
3. let it replace the app files in place
4. launch the updated build

User configuration, cached pools, mapping overrides, and other runtime data stay in the Roaming AppData config area, not in the install folder.

## Source run

```powershell
python .\Nishizumi_Paintsv6_nobrowser.py
```

## Source build

Build the onedir application:

```powershell
.\scripts\build_nobrowser_dir.bat
```

Build the installer:

```powershell
.\scripts\build_installer.bat
```

## Installed build versus source build

Installed builds are for normal users. Source builds are useful when:

- testing local code changes
- verifying the PyInstaller packaging
- preparing a new release
- debugging runtime-path issues

The release build ships the icon assets and bundled showroom mapping seed from the repository `assets/` and `data/` folders.
