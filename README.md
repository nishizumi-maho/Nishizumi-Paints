# Nishizumi Paints

Nishizumi Paints is a Windows desktop companion for iRacing that downloads Trading Paints liveries, applies them automatically, and fills missing car, helmet, and suit assets with configurable random fallback sources.

[Download the latest release](https://github.com/nishizumi-maho/Nishizumi-Paints/releases/latest)
[Read the full manual](./docs/wiki/Home.md)
[View the changelog](./CHANGELOG.md)
[Read the unofficial Trading Paints API notes](./trading_paints_unofficial_api_sdk.md)
[Security policy](./SECURITY.md)

## Requirements

- Windows 10 or Windows 11
- iRacing
- Internet access for Trading Paints and public showroom downloads

## Install

1. Download the latest setup executable from the [Releases](https://github.com/nishizumi-maho/Nishizumi-Paints/releases/latest) page.
2. Run `NishizumiPaints-Setup-6.3.0.exe`.
3. Keep the startup and background options enabled if you want the app to keep monitoring from the tray.
4. Finish the Quick Start wizard after first launch.

## Update

1. Download the newest setup executable from the [Releases](https://github.com/nishizumi-maho/Nishizumi-Paints/releases/latest) page.
2. Run it over the existing installation.
3. The installer reuses the same app ID and install path, so upgrades are performed in place.

## First launch

The Quick Start wizard covers:

- Easy mode or Advanced mode
- iRacing Documents folder detection
- safe fallback defaults
- AI member ID setup
- startup and background behavior

## Run from source

```powershell
python .\Nishizumi_Paintsv6_nobrowser.py
```

## Build from source

Build the application directory:

```powershell
.\scripts\build_nobrowser_dir.bat
```

Build the installer after the app build:

```powershell
.\scripts\build_installer.bat
```

## Documentation

The full manual is versioned in [`docs/wiki`](./docs/wiki/Home.md). It covers installation, every tab, runtime behavior, online fallback, RandomPool, collections, AI flows, tray/headless operation, troubleshooting, and the source-code layout.

## Support

Please use GitHub Issues for bug reports and feature requests.
