# General Tab

The General tab is the advanced-mode control panel for app-wide behavior. It does not hold the RandomPool panel anymore; that moved to the Random tab so fallback configuration is grouped together.

## Main areas

- interface mode
- startup and background behavior
- cleanup and self-protection options
- iRacing UI car previews
- general download worker mode
- online fallback lane behavior
- automatic iRacing Documents detection with optional custom folder override

## Interface mode

This section lets the user switch between:

- Easy mode
- Advanced mode

Changing modes does not reset configuration. It only changes what the UI exposes.

## Startup and background

The main startup controls are:

- `Start with Windows`
- `Start minimized`
- `Keep running in background on close`
- `Auto refresh paints`
- `Check for updates automatically`

Easy mode also exposes the essential startup/background controls directly, but the same underlying config values are shared with this tab.

## Session protection and self behavior

This area controls how the app treats the local user and live-session paint cleanup. Depending on the current build, it can include settings such as:

- keep my livery locally
- update my own paints
- delete live session paints
- do not apply random paints in team events
- do not apply random paints to myself
- use driver personal car when team car is missing
- use driver personal suit when team suit is missing
- use driver personal helmet when team helmet is missing
- preload team drivers' personal paints

The self-protection options are important when the user wants fallback for everybody else but never wants the app to replace their own visible car with a random result.

The team-driver options are enabled by default. In Team sessions, the app tries the team's car, helmet, and suit first. If one item is missing for the team, the matching per-item option allows the app to use the personal paint for the driver currently in the car. When the active driver changes, the app refreshes the team target for the new driver. If neither the team nor that driver has the item, the normal random fallback rules apply; if random paints in team events are disabled, iRacing keeps its default item.

The preload option is also enabled by default. When a Team session is detected, the app caches personal paints for team drivers exposed by the iRacing session data. That cache can be applied immediately if one of those drivers later becomes the active driver in the team car.

In 7.0, Team driver swaps are treated conservatively: the app confirms a detected active-driver change before clearing and reapplying files, then schedules short follow-up refreshes so late iRacing or Trading Paints data can still be applied.

## iRacing UI car previews

This panel keeps your own Trading Paints assets in the iRacing paint folder at all times, so the 3D car viewer in the iRacing UI (`My Content > Cars`) always renders your livery instead of the default one.

It exposes:

- `Always show my paints in the iRacing UI car previews`, on by default
- `Re-check Trading Paints every N minutes`, default 30
- an optional `iRacing customer ID` override, empty means automatic detection
- `Sync previews now`
- a live status line with the car count, the resolved customer ID, and the last check time

The Easy screen shows a compact version of the same panel.

Session cleanup can no longer delete these files, and they are re-installed immediately after each cleanup pass. See [iRacing UI Car Previews](iRacing-UI-Car-Previews) for the full behavior, the customer ID resolution order, and troubleshooting.

## Download worker mode

This section controls the main manifest, download, and save worker counts for the session pipeline.

### Safe

Safe mode is the default recommended option. It uses adaptive workers with protective caps chosen by the app.

### Manual

Manual mode exposes fixed manifest, download, and save worker counts from `1` to `100`.

### Session Total

Session Total is the fastest aggressive mode. It removes the protective session cap and uses the current session size to drive worker parallelism as far as the runtime pipeline allows.

Use it when absolute throughput matters more than caution.

## Online fallback lanes

This section is separate from the main worker mode. It controls how many car models the online fallback works on at the same time. A lane is one car model (car directory): the drivers of that car are handled one after the other inside it.

### Safe

One car model at a time.

### Manual

Up to the configured number of car models at once.

### Session Total

Every car model in the session at once. This is the fastest lane mode. In a single-make race there is only one car model, so every mode behaves the same.

## Online accessory behavior

The section also holds two online-fallback toggles:

- **Process cars, helmets, and suits together online**: helmets and suits are fetched while the car lanes run, instead of after them.
- **Give timed-out online fallbacks one final online retry before local fallback**: a car, helmet, or suit whose download failed gets one more online try after the lanes finish. Only what is still missing after that comes from the local pool.

Before 7.3.6 these four settings were saved but not used: the online fallback handled one driver at a time.

Those settings work together with the Random tab. The Random tab decides who is eligible for fallback; the General tab decides how aggressively the online engine runs.

## Advanced folder settings

The app detects the iRacing Documents folder automatically. Most users do not need to choose a path manually.

Enable `Customize iRacing Documents folder` only when automatic detection points at the wrong folder or cannot find the folder. Manual selection affects:

- live-session paint output
- AI roster syncing
- replay-pack features
- any local file operations that depend on the standard iRacing folder layout