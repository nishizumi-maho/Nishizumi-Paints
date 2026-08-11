# iRacing UI Car Previews

This page explains how Nishizumi Paints keeps your own paints visible in the iRacing UI 3D car viewer, and how to troubleshoot it.

## What this feature is

The iRacing UI has a 3D car viewer under `My Content > Cars > <vehicle>`. It renders the same custom paint files the sim uses, read straight from the iRacing paint folder:

| Asset | File |
| --- | --- |
| Car paint | `Documents\iRacing\paint\<car directory>\car_<customer id>.tga` |
| Custom number | `Documents\iRacing\paint\<car directory>\car_num_<customer id>.tga` |
| Spec map | `Documents\iRacing\paint\<car directory>\car_spec_<customer id>.mip` |
| Decal control | `Documents\iRacing\paint\<car directory>\decal_<customer id>.tga` |
| Helmet | `Documents\iRacing\paint\helmet_<customer id>.tga` |
| Suit | `Documents\iRacing\paint\suit_<customer id>.tga` |

The UI reloads the viewer as soon as one of those files changes on disk. If the file is missing, the UI falls back to the default iRacing livery.

Before 7.3, those files only existed while a live session was running, and session cleanup removed them again afterwards, so the previews were only correct by accident. Nishizumi Paints now owns them explicitly.

## How Nishizumi Paints keeps the previews correct

1. It resolves your iRacing customer ID (see below).
2. It reads your personal Trading Paints manifest.
3. It mirrors your own assets into `%APPDATA%\Nishizumi-Paints\UiPreviewCache\<customer id>`.
4. It installs that mirror into the iRacing paint folder whenever iRacing is idle.
5. It re-installs the mirror right after every session cleanup pass.

Because step 4 reads from a local mirror, the previews are restored instantly and work with no internet connection.

### What is included

Only your own personal assets are used:

- Team paints are excluded. They are written as `car_team_<team id>.tga`, which the UI viewer never reads.
- Superspeedway variants are excluded. The viewer always renders the standard paint.
- When a car has several manifest entries for the same asset type, the freshest one wins, matching the session pipeline's own selection rules.

### What it never does

- It never runs while a session is being processed, so it cannot compete with the live paint pipeline.
- It never edits any iRacing setting.
- It never deletes a file it did not install. Removal is signature checked, so a paint you made by hand or another tool installed is left alone.

## Customer ID detection

The viewer only ever renders `car_<customer id>.tga`, so the wrong ID means silently empty previews. The ID is resolved in this order:

1. The manual override in `General > iRacing UI car previews`.
2. The live iRacing session, when iRacing is running.
3. The Trading Paints member ID from the Showroom tab.
4. The AI roster member ID from the AI tab.
5. A confirmed Trading Paints login.
6. The ID remembered from a previous run.

The last entry is what lets the previews work before iRacing has been started even once in the current Windows session.

If none of these is known yet, the status line reads `Waiting for your iRacing customer ID`. Join any iRacing session once, or type the ID into the override field.

## Controls

The panel lives in `General > iRacing UI car previews`, and a compact version is on the Easy screen.

| Control | Meaning |
| --- | --- |
| `Always show my paints in the iRacing UI car previews` | Master switch. On by default. |
| `Re-check Trading Paints every N minutes` | How often the manifest is re-read. Default 30, range 5 to 1440. |
| `iRacing customer ID` | Optional override. Leave empty for automatic detection. |
| `Sync previews now` | Forces an immediate manifest re-read and re-install. |
| Status line | Live state, car count, resolved customer ID and its source, and last check time. |

Command line and headless equivalents:

- `--no-ui-previews` starts the app with the feature turned off.
- The headless control command `sync_ui_previews` forces a sync.
- The headless `status` response includes `ui_preview_state`, `ui_preview_message`, `ui_preview_member_id`, and `ui_preview_cars`.

## Refresh behavior

- A manifest re-read runs at startup, when the customer ID changes, when you press `Sync previews now`, and on the configured interval.
- An asset is only re-downloaded when its Trading Paints manifest URL actually changes.
- A local re-install check runs about every 20 seconds while iRacing is idle. It compares a recorded file signature, so an unchanged file costs one `stat` and no copying.
- A paint removed from your Trading Paints account stops being previewed, and its file is removed from the iRacing paint folder.

## Custom Number paints

iRacing only uses `car_num_<customer id>.tga` when `Hide car numbers` is enabled in `iRacing Settings > Graphics`. That option is stored as `hideCarNum` in the `[Graphics]` section of `Documents\iRacing\app.ini`.

Nishizumi Paints reads that value read-only. When you have Custom Number paints synced but the option is off, the status line and the activity log say so. The app does not change the setting for you.

## Turning the feature off

Turning the switch off removes the preview files the app installed and stops managing them. The local mirror is kept, so switching the feature back on re-installs everything without downloading again.

## Troubleshooting

| Symptom | Cause and fix |
| --- | --- |
| Status says `Waiting for your iRacing customer ID` | No ID source is known yet. Join an iRacing session once, or fill the override field. |
| Status shows a Trading Paints manifest error | Trading Paints was unreachable. The app retries automatically after about two minutes. |
| Status says only some files could be put in place | One or more assets could not be downloaded, often because a paint is Pro-only or was removed. The rest are still previewed and the missing ones are retried. |
| Preview shows the number stamped by iRacing instead of your custom number art | Enable `Hide car numbers` in `iRacing Settings > Graphics`. |
| The preview does not change after you switch your active paint on the Trading Paints website | Press `Sync previews now`, or wait for the next interval. |
| Previews disappear after a session | Check that the feature is still enabled. The app re-installs the files after every cleanup pass, normally within a few seconds of the session ending. |

## Related pages

- [General Tab](General-Tab)
- [Runtime Paths and Files](Runtime-Paths-and-Files)
- [Session and Download Pipeline](Session-and-Download-Pipeline)
- [Troubleshooting](Troubleshooting)
