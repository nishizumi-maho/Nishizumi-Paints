# Nishizumi Paints

<img width="524" height="524" alt="Nishizumi Paints icon" src="https://github.com/user-attachments/assets/b3a5d4a8-3808-4696-8503-26c416f86f33" />

Nishizumi Paints is a Windows desktop companion for iRacing. It watches live sessions, downloads Trading Paints liveries, fills missing car, helmet, and suit assets from online or local fallback sources, and gives you manual control over individual drivers from the Session table.

[Download the latest release](https://github.com/nishizumi-maho/Nishizumi-Paints/releases/latest)
;
[Read the manual](./docs/wiki/Home.md)
;
[View the changelog](./CHANGELOG.md)
;
[Security policy](./SECURITY.md)

## Requirements

- Windows 10 or Windows 11
- iRacing
- Internet access for Trading Paints and public showroom downloads

## Install or update

1. Download the latest `NishizumiPaints-Setup-*.exe` from [Releases](https://github.com/nishizumi-maho/Nishizumi-Paints/releases/latest).
2. Run the installer.
3. Keep startup/background options enabled if you want monitoring to continue from the tray.
4. Finish the Quick Start wizard after first launch.

Upgrades use the same app ID and install path, so a newer installer can be run over an existing installation.

## What's new in 7.1 experimental

- Manual Showroom collection imports now keep all downloadable public collection paints, including public paints owned by Pro users or paints with stamped numbers, instead of using the stricter online-fallback filter.
- The Session table `Random` action now honors Local mode and pulls from the Local RandomPool when Online fallback is disabled.
- First-run setup keeps the iRacing Documents folder automatic unless detection fails; Advanced mode exposes a `Customize iRacing Documents folder` checkbox for manual paths.
- Double-click camera switching from the Session table now targets the selected driver with the Chase camera.
- The 7.0 Team-session fallback, driver-swap, multi-select Session actions, favorites/blocklist, and paint-history restore work remain included.

## Session table quick guide

- Select one driver to manage that driver's car, helmet, or suit.
- Use `Ctrl+click` to toggle multiple drivers, or `Shift+click` to select a range.
- Compatible Session actions apply to every selected driver that can use that action.
- Double-click a driver row to switch the in-game iRacing camera to that driver's car using Chase.
- Use `Random` to fetch a new random fallback result for the selected item.
- Use `Favorite` or `Block` when the selected item came from a random fallback source.
- Use `Restore previous` to put back the last saved local paint-history snapshot.
- Use `Forget` to clear fixed override memory and return to the real Trading Paints or restored history source when available.

## Random fallback quick guide

1. In **Random Step 1**, choose which targets can receive fallback paints: cars, helmets, suits, real drivers, and AI.
2. In **Random Step 2**, choose the preferred source: `Online` for public showroom downloads or `Local` for the RandomPool.
3. In **Random Step 3**, choose public showroom sources and manage the Local RandomPool.

The Local RandomPool can be filled from manual Showroom imports, collections, or optional recycling of downloaded session car paints.

## Team session quick guide

The recommended 7.1 experimental Team fallback order is:

1. Team paint for the item.
2. Current driver's personal paint for the same item, if the matching General-tab fallback option is enabled.
3. Random fallback, if the target is eligible.
4. iRacing default.

The Team driver-personal fallback options are split by car, suit, and helmet. Preloading is enabled by default so driver swaps can apply cached personal paints faster.

## Showroom tools

Open **Showroom** when you want to pre-fill paints manually instead of waiting for a live session fallback.

- **Car** downloads random public non-PRO paints for one mapped iRacing car.
- **Member ID** downloads a known member's car, helmet, and suit paints.
- **Teams** downloads known Team paints.
- **Showroom links** accepts one or more Trading Paints paint links.
- **Collection** imports usable public paints from a Trading Paints collection.

## Privacy notes

The normal 7.1 experimental online fallback path is browserless and does not require a Trading Paints login, password, cookie, token, or browser profile. Runtime data such as settings, paint history, RandomPool files, collection caches, and local iRacing paint folders should stay local and should not be committed.

## Run from source

```powershell
python .\Nishizumi_Paintsv6_nobrowser.py
```

## Build from source

```powershell
.\scripts\build_nobrowser_dir.bat
.\scripts\build_installer.bat
```

## Documentation

The full manual is versioned in [`docs/wiki`](./docs/wiki/Home.md). It covers installation, every tab, runtime behavior, online fallback, RandomPool, collections, AI flows, tray/headless operation, troubleshooting, privacy, and the source-code layout.

## Support

Please use GitHub Issues for bug reports and feature requests.
