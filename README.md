# Nishizumi Paints

<img width="512" height="512" alt="nishizumi_paints_icon" src="https://github.com/user-attachments/assets/7ba4ccbc-7dfe-4b8c-abe2-182e3fd0254a" />

Download releases here: https://github.com/nishizumi-maho/Nishizumi-Paints/releases

**Nishizumi Paints** is a lightweight Windows desktop app for **iRacing** that watches the current session, downloads the correct **Trading Paints** files for the drivers in that session, installs them into your local iRacing paint folders, and optionally refreshes textures so liveries appear in game with as little manual work as possible.

The current application is built around a simple idea:

- open it
- leave it running
- join sessions
- let it handle the paint workflow automatically

At the same time, the current build is much more advanced than the older README versions. It now includes:

- **single-instance protection**
- **automatic and manual GitHub update checks**
- **three UI tabs** instead of the older single-page description
- **AI roster tools**
- **a local random fallback system**
- **Trading Paints contextual fetch support** for team / series / league / night / numbers cases
- **superspeedway `_ss` support** when relevant
- **log export**
- **a TP worker monitor**
- **manual or adaptive worker control**
- **local cleanup with preservation rules**

---

## Table of contents

- [What the app does](#what-the-app-does)
- [Main features](#main-features)
- [How the current version works](#how-the-current-version-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Quick start](#quick-start)
- [User interface overview](#user-interface-overview)
- [General tab](#general-tab)
- [AI & Random tab](#ai--random-tab)
- [Logs tab](#logs-tab)
- [Download workers](#download-workers)
- [TP worker monitor](#tp-worker-monitor)
- [Random pool](#random-pool)
- [AI support](#ai-support)
- [GitHub update checks](#github-update-checks)
- [Buttons and manual actions](#buttons-and-manual-actions)
- [Activity log and status information](#activity-log-and-status-information)
- [Command-line options](#command-line-options)
- [Files and folders used by the app](#files-and-folders-used-by-the-app)
- [Advanced technical details](#advanced-technical-details)
- [Troubleshooting](#troubleshooting)
- [Known limitations](#known-limitations)
- [Privacy and network behavior](#privacy-and-network-behavior)
- [FAQ](#faq)

---

## What the app does

Nishizumi Paints continuously watches iRacing session data through the **iRacing SDK**.

When you join a session, the app can:

1. detect the current session and driver list
2. identify each driver's session target, car path, and relevant context
3. ask Trading Paints for the files that match that session
4. filter those responses so each driver receives only the files that fit the current car and file type
5. download the required files in parallel
6. extract compressed files when needed
7. install the final files into the correct local iRacing folders
8. optionally ask iRacing to refresh textures
9. keep watching for session changes
10. clear tracked live session paints when they are no longer needed
11. optionally recycle downloaded TP car sets into a **local random pool** for later fallback use

For normal users, the value is convenience.
For advanced users, the value is that the app is now much closer to a full paint workflow manager rather than just a simple downloader.

---

## Main features

### Core paint downloading

- Watches iRacing sessions continuously while the app is open
- Uses the **iRacing SDK** by default
- Detects session changes automatically
- Downloads matching Trading Paints files for session participants
- Supports:
  - car paints
  - car spec maps
  - car decals
  - number layers
  - helmets
  - suits
- Extracts `.bz2` files automatically
- Saves files into the correct iRacing paint folders
- Can automatically trigger an iRacing texture reload
- Can clear old live session paints when needed
- Can preserve your own livery targets when cleanup runs

### Trading Paints context support

This build does not rely only on simple per-user lookups.
It can use contextual session information such as:

- team-session state
- event time / night value
- series ID
- league ID
- number-texture state
- per-driver list values including user, car path, team ID, number, and custom paint extension

That matters because some Trading Paints behavior depends on more than only the user ID.

### Superspeedway support

The script contains superspeedway-specific handling for car-related paints.
When the session is treated as a superspeedway session, compatible car files can be saved in both normal and `_ss` forms when appropriate.

### AI tools

The current build includes a full AI-related toolset:

- sync Trading Paints AI rosters from your account
- store synced rosters locally in the iRacing AI rosters folder
- clone the active synced roster into a local editable version
- randomize the active AI roster using local TP-sourced material
- copy your current car into the local AI livery area
- copy the current session cars into the local AI livery area

### Local random fallback system

The app includes a **local random fallback** system.

This is important to understand correctly:

- it is **local**
- it is built from **Trading Paints-sourced paints already downloaded by the app**
- it can also reuse compatible local AI-livery sources when available
- it is not a separate online random-livery service

It can be used for:

- fallback liveries for real drivers who do not have a usable TP paint for the current session
- fallback for AI workflows
- randomized local AI roster creation
- reusing cached material instead of losing it after normal live-session cleanup

### Reliability and daily-use features

- retry logic for manifest requests and downloads
- exponential backoff on retry
- session fingerprinting to avoid unnecessary repeated work
- temp staging before final install
- atomic save / replace behavior where possible
- duplicate removal before the final save phase
- stale temp cleanup on startup
- random-pool limit enforcement
- watchdog restart behavior if the background service stops unexpectedly
- single-instance protection with focus-restore behavior if launched again

### User-facing convenience

- compact built-in desktop UI
- no start / stop workflow in normal use
- background-on-close support
- Windows auto-start support
- start-minimized behavior for auto-start launches
- manual refresh
- manual cleanup
- update check button
- paint-folder shortcut
- log export
- TP worker monitor

---

## How the current version works

### 1. Startup

When the app starts, it loads saved settings, initializes logging, creates the UI, starts the background service, enables single-instance handling, schedules update checks, and refreshes the random-pool summary.

If it was launched by Windows auto-start and **Start minimized** is enabled, it starts minimized or hidden to the background area depending on the close/background setting.

### 2. Single-instance handling

Only one full instance is meant to run at a time.
If you launch the EXE again while the app is already running:

- a second full copy is not supposed to stay active
- the existing instance is notified
- the existing window is brought to the front

This prevents duplicate watchers and duplicate downloads.

### 3. Session polling

The background service polls the SDK and builds a session model.
That model includes items such as:

- session IDs
- users in session
- team-session state
- series / league context
- number-texture context
- track name / config
- superspeedway detection
- AI roster information when available
- local user / team identity used for preservation logic

### 4. Trading Paints lookup

The app first tries to use **contextual Trading Paints requests** when enough session data is available.
If that is not possible, it can fall back to the simpler user-based fetch path.

### 5. Matching

The returned results are filtered so only the correct files are used for the current car, the current participant, and the current file type.
This helps avoid wrong-car downloads.

### 6. Download and save pipeline

The pipeline has three practical stages:

1. manifest lookups
2. file downloads
3. save / extraction / install

The app can run those stages in **Auto** or **Manual** worker mode.

### 7. Pool archival and fallback

If **Recycle downloaded TP paints into the local random pool** is enabled, reusable TP car sets are archived before live session copies disappear.
Then the app can optionally apply local random fallback logic for real drivers and AI targets that still need a usable paint.

### 8. Texture refresh

If **Auto refresh paints** is enabled, the app waits until iRacing is in a usable state and then requests a texture reload.

### 9. Cleanup and preservation

When the app refreshes a session or moves to another session, tracked live session paints can be removed.
If **Keep my livery locally** is enabled, the local user / team targets are preserved above normal cleanup.

---

## Requirements

### Operating system

- **Windows**

The UI, tray/background behavior, auto-start behavior, and EXE flow are Windows-oriented.

### Python

- **Python 3.10+** recommended

### iRacing

- iRacing installed
- iRacing SDK accessible from the running environment

### Python packages

See `requirements.txt`.
At minimum, the runtime app uses:

- `requests`
- `PyYAML`
- `pyirsdk`

---

## Installation

### Option 1: run from Python source

1. Install Python
2. Clone or download the repository
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. Run the current script:

```bash
python nishizumi_paints_single_instance_v5_team_sessions_updates_v21.py
```

### Option 2: build a Windows EXE

1. Install Python
2. Install dependencies:

```bash
pip install -r requirements.txt
pip install pyinstaller
```

3. Run the provided build batch file
4. Run the generated EXE from the `dist` folder

---

## Quick start

1. Launch **Nishizumi Paints**
2. Leave the default settings enabled unless you have a specific reason to change them
3. Start iRacing
4. Join a session
5. Let the app detect the session, fetch paints, install them, and refresh textures
6. Leave the app open in the background if you want it always ready

Recommended default usage for most people:

- leave **Auto start** enabled
- leave **Start minimized** enabled if you want silent Windows startup
- leave **Keep running in background on close** enabled
- leave **Auto refresh paints** enabled
- leave **Check for updates automatically** enabled
- leave **Sync TP AI rosters** enabled if you use AI content
- leave **Recycle downloaded TP paints into the local random pool** enabled if you want useful fallback reuse later
- leave **Download workers mode** on **Auto** unless you specifically want fixed worker counts

---

## User interface overview

The current UI is **tab-based**.
That is one of the biggest differences from older README versions.

### Header

The header shows:

- app name
- app version
- live service status text

### Tabs

The notebook contains **three tabs**:

- **General**
- **AI & Random**
- **Logs**

### Footer

The footer shows:

- a persistent “Always active while open” indicator
- GitHub update status text
- the running version label

The random-pool summary is **not** in the footer. It is shown inside the **AI & Random** tab.

---

## General tab

The **General** tab contains the core daily-use settings and actions.

### General settings

#### Auto start

Registers the app in Windows auto-start.

Default: **On**

#### Start minimized

Only affects launches that come from Windows auto-start.
If the app is launched manually, it stays visible.

Default: **On**

#### Keep running in background on close

When enabled, clicking `X` hides the app instead of fully exiting.
If the tray/background icon path works, the window is withdrawn and the app keeps running.

Default: **On**

#### Auto refresh paints

Requests an iRacing texture reload after new paints are installed, when it is safe to do so.

Default: **On**

#### Check for updates automatically

Enables scheduled GitHub release checks.

Default: **On**

### Session settings

#### Update my own paints

Includes your own current user in the normal Trading Paints sync workflow.

Default: **On**

#### Keep my livery locally

Preserves your own local user/team targets above normal cleanup logic.
This matters for session changes, manual clear actions, and shutdown cleanup.

Default: **On**

#### Delete live session paints

Allows tracked live session paints to be removed when they are no longer needed.

Important behavior:

- if random-pool recycling is enabled, reusable TP car sets can still be archived first
- if random-pool recycling is disabled, cleanup behaves like real deletion for those live copies

Default: **On**

#### Verbose logs

Enables more detailed diagnostic logging.
If enabled, the UI also forces the activity log to stay visible.

Default: **Off**

### Download settings

#### Worker mode

Lets you choose between:

- **Auto**
- **Manual**

Default: **Auto**

#### Manual manifests

Fixed worker count for manifest lookups in manual mode.
Allowed range: **1 to 100**

#### Manual downloads

Fixed worker count for actual downloads in manual mode.
Allowed range: **1 to 100**

#### Manual saves

Fixed worker count for save / extraction / install work in manual mode.
Allowed range: **1 to 100**

Current manual defaults in this build:

- manifests = **100**
- downloads = **100**
- saves = **100**

These values only matter if the mode is set to **Manual**.

### General tab buttons

- **Refresh paints**
- **Clear downloaded**
- **Check updates**
- **Paint folder**

---

## AI & Random tab

The **AI & Random** tab contains all AI tools and local random-pool controls.

### AI & Random settings

#### Sync TP AI rosters

Automatically syncs Trading Paints AI rosters from the current member account when relevant session context appears.

Default: **On**

#### Random fallback for AI

Allows the local random system to be used for AI targets.

Default: **On**

#### Random fallback for drivers without a TP paint

Allows real-driver fallback when a driver does not have a usable TP car paint for the current session.

Default: **On**

#### Recycle downloaded TP paints into the local random pool

When enabled, reusable TP car sets downloaded during normal session operation are archived into the random pool before live session cleanup removes the active-session copies.

This is one of the most important options in the current app.
Without it, cleanup can permanently remove those live-session copies instead of preserving them for later fallback use.

Default: **On**

#### Random pool max size (GB)

Controls the storage cap for the local random pool.
The UI accepts a large range, and the app will clamp and enforce the configured value.

Default: **5 GB**

### Random pool summary

This tab displays a live summary string showing:

- current pool size
- configured limit
- number of cached sets
- number of car types represented

### AI actions

#### Sync AI rosters

Runs a manual AI-roster sync immediately.

#### Clone active AI roster

Creates a local editable copy of the currently active synced roster.

#### Randomize active AI roster

Builds a **local randomized AI roster** using compatible local sources.
If successful, the script tells you to recreate the AI session or select that local roster in iRacing.

#### Copy my car to AI

Copies your own current saved car into the local AI livery area.

#### Copy session cars to AI

Copies cars from the current saved session set into the local AI livery area.

### AI & Random folder / maintenance buttons

#### AI rosters

Opens the local iRacing AI rosters folder.

#### AI livery folder

Opens the app's local AI livery folder.

#### Random pool

Opens the local random-pool folder.

#### Clean pool now

Fully clears the random-pool directory.

#### Rebuild pool from current files

Scans local paint files and tries to rebuild the pool from what already exists.
This is useful if you already have many saved paints and want to seed the pool without waiting for future sessions.

---

## Logs tab

The **Logs** tab contains logging and diagnostics controls.

### Log options

#### Show activity

Shows or hides the activity log panel.

Default: **On**

#### Show TP monitor

Shows or hides the TP worker monitor panel.

Default: **On** in the current build.

#### Export log

Exports the visible activity log, plus monitor information when available, to a text file.
This is useful for support, debugging, and performance comparisons.

### Activity panel

The activity panel is the main running log for the app.
It starts with a ready message and then continues to append operational lines.

### TP worker monitor

The monitor summarizes the most recent completed session and helps you estimate how much effective parallelism you are really getting.
A **Reset TP monitor** button is also present.

---

## Download workers

The app supports two worker modes.

### Auto mode

**Auto** is the recommended choice for most users.
The app dynamically balances the three pipeline stages:

- manifests
- downloads
- saves

It is meant to stay light on smaller sessions and still scale up on larger sessions.

### Manual mode

**Manual** is meant for advanced users who want repeatable, fixed values.
You manually set:

- manifests
- downloads
- saves

The app then uses those exact values every session until you change them.

### Why three worker values matter

This is not only a downloader.
If manifests or saves are too low, they can become the bottleneck even when downloads are high.
That is why manual mode exposes all three stages.

### Which mode should most users use

Use **Auto** unless you specifically want to benchmark, cap, or force known-good fixed values.

---

## TP worker monitor

The TP worker monitor reports information such as:

- last session name
- worker mode used
- requested manifest / download / save workers
- files queued and saved
- download stage time
- save stage time
- files per second
- average file time
- average Mbps
- effective observed parallelism
- best observed values from the current accumulated snapshot

The key point is that **requested workers** and **effective parallelism** are not always the same thing.
You can request a very high number and still observe a much lower real ceiling.

That makes this monitor useful for:

- comparing Auto vs Manual
- testing several manual presets
- finding your practical ceiling
- deciding whether higher values are helping or only adding overhead

---

## Random pool

The random pool is a local cache of reusable paint sets.

Default location on Windows:

```text
%APPDATA%\Nishizumi-Paints\RandomPool
```

### What it is used for

- random fallback for real drivers without a usable TP paint
- AI fallback use
- AI roster randomization
- preserving reusable TP car sets beyond live-session cleanup

### What the pool stores

Depending on what is available, a reusable set may include:

- car file
- spec map
- decal
- source metadata
- car-path grouping

### Size control

The pool is automatically trimmed when it exceeds the configured size limit.

Default limit: **5 GB**

---

## AI support

The app now has real AI workflow support, not only live-session downloading.

### Synced AI rosters

The app can fetch your Trading Paints AI roster list and roster data, then save them into the local iRacing AI rosters area.

### Local clones

You can clone a synced roster into a local editable copy.
That is useful when you want a local version that no longer depends on the synced copy directly.

### Randomized local AI rosters

The randomization flow builds a new **local** roster from compatible locally available sources.
If a randomized roster is created successfully, you can recreate the AI session or select that roster manually in iRacing.

### Copy-to-AI flows

You can also copy your current saved car or the current session cars into the local AI livery area for reuse.

---

## GitHub update checks

The current build includes both automatic and manual update checking.

### Automatic checks

If automatic update checks are enabled:

- an initial scheduled check is queued shortly after startup
- later checks are scheduled periodically

### Manual checks

The **Check updates** button starts an immediate check.

### What happens when an update is found

If a newer public GitHub release exists:

- the footer status changes to show that an update is available
- the log records the result
- the user can be prompted to open the latest release page

If the local build is newer than the latest public release, the app reports that too.

---

## Buttons and manual actions

### Refresh paints

Requests a new pass for the current session.
Useful when you want to force a re-download for testing or after a change.

### Clear downloaded

Requests cleanup of currently tracked live-session downloads.
Useful when you want a clean state quickly.

### Check updates

Runs an immediate GitHub release check.

### Paint folder

Opens the local iRacing paint folder.

### Export log

Writes the visible log and monitor information to a text file.

### Reset TP monitor

Clears the accumulated monitor snapshot so the next comparison run starts fresh.

### Pool-maintenance buttons

- **Clean pool now** wipes the random pool
- **Rebuild pool from current files** tries to repopulate it from existing local files

---

## Activity log and status information

### Activity log

The activity log can contain messages such as:

- waiting for iRacing
- processing a session
- worker mode selection
- manifest progress
- download progress
- save progress
- AI roster sync events
- random-pool archival and trimming
- random fallback results
- texture reload attempts
- watchdog recovery events
- update-check results

### Header status

The header status shows the current service state, for example while watching or processing.

### Footer status

The footer shows:

- “Always active while open” on the left
- update status on the right
- version label on the right

---

## Command-line options

The current script still supports headless and file-based usage.

Example headless launch:

```bash
python nishizumi_paints_single_instance_v5_team_sessions_updates_v21.py --nogui
```

### Available options

#### `--session-yaml`

Path to an iRacing `session_info` YAML dump file.

#### `--iracing-sdk`

Force SDK-based reading instead of file-based reading.
If `--session-yaml` is omitted, SDK mode is already the default.

#### `--watch`

Keep running and process each new session ID in the YAML file.

#### `--poll-seconds`

Polling interval in seconds.
Default: **0.8**

#### `--paints-dir`

Override the iRacing paint directory.

#### `--temp-dir`

Override the temp working directory.
Default base behavior uses the system temp directory plus `NishizumiPaints`.

#### `--keep-session-paints`

Do not delete old session paints when session changes or exits.

#### `--max-concurrent-manifests`

Upper cap for auto-tuned manifest workers.
Default: **10**

#### `--max-concurrent-downloads`

Upper cap for auto-tuned download workers.
Default: **8**

#### `--retries`

Number of retry attempts for manifest / download requests.
Default: **3**

#### `--retry-backoff-seconds`

Base backoff interval for retry timing.
Default: **1.0**

#### `--nogui`

Run without the built-in UI.

#### `--autostart-launched`

Internal flag used by the Windows auto-start flow.
Normal users do not need to pass this manually.

#### `-v` / `--verbose`

Enable verbose debug logging.

---

## Files and folders used by the app

### Local paint folder

Default:

```text
Documents\iRacing\paint
```

This is where normal live-session livery files are installed.

### AI rosters folder

Default:

```text
Documents\iRacing\airosters
```

This is where synced and local AI rosters live.

### AI livery folder

Default on Windows:

```text
%APPDATA%\Nishizumi-Paints\AiLiveries
```

### Random pool folder

Default on Windows:

```text
%APPDATA%\Nishizumi-Paints\RandomPool
```

### Settings file

Default on Windows:

```text
%APPDATA%\NishizumiPaints\settings.json
```

Note the folder name here is **NishizumiPaints** with no hyphen, while some other cached folders use **Nishizumi-Paints** with a hyphen.

### Temp working folder

Default behavior uses:

```text
%TEMP%\NishizumiPaints
```

### Windows auto-start entry

When **Auto start** is enabled, the app writes a Windows Run entry for the current user.

---

## Advanced technical details

### Session fingerprinting

The app fingerprints the effective session using session IDs, normalized users, and important context such as team state, event time, series, league, number-texture state, track, config, and superspeedway state.
That prevents unnecessary repeated processing.

### Trading Paints context payload

When enough information is available, the app builds contextual Trading Paints payloads instead of relying only on simple fetches.
That improves behavior for more complex session types.

### Superspeedway detection nuance

The script contains dedicated superspeedway logic and special-case Daytona handling so not every Daytona-related configuration is blindly treated the same way.

### Temp staging and atomic replacement

Files are downloaded into temp working areas first, then written into final destinations through safer replace behavior where possible.
That reduces the chance of partial visible files.

### Random fallback sources

The local fallback system can draw from the random pool and compatible local AI-livery sources when present.
It also tracks repeated-source use so it can avoid reuse too early when possible.

### Watchdog recovery

If the service stops unexpectedly, the UI-side poll logic can detect that and start it again.

### Log retention inside the UI

The visible log widget keeps a rolling history rather than growing forever without limit.

---

## Troubleshooting

### The app says the iRacing SDK is missing

Install the runtime package:

```bash
pip install pyirsdk
```

If you are using a frozen EXE, make sure your build process bundles the necessary SDK-related pieces correctly.

### The app is open but not processing a session

Check:

- iRacing is running
- you are in a valid session
- the SDK is accessible
- the activity log is visible
- verbose logs if deeper diagnosis is needed

### Liveries saved but not visible immediately

There can be a delay between file installation and visible in-game refresh.
iRacing still has to apply the reloaded textures.

### Closing the window did not fully exit the app

That is expected when **Keep running in background on close** is enabled.

### Launching the EXE again did not create another copy

That is expected.
The app is single-instance and should focus the existing copy.

### Random fallback does not seem to do anything

Possible reasons:

- the random pool is empty
- recycling into the random pool is disabled
- the current car type has no matching cached entries yet
- AI-related local sources are not available for that car path yet

### AI hosted-session liveries do not change live

That can still happen.
The most reliable approach is usually:

- sync AI rosters
- clone or randomize a local AI roster if needed
- recreate or reselect the roster in iRacing

### The pool was cleaned and files disappeared

That is expected for **Clean pool now**.
It is a real clear action, not a soft hide.

### Manual worker values do not change automatically between sessions

That is expected in **Manual** mode.
Manual mode is fixed until you change it.

---

## Known limitations

- The app depends on iRacing SDK availability
- Texture appearance timing is still partly controlled by iRacing itself
- Trading Paints-side availability still depends on the files that actually exist for that user / context
- Hosted AI workflows are most reliable through synced/local roster workflows, not guaranteed live repainting in every possible situation
- Random fallback can only use what already exists locally for that car type
- Extremely high worker values do not guarantee better real throughput
- Auto-start, tray/background behavior, and registry behavior are Windows-specific usage patterns

---

## Privacy and network behavior

Nishizumi Paints is focused on the paint workflow only.

In practical terms, it:

- talks to the iRacing SDK locally
- talks to Trading Paints endpoints relevant to current-session paints and AI rosters
- can check GitHub releases for updates
- writes files into local iRacing paint folders and app working folders

It is not intended to browse unrelated personal files or behave like a general cloud-sync tool.

---

## FAQ

### Does the app need to stay open?

Yes. If the app is open, it is considered active.

### Do I need to press Start?

No. The normal workflow has no Start / Stop buttons.

### Can I close the window and keep it running?

Yes. If **Keep running in background on close** is enabled, clicking `X` hides it instead of fully exiting.

### Can I open the app more than once?

No. It is intended to run as a single instance.
Launching it again should focus the existing copy.

### Should I use Auto or Manual worker mode?

Use **Auto** unless you specifically want fixed repeatable values.

### What is the random pool in simple terms?

It is a local cache of reusable TP-style car sets that the app can reuse later.

### Will deleting live session paints always erase everything forever?

Not necessarily.
If random-pool recycling is enabled, reusable TP car sets can still be archived first.

### Is the app safe to leave running all the time?

That is one of the intended usage patterns.

### Is the app meant for both normal users and advanced users?

Yes.
The defaults are designed for simple daily use, while the logs, worker controls, AI tools, and monitor exist for deeper control and debugging.
