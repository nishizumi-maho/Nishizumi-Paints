# Session Tab

The Session tab is the live control surface for the current iRacing session.

## What it shows

- current session drivers
- car, helmet, and suit status per driver
- iRacing metadata such as iRating, license, and number
- live state changes while downloads, saves, and fallback actions are happening

## Driver-level actions

For a selected driver, the app can expose:

- **Open TP**
- **Assign link**
- **Assign current**
- **Random**
- **Forget**

These actions are available per asset type where supported.

## Random

The Session tab Random action picks a fresh compatible paint for that driver and applies it immediately. In 6.0.0, this also triggers a texture reload correctly instead of waiting for a manual refresh.

## Forget

Forget now behaves differently depending on what the driver is using:

- if the driver had a manual override and also has a real Trading Paints asset, the app restores the original asset
- if the remembered source was only a fallback choice, the app simply stops remembering it for later sessions

## Session changes

The app now refreshes the Session tab more reliably when the active iRacing session changes, instead of leaving stale rows behind.
