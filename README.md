# Nishizumi Paints

<img width="512" height="512" alt="nishizumi_paints_icon" src="https://github.com/user-attachments/assets/7ba4ccbc-7dfe-4b8c-abe2-182e3fd0254a" />

Download releases here: https://github.com/nishizumi-maho/Nishizumi-Paints/releases

**Nishizumi Paints** is a Windows desktop app for **iRacing** that watches the current session, downloads the correct **Trading Paints** files for the people in that session, installs them into your iRacing paint folders, and can also fill missing paints with a local or online fallback workflow.

The app is designed so a normal user can:

- open it once
- go through the initial setup
- leave it running
- join sessions in iRacing
- let the app handle paint downloading and fallback automatically

This README reflects the current app flow and interface, including:

- startup mode selection (**normal window** or **console/headless**)
- the **Quick Start** wizard
- separate **AI** and **Random** tabs
- the **Online Trading Paints** fallback workflow
- support for a **secondary / smurf / mule** Trading Paints account
- the **TP manifest member ID override** field
- **TP mule fast mode**
- optional **showroom total-page detection**
- a **local random paints pool** that still matters even when Online is selected
- a **bundled / embedded browser runtime** workflow for Trading Paints login
- the new **Session Total** worker mode
- **incremental same-session roster refreshes** instead of redownloading the whole session
- separate **car / suit / helmet** session states
- support for **helmet** and **suit** fallback handling
- a **Reset app settings** tool in the Logs tab

---

## Read this first - how to use the app

If you only want the practical version, read this section first.

### What the app is for

Nishizumi Paints keeps watching your current iRacing session and tries to make sure the correct paints are present in your local `Documents\iRacing\paint` folders.

In simple terms, it can:

- download the normal Trading Paints files for people in your session
- download and save **car**, **helmet**, and **suit** files when available
- fill in missing paints when some drivers or AI cars do not have a usable TP paint
- reuse local cached paints later so you do not lose everything after a session ends
- react to roster changes inside the same session without throwing away everything it already downloaded

### The simplest recommended setup

For most users, the easiest and best setup is:

1. launch the app in the normal **window** mode
2. go through **Quick Start**
3. leave **Preferred source** on **Online**
4. connect a **secondary / smurf / mule** Trading Paints account if possible
5. if you use a mule account, enter its **Trading Paints member ID** when the app asks
6. leave the app open while you race

That gives you the best chance of getting varied fallback paints for missing drivers without constantly touching your main account.

### Why the app asks you to log in to Trading Paints

The normal Trading Paints sync only works when a driver already has a matching TP paint exposed for the current session and car.

The **Online** fallback is different. To pull random showroom paints for drivers who are missing a usable TP paint, the app has to connect to a real Trading Paints account and temporarily switch that connected account's active paint so it can capture the resulting manifest/files.

That is why a Trading Paints login is required for the **Online** fallback mode.

### Why the connected car paint can keep changing

This is expected behavior in **Online** fallback mode.

To get a random showroom paint, the app temporarily tells Trading Paints to set another paint as the active paint on the account that is connected in the app. Then it reads the resulting files and saves them locally for the missing session target.

So if you connect:

- your **main account**, your main account's active TP paint can change temporarily while the app is working, then the app tries to restore it
- a **secondary mule account**, the mule account is the one that changes instead

This is exactly why a separate mule account is usually the better choice.

### Why a secondary / mule account is recommended

A mule account is simply a second Trading Paints account that you use only for Nishizumi Paints.

Benefits:

- your main account is not the one being switched around during online fallback
- the app can use **TP mule fast mode** for better speed
- you do not have to worry as much about the app restoring your real everyday paint after every fallback action

Important detail: you can be **racing on one iRacing account** while the app is **logged in to another Trading Paints account** for the online fallback workflow. That is the intended mule-account setup.

### Is it safe to log in through the app

The app does **not** ask you to type your Trading Paints password into a custom text field inside Nishizumi Paints.

Instead, it opens a persistent browser profile and you log in through the normal Trading Paints site in the browser window. The app then reuses that local browser profile for the online workflow.

In practical terms:

- your login is stored locally on your PC in the app's Trading Paints browser profile
- the app reuses that local profile instead of asking for your password every time
- anyone with access to that Windows user profile can potentially access that saved browser session, so keep your Windows account and PC secure

If you are still uncomfortable with this, use **Local** fallback only, or use a separate mule account just for the app.

### Which source should I choose

- **Online**: recommended for most people, better variety, best results for missing paints
- **Local**: simpler and does not require a TP login, but it can only reuse paints you already cached locally

Even when **Online** is selected, the **local random paints pool** still matters because it can be used as a backup when online fallback cannot finish a target.

### What to do if I use a secondary account

If you connect a secondary / mule account, you should usually do all of the following:

- choose **Smurf / mule account** when the app asks what kind of account you are connecting
- let the app enable **TP mule fast mode**
- fill in the **TP manifest member ID override** with the Trading Paints member ID of that mule account

If that member ID is missing or wrong, the app may be able to switch paints on the connected account but still fail to capture the updated files correctly.

### What the local random paints pool is

The local random paints pool is a local cache of extra paints the app can reuse later.

So even if you mainly want **Online**, it is still good to keep the pool enabled. It helps with:

- local fallback if online fails
- reusing paints from earlier sessions
- better behavior across AI and real-driver fallback cases

### In one sentence

If you want the best beginner-friendly setup: use the normal window mode, go through Quick Start, choose **Online**, and connect a **secondary mule account** if you can.

---

## Table of contents

- [Read this first - how to use the app](#read-this-first---how-to-use-the-app)
- [What the app does](#what-the-app-does)
- [How Nishizumi Paints handles missing paints](#how-nishizumi-paints-handles-missing-paints)
- [Why Online fallback is recommended](#why-online-fallback-is-recommended)
- [Primary account vs secondary mule account](#primary-account-vs-secondary-mule-account)
- [Important warning about the connected Trading Paints account](#important-warning-about-the-connected-trading-paints-account)
- [Requirements](#requirements)
- [Installation](#installation)
- [Bundled browser runtime](#bundled-browser-runtime)
- [First launch](#first-launch)
- [Quick Start wizard](#quick-start-wizard)
- [Startup mode selector](#startup-mode-selector)
- [User interface overview](#user-interface-overview)
- [Session tab](#session-tab)
- [General tab](#general-tab)
- [AI tab](#ai-tab)
- [Random tab](#random-tab)
- [Logs tab](#logs-tab)
- [Trading Paints login flow](#trading-paints-login-flow)
- [TP manifest member ID override](#tp-manifest-member-id-override)
- [TP mule fast mode](#tp-mule-fast-mode)
- [Optional showroom total-page detection](#optional-showroom-total-page-detection)
- [How the local random paints pool works](#how-the-local-random-paints-pool-works)
- [AI support](#ai-support)
- [Download workers](#download-workers)
- [Same-session roster changes](#same-session-roster-changes)
- [Replay packs](#replay-packs)
- [Buttons and manual actions](#buttons-and-manual-actions)
- [Command-line options](#command-line-options)
- [Files and folders used by the app](#files-and-folders-used-by-the-app)
- [Troubleshooting](#troubleshooting)
- [FAQ](#faq)

---

## What the app does

Nishizumi Paints continuously watches iRacing session data through the **iRacing SDK**.

When you join a session, the app can:

1. detect the current session and driver list
2. identify each driver's car path and session context
3. ask Trading Paints for matching files
4. download the required files in parallel
5. extract `.bz2` files when needed
6. save the final files into the correct local iRacing paint folders
7. optionally trigger an iRacing texture reload
8. optionally fill missing paints with a **Local** or **Online** fallback source
9. optionally recycle downloaded TP car sets into a reusable **local random paints pool**
10. keep watching for the next session automatically

What it can fetch and save depends on what is available for the user and car combination, but it now treats the session assets separately so you can see **car**, **suit**, and **helmet** progress more clearly.

---

## How Nishizumi Paints handles missing paints

Not every driver in a session has a usable Trading Paints livery for the current car.

The app can apply fallback paints for:

- **real drivers without a TP paint**
- **AI drivers without a TP paint**

The fallback handling is not limited to the main car texture anymore. The app can also try to resolve **helmet** and **suit** files using the same general fallback idea when those files are missing.

Then you choose a **Preferred source**:

- **Online**
- **Local**

### Online

The app uses the connected Trading Paints account to pull random showroom paints for the missing targets.

### Local

The app uses the **local random paints pool** that it has already built from previous downloads and local sources.

### Important detail

Even if you choose **Online**, the **local random paints pool still matters**.
If the online showroom process fails for a target, the app can still fall back to local material when available.

---

## Why Online fallback is recommended

For most users, **Online** is the best and recommended source preference.

Why:

- it usually gives much better variety
- it can pull random paints directly from the Trading Paints showroom
- it avoids being limited only to paints you already cached locally

The app itself now encourages this path in Quick Start and in the Random tab.

**Local** still has value, but mainly as:

- a backup
- an offline-friendly option
- a way to reuse already captured material

---

## Primary account vs secondary mule account

When you use **Online** fallback, the app needs a Trading Paints account connected in the browser profile used by Nishizumi Paints.

You have two practical options:

### 1. Primary account

This is the same account you normally use.

Use this when:

- you want the simplest setup
- you do not have a separate account for the app

In this mode, the app protects and restores your original paint after online fallback activity.

### 2. Secondary / smurf / mule account

This is a separate account used only so the app can switch paints, capture them, and use them as random showroom fallback sources.

This is usually the **preferred** setup for power users.

Use this when:

- you want the cleanest separation between your racing account and the account doing the paint switching
- you want the fastest online fallback workflow
- you do not want your main account's Trading Paints car to keep changing while the app is working

If you already have or want to keep a separate account dedicated to the app, this is the best place to use it.

When using a mule account, the app can enable **TP mule fast mode**, which skips extra restore/protection steps that only matter when the account is also used for normal racing.

---

## Important warning about the connected Trading Paints account

This is the most important thing to understand before using **Online** fallback.

To pull a random showroom paint, Nishizumi Paints temporarily changes the **active paint on the connected Trading Paints account**.

That means:

- if you connected your **primary account**, the active paint on that account can temporarily change while the app is working
- after the download is captured, the app restores the original paint again
- if you connected a **secondary mule account**, that mule account is the one that changes instead

This behavior is normal and required for the current online fallback method.

So in simple terms:

- **Primary account** → your own connected TP account changes temporarily, then gets restored
- **Mule account** → the mule account changes temporarily, which is usually better for convenience and speed

If you do not want your main Trading Paints account to be used this way, use a separate mule account.

---

## Requirements

- **Windows**
- **iRacing** installed
- iRacing SDK available
- Python 3.10+ if running from source

Main Python packages used by the runtime include:

- `requests`
- `PyYAML`
- `pyirsdk`
- `playwright` for the online Trading Paints browser/profile workflow

---

## Installation

### Option 1: run from Python source

1. Install Python
2. Clone or download the repository
3. Install dependencies:

```bash
pip install -r requirements.txt
```

4. If you plan to use **Online** fallback from source, also make sure the Playwright browser runtime is available in a way your environment expects.
5. Run the current script.

### Option 2: use a compiled Windows EXE

1. Download the latest release package from GitHub
2. Extract the full release folder
3. Keep the EXE and its support folders together
4. Open the EXE
5. Go through the startup selector and Quick Start on first use

If you use a compiled **directory/onedir** release, do not separate the EXE from its support folders.

---

## Bundled browser runtime

The compiled app can use a **bundled / embedded Chromium-based browser runtime** for the Trading Paints login flow.

This is useful because the app does not have to depend only on a separately installed Google Chrome anymore.

### What the app checks first

If available, the app can prefer a browser shipped with the app itself, for example inside folders such as:

- `embedded_browser`
- `browser`
- `chrome`
- `chrome_runtime`
- `chrome-portable`
- `ms-playwright`

Typical expected layouts include a direct `chrome.exe` or a `chrome-win64\chrome.exe` style folder.

### If no bundled browser is available

The app can still fall back to installed Chromium-based browsers such as:

- Google Chrome
- Microsoft Edge
- Brave
- Chromium

### Practical recommendation

For normal EXE releases, keep the bundled browser files exactly where the release package expects them. Do not move the EXE somewhere else by itself if your package includes a local browser runtime.

---

## First launch

On first launch, the app is meant to guide the user instead of dumping every setting at once.

The intended normal flow is:

1. choose **normal window** or **console**
2. go through the **Quick Start** wizard
3. choose Local or Online fallback preference
4. connect Trading Paints if using Online
5. finish setup
6. leave the app running and go race

For most users, the best first setup is:

- **normal window** first
- **Online** preferred source
- **secondary mule account** if available
- **TP mule fast mode** enabled only for that secondary account

---

## Quick Start wizard

The app now includes a built-in **Quick Start** wizard.

It appears on first setup and is meant to help a non-technical user finish the important decisions quickly.

The wizard walks through:

1. **Startup mode guidance**
2. **Missing paint fallback targets**
3. **Preferred source**
4. **Trading Paints login**
5. **Ready / final recommendations**

### Important Quick Start behavior

- if you choose **Online**, you cannot finish Quick Start until the Trading Paints login succeeds
- if you connect a **smurf / mule** account there, the app automatically enables **TP mule fast mode** for that profile
- after a successful smurf login, the app asks for the **secondary Trading Paints member ID**
- if the login succeeds during Quick Start, the app waits and only restarts **after** the wizard is finished

---

## Startup mode selector

Before the main window, the app can show a small startup selector.

It lets you choose:

- **GUI / normal window**
- **Console / headless**

### Recommended usage

- **Normal window** is recommended for initial setup
- **Console / headless** is for advanced users after the app is already configured

The app also reminds the user that the startup selector can be shown again by:

- holding **Shift** while opening the app
- using `--gui`
- resetting the program settings

### Shared settings

GUI and console/headless use the same settings file.

---

## User interface overview

The current UI has **five tabs**:

- **Session**
- **General**
- **AI**
- **Random**
- **Logs**

The idea is:

- **Session** = what the app is doing right now
- **General** = core behavior and maintenance
- **AI** = AI-specific tools
- **Random** = fallback logic and online/local source choice
- **Logs** = diagnostics, export, reset

---

## Session tab

The **Session** tab shows the live session and the per-driver status.

The current driver list includes columns such as:

- overall state
- **car** state
- **suit** state
- **helmet** state
- number
- iRating
- license
- safety rating
- name

### Important fallback labels

The Session tab can distinguish between:

- **FALLBACK LOCAL**
- **FALLBACK ONLINE**

That helps the user understand whether a missing paint was filled from the local pool or from the online Trading Paints workflow.

Other states can include:

- queued
- downloading
- downloaded
- missing
- skipped
- replay pack

The separate **car / suit / helmet** columns are there so the user can see exactly which asset type is missing, queued, downloaded, or resolved by fallback.

---

## General tab

The **General** tab now contains the broad app settings, the action buttons, download worker settings, and the **Local random paints pool** controls.

### General settings

- **Auto start**
- **Start minimized**
- **Keep running in background on close**
- **Auto refresh paints**
- **Check for updates automatically**

### Session settings

- **Update my own paints**
- **Keep my livery locally**
- **Delete live session paints**

### Download settings

- **Worker mode**
- **Manual manifests**
- **Manual downloads**
- **Manual saves**

### Actions

- **Clear downloaded**
- **Refresh paints**
- **Paint folder**
- **Check updates**

### Local random paints pool

This block was moved to the General tab on purpose, because it matters in all modes.

The description is intentionally simple:

> Keeps extra local paints the app can reuse later when a driver or AI has no TP paint. This still matters even if you prefer Online.

Controls include:

- **Recycle downloaded TP car paints into the local random pool**
- **Max size (GB)**
- **Open pool**
- **Clean pool now**
- **Rebuild from current files**

---

## AI tab

The **AI** tab now contains only AI-related actions that are not the general random fallback source selection.

### AI sync

- **Sync TP AI rosters**

### AI actions

- **Sync AI rosters**
- **Clone active AI roster**
- **Randomize active AI roster**
- **Copy my car to AI**
- **Copy session cars to AI**

### AI folders

- **AI rosters**
- **AI livery folder**

---

## Random tab

The **Random** tab is now meant to feel more like a guided setup flow.

### Step 1 • Who should get fallback paints?

- **Fallback for drivers without a TP paint**
- **Fallback for AI drivers without a TP paint**

These are both enabled by default.

### Step 2 • Preferred source

Options:

- **Local**
- **Online**

The preferred source now defaults to **Online**.

If the user switches to **Local**, the app can show a final reminder encouraging the user to consider **Online**, because it usually gives better variety.

### Step 3 • Online Trading Paints

This area stays visible even when Local is the selected preference.
The goal is to keep the logic clear:

- Local can be the selected preference
- Online settings can still be prepared in advance
- the local pool still matters either way

When Local is selected, the Online area can visually show that it is **OFF** for the current preference while still allowing configuration.

The login flow can use a bundled browser runtime if your release package includes one.

---

## Logs tab

The **Logs** tab now contains:

- **Show activity**
- **Verbose logs**
- **Show TP monitor**
- **Export log**
- **Reset app settings**

### Reset app settings

This deletes the saved config file and restarts the app with defaults.

That is useful when the user wants a full clean reset.

After resetting settings, the app should show the startup flow again, including:

- startup mode selection
- first-time Quick Start

---

## Trading Paints login flow

You can connect Trading Paints from the **Random** tab or through **Quick Start**.

### Account choice popup

The app now asks whether you want to connect:

- **Primary account**
- **Smurf / mule account**

### Browser instruction popup

Then the app explains that the browser will open and that you should:

1. log in to Trading Paints
2. wait until site authentication finishes
3. minimize the browser
4. come back to Nishizumi Paints
5. click **I logged in**

### Success popup

When the login is confirmed successfully, the app shows:

- **Logged in successfully!**

### Smurf / mule account extra step

If the connected account is a secondary smurf/mule account, the app then asks for the **Trading Paints member ID** of that account.

This is important because the app cannot automatically infer the secondary member ID from your main iRacing local user.

If the user skips this or enters the wrong value, online fallback may later fail and the log will tell them to fix the member ID override.

---

## TP manifest member ID override

This field is for the case where:

- the Trading Paints account used by the app
- is **not** the same account as the local iRacing user in the session

That is exactly what happens in a typical **mule account** setup.

If you are using a secondary Trading Paints account, this field is usually required.

### Why it matters

The online fallback needs to poll the correct Trading Paints member manifest.
If the member ID is wrong, the app may switch paints on the connected account but fail to see the updated manifest files.

### Practical rule

- **Primary account**: usually leave this empty
- **Secondary mule account**: usually fill this in with that secondary account's TP member ID

---

## TP mule fast mode

This option should be used **only** when the connected Trading Paints account is a **secondary mule account**.

What it does:

- skips original-scheme capture
- skips final original-scheme restore
- skips slow dashboard confirmation loops
- polls the manifest more directly after each `setScheme`

This makes the online fallback faster and cleaner for a mule account.

### Do not use mule fast mode on your normal main account unless you fully understand the behavior

Why:

- in mule fast mode, the app does not restore the original paint at the end
- that is fine for a dedicated mule account
- that is usually **not** what a normal user wants on their main account

---

## Optional showroom total-page detection

The Online Trading Paints area includes an optional checkbox:

- **Detect showroom total pages (slower)**

### What it does

When enabled, the app first probes the showroom and detects the real total number of pages for that car.
Then, instead of using the fixed default page range, it chooses its random showroom page from the **real detected range**.

### What it does not do

It does **not** mean the app will always fetch many pages.
The normal idea is still:

- choose one random page first
- avoid repeating already-used pages in the same session/car
- only go to another page if one page does not provide enough usable schemes

### Why it is optional

Because it adds overhead.
It is mainly for users who want a more accurate random-page range and are willing to trade some startup time for that.

### Without this option

The app chooses random showroom pages from a fixed built-in range.

### With this option

The app chooses random showroom pages from the **real detected total** for that showroom.

---

## How the local random paints pool works

The local random paints pool is a reusable local cache.

It stores compatible paint sets that the app has already downloaded or rebuilt into the pool.

This pool is used for:

- local fallback for real drivers
- local fallback for AI
- backup when online fallback fails
- future reuse instead of losing good downloaded paints

### Important practical point

Even if your preferred source is **Online**, you usually still want the local pool enabled.
That is why it now lives in the **General** tab.

---

## AI support

AI support is now clearer and more separated from the general random fallback source choice.

You can:

- sync Trading Paints AI rosters
- clone the active AI roster
- randomize the active AI roster from local material
- copy your own car into AI livery storage
- copy session cars into AI storage

---

## Download workers

The app supports three worker modes:

- **Session Total**
- **Auto**
- **Manual**

### Session Total

This is now the default worker mode for new configs.

It automatically sets:

- **manifests** = exact number of users in the current session
- **downloads** = exact number of queued download items
- **saves** = exact number of queued save items

This mode is meant for users who want the app to use the full current session size instead of the normal auto-tuned caps.

### Auto

This is the adaptive mode.
The app uses its own tuning rules and configured caps.

### Manual

This is for advanced users who want fixed values.

Manual controls:

- manifests
- downloads
- saves

Allowed range: **1 to 100**

### Saved choice

The selected worker mode is stored in the normal settings file, so the app remembers whether you left it on **Session Total**, **Auto**, or **Manual**.

---

## Same-session roster changes

The app can detect when the roster changes **inside the same session**.

Instead of treating that like a full new session every time, the intended behavior is to refresh the current session more intelligently so it does not have to throw away and redownload everything that was already resolved for unchanged drivers.

In practical terms, the goal is:

- keep what is already valid for the current session
- only fetch what is actually new or newly missing
- avoid unnecessary full-session redownloads when a few people join or leave

This is especially useful in busy sessions where the roster can keep changing.

---

## Replay packs

The app also supports replay-pack capture and restore logic.

This can help preserve the paint set of a session for replay use later.

---

## Buttons and manual actions

### General tab

- **Clear downloaded**
- **Refresh paints**
- **Paint folder**
- **Check updates**

### General > Local random paints pool

- **Open pool**
- **Clean pool now**
- **Rebuild from current files**

### AI tab

- **Sync AI rosters**
- **Clone active AI roster**
- **Randomize active AI roster**
- **Copy my car to AI**
- **Copy session cars to AI**
- **AI rosters**
- **AI livery folder**

### Random tab

- **Connect Trading Paints**
- **I logged in**
- **Showroom**
- **Auth profile**
- **OK** for member ID override

### Logs tab

- **Export log**
- **Reset TP monitor**
- **Reset app settings**

---

## Command-line options

Common examples:

```bash
python nishizumi_paints.py
python nishizumi_paints.py --gui
python nishizumi_paints.py --nogui
```

Important behavior:

- `--gui` forces the normal window
- `--nogui` forces console/headless mode
- holding **Shift** while opening the app shows the startup selector again

---

## Files and folders used by the app

### Main settings file

```text
%APPDATA%\NishizumiPaints\settings.json
```

### Local paint folder

```text
Documents\iRacing\paint
```

### Random pool folder

```text
%APPDATA%\Nishizumi-Paints\RandomPool
```

### AI rosters folder

```text
Documents\iRacing\airosters
```

### AI livery folder

```text
%APPDATA%\Nishizumi-Paints\AiLiveries
```

### Replay packs folder

```text
%APPDATA%\Nishizumi-Paints\ReplayPacks
```

### Trading Paints auth profile

This is the persistent browser profile the app uses for the online Trading Paints workflow.

### Temporary working folder

```text
%TEMP%\NishizumiPaints
```

### Optional bundled browser folder

Depending on your build/release layout, the EXE can also use a browser kept next to the app, commonly in a folder such as:

```text
embedded_browser
```

---

## Troubleshooting

### Online fallback is selected, but it is not working

Check these first:

- Trading Paints login really succeeded
- the correct account is connected
- if using a secondary account, the **TP manifest member ID override** is filled correctly
- the account is allowed to access the showroom normally
- the activity log does not show an online auth/profile error
- if your EXE package uses a bundled browser, make sure the EXE was not separated from it

### I connected a smurf account but online fallback still fails

Most likely causes:

- the secondary Trading Paints member ID was not entered
- the member ID was entered incorrectly
- the app can log in, but is polling the wrong member manifest

The log should warn about this kind of problem.

### Why is my paint changing on Trading Paints?

Because that is how the online showroom fallback works.
The app temporarily changes the connected account's active paint to capture the files.

If you do not want this on your main account, use a dedicated mule account.

### Should I use mule fast mode?

Only for a dedicated mule account.
Do not treat it as a generic speed boost for your normal primary account.

### The app is open but not processing a session

Check:

- iRacing is running
- the SDK is available
- you are in a valid session
- the log is visible

### Why did the session rerun when people joined or left?

A roster change inside the same session can trigger a refresh pass.
The current goal is to keep that refresh as incremental as possible instead of treating the whole session like a brand new one.

### I want to start over from scratch

Use **Reset app settings** in the Logs tab.
That deletes the config and restarts the app with defaults.

---

## FAQ

### Do I need to keep the app open?

Yes. The app only works while it is running.

### Is Online or Local better?

For most people, **Online** is better and recommended.
It gives much better variety.

### Does Local still matter if I use Online?

Yes.
The local random paints pool still matters because it can be reused later and can still act as backup.

### Can I race on one account and connect Trading Paints with another?

Yes.
That is exactly what the **secondary / smurf / mule account** workflow is for.

### Why does the app ask for a secondary Trading Paints member ID?

Because the app cannot automatically infer the member ID of a separate connected Trading Paints account from your local iRacing user in the current session.

### What is the best advanced setup?

Usually:

- race on your normal main account
- connect Trading Paints with a secondary mule account
- fill in the mule account's TP member ID override
- enable **TP mule fast mode**
- keep **Online** as the preferred source
- leave **Session Total** as the worker mode if you want the app to scale exactly to the current session size

### Can I use console mode every day?

Yes, but it is mainly for advanced users after the initial setup is already done.
The normal window is recommended first.
