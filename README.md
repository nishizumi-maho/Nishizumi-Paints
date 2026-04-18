# Nishizumi Paints

Nishizumi Paints is a Windows desktop companion for iRacing that downloads Trading Paints liveries, applies them automatically, and fills missing car, helmet, and suit assets with configurable random fallback sources.

[Download the latest release](https://github.com/nishizumi-maho/Nishizumi-Paints/releases/latest)
[Read the full manual](./docs/wiki/Home.md)
[View the changelog](./CHANGELOG.md)
[Security policy](./SECURITY.md)

## Requirements

- Windows 10 or Windows 11
- iRacing
- Internet access for Trading Paints/public showroom downloads

## Installation

1. Download the latest installer from the [Releases](https://github.com/nishizumi-maho/Nishizumi-Paints/releases/latest) page.
2. Run `NishizumiPaints-Setup-6.0.0.exe`.
3. Leave the startup/background options enabled if you want the app to keep monitoring in the tray.
4. Finish the Quick Start wizard on first launch.

## Updating

1. Download the newest installer from the [Releases](https://github.com/nishizumi-maho/Nishizumi-Paints/releases/latest) page.
2. Run it over the existing installation.
3. The installer reuses the same app ID and installation path, so upgrades are handled in place.

## First launch

The app will guide you through:

- choosing **Easy mode** or **Advanced mode**
- confirming the iRacing Documents folder
- selecting safe defaults for downloads and fallback
- entering the iRacing member ID used for AI workflows

## What the app covers

- Live iRacing session monitoring
- Automatic Trading Paints downloads
- Public showroom fallback for cars, helmets, and suits
- Local random pool fallback
- Collection-based RandomPool seeding
- AI roster sync and AI session support
- Session overrides, fixed paints, and quick randomization
- Headless/background operation
- Tray icon control with restore and exit actions

## Running from source

```powershell
python .\Nishizumi_Paintsv6_nobrowser.py
```

## Building

Build the application directory:

```powershell
.\build_nobrowser_dir.bat
```

Build the installer after the app build:

```powershell
.\build_installer.bat
```

## Documentation

The full manual is versioned in [`docs/wiki`](./docs/wiki/Home.md) and covers:

- Quick Start
- every app tab
- online fallback behavior
- RandomPool and collection workflows
- background/headless operation
- troubleshooting and release maintenance

## Support

Please use GitHub Issues for bug reports and feature requests.
