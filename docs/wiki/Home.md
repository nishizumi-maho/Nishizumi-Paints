# Nishizumi Paints Wiki

This folder is the versioned source of the Nishizumi Paints manual. It is written to stand on its own inside the repository and can also be mirrored to a GitHub wiki later.

Nishizumi Paints is a Windows desktop companion for iRacing. It watches live sessions, downloads normal Trading Paints liveries, fills gaps with configurable random fallback sources, manages AI rosters, and keeps the whole workflow usable for both casual and advanced users.

## What the app does

- monitors the iRacing SDK and reacts to session changes
- downloads real Trading Paints assets when they exist
- applies public-showroom fallback for cars, helmets, and suits when they do not
- keeps a local RandomPool for reusable fallback assets
- supports per-driver overrides and quick randomization from the Session tab
- syncs AI rosters and AI livery assets
- runs in Easy mode, Advanced mode, tray/background mode, and headless mode

## Recommended reading order

1. [Installation and Updating](Installation-and-Updating)
2. [Quick Start Wizard](Quick-Start-Wizard)
3. [General Tab](General-Tab)
4. [Session Tab](Session-Tab)
5. [Random Tab](Random-Tab)
6. [Showroom Tab](Showroom-Tab)
7. [Online Fallback System](Online-Fallback-System)
8. [Local RandomPool](Local-RandomPool)
9. [Showroom Mapping and Collections](Showroom-Mapping-and-Collections)
10. [AI Tab](AI-Tab)
11. [Background and Headless Modes](Background-and-Headless-Modes)
12. [Troubleshooting](Troubleshooting)

## Core concepts

### Normal Trading Paints downloads

If a driver already has a usable Trading Paints paint for the current car and session, Nishizumi Paints downloads it through the normal manifest flow and installs it into the iRacing paint folder.

### Public online fallback

If a driver does not have a usable Trading Paints paint, the app can fetch a public showroom paint directly. This is the main no-browser online fallback path, including cars, helmets, and suits.

### RandomPool

The RandomPool is the local reusable fallback cache. It can be filled manually from the Showroom tab, from collection imports, or from optional recycling of session paints.

### Collection pool

The app can also cache paints from Trading Paints collections. This is useful for curated themed sets that should be reused locally without relying on a live session fetch. When normal public showroom coverage is disabled, the app now keeps reusing the selected collection paints within the same session instead of leaving later targets unchanged.

### Per-driver memory

The Session tab can remember fixed overrides for a driver. It can also forget them. Forgetting now restores a driver back to the real Trading Paints paint if the driver had one and only clears fallback memory when the driver did not.

## User-interface modes

### Easy mode

Easy mode keeps only the basic screen visible:

- current status
- startup/background behavior
- basic random fallback controls
- the minimum options needed for a new or casual user

### Advanced mode

Advanced mode exposes the full tab set:

- Session
- General
- AI
- Random
- Showroom
- Logs

You can switch between Easy mode and Advanced mode at any time from inside the app.

## Architecture references

For code-oriented documentation, also read:

- [Architecture Overview](Architecture-Overview)
- [Runtime Paths and Files](Runtime-Paths-and-Files)
- [Session and Download Pipeline](Session-and-Download-Pipeline)
- [Source Code Map](Source-Code-Map)
- [`trading_paints_unofficial_api_sdk.md`](../../trading_paints_unofficial_api_sdk.md)
