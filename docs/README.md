# Nishizumi Paints

<img width="512" height="512" alt="nishizumi_paints_icon" src="https://github.com/user-attachments/assets/7ba4ccbc-7dfe-4b8c-abe2-182e3fd0254a" />

Download releases here: https://github.com/nishizumi-maho/Nishizumi-Paints/releases

**Nishizumi Paints** is a Windows desktop app for **iRacing**. It watches the current session, downloads matching **Trading Paints** files, installs them into your local iRacing paint folders, reloads textures, and can fill missing paints with local cached paints, Trading Paints collections, or public showroom paints.

This README reflects the current **4.0.0** script flow and interface.

Current highlights:

- startup choice between normal window and console/headless mode
- Quick Start wizard with iRacing Documents folder detection
- five visible tabs: **Session**, **General**, **AI**, **Random**, and **Logs**
- separate session states for **car**, **helmet**, and **suit**
- per-driver fixed paint actions: **Open TP**, **Assign link**, **Assign current**, **Random**, and **Forget**
- Online Trading Paints fallback with a protected fast path enabled automatically
- support for using a secondary Trading Paints account through the manifest member ID override
- Trading Paints **collection pool** support before the normal public showroom fallback
- no collection paint repeats inside the same session, including same-session roster updates
- full Trading Paints showroom URLs for openable fallback, collection, and override paints
- disabled **Open TP** buttons for real downloaded paints that do not have a useful showroom page
- always-on showroom total-page detection for online fallback
- local random paint pool with separate size caps for cars, helmets, and suits
- bundled or installed Chromium-based browser workflow for Trading Paints login
- **Session Total** worker mode as the default for new configs
- incremental same-session roster refreshes
- AI roster sync and AI randomization tools
- replay pack support
- showroom mapping scan/review tools in the Logs tab
- app settings reset from the Logs tab

---

## Read This First

For most users, the best setup is:

1. Start the app in the normal window mode.
2. Finish Quick Start.
3. Confirm the detected iRacing Documents folder.
4. Leave **Preferred source** on **Online**.
5. Connect Trading Paints.
6. If you use a secondary Trading Paints account, enter that account's iRacing member ID in **TP manifest member ID override**.
7. Leave the app running while you race.

After setup, console/headless mode is useful for daily use because it keeps the monitor running with less UI overhead.

### Why Trading Paints login is needed

Normal Trading Paints downloads only work when the driver already has a matching paint available in the manifest.

Online fallback is different. When a driver has no usable paint, Nishizumi Paints can temporarily select a showroom paint on the connected Trading Paints account, read the resulting manifest files, save those files locally for the target driver, and then restore the connected account's original paint.

That means Online fallback needs a real Trading Paints browser session.

### Primary Account Or Secondary Account

You can connect either:

- your primary Trading Paints account
- a secondary account used only by Nishizumi Paints

A secondary account is recommended if you plan to use Online fallback heavily. Your main account can keep racing normally while the app uses the secondary account for showroom paint capture.

When a secondary account is connected, fill in **TP manifest member ID override** with that secondary account's iRacing member ID. Without that, the app may switch paints on the connected account but poll the wrong manifest.

### Protected Fast Path

Older builds exposed extra speed-mode choices for Trading Paints fallback. The current build does not ask the user to choose those modes anymore.

The current behavior is:

- the protected fast path is always enabled
- the app keeps backup/restore protection for the connected account
- the slow per-paint dashboard confirmation loop is skipped automatically
- the old aggressive background mode is forced off

### Local Pool Still Matters

Even with **Online** selected, the local random paint pool is still useful. It can cover a target when Trading Paints times out, the showroom does not expose fresh files, or the collection/public fallback cannot finish cleanly.

---

## Table Of Contents

- [Read This First](#read-this-first)
- [What The App Does](#what-the-app-does)
- [How Missing Paints Are Resolved](#how-missing-paints-are-resolved)
- [Startup Modes](#startup-modes)
- [Quick Start](#quick-start)
- [User Interface](#user-interface)
- [Session Tab](#session-tab)
- [General Tab](#general-tab)
- [AI Tab](#ai-tab)
- [Random Tab](#random-tab)
- [Logs Tab](#logs-tab)
- [Trading Paints Login](#trading-paints-login)
- [Collection Pool](#collection-pool)
- [Online Fallback](#online-fallback)
- [Local Random Paint Pool](#local-random-paint-pool)
- [AI Support](#ai-support)
- [Download Workers](#download-workers)
- [Same-Session Roster Changes](#same-session-roster-changes)
- [Replay Packs](#replay-packs)
- [Requirements](#requirements)
- [Installation](#installation)
- [Command-Line Options](#command-line-options)
- [Files And Folders](#files-and-folders)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)

---

## What The App Does

Nishizumi Paints watches iRacing session data through the iRacing SDK.

When a session is found, the app can:

1. read the current session ID and driver list
2. identify each driver's car directory, team/user target, number, and session context
3. request matching Trading Paints manifests
4. download car, decal, spec, number, helmet, and suit files when available
5. extract `.bz2` files
6. save files into the selected iRacing Documents paint folders
7. trigger iRacing texture reloads
8. apply fixed driver overrides when configured
9. fill missing paints from configured Trading Paints collections
10. fill remaining missing paints from the public Trading Paints showroom
11. fall back to the local random pool when online resolution cannot finish
12. recycle usable downloaded paints into local pools
13. keep watching for new sessions or new drivers inside the same session

The app treats cars, helmets, and suits separately. A driver can have a downloaded helmet, an online fallback car, and a missing suit, and the Session tab will show those states independently.

---

## How Missing Paints Are Resolved

The app resolves paints in layers.

1. **Normal Trading Paints manifest download**
   If the driver already has a usable TP paint for the current session, the app downloads it directly.

2. **Fixed driver override**
   If you assigned a specific paint to a driver from the Session tab, that fixed paint wins and stays marked as an override.

3. **Trading Paints collection pool**
   If collections are configured, the app tries compatible paints from those collections first.

4. **Public showroom online fallback**
   If Online is selected and collection coverage is unavailable or exhausted, the app can pick a random public showroom paint.

5. **Local random pool**
   If online fallback fails, times out, or is not selected, the app can use locally cached paint sets.

Fallback can apply to real drivers and AI drivers, depending on the toggles in the Random tab.

---

## Startup Modes

At startup, the app can launch as:

- **GUI / normal window**
- **Console / headless**

Use the normal window for setup. Use console/headless after setup if you want the monitor running with less UI overhead.

The startup selector can be shown again by holding **Shift** while opening the app or by resetting app settings.

GUI and console/headless share the same settings file.

If a headless service is already running, the GUI can attach to it instead of starting a second monitor.

---

## Quick Start

Quick Start guides the first setup.

It covers:

1. startup mode guidance
2. iRacing Documents folder detection and confirmation
3. download worker mode
4. missing paint fallback targets
5. Trading Paints login
6. final recommendations

Important behavior:

- the wizard searches for the iRacing Documents folder and asks you to confirm it
- **Session Total** is presented as the default fast worker mode
- **Auto** is available for lower or mid-range hardware
- random cars, helmets, and suits can be enabled separately for real drivers and AI
- Online fallback cannot be completed until Trading Paints login succeeds
- there is no speed-mode choice in Quick Start; the protected fast path is automatic
- after a successful Trading Paints login during Quick Start, the app waits until the wizard is finished before restarting

---

## User Interface

The visible tabs are:

- **Session**
- **General**
- **AI**
- **Random**
- **Logs**

There is no visible Experimental tab in the current app.

---

## Session Tab

The Session tab shows the live session and per-driver paint state.

Columns include:

- **Car**
- **Suit**
- **Helmet**
- **iRacing ID**
- **#**
- **iR**
- **Lic**
- **SR**
- **Name**

Common states include:

- queued
- downloading
- downloaded
- override
- replay pack
- fallback local
- fallback online
- missing
- skipped

### Selected Driver Fixed Paints

When you select a driver, the Session tab exposes fixed-paint controls for **Car**, **Helmet**, and **Suit**:

- **Open TP** opens the Trading Paints showroom page for the current openable paint.
- **Assign link...** assigns a specific Trading Paints showroom link or scheme ID to that driver.
- **Assign current** fixes the paint currently on that driver in the session.
- **Random** picks a random compatible Trading Paints showroom paint and fixes it.
- **Forget** removes the fixed override and cached fixed files for that driver/kind.

Important details:

- **Assign current** works for a random/fallback paint that is already on the car, helmet, or suit.
- Fixed paints keep the **override** state instead of turning into normal **downloaded** states after the session finishes.
- **Open TP** is enabled only when the current asset has a useful showroom page.
- Real downloaded paints that only point to a driver profile do not enable **Open TP**, because that profile page does not identify the current paint.
- Fallback and collection paints use full showroom URLs such as `https://www.tradingpaints.com/showroom/view/339982/Schnitzelwagen-Solstice-V2`.
- Buttons update as each driver's assets become available, so you do not need to wait for every download in the whole session.

---

## General Tab

The General tab contains broad app behavior, worker settings, online fallback lane settings, and local random pool settings.

### Actions

- **Clear downloaded**
- **Refresh paints**
- **Trigger global reload**
- **Paint folder**
- **Check updates**

### Settings

- **Auto start**
- **Start minimized**
- **Keep running in background on close**
- **Auto refresh paints**
- **Check for updates automatically**

### Session

- **Update my own paints**
- **Keep my livery locally**
- **Delete live session paints**
- **Do not apply random paints in team events**

### iRacing Documents Folder

The app stores a configurable iRacing Documents root.

Controls:

- read-only current path field
- **Change...**
- **Default**

When a new folder is confirmed, the app restarts to apply the change cleanly.

### Downloads

- **Worker mode**
- **Manual manifests**
- **Manual downloads**
- **Manual saves**

### Online Fallback Lanes

- **Lane mode**
- **Manual max lanes**
- **Process cars, helmets, and suits together online (advanced)**
- **Retry timed-out online fallbacks at the end before local fallback**

Lane modes:

- **Safe**: one online car lane at a time
- **Session Total**: one car lane per active car group
- **Manual**: user-defined cap

Timed-out online paints get an initial 90-second attempt. If the retry option is enabled, they are queued for a final retry window before falling back to the local random pool.

### Local Random Paints Pool

The local random paints pool lives in the General tab because it matters for both Local and Online workflows.

Controls:

- **Recycle downloaded TP car paints into the local random pool**
- **Max size (GB)**
- category caps for **Cars**, **Helmets**, and **Suits**
- **Open pool**
- **Clean pool now**
- **Rebuild from current files**

The app normalizes category caps so they stay inside the total pool size.

---

## AI Tab

The AI tab contains AI-specific tools.

### AI Sync

- **Sync TP AI rosters**
- iRacing member ID field for AI collections
- **OK** button for saving that member ID

If the AI member ID is empty, the app can auto-fill it once from the first active iRacing account it sees through the SDK or from a confirmed primary login.

### Collection Roster Guards

When an active AI roster comes from a synced Trading Paints collection, the AI tab exposes:

- **Do not download random AI cars**
- **Do not download random AI helmets**
- **Do not download random AI suits**

These options help avoid replacing collection paints with unrelated random fallback assets.

### AI Actions

- **Sync AI rosters**
- **Randomize active AI roster**
- **Clone active AI roster**
- **Copy my car to AI**
- **Copy session cars to AI**

### AI Folders

- **AI rosters**
- **AI livery folder**

---

## Random Tab

The Random tab controls missing-paint fallback.

### Step 1 - Who Should Get Fallback Paints?

Groups:

- **Random cars**
- **Random helmets**
- **Random suits**

Each group has separate toggles for:

- **Real Drivers**
- **AI**

Fresh configs start with fallback targets enabled.

### Step 2 - Preferred Source

Options:

- **Local**
- **Online**

The default preferred source is **Online**.

### Step 3 - Online Trading Paints

This section includes:

- connection status
- **Connect Trading Paints**
- **I logged in**
- **Disconnect**
- **Showroom**
- **Auth profile**
- **TP manifest member ID override**
- **Collection pool**

The Online section can stay configured even when Local is selected.

---

## Logs Tab

The Logs tab contains diagnostics, activity, mapping tools, and reset tools.

### Log Options

- **Show activity**
- **Verbose logs**
- **Show TP monitor**
- **Export log**
- **Reset app settings**

### TP Worker Monitor

The app can show download/save worker monitor output and reset the monitor.

### Showroom Mapping Tools

The current app includes Trading Paints showroom mapping tools:

- **Scan now**
- **Review pending cars**
- **Open editable JSON**
- **Reset user mapping**
- **Open mapping folder**
- **Open bundled seed**

The startup scan can report how many iRacing cars are mapped, pending, or unsupported.

Mapping matters because online fallback needs to map an iRacing car directory to a Trading Paints showroom category, car ID, and slug.

---

## Trading Paints Login

Trading Paints login can be started from Quick Start or from the Random tab.

The app opens a persistent Chromium-based browser profile. You log in on the normal Trading Paints website, then return to Nishizumi Paints and click **I logged in**.

The app does not ask for your Trading Paints password in a custom Nishizumi Paints field.

### Browser Runtime

The compiled app can use a bundled Chromium-based runtime when one is shipped beside the EXE.

Supported local layouts can include:

- `embedded_browser`
- `browser`
- `chrome`
- `chrome_runtime`
- `chrome-portable`
- `ms-playwright`

If no bundled browser is available, the app can fall back to installed Chromium-based browsers such as:

- Google Chrome
- Microsoft Edge
- Brave
- Chromium

### Disconnect

**Disconnect** clears the saved Trading Paints browser/profile data on this PC. After that, Online fallback requires a new login.

---

## Collection Pool

The collection pool lets you add Trading Paints collection IDs or URLs. When Online fallback runs, the app tries those collections before the normal public showroom.

Controls:

- collection ID/URL entry
- **Add**
- collection list
- **Use normal public showroom when selected collections cannot cover a target**
- **Remove selected**
- **Clear list**
- **Collections**
- **Cache**
- **Clean cache...**

Behavior:

- collection paints are cached locally per collection
- the app does not repeat the same collection source inside the same session
- used collection sources are remembered across same-session roster updates
- if the selected collections run out of compatible non-repeating paints, normal public showroom fallback can cover the target when the coverage checkbox is enabled
- removed collection IDs have their unused collection cache cleaned
- **Clean cache...** accepts a collection ID or URL, or can clean all configured collection caches after confirmation

This is useful when you want random fallback to come from a curated Trading Paints collection first.

---

## Online Fallback

Online fallback uses the connected Trading Paints account to capture compatible showroom paints.

Current behavior:

- showroom total-page detection is always enabled
- the app probes the real showroom page count before filling the pool
- random pages are chosen from the detected page range
- the app skips the connected account's original scheme when picking fallback paints
- the protected fast path is always used
- the original connected account paint is restored after online fallback
- timed-out targets can be retried near the end before local fallback

If a showroom paint is selected online but the connected account manifest never exposes fresh files in time, the app logs that timeout and can fall back to local material.

---

## Local Random Paint Pool

The local random pool stores reusable paint sets.

It can store:

- car paint sets
- helmet paint sets
- suit paint sets

It is used for:

- Local fallback mode
- backup after Online fallback timeouts
- AI fallback
- future reuse of downloaded paints

The pool has a total size cap and per-category caps.

---

## AI Support

The app can:

- sync Trading Paints AI rosters into the iRacing `airosters` folder
- randomize the active AI roster
- clone the active AI roster
- copy your car to AI livery storage
- copy session cars to AI storage
- apply local or online fallback to missing AI paints when enabled
- avoid randomizing AI collection roster paints when the AI guard options are enabled

If iRacing already loaded an AI roster, recreate the AI session after syncing so iRacing picks up the new carsets.

---

## Download Workers

The app supports three normal worker modes.

### Session Total

Default for new configs.

It sets:

- manifests = number of users in the current session
- downloads = number of queued download items
- saves = number of queued save items

This is the fastest default for many sessions.

### Auto

Adaptive mode using internal caps and tuning.

This can be gentler on lower or mid-range hardware.

### Manual

Advanced fixed values.

Manual ranges:

- manifests: 1 to 100
- downloads: 1 to 100
- saves: 1 to 100

Fresh configs start the manual fields at `100 / 100 / 100`, but those values only matter when Manual is selected.

Online fallback lanes are separate from normal download workers.

---

## Same-Session Roster Changes

The app can detect new drivers entering the same session.

Instead of redownloading everything, it refreshes incrementally:

- unchanged drivers keep their current resolved paint state
- only new targets are fetched
- fixed overrides remain protected
- collection pool source choices are remembered so the same collection paint is not reused later in that same session

This is especially useful in busy sessions where drivers keep joining.

---

## Replay Packs

The app includes replay-pack capture and restore logic.

Replay packs help preserve paint sets for later replay use instead of depending only on live-session files.

---

## Requirements

For the Windows release:

- Windows
- iRacing installed
- access to the iRacing Documents folder
- a Chromium-based browser runtime for Trading Paints login, either bundled with the release or installed on the PC

For running from Python source:

- Python 3.10+
- `requests`
- `PyYAML`
- `pyirsdk`
- `playwright`
- a compatible Chromium runtime for the Trading Paints browser/profile workflow

---

## Installation

### Option 1 - Run From Python Source

1. Install Python 3.10+.
2. Clone or download the repository.
3. Install the Python dependencies:

```bash
pip install requests PyYAML pyirsdk playwright
```

4. If using Online fallback from source and you do not already have a supported browser available, install Playwright's Chromium runtime:

```bash
python -m playwright install chromium
```

5. Run the script.

### Option 2 - Use The Windows EXE

1. Download the latest release package.
2. Extract the full folder.
3. Keep the EXE and support folders together.
4. Open the EXE.
5. Complete startup selection and Quick Start.

For onedir releases, do not separate the EXE from its bundled support folders.

---

## Command-Line Options

Common examples:

```bash
python Nishizumi_Paintsv4_embedded_browser.py
python Nishizumi_Paintsv4_embedded_browser.py --gui
python Nishizumi_Paintsv4_embedded_browser.py --nogui
```

Useful options:

- `--gui`: force the normal window
- `--nogui`: run without the built-in UI
- `--session-yaml PATH`: read session data from a YAML dump
- `--iracing-sdk`: read live data from the iRacing SDK
- `--watch`: keep watching a YAML file for new sessions
- `--poll-seconds N`: polling interval
- `--paints-dir PATH`: override the iRacing paint/Documents path
- `--temp-dir PATH`: override the temporary folder
- `--keep-session-paints`: do not delete old session paints when the session changes or exits
- `--max-concurrent-manifests N`: cap manifest requests
- `--max-concurrent-downloads N`: cap downloads
- `--retries N`: manifest/download retry count
- `--retry-backoff-seconds N`: retry backoff base
- `-v`, `--verbose`: enable debug logs

Hidden managed-headless/autostart flags are used internally by the app.

---

## Files And Folders

### Settings

```text
%APPDATA%\NishizumiPaints\settings.json
```

### Driver Fixed Paint Overrides

```text
%APPDATA%\NishizumiPaints\.nishizumi_driver_paint_overrides.json
```

### Recent Trading Paints Schemes

```text
%APPDATA%\NishizumiPaints\.nishizumi_tp_recent_schemes.json
```

### Showroom Mapping Override

```text
%APPDATA%\NishizumiPaints\tp_showroom_mapping.seed.json
```

### Local Paint Folder

```text
<selected iRacing Documents folder>\paint
```

### AI Rosters Folder

```text
<selected iRacing Documents folder>\airosters
```

### Random Pool

```text
%APPDATA%\Nishizumi-Paints\RandomPool
```

### Collection Pool Cache

```text
%APPDATA%\Nishizumi-Paints\CollectionPool
```

### AI Livery Folder

```text
%APPDATA%\Nishizumi-Paints\AiLiveries
```

### Replay Packs

```text
%APPDATA%\Nishizumi-Paints\ReplayPacks
```

### Session Exports

```text
%APPDATA%\Nishizumi-Paints\Exports
```

### Trading Paints Auth Profile

```text
%APPDATA%\Nishizumi-Paints\TPAuthProfile
```

### Temporary Working Folder

```text
%TEMP%\NishizumiPaints
```

### Bundled Browser Folder

Common release layouts include:

```text
embedded_browser
browser
chrome
chrome_runtime
chrome-portable
ms-playwright
```

---

## Troubleshooting

### Online fallback is selected, but nothing is happening

Check:

- Trading Paints login succeeded
- the correct account is connected
- if using a secondary account, **TP manifest member ID override** is filled correctly
- the app can open the Trading Paints showroom
- the car has a showroom mapping
- the log does not show a browser/profile error
- the EXE was not separated from its bundled browser runtime

### The app selected an online paint but never got files

Trading Paints can accept a showroom selection without exposing fresh manifest files quickly enough.

The app logs this as a timeout and can retry near the end before using the local pool.

### Open TP is disabled

This is expected for real downloaded paints that do not have a useful showroom URL.

The button is enabled for current session paints that have a real showroom scheme URL, such as collection paints, online fallback paints, or fixed override paints.

### A collection ran out of paints

The app will not reuse the same collection source in the same session. If the configured collections cannot cover more targets, the app can continue with the normal public showroom when that checkbox is enabled.

### My main Trading Paints paint changed temporarily

That can happen during Online fallback because the app must temporarily select showroom paints on the connected account. The current app uses the protected fast path and restores the original paint afterward.

Use a secondary account if you do not want your main account involved in that workflow.

### The app reran when someone joined

Same-session roster changes trigger an incremental refresh. The app fetches only new targets and keeps existing resolved state.

### I want to start over

Use **Reset app settings** in the Logs tab.

This deletes the saved config and restarts the app with defaults, including the startup selector and Quick Start.

---

## FAQ

### Do I need to keep the app open?

Yes. The app only monitors and installs paints while it is running.

### Is Online or Local better?

Online is recommended for most users because it can pull fresh showroom paints. Local is simpler and useful as a backup.

### Does Local still matter when Online is selected?

Yes. The local pool is still used as backup when online fallback cannot finish a target.

### Can I race on one account and connect Trading Paints with another?

Yes. That is the recommended secondary-account setup.

### Why does the app ask for another member ID?

Because the account used for online fallback may not be the same iRacing account currently racing. The override tells the app which member manifest to poll.

### Why is showroom page detection not optional anymore?

The current app always enables it so random showroom pages come from the real detected page count instead of a fixed guess.

### What is the best advanced setup?

Usually:

- race on your main account
- connect Trading Paints with a secondary account
- set that secondary account's member ID override
- keep **Online** as the preferred source
- use collection pool IDs when you want curated random fallback
- leave **Session Total** as the normal download worker mode unless your PC or network prefers Auto
