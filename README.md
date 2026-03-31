# Nishizumi Paints

**Nishizumi Paints** is a lightweight desktop app for **iRacing** that watches your current session, downloads the correct Trading Paints files for the drivers in that session, installs them into your local iRacing paint folder, and optionally triggers an automatic texture refresh so the paints appear in-game without manual work.

The app is designed to be:

- **always-on while open**
- **minimal in UI and CPU usage**
- **fast on large sessions**
- **safe to leave running in the background**
- **simple enough for normal users, detailed enough for power users**

It includes a compact built-in UI, persistent settings, tray support, autostart support on Windows, retry logic, download auto-tuning, automatic cleanup, and detailed activity logging.

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
- [Buttons and actions](#buttons-and-actions)
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
3. asks Trading Paints which paint files exist for those users
4. filters the returned files so each driver only gets files that match the car currently in the session
5. downloads those files in parallel
6. extracts compressed paint files when needed
7. installs them into your local `Documents\iRacing\paint` folder
8. optionally tells iRacing to reload textures
9. keeps watching for session changes
10. optionally clears downloaded files when you leave that session or exit the app

The app is meant to remove the usual manual workflow of:

- opening another downloader
- waiting for it to sync
- pressing `Ctrl+R`
- clearing old session files by hand

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
- Can clear session files when you leave a session
- Can preserve your own local livery if desired

### Reliability and stability

- Built-in retry logic for manifest requests and file downloads
- Exponential retry backoff
- Session fingerprinting to avoid unnecessary repeat work
- Worker auto-tuning for downloads and manifest lookups
- Duplicate item removal before download
- Safe temp-folder handling and stale temp cleanup
- Atomic save/replace behavior to reduce partial-file issues
- Background watchdog that restarts the worker loop if it crashes

### UI and usability

- Small built-in desktop UI
- Always active while open, no manual Start/Stop workflow
- Optional activity log
- Verbose logging option
- Windows autostart support
- Start minimized when launched by Windows autostart
- Minimize to tray behavior on close
- Manual “Refresh paints” action
- Manual “Clear downloaded” action
- One-click open paint folder

### Build and deployment

- Pure Python source
- Ready for PyInstaller one-file EXE build
- Supports a custom app icon for both UI and final EXE

---

## How it works

This section explains the full workflow in plain language.

### 1. App startup

When the app starts, it loads the saved configuration from a JSON settings file in the user's app data folder.

It then:

- initializes logging
- prepares the background service
- builds the UI
- starts the background watcher thread automatically
- optionally minimizes to tray if the app was launched by autostart and `Start minimized` is enabled

When the app is opened manually by double-clicking it, it **stays visible**. The minimized startup behavior is only meant for Windows autostart launches.

### 2. SDK connection

The service tries to initialize the iRacing SDK.

There are two common outcomes:

- **iRacing is already running and connected to a session**: the service immediately starts processing
- **iRacing is not running yet or not in a session**: the service stays alive and waits in watch mode

This means you can open Nishizumi Paints before launching iRacing and just leave it running.

### 3. Session polling

The app periodically polls the SDK. It reads:

- `WeekendInfo`
- `DriverInfo`
- `SessionInfoUpdate`
- `OkToReloadTextures` when needed

Instead of reading raw YAML only, the app uses the relevant SDK sections and builds its own internal session model.

If the session data has not changed since the last poll, the app does nothing. This avoids repeated downloads and unnecessary work.

### 4. Session model creation

From the SDK data, the app builds a session object containing:

- the main session ID
- the sub-session ID if present
- a set of users in the session
- each user's `UserID`
- each user's `CarPath`
- the local driver's own user ID when it can be determined

That local user identification is important for options like:

- **Update my own paints**
- **Keep my livery locally**

### 5. Manifest lookups

For each user in the session, the app calls the Trading Paints manifest endpoint and asks which files exist for that specific `UserID`.

Those lookups happen in parallel, with an auto-tuned worker count.

The result for each driver may contain different file types such as car, helmet, suit, spec map, and so on.

### 6. File matching

Not every file returned by a user manifest should be installed. A user may have paints for several cars, but the current session only uses one specific car.

To avoid installing the wrong files, Nishizumi Paints checks whether the manifest entry matches the driver's current `CarPath`.

Matching rules include:

- exact directory match
- normalized directory match for slightly different naming formats
- helmet and suit files are always accepted for that user

### 7. Download queue building

After matching, the app builds the final queue of files that should be downloaded.

Before downloading:

- duplicate entries are removed
- the download worker count is auto-tuned
- progress totals are known in advance for logging

### 8. Parallel downloads

Downloads are performed in parallel using worker threads.

Each item is downloaded into a temp session folder first, not directly into the final iRacing paint folder.

This helps with:

- cleanup
- crash recovery
- partial-download safety
- clearer session separation

If a request fails, retry logic is applied automatically.

### 9. Extraction and install

After download:

- `.bz2` files are decompressed
- final output filenames are generated according to the iRacing paint naming rules
- files are written atomically using a temp destination plus `os.replace`

This reduces the chance of corrupt or partially written paint files.

### 10. Texture reload

If **Auto refresh paints** is enabled, the app tries to tell iRacing to reload textures through the SDK.

It does not blindly spam reload requests. Instead, it checks whether iRacing reports that it is safe to reload textures.

If not immediately allowed, the app waits and tries again. If the SDK never becomes ready for too long, it can attempt a forced refresh later.

### 11. Session cleanup behavior

When you leave a valid session, or when a new session replaces the current one, the app can automatically remove the previously downloaded files.

This helps avoid keeping old session files around forever and keeps the local paint folder cleaner.

If **Keep my livery locally** is enabled, your own downloaded files can be preserved while the rest are removed.

### 12. Watchdog behavior

If the internal worker loop crashes unexpectedly, the app logs the crash and tries to recover by restarting the service loop.

This is one of the reasons the app is safe to leave open for long periods.

---

## Requirements

### Operating system

- **Windows** is the main supported target, especially for:
  - tray behavior
  - registry-based autostart
  - EXE builds

The script can technically run elsewhere in some cases, but the app is primarily designed for Windows + iRacing.

### Software

- Python 3.10 or newer recommended
- iRacing installed
- iRacing SDK available to Python
- Internet connection

### Python packages

Install the dependencies with:

```bash
pip install requests pyyaml pyirsdk
```

Notes:

- `tkinter` is included with most normal Windows Python installs
- `pyinstaller` is only needed if you want to build the EXE

---

## Installation

### Option 1: Run the Python script directly

Place these files together in one folder:

- `nishizumi_paints_build_ready.py`
- `nishizumi_paints_icon.ico`
- `nishizumi_paints_icon.png`

Then run:

```bash
python nishizumi_paints_build_ready.py
```

### Option 2: Build the EXE

See [Build the EXE](#build-the-exe) below.

---

## Quick start

1. Install Python and the required packages
2. Run `nishizumi_paints_build_ready.py`
3. Leave the app open
4. Launch iRacing whenever you want
5. Join a session
6. Nishizumi Paints will automatically detect the session and fetch the correct paint files
7. If `Auto refresh paints` is enabled, the app will attempt to refresh textures automatically

Recommended default usage:

- leave the app open in the background
- use tray minimize if you want a clean desktop
- keep `Auto refresh paints` enabled
- keep `Delete downloaded livery` enabled unless you specifically want old session files to remain
- leave `Parallel downloads` at **8** unless you know why you want more

---

## User interface overview

The UI is deliberately compact and split into a few simple sections.

### Header

The top row shows:

- **App name**
- **Version**
- **Current status**

Typical status values include:

- `Starting`
- `Watching`
- `Processing <session id>`
- `Watching • <session id>`
- `Recovering`
- `Stopped`
- `SDK unavailable`

### General

Contains startup and window behavior options.

### Session

Contains session-specific paint behavior and logging options.

### Downloads

Contains the parallel download cap and the manual refresh action.

### Bottom actions

Contains utility buttons such as:

- `Clear downloaded`
- `Paint folder`
- `Hide`

### Activity

A scrollable live log panel that shows what the background service is doing.

---

## Detailed explanation of every option

This section explains **every checkbox and control** in the app.

### Auto start

When enabled on Windows, the app writes a registry entry under the current user's `Run` key so Nishizumi Paints launches automatically when Windows starts.

Important details:

- this is per-user autostart, not system-wide service installation
- if the app is running from source, it stores a Python command line in the registry
- if the app is running as a packaged EXE, it stores the EXE path in the registry

Best for users who want the app always ready before launching iRacing.

### Start minimized

Controls whether the app should start hidden/minimized **when launched automatically from Windows autostart**.

Important detail:

- it does **not** hide the window when you open the app manually by double-clicking it
- this was intentionally designed to avoid confusing non-technical users

### Minimize to tray on close

Changes what happens when the window close button is pressed.

If enabled:

- closing the window hides the app to the system tray instead of exiting
- the watcher keeps running
- paint downloading continues normally

If disabled:

- closing the window exits the app completely

### Auto refresh paints

If enabled, the app tries to ask iRacing to reload textures after the new paint files are saved.

If disabled:

- the app still downloads and installs files
- but it will not request the SDK texture refresh
- the user may need to rely on manual refresh behavior if they want immediate appearance changes

### Update my own paints

Controls whether the app should also fetch paint files for your own driver from the server.

If enabled:

- your own current Trading Paints livery can be re-downloaded like everyone else's in the session

If disabled:

- the app skips manifest syncing for your own driver
- useful if you prefer to keep only your current local files untouched

### Keep my livery locally

Controls cleanup behavior for your own files.

If enabled:

- when the app clears downloaded session files, it keeps your own paint files if it can identify your user ID in the session

If disabled:

- your own downloaded session files are treated like any other and can be removed during cleanup

This option is especially useful for people who want automatic cleanup but do not want their own current livery removed.

### Delete downloaded livery

Controls whether the app removes downloaded session files when the session becomes inactive or when the app exits.

If enabled:

- session files are cleaned when you leave a valid session
- session files are cleaned when the app exits
- helps keep the local paint folder tidy

If disabled:

- files are left behind after the session/app ends
- useful for debugging, manual inspection, or keeping downloaded assets around

### Show activity

Controls whether the live `Activity` log panel is visible in the UI.

If disabled:

- the app still works normally
- the service still runs
- the log panel is just hidden from view

### Verbose logs

Switches the log level from standard informational logging to detailed debug logging.

If enabled:

- more internal details appear in the activity panel
- helpful for troubleshooting SDK behavior, matching logic, worker tuning, and retries
- enabling this also automatically forces `Show activity` on, so the detailed logs are actually visible

### Parallel downloads

Sets the **upper cap** for how many paint downloads the app is allowed to run in parallel.

Default value:

- **8**

Valid range:

- **1 to 24**

Important detail:

- this is a **cap**, not a fixed always-on number
- the app still auto-tunes the actual worker count below that limit depending on session size

The UI includes a reminder:

> Default is 8 • higher values use more internet • above 20 is at your own risk

That is intentional. Larger values can increase throughput in large sessions, but they also increase:

- bandwidth use
- short-term server pressure
- chance of transient failures
- debugging complexity on weak connections

---

## Buttons and actions

### Refresh paints

This does **not** simply refresh textures.

It requests a **manual re-download pass** for the current session.

What happens internally:

1. the app marks the current session for a forced refresh
2. the next loop treats the session as needing a new fetch even if the fingerprint is unchanged
3. if cleanup-before-fetch is enabled, old session files may be removed first
4. the app fetches manifests again
5. matching files are downloaded again
6. files are reinstalled
7. texture reload is requested again if enabled

Use this when:

- a paint changed on the server
- you want to force another sync
- you are debugging download behavior

### Clear downloaded

Requests immediate cleanup of the currently downloaded session files.

What happens internally:

- the current downloaded file list is cleared
- if `Keep my livery locally` is enabled, your own files may be preserved
- if `Auto refresh paints` is enabled, a new texture reload request is queued so iRacing updates what it is displaying

Use this when:

- you want to remove downloaded session paints without exiting the app
- you are troubleshooting file installation behavior

### Paint folder

Opens the local iRacing paint folder in the operating system file browser.

On Windows this opens:

```text
Documents\iRacing\paint
```

Use this when:

- you want to inspect installed files manually
- you want to compare session output
- you want to verify that a paint was downloaded correctly

### Hide

Sends the app window to tray if tray support is available.

If tray support is not available, it falls back to a normal minimize operation.

Use this when:

- you want the app to keep running without occupying taskbar/window space

---

## Activity log and status messages

The activity panel is one of the most important tools for understanding what the app is doing.

### Common log patterns

#### Startup

```text
iRacing SDK watcher started. Waiting for iRacing/session...
```

The app is alive and waiting.

#### Session processing

```text
Processing session 304985042_84631336
```

A valid session was found and work has started.

#### Manifest progress

```text
Manifest progress 3/12 • user 697744: 3 matching files
```

This means:

- 3 manifest requests out of 12 users have completed
- user `697744` produced 3 relevant files for the current session

#### Download attempt lines

```text
[4/20] Downloading helmet for user 697744 (helmets) [attempt 1/3]
```

This means:

- this item is #4 out of 20 total queued downloads
- the file type is `helmet`
- the owner user ID is `697744`
- the manifest directory for the item is `helmets`
- this is attempt 1 of up to 3

#### Download progress lines

```text
Download progress 7/20 • completed user 697744 helmet
```

This means:

- 7 finished download futures have completed so far
- the downloaded item that just completed was that user's helmet file

#### Save progress

```text
Save progress 7/20 • user 697744 helmet
```

This means the file has already been moved/extracted into the final iRacing paint location.

#### Session completion

```text
Session 304985042_84631336 complete: 20 queued, 20 downloaded, 20 saved
```

This is the best high-level summary line.

#### Texture reload

```text
Triggered iRacing texture reload via SDK
```

The app successfully asked iRacing to refresh textures.

#### Waiting for reload permission

```text
Waiting for iRacing to allow texture reload before refreshing paints...
```

The app is being cautious and waiting until iRacing says it is safe to refresh.

### Verbose logs

When `Verbose logs` is enabled, you may also see messages about:

- poll state changes
- SDK startup edge cases
- unchanged `SessionInfoUpdate`
- directory normalization matches
- duplicate download removal
- auto-tune decisions
- retry delays
- cleanup details
- crash recovery

---

## Advanced technical details

This section is intentionally more detailed for advanced users, maintainers, and anyone who wants to understand the app deeply.

### Session fingerprinting

The app does not just look at a session ID alone. It creates a **fingerprint** composed of:

- `SessionId`
- the sorted `(user_id, car_path)` pairs in the session

This helps prevent unnecessary reprocessing when nothing meaningful changed.

### Download worker auto-tuning

The configured `Parallel downloads` value is not always the exact number of active workers. It is a cap.

Actual download workers are selected like this:

- up to 10 items → 4 workers
- up to 20 items → 8 workers
- up to 40 items → 12 workers
- up to 80 items → 16 workers
- above 80 items → 20 workers

Then the app takes the minimum of:

- item count
- auto-tuned value
- user-configured cap

### Manifest worker auto-tuning

Manifest requests are tuned separately:

- up to 10 users → 4 workers
- up to 20 users → 6 workers
- up to 40 users → 8 workers
- above 40 users → 10 workers

The manifest cap is automatically derived from the download cap when the service runs in the UI flow.

Derived mapping:

- download cap 1–4 → manifest cap 3
- download cap 5–8 → manifest cap 5
- download cap 9–12 → manifest cap 7
- download cap 13–16 → manifest cap 8
- above 16 → manifest cap 10

### Retry behavior

The app retries manifest and download requests.

Defaults:

- retries: `3`
- retry backoff base: `1.0` second

Backoff pattern:

- attempt 1 retry wait → 1 second
- attempt 2 retry wait → 2 seconds
- attempt 3 retry wait → 4 seconds

The delay is capped so it does not grow forever.

### Thread-local HTTP sessions

Each worker thread gets its own reusable `requests.Session` object.

Benefits:

- lower connection setup overhead
- cleaner concurrency model
- better reuse of HTTP connections

### Atomic writes

Files are not written directly to the final destination name first.

Instead, the app:

1. writes or moves into a temp target file
2. replaces the final target using `os.replace`

Benefits:

- reduced chance of partially written output files
- safer updates if a crash happens mid-save

### Stale temp cleanup

At startup, the app cleans old temp files in the app temp directory if they are older than the configured stale threshold used by the code.

This helps keep abandoned temp folders from accumulating after interrupted runs.

### Watchdog and recovery

The worker loop is wrapped so that if it crashes unexpectedly, the service can:

- log the exception
- log a traceback in verbose mode
- mark status as recovering
- wait briefly
- attempt to restart the main loop

### Texture reload control

Auto-refresh is intentionally conservative.

The app checks SDK readiness through `OkToReloadTextures`. If iRacing is not ready yet:

- it waits first
- logs that it is waiting
- optionally forces a refresh later if the ready flag stays unavailable too long

This reduces the chance of firing reload requests too early.

### Own-driver behavior

The app tries to determine your own iRacing user ID by comparing:

- the session's `DriverCarIdx`
- each driver's `CarIdx`

That allows it to:

- skip syncing your own livery when desired
- preserve your own files during cleanup when desired

---

## Headless mode and command-line options

The app includes a no-GUI mode.

Run:

```bash
python nishizumi_paints_build_ready.py --nogui
```

This starts the background service without the desktop UI.

### Available command-line options

#### `--nogui`
Runs the service without the built-in UI.

#### `--session-yaml <path>`
Reads session data from a YAML file instead of the iRacing SDK.

Useful for testing or offline development.

#### `--iracing-sdk`
Forces SDK mode explicitly. If no session YAML file is given, SDK mode is already the default.

#### `--watch`
Keep running and watch for changes when using session YAML input.

#### `--poll-seconds <float>`
Polling interval between checks.

UI default behavior uses the saved config, which defaults to `0.8` seconds.

#### `--paints-dir <path>`
Override the default local paint folder.

#### `--temp-dir <path>`
Override the temp working folder.

#### `--keep-session-paints`
In headless mode, keeps downloaded session paints instead of deleting them on session change/exit.

#### `--max-concurrent-manifests <int>`
Sets a cap for manifest lookups in command-line mode.

#### `--max-concurrent-downloads <int>`
Sets a cap for downloads in command-line mode.

#### `--retries <int>`
Number of retries for network operations.

#### `--retry-backoff-seconds <float>`
Base retry delay.

#### `-v` / `--verbose`
Enable debug-level logging.

---

## Build the EXE

The repository includes a Windows batch file that automates the PyInstaller build.

### Files needed in the same folder

- `nishizumi_paints_build_ready.py`
- `nishizumi_paints_icon.ico`
- `nishizumi_paints_icon.png`
- `build_nishizumi_paints_exe.bat`

### Build steps

1. Open the folder on Windows
2. Double-click `build_nishizumi_paints_exe.bat`
3. The batch file installs or updates `pyinstaller`
4. PyInstaller builds a one-file, windowed EXE
5. The final executable appears in the `dist` folder

### What the batch file does

It runs a PyInstaller command equivalent to:

```bash
py -m PyInstaller --noconfirm --clean --onefile --windowed --name "Nishizumi Paints" --icon "nishizumi_paints_icon.ico" --add-data "nishizumi_paints_icon.ico;." --add-data "nishizumi_paints_icon.png;." "nishizumi_paints_build_ready.py"
```

This ensures the icon files are bundled into the executable so the app can use them at runtime.

---

## Files and folders used by the app

### Local iRacing paint folder

Default:

```text
%USERPROFILE%\Documents\iRacing\paint
```

Examples of generated files:

- `car_<userid>.tga`
- `decal_<userid>.tga`
- `car_num_<userid>.tga`
- `car_spec_<userid>.mip`
- `helmet_<userid>.tga`
- `suit_<userid>.tga`

### Temp working folder

Default:

```text
%TEMP%\NishizumiPaints
```

Used for:

- per-session temp downloads
- decompression staging
- crash-safe intermediate work

### Settings file

Default on Windows:

```text
%APPDATA%\NishizumiPaints\settings.json
```

Stores persistent UI settings such as:

- autostart
- tray behavior
- log visibility
- download cap
- retries
- poll interval

### Windows autostart registry key

Stored under:

```text
HKEY_CURRENT_USER\Software\Microsoft\Windows\CurrentVersion\Run
```

Value name:

```text
NishizumiPaints
```

---

## Performance notes

### Recommended download cap

For most users:

- **8** is a very good default

This keeps the app responsive and efficient without being too aggressive.

### When to increase it

You might increase the cap if:

- your internet connection is strong
- you frequently join large official sessions
- you want slightly faster total sync time

### When not to increase it

Leave it at 8 or lower if:

- your connection is unstable
- you use mobile hotspot or limited bandwidth
- you see more transient failures at higher concurrency
- you do not need every last bit of speed

### Why higher values can be worse

More parallel workers do not always mean better real-world results. Higher values can cause:

- more simultaneous bandwidth use
- burstier request patterns
- more retry events on unstable networks
- more difficult debugging when problems happen

---

## Troubleshooting

### The app says it is watching, but nothing downloads

Check:

- iRacing is running
- you are actually inside a valid session
- the SDK is available to Python
- verbose logs for SDK poll state messages

### Paints downloaded, but they appeared a few seconds later

That delay is usually the iRacing texture pipeline catching up after the reload request. The app can save the files quickly, but visible appearance in the sim still depends on the game side finishing the refresh.

### My own paint keeps disappearing

Check:

- `Keep my livery locally`
- `Delete downloaded livery`
- `Update my own paints`

If you want cleanup for everyone else but not for your current car, keep `Keep my livery locally` enabled.

### I closed the window and thought the app exited

If `Minimize to tray on close` is enabled, closing the window hides it instead of exiting it. This is intentional.

### Verbose logs are not visible

Enable:

- `Verbose logs`
- `Show activity`

The UI also forces activity visibility when verbose logging is enabled.

### The app does not start with Windows

Check:

- `Auto start` is enabled
- Windows did not block the startup entry
- the EXE or Python path still exists where the registry entry points

### Refresh paints did not instantly change what I see

The button triggers a re-download workflow. Actual visible change still depends on:

- the new file really being different
- iRacing accepting the texture reload request
- the game finishing its own refresh pipeline

### The service stopped unexpectedly

The UI includes a watchdog. In many cases the app will log that the service stopped and automatically restart it. Check the activity log for the lines immediately before the recovery.

---

## Known limitations

- The app depends on the iRacing SDK being available and usable from Python
- The app is built around the current Trading Paints fetch workflow and expected manifest behavior
- Texture reload timing ultimately depends on what iRacing allows and when it applies the visual update
- Windows tray and autostart behavior are Windows-specific features
- The app cannot guarantee that every driver has a matching server-side paint for every session
- Very aggressive concurrency settings can increase the chance of transient failures

---

## Privacy and network behavior

Nishizumi Paints is very focused in what it does.

It interacts with:

- the local iRacing SDK
- the local iRacing paint folder
- the Trading Paints fetch endpoint for user paint manifests and files

It does **not** need a full browser workflow to operate in the normal session-sync path shown here.

It stores local settings in a JSON file so your preferences persist between runs.

---

## FAQ

### Is the app always active?

Yes. If the app is open, it is considered active. The design intentionally avoids Start/Stop buttons.

### Can I leave it open all the time?

Yes. That is one of the intended usage styles.

### Can I hide it without stopping it?

Yes. Use the `Hide` button or close the window if `Minimize to tray on close` is enabled.

### Does it work if iRacing is not open yet?

Yes. It can start first and wait.

### What is the safest download setting?

For most users: **8**.

### What is the fastest setting?

There is no single best number for everyone. Higher caps can be faster on strong internet, but they are more aggressive and not always better. Values above **20** should be treated as experimental.

### What happens if I switch sessions?

The app detects the session change, optionally clears old downloaded files, and starts processing the new session.

### What happens if I leave the session and go back to the menu?

If `Delete downloaded livery` is enabled, the app clears the downloaded session files when no active valid session is detected.

### Can I use it without the UI?

Yes. Use `--nogui`.

---

## Recommended GitHub repository contents

If you are publishing this project, a clean repository layout would be something like:

```text
.
├─ README.md
├─ LICENSE
├─ requirements.txt
├─ nishizumi_paints_build_ready.py
├─ nishizumi_paints_icon.ico
├─ nishizumi_paints_icon.png
└─ build_nishizumi_paints_exe.bat
```

Suggested `requirements.txt`:

```text
requests
PyYAML
pyirsdk
```

---

## Final notes

Nishizumi Paints is meant to feel invisible when everything is working correctly:

- open it once
- leave it running
- join sessions
- let it do the work

The app is intentionally small on the surface, but there is a lot happening underneath to make it fast, stable, and practical for real iRacing use.
