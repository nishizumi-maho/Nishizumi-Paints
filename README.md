# Nishizumi Paints
<img width="524" height="524" alt="image" src="https://github.com/user-attachments/assets/b3a5d4a8-3808-4696-8503-26c416f86f33" />


Nishizumi Paints is a Windows desktop companion for iRacing that downloads Trading Paints liveries, applies them automatically, and fills missing car, helmet, and suit assets with configurable random fallback sources.

[Download the latest release](https://github.com/nishizumi-maho/Nishizumi-Paints/releases/latest)
;
[Read the full manual](./docs/wiki/Home.md)
;
[View the changelog](./CHANGELOG.md)
;
[Read the unofficial Trading Paints API notes](./trading_paints_unofficial_api_sdk.md)
;
[Security policy](./SECURITY.md)

## Requirements

- Windows 10 or Windows 11
- iRacing
- Internet access for Trading Paints and public showroom downloads

## Install

1. Download the latest setup executable from the [Releases](https://github.com/nishizumi-maho/Nishizumi-Paints/releases/latest) page.
2. Run the downloaded `NishizumiPaints-Setup-*.exe`.
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

## Using the 6.5 Showroom tools

Open **Showroom** when you want to pre-fill paints manually instead of waiting for a live session fallback.

### Choose Showroom sources

In **Advanced mode**, enable the public Showroom sources the app may use:

- **Trending**
- **Newest**
- **Most favorited**
- **Most raced (ever)**

If more than one source is enabled, Nishizumi Paints randomly chooses one enabled source each time it fetches a public random paint. New or missing configs default to all four sources enabled.

### Download random paints for one car

1. Open **Showroom**.
2. Use the **Car** tab.
3. Click the **Car** field and choose a car from the dropdown, or type part of the car name to filter suggestions.
4. Choose how many paints to download and the max page scan limit.
5. Click **Download to RandomPool**, or choose a custom folder first and click **Download to custom folder**.

### Download a member's paints

Use **Showroom > Member ID** when you know a Trading Paints/iRacing member ID.

- To download one car: enter the Member ID, choose the car, then click **Download car to iRacing paints** or **Download car to custom folder**.
- To download everything found for that member: enter only the Member ID, then use the **Download everything** box and click **Download ALL member paints...**. The app saves all returned cars, helmets, and suits into an organized member folder.

### Download a team's paints

Use **Showroom > Teams** when you know a Trading Paints team ID.

- To download one car: enter the Team ID, choose the car, then click **Download to iRacing paints** or **Download to custom folder**.
- To download everything found for that team: enter only the Team ID, then use the **Download everything** box and click **Download ALL team paints...**. The app scans mapped Trading Paints cars and saves found car, helmet, and suit assets into an organized team folder.

### Other Showroom tabs

- **Showroom links**: paste one or more Trading Paints paint links, one per line.
- **Collection**: paste a Trading Paints collection URL or ID to download usable public non-PRO paints from that collection.

### Local RandomPool recycle option

The **Recycle downloaded TP car paints into the local random pool** checkbox is off by default. Leave it off if you only want live downloads to be used for the current workflow. Turn it on if you want downloaded Trading Paints car paints to be archived into the local RandomPool for future fallback reuse.

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
