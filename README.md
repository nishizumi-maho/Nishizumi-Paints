# Nishizumi Paints

<img width="512" height="512" alt="nishizumi_paints_icon" src="https://github.com/user-attachments/assets/7ba4ccbc-7dfe-4b8c-abe2-182e3fd0254a" />

**Nishizumi Paints** is a lightweight Windows desktop app for **iRacing** that watches your current session through the **iRacing SDK**, downloads the correct **Trading Paints** files for the drivers in that session, installs them into your local iRacing paint folder, and optionally tells iRacing to refresh textures so the liveries appear in-game with as little manual work as possible.

The app is designed to be:

- **always active while open**
- **small and practical**
- **fast on large sessions**
- **safe to leave running in the background**
- **simple for normal users**
- **detailed enough for advanced users and debugging**

Nishizumi Paints includes a compact built-in UI, persistent settings, Windows auto-start support, single-instance protection, retry logic, adaptive download tuning, optional manual worker control, automatic cleanup behavior, and a detailed activity log.

---

## Table of contents

- [What the app does](#what-the-app-does)
- [Main features](#main-features)
- [How it works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [User interface overview](#user-interface-overview)
- [Detailed explanation of every option](#detailed-explanation-of-every-option)
- [Download workers](#download-workers)
- [TP worker monitor](#tp-worker-monitor)
- [Buttons and manual actions](#buttons-and-manual-actions)
- [Activity log and status messages](#activity-log-and-status-messages)
- [Advanced technical details](#advanced-technical-details)
- [Headless mode and command-line options](#headless-mode-and-command-line-options)
- [Build the EXE](#build-the-exe)
- [Files and folders used by the app](#files-and-folders-used-by-the-app)
- [Performance notes](#performance-notes)
- [Troubleshooting](#troubleshooting)
- [Known limitations](#known-limitations)
- [Privacy and network behavior](#privacy-and-network-behavior)
- [FAQ](#faq)

---

## What the app does

Nishizumi Paints continuously watches iRacing session data through the **iRacing SDK**.

When you join a session, the app:

1. reads the current session ID and driver list
2. identifies each driver's `UserID` and `CarPath`
3. asks Trading Paints which files exist for those users
4. filters those results so each driver only receives files that match the car currently being used in the session
5. downloads the needed files in parallel
6. extracts compressed files when needed
7. installs them into your local `Documents\iRacing\paint` folder
8. optionally tells iRacing to reload textures
9. keeps watching for session changes
10. optionally removes previously downloaded session files when they are no longer needed

The app is meant to reduce the usual manual workflow of:

- opening another downloader
- waiting for it to sync
- pressing `Ctrl+R`
- manually clearing old session files
- re-opening the same helper app again and again

---

## Main features

### Core functionality

- Watches iRacing sessions continuously while the app is open
- Uses the iRacing SDK by default
- Detects session changes automatically
- Downloads matching Trading Paints files for session participants
- Supports:
  - car paints
  - car decals
  - number layers
  - spec maps
  - helmets
  - suits
- Extracts `.bz2` paint files automatically
- Saves files into the correct local iRacing paint folders
- Can automatically trigger an iRacing texture reload
- Can remove downloaded session files when leaving a session or exiting iRacing
- Can preserve your own livery locally
- Can optionally refresh the current session manually with one button

### Reliability and stability

- Built-in retry logic for manifest requests and file downloads
- Exponential backoff on retries
- Session fingerprinting to avoid repeated work
- Duplicate removal before the final download phase
- Automatic stale temp cleanup on startup
- Atomic save/replace behavior to reduce partial-file issues
- Background watchdog that restarts the worker loop if it crashes unexpectedly
- One-instance protection to avoid multiple copies of the app running at once
- Re-open behavior that brings the existing app window into focus instead of launching duplicates

### UI and usability

- Small built-in desktop UI
- No Start/Stop workflow
- The app is considered active as long as it is open
- Optional activity log panel
- Optional verbose logging
- Optional TP worker monitor panel for throughput testing
- Windows auto-start support
- Start minimized when launched automatically by Windows
- Keep running in the Windows background area on close
- Manual “Refresh paints” action
- Manual “Clear downloaded” action
- One-click open paint folder action
- Manual or automatic download worker control

### Build and deployment

- Pure Python source
- Ready for PyInstaller one-file EXE builds
- Supports a custom app icon for the UI and the final EXE

---

## How it works

This section explains the full workflow from startup to session cleanup.

### 1. App startup

When the app starts, it loads the saved configuration from a JSON settings file stored in the user's app data folder.

It then:

- initializes logging
- prepares the background service
- creates the UI
- starts the background watcher automatically
- starts the single-instance listener
- optionally minimizes only when launched by Windows auto-start and `Start minimized` is enabled

If the app is opened manually by double-clicking it, it stays visible. The minimized startup behavior is only meant for automatic startup launches.

### 2. Single-instance protection

Nishizumi Paints is designed to allow only **one running instance**.

If the user opens the EXE again while one instance is already active:

- a second full copy is **not** launched
- the existing app is notified
- the existing window is brought to the front instead

This avoids duplicate background watchers, duplicate downloads, duplicate texture reloads, and general confusion.

### 3. SDK connection

The service tries to initialize the iRacing SDK.

There are two common outcomes:

- **iRacing is already running and connected to a session**: the service immediately begins watching and can process the session
- **iRacing is not running yet or not in a valid session**: the service stays alive and waits

This means Nishizumi Paints can be opened before iRacing and simply left running.

### 4. Session polling

The app periodically polls the SDK. It reads values such as:

- `WeekendInfo`
- `DriverInfo`
- `SessionInfoUpdate`
- `OkToReloadTextures` when a texture reload is needed

If the relevant session data has not changed since the last poll, the app does nothing. That prevents repeated work and unnecessary network traffic.

### 5. Session model creation

From the SDK data, the app builds an internal session object containing:

- the main session ID
- the sub-session ID if present
- a set of users in the current session
- each user's `UserID`
- each user's `CarPath`
- the local player's user ID when it can be determined

That local player identification is important for settings like:

- **Update my own paints**
- **Keep my livery locally**

### 6. Manifest lookups

For each user in the session, the app queries the Trading Paints manifest endpoint and asks which files exist for that specific `UserID`.

Those manifest lookups are performed in parallel. The number of manifest workers is derived from the download worker mode so the app remains balanced.

### 7. File matching

A user can have paints for several cars, but the current session only uses one car per driver.

To avoid installing the wrong files, Nishizumi Paints filters the manifest response using the driver's current `CarPath`.

Matching rules include:

- exact directory match
- normalized directory match for slight naming differences
- helmet and suit files are accepted independently of the car directory

### 8. Download queue building

After matching, the app builds the final queue of files that should be downloaded.

Before the first download starts:

- duplicates are removed
- the worker count is resolved
- progress totals become known in advance
- per-stage progress logging is prepared

### 9. Parallel downloads

Downloads are performed in parallel using worker threads.

Each file is first downloaded into a temp session folder rather than directly into the final iRacing paint folder. This helps with:

- cleanup
- crash recovery
- separation between sessions
- safer file replacement
- reduced risk of leaving partially written files in the live paint folder

If a request fails, automatic retry logic is used.

### 10. Extraction and install

After download:

- `.bz2` files are decompressed
- output filenames are mapped to iRacing's paint naming rules
- files are written atomically using a temporary destination and final replace operation

This reduces the chance of corrupt or half-written paint files.

### 11. Texture reload

If **Auto refresh paints** is enabled, the app tells iRacing to reload textures through the SDK.

It does not blindly spam reload requests. It checks whether iRacing reports that it is safe to reload textures.

If texture reload is not immediately allowed, the app waits and tries again.

### 12. Session cleanup behavior

When you leave a valid session, or when a new session replaces the current one, the app can remove previously downloaded files automatically.

This keeps the local paint folder from accumulating old session files forever.

If **Keep my livery locally** is enabled, the app can preserve your own files while still cleaning up the rest.

### 13. Background behavior on close

If **Keep running in background on close** is enabled and you click the window close button (`X`):

- the app does **not** exit
- the main window is hidden
- the app continues running in the Windows notification area / “Show hidden icons” area
- the background watcher keeps working

This is useful for users who want the app to stay active without leaving the main window visible.

### 14. Watchdog behavior

If the internal worker loop stops unexpectedly, the watchdog logs the event and restarts the background service loop.

This helps the app stay usable over long sessions and long-running desktop use.

---

## Requirements

### Operating system

- **Windows**

The UI, auto-start behavior, notification-area behavior, and EXE build flow are all aimed at Windows desktop usage.

### Python

- **Python 3.10+** recommended

### iRacing

- iRacing installed
- iRacing SDK accessible from the running environment

### Python packages

See [`requirements.txt`](requirements.txt).

At minimum, the runtime app uses:

- `requests`
- `PyYAML`
- `pyirsdk`

---

## Installation

### Option 1: run from Python source

1. Install Python
2. Clone or download this repository
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run the app:

```bash
python nishizumi_paints_single_instance_v5.py
```

### Option 2: build a Windows EXE

1. Install Python
2. Install dependencies:

```bash
pip install -r requirements.txt
pip install pyinstaller
```

3. Use the provided build batch file
4. Run the generated EXE

---

## Quick start

1. Launch **Nishizumi Paints**
2. Leave the default settings enabled if you want the easiest experience
3. Start iRacing
4. Join a session
5. The app will detect the session, fetch the necessary paints, install them, and refresh textures if enabled
6. Leave the app open in the background if desired

Recommended default usage:

- leave **Auto start** enabled
- leave **Start minimized** enabled if you want Windows startup to stay unobtrusive
- leave **Keep running in background on close** enabled
- leave **Auto refresh paints** enabled
- leave **Download workers mode** on **Auto**
- only enable **Verbose logs** when you actually need deeper diagnostics

---

## User interface overview

The app window is intentionally compact.

It is divided into three main areas:

### 1. Header

The top row shows:

- app name
- app version
- service status text

### 2. Settings area

The middle portion is divided into three groups:

- **General**
- **Session**
- **Downloads**

### 3. Actions and activity area

The lower portion contains:

- the **Clear downloaded** button
- the **Paint folder** button
- the optional **TP worker monitor** panel
- the **Activity** log panel

---

## Detailed explanation of every option

This section explains every checkbox and control in the UI.

### Auto start

When enabled, Nishizumi Paints registers itself to launch automatically when Windows signs in.

Use this if you want the app to always be available without launching it manually.

Default: **On**

### Start minimized

When enabled, Nishizumi Paints starts minimized **when launched by Windows auto-start**.

Important:

- if the app is launched manually, it stays visible
- this prevents confusing behavior when the user intentionally opens it themselves

Default: **On**

### Keep running in background on close

When enabled, clicking the `X` button hides the window instead of exiting the app.

The app continues running in the Windows notification area, commonly accessed through **Show hidden icons**.

This keeps the watcher active without leaving the main window visible.

Default: **On**

### Auto refresh paints

When enabled, the app attempts to trigger an iRacing texture reload after installing new paint files.

This reduces the need for manual refresh actions.

Default: **On**

### Update my own paints

When enabled, the app includes your own user in the Trading Paints sync process.

This is useful if you also want your own current livery pulled through the same workflow.

Default: **On**

### Keep my livery locally

When enabled, your own installed livery files are preserved when downloaded session files are cleaned up.

This is useful if you do not want your own files removed when the session changes or when cleanup runs.

Default: **On**

### Delete downloaded livery

When enabled, downloaded session files can be removed automatically when they are no longer needed.

This helps keep the iRacing paint folder cleaner and reduces disk clutter.

Default: **On**

### Show activity

Shows the activity panel in the UI.

This is useful for:

- normal visibility into what the app is doing
- quick troubleshooting
- checking whether a session has been detected

Default: **On**

### Show TP monitor

Shows the **TP worker monitor** panel.

This panel is meant for advanced testing. It helps estimate the effective parallelism Trading Paints is actually allowing in real sessions by comparing requested workers against observed throughput.

Use this when:

- you want to discover your practical worker ceiling
- you are tuning manual manifest, download, or save workers
- you want to compare Auto mode against Manual mode with real measurements

Because most users do not need it on every run, it is hidden by default.

Default: **Off**

### Verbose logs

Enables more detailed logging.

Verbose logging is useful for debugging but intentionally disabled by default so the app stays cleaner for normal users.

Default: **Off**

### Download workers mode

Lets you choose between **Auto** and **Manual**.

This controls how many concurrent download workers Nishizumi Paints uses.

Default: **Auto**

### Manual manifests, downloads, and saves

These controls are only used when **Download workers mode** is set to **Manual**.

In Manual mode, Nishizumi Paints lets you set three separate fixed worker counts:

- **Manual manifests**
- **Manual downloads**
- **Manual saves**

Allowed range for each:

- minimum: **1**
- maximum: **100**

If you set the values manually, the app will honor those exact numbers in every session until you change them again.

Example:

- manifests = **16**
- downloads = **20**
- saves = **16**

In that case, every session will use exactly those three values instead of auto-tuning.

Default values: **8 / 8 / 8**

---

## Download workers

Nishizumi Paints supports two worker modes.

### Auto mode

**Auto** is the default mode and the recommended option for most users.

In Auto mode, the app dynamically adjusts worker counts based on the current session size and workload. It does not only tune downloads. It also keeps the surrounding stages balanced so the pipeline stays efficient overall:

- manifest lookups are auto-sized
- downloads are auto-sized
- saves are auto-sized

The goal is to keep the downloader light on smaller sessions while still scaling up when there are more liveries to process. Auto mode is designed to balance:

- speed
- stability
- bandwidth usage
- responsiveness
- reduced manual micromanagement

Use Auto if you want the app to make the decision for you.

### Manual mode

If preferred, the downloader can be switched to **Manual** mode.

In Manual mode, you set three separate fixed values:

- **Manual manifests**
- **Manual downloads**
- **Manual saves**

Each can be set from **1 to 100**.

Once set, Nishizumi Paints will honor those exact values in every session instead of using adaptive behavior.

Examples:

- manifests = **12**, downloads = **16**, saves = **16**
- manifests = **16**, downloads = **20**, saves = **16**
- manifests = **25**, downloads = **25**, saves = **25**

If you set downloads to **20**, the app will keep using **20 download workers in every session** until you change it. The same applies to manifests and saves.

### Why manual mode exists

Manual mode is meant for advanced users who want repeatable, fixed behavior.

It is especially useful when you want to:

- benchmark different worker values on your own connection
- compare the real throughput of several presets
- cap the app to a conservative value for a slower connection
- force a specific worker level that you already know performs best on your setup
- tune manifest, download, and save stages separately instead of treating them as one number

### Why manifests and saves matter too

The pipeline is not just a download stage. It has three main worker-driven parts:

1. **Manifest lookups**: asks Trading Paints which files exist for each driver
2. **Downloads**: fetches the actual files
3. **Saves**: extracts and installs files into the iRacing paint folder

If only downloads are tuned while manifests or saves are too low, one of those stages can become the new bottleneck. Manual mode exists so advanced users can tune the full pipeline when needed.

### Which mode should I use

- Use **Auto** for the best plug-and-play behavior
- Use **Manual** if you specifically want fixed, repeatable values
- Use **Manual + TP worker monitor** if you want to discover your practical ceiling and find the best preset for your setup

### Notes

- Auto mode remains the safest general-purpose choice
- Manual mode does not auto-scale
- Higher manual values can increase bandwidth usage and network pressure
- Very high requested values do not always mean more real throughput
- The TP worker monitor exists to help you measure the effective parallelism you are actually getting

## TP worker monitor

The **TP worker monitor** is an advanced diagnostics panel that estimates how much real parallelism Trading Paints is effectively allowing in practice.

It is **hidden by default**. To show it, enable **Show TP monitor** in the UI.

### What it shows

After a completed session, the monitor summarizes:

- the last processed session ID
- whether you were using **Auto** or **Manual** mode
- the requested worker values for manifests, downloads, and saves
- total file count for that session
- download stage time
- save stage time
- files per second
- average time per file
- average download Mbps
- effective observed parallelism
- an approximate observed ceiling hint

### What the numbers mean

The key value is usually **effective parallelism**.

That number is an estimate of how many downloads were truly progressing in parallel based on observed stage timings. It is often much lower than the number you requested, especially when you ask for very high manual worker counts.

Example:

- requested downloads = **100**
- effective parallelism = **25.5**

That means the app asked for 100 workers, but the real observed behavior looked more like about 25 active parallel downloads.

### Why this is useful

The monitor helps you discover your **practical ceiling**. That ceiling might come from Trading Paints, your network, connection reuse, file sizes, or the full end-to-end path.

From a tuning perspective, that difference does not matter much. What matters is the real throughput you actually get.

### When to use it

Use the TP worker monitor when you want to:

- compare Auto mode against Manual mode
- find the best fixed manual worker preset
- understand whether downloads or saves are the current bottleneck
- verify whether very high worker counts are helping or just creating overhead

### When to leave it hidden

For normal daily usage, you can leave it hidden. The panel is mainly intended for advanced tuning and debugging.

### Reset TP monitor

The **Reset TP monitor** button clears the accumulated monitor snapshot so you can start a fresh comparison run.

This is useful when testing several presets back to back and you want the monitor to reflect only the newest data.

## Buttons and manual actions

Nishizumi Paints intentionally keeps the number of buttons small.

### Refresh paints

Requests a new download pass for the current session.

Use this when:

- you want to force another sync for the active field
- you know liveries changed and want another pass
- you want to validate a fix while testing

### Clear downloaded

Removes tracked downloaded files that belong to the app's managed session handling.

Use this when:

- you want to clear session-managed files immediately
- you are debugging a livery issue
- you want a clean state before testing again

### Paint folder

Opens the local iRacing paint directory in Windows Explorer.

Use this when:

- you want to inspect installed files manually
- you want to verify file names
- you want to compare what the app downloaded against what is already present

---

## Activity log and status messages

The activity log shows what the background service is doing.

Typical examples include:

- waiting for iRacing or a valid session
- processing a session
- manifest lookup progress
- download progress
- save progress
- cleanup actions
- SDK reload events
- watchdog recovery events

### Status text in the header

The header status may show states such as:

- `Starting`
- `Watching`
- `Processing`
- `Background`
- `Error`

Exact wording may vary slightly depending on the current build state.

### Progress-style logging

Nishizumi Paints includes stage progress messages to make debugging easier later.

Examples:

- `Manifest progress 3/12`
- `Download progress 7/20`
- `Save progress 7/20`

This helps identify:

- where a run is currently spending time
- whether problems happen before download, during download, or during file install
- how far a session got before an interruption

### Verbose logs

When `Verbose logs` is enabled, you may also see lower-level messages such as:

- SDK polling details
- unchanged session checks
- directory normalization matches
- retry timing information
- internal recovery notes

Because verbose mode is intended for diagnostics, it is **disabled by default**.

---

## Advanced technical details

This section is intentionally more detailed for advanced users and developers.

### Session fingerprinting

The app keeps an internal fingerprint made from:

- session identifiers
- driver user IDs
- driver car directories

If the fingerprint has not changed, the app skips reprocessing.

This prevents unnecessary repeat downloads and file writes.

### HTTP session reuse

The downloader reuses thread-local HTTP sessions with connection pooling.

This improves:

- efficiency
- connection reuse
- overall responsiveness during large batches

### Retry behavior

Manifest requests and downloads both use retry logic.

The retry strategy uses exponential backoff based on the configured base interval.

Typical pattern:

- attempt 1
- wait `1x`
- attempt 2
- wait `2x`
- attempt 3
- wait `4x`

This helps with transient network failures without permanently stalling the app.

### Temp folder strategy

Downloads are placed into a temp directory first, under a session-specific folder.

This gives the app:

- cleaner organization
- easier cleanup
- safer installs
- less risk of mixing old partial data into the live paint folder

### Atomic file writes

When possible, the app writes through a temporary destination and then replaces the final file atomically.

This reduces the chance of partially written visible files.

### Cleanup tracking

The app tracks which files it saved for the current managed session.

This is important because cleanup should target only the files the app installed as part of its tracked session process, not arbitrary unrelated files in the paint folder.

### Notification-area behavior

When the close behavior is enabled, the app hides to the Windows notification area instead of exiting.

This is the area commonly reached through the `Show hidden icons` button on the taskbar.

It is not meant as a desktop minimize action. The purpose is to keep the service alive without showing the full app window.

### Single-instance signal path

A small local inter-process signaling mechanism is used to bring the existing window back into focus if the EXE is launched again.

This prevents the classic problem of users opening multiple background helper copies by accident.

### Watchdog recovery

If the background loop stops unexpectedly, the watchdog:

- detects the stop
- logs the event
- attempts to restart the worker loop

This improves long-running stability.

---

## Headless mode and command-line options

Nishizumi Paints can also run without the built-in UI.

Example:

```bash
python nishizumi_paints_single_instance_v5.py --nogui
```

### Common options

#### `--nogui`

Runs the app without the desktop UI.

#### `--autostart-launched`

Internal flag used for Windows auto-start behavior. Normal users usually do not need to pass this manually.

#### `-v` / `--verbose`

Enables verbose logging.

#### `--poll-seconds`

Adjusts the SDK polling interval.

#### `--retries`

Sets how many retry attempts are allowed for manifest/download requests.

#### `--retry-backoff-seconds`

Sets the base retry backoff interval.

#### `--max-concurrent-downloads`

Defines the auto-mode upper cap for download workers.

#### `--max-concurrent-manifests`

Defines the upper cap for manifest lookup workers.

---

## Build the EXE

A Windows batch file is included for PyInstaller builds.

Typical build flow:

1. place the script, icon, and build batch file together
2. run the build batch file
3. wait for PyInstaller to finish
4. run the generated EXE from the `dist` folder

If you are using the latest single-instance version, use the corresponding build batch file shipped with that version.

### Typical build requirements

```bash
pip install -r requirements.txt
pip install pyinstaller
```

If your build script handles SDK packaging explicitly, it may also install or verify:

- `pyirsdk`
- `irsdk` hidden import collection
- package metadata collection for the frozen app

---

## Files and folders used by the app

### Local paint folder

Default:

```text
Documents\iRacing\paint
```

This is where the final livery files are installed.

### Temp folder

A temporary working folder is used for staged downloads before final installation.

### Settings file

Typical path on Windows:

```text
%APPDATA%\NishizumiPaints\settings.json
```

This stores UI preferences and operational settings.

### Windows auto-start entry

When **Auto start** is enabled, the app writes the necessary startup entry for Windows sign-in launch behavior.

---

## Performance notes

Nishizumi Paints is intended to stay light while still scaling well.

### Good default approach

For most users:

- keep the app open
- keep **Auto refresh paints** enabled
- keep **Download workers mode** on **Auto**
- only use **Manual** mode if you truly want a fixed worker count
- only enable **Verbose logs** when actively debugging

### Why Auto mode is recommended

Most users do not benefit from micro-managing worker counts.

Auto mode adapts to small sessions and large sessions without requiring the user to constantly change settings.

### Manual mode considerations

Manual mode is best for advanced users who want repeatable behavior.

Higher values may:

- use more bandwidth
- create more simultaneous network pressure
- provide less benefit on slower or unstable connections

### Manifest and download balance

The app does not only download files. It also performs manifest lookups first. Those phases are balanced so one stage does not become wildly more aggressive than the other.

---

## Troubleshooting

### The app says the iRacing SDK is not installed

Install the SDK package:

```bash
pip install pyirsdk
```

If you are using a frozen EXE build, make sure the build script correctly bundles:

- `irsdk`
- its package data
- any required metadata

### The app is open but no session is being processed

Check:

- iRacing is running
- you are actually in a valid session
- the SDK is accessible
- the activity log is visible
- verbose logs if you need deeper diagnosis

### Liveries downloaded but appeared a few seconds later

A small delay between file save and visible car update can happen because iRacing still needs time to apply the refreshed textures.

### Closing the window did not exit the app

This is expected when **Keep running in background on close** is enabled.

The app hides to the Windows notification area and keeps running.

### Verbose logs are not visible

Check that:

- `Show activity` is enabled
- `Verbose logs` is enabled

Verbose mode is off by default.

### I launched the EXE again and no new window appeared

That is usually expected.

The app is single-instance. Launching it again should bring the existing instance into focus instead of creating another copy.

### My manual workers values are not changing per session

That is expected when `Download workers mode` is set to **Manual**.

Manual mode is intentionally fixed and honored across all sessions until changed. That applies separately to manifests, downloads, and saves.

---

## Known limitations

- The app depends on iRacing SDK availability
- Texture appearance timing is still partly controlled by iRacing's own reload and rendering behavior
- Auto-start and notification-area behavior are Windows-oriented features
- Trading Paints-side availability depends on the user actually having files available for the requested content
- Manual refresh is still sometimes useful in edge cases even when auto refresh is enabled

---

## Privacy and network behavior

Nishizumi Paints does not attempt to be a general cloud sync platform.

Its network behavior is focused on the specific job of downloading relevant livery assets for the current session.

In practical terms, it:

- talks to the iRacing SDK locally
- requests Trading Paints file manifests for relevant users
- downloads only the files that match the current session need
- writes files into the local iRacing paint folder

It is not intended to browse unrelated personal data or act outside the livery workflow.

---

## FAQ

### Does the app need to stay open?

Yes. If the app is open, it is considered active and watching.

### Do I need to press Start?

No. There are no Start/Stop buttons in the main workflow. The app starts watching automatically.

### Can I close the window and keep it running?

Yes. If **Keep running in background on close** is enabled, clicking `X` hides the app to the Windows notification area instead of exiting.

### Can I open the app more than once?

No. The app is designed to allow only one instance. Opening it again should focus the existing instance.

### Should I use Auto or Manual worker mode?

Use **Auto** unless you specifically want fixed manifest, download, and save worker counts.

### If I set Manual values, will the app really use them every session?

Yes. Manual mode is fixed. If you set manifests, downloads, and saves manually, the app honors those exact values across sessions until you change them.

### Why are verbose logs off by default?

Because most users do not need extra diagnostic noise all the time. They are mainly for debugging and support cases.

### Why does the app sometimes take a few seconds after refresh to show the paint?

Because file installation and texture application are not exactly the same moment. iRacing still needs time to apply the refreshed textures.

### Can I leave the app running all the time?

Yes. That is one of the intended usage patterns.

---

## Final notes

Nishizumi Paints is built around a simple idea: **open it, leave it running, join sessions, and let it handle the rest**.

The UI is intentionally minimal, but the behavior underneath is meant to be robust enough for real daily use:

- automatic watching
- safe background operation
- single-instance behavior
- adaptive downloads
- optional fixed manual worker control
- session cleanup
- texture refresh support
- detailed logging when needed

If you want the easiest experience, leave the defaults enabled and keep the worker mode on **Auto**.
