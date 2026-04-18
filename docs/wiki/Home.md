# Nishizumi Paints Wiki

Nishizumi Paints is a Windows desktop application for iRacing that automates Trading Paints downloads and fills missing liveries with configurable random fallback sources.

## What the app does

- Monitors live iRacing sessions
- Downloads normal Trading Paints liveries when they exist
- Applies manual overrides per driver
- Fills missing cars, helmets, and suits from the public showroom
- Uses a local RandomPool as a final offline-style fallback
- Syncs AI rosters
- Supports Easy mode, Advanced mode, tray/background use, and headless monitoring

## Recommended reading order

1. [Installation and Updating](Installation-and-Updating)
2. [Quick Start Wizard](Quick-Start-Wizard)
3. [Session Tab](Session-Tab)
4. [Random Tab](Random-Tab)
5. [Showroom Tab](Showroom-Tab)
6. [Background and Headless Modes](Background-and-Headless-Modes)
7. [Troubleshooting](Troubleshooting)

## Main concepts

### Normal Trading Paints download

If a driver already has a usable Trading Paints asset for the current car and session, Nishizumi Paints downloads and installs it normally.

### Online fallback

If a driver does not have a usable Trading Paints asset, the app can fetch public showroom paints directly. In the current 6.0.0 release, this is the main no-browser online fallback path.

### RandomPool

The local RandomPool is a cache of reusable fallback assets. It can be filled manually from the Showroom tab or by optional recycling of downloaded session paints.

### Fixed driver override

From the Session tab, you can force a specific car, helmet, or suit for a single driver. That override is remembered and wins over normal fallback logic.

## User interface overview

- **Easy mode** keeps the app focused on the essential monitor, status, and fallback controls.
- **Advanced mode** exposes the full tab set:
  - Session
  - General
  - AI
  - Random
  - Showroom
  - Logs

## Version notes

Version 6.0.0 is the release that consolidates the no-browser/public-showroom workflow, adds the installer, and introduces the Easy mode split.
