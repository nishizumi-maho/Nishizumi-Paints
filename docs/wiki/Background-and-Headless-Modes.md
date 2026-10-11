# Background and Headless Modes

Nishizumi Paints is designed to keep monitoring without forcing the user to keep a large window open the whole time.

## Tray behavior

When the app is running in the tray:

- right-click opens a menu with `Open app` and `Exit`
- double-click with the left mouse button restores the main window

This makes background use practical for users who want the app always available but mostly out of sight.

## Keep running in background on close

This setting changes what happens when the user closes the main window:

- enabled: close hides to the tray and the monitor keeps running
- disabled: close actually shuts the app down

This option is exposed both in Advanced mode and in the Easy mode General box so users do not need to switch modes just to control it.

## Start with Windows

The app can register itself in the per-user Windows startup entry. The installer can set the initial value, and the app can later update the same registry entry.

## Start minimized

This is useful for users who want the app to launch on sign-in and immediately stay out of the way.

## Single-instance behavior

The script includes a single-instance lock and a signal server so a second launch does not create a separate competing monitor process.

The lock is checked before anything else. Opening the app while it is already running, for example from the tray after it started with Windows, brings the running copy forward without showing the startup mode selector. The one exception is a window opened while the headless service runs: it attaches to the service as a settings controller (see below).

## Startup mode selector

The first start asks whether to open the normal window or run console-only (headless). **Remember this choice** is ticked by default, and the choice is saved as `launch_mode_preference` in `settings.json`.

- With a saved choice the app starts straight in that mode.
- Holding `Shift` while opening the app shows the selector again, also while the app is already running.
- `--gui` and `--nogui` always win over the saved choice.
- A start with Windows never asks: it uses the saved choice, or the normal window when none is saved.
- Switching to headless or back from inside the window saves that mode as the new choice.

The startup mode is written on its own, without rewriting other settings, and a running window reads it from disk whenever it saves its settings. A copy that was already running can therefore never write an older startup mode back over a newer choice. `settings.json` is replaced in one step, and a read that lands while another copy is saving is tried again.

## Headless mode

The code also contains a headless control server and launch-mode handling. Headless mode is intended for users who want monitoring behavior without the full interactive window.

That matters for:

- autostart scenarios
- service-like usage
- keeping the app available while relying mostly on logs and tray controls

### Headless control commands

The local control server accepts these commands:

| Command | Effect |
| --- | --- |
| `ping` / `hello` | Confirms the headless service is reachable and reports the app version. |
| `status` | Reports service state, the current session, and the iRacing UI preview state. |
| `reload_config` | Re-reads `settings.json` and applies it to the running service. |
| `sync_ui_previews` | Forces an immediate iRacing UI car preview sync. |
| `check_updates` | Checks GitHub for a new version now, even when automatic checks are off. |
| `install_update` | Downloads, verifies, and installs the newest release, then restarts the service in headless mode. |
| `stop` | Shuts the headless service down. |

The `status` response includes `ui_preview_state`, `ui_preview_message`, `ui_preview_member_id`, and `ui_preview_cars`, so preview health is visible without the full window. The GUI shows the same information when it attaches to a running headless service.

It also includes `update_state` (`idle`, `checking`, `up_to_date`, `available`, `downloading`, `installing`, or `failed`), `update_message`, `latest_release_tag`, and `update_available`.

### Updates in headless mode

The headless service checks for updates on its own, following the same settings as the window:

- With **Check for updates automatically** on, it checks GitHub about 20 seconds after starting and then every 6 hours. A failed check is retried after 15 minutes, which covers a start with Windows before the network is up.
- A new version is written to the console and announced with a Windows notification from a tray icon. Clicking the notification installs it. The tray icon also offers `Open app`, which brings the console forward, and `Exit`.
- With **Install updates automatically** on, it installs the update without asking.

Installing downloads the installer only from GitHub's release hosts, checks its SHA-256 digest against the one published with the release, runs it silently, and stops the service. The installer then starts the app again with `--nogui`. Builds that cannot install by themselves, such as running the script from source, point to the release page instead.

A window attached to the headless service leaves updates to the service. **Download and install** in that window hands the update to the service and closes the window, and the window also closes when the service shuts down to install an update, so nothing holds the installer up.

### Headless command line switches

- `--nogui` runs without the built-in UI.
- `--keep-session-paints` keeps live session paints instead of cleaning them up.
- `--no-ui-previews` turns the always-on [iRacing UI car previews](iRacing-UI-Car-Previews) off for that run.
- `--iracing-documents-dir <folder>` (old name `--paints-dir`) uses another iRacing documents folder, the one that holds `paint`, `replay` and `airosters`. Passing its `paint` folder works too. Paints always go into that `paint` folder, because it is the only place iRacing reads them from.
- `--temp-dir <folder>` keeps downloads in progress in a `NishizumiPaints` folder inside the folder given, instead of in the system temp folder.
- `--poll-seconds`, `--retries`, `--retry-backoff-seconds`, `--max-concurrent-manifests` and `--max-concurrent-downloads` override those settings for that run, and `-v` turns on debug logging.

`--session-yaml`, `--watch` and `--iracing-sdk` are still accepted so old shortcuts keep working, but they do nothing: the app always reads the live iRacing session.

## Interaction with Easy and Advanced mode

UI mode does not disable background or headless behavior. Easy mode only reduces visible complexity. The background monitor and tray logic still run the same core service underneath.
