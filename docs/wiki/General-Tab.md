# General Tab

The General tab is the advanced-mode control panel for app-wide behavior. It does not hold the RandomPool panel anymore; that moved to the Random tab so fallback configuration is grouped together.

## Main areas

- interface mode
- startup and background behavior
- cleanup and self-protection options
- general download worker mode
- online fallback lane behavior
- iRacing Documents folder management

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

This section is separate from the main worker mode. It controls how many public showroom car lanes can run at once when the app is filling missing paints online.

### Safe

One car lane at a time.

### Manual

Use the configured manual lane cap.

### Session Total

One lane per car group with no extra hard cap. This is the fastest lane mode.

## Online accessory behavior

The General tab also holds the advanced online-fallback toggles for:

- processing cars, helmets, and suits together online
- giving timed-out online fallbacks one final retry stage before local fallback

Those settings work together with the Random tab. The Random tab decides who is eligible for fallback; the General tab decides how aggressively the online engine runs.

## iRacing Documents folder

The selected iRacing Documents folder is shown here and can be changed later. Changing it affects:

- live-session paint output
- AI roster syncing
- replay-pack features
- any local file operations that depend on the standard iRacing folder layout
