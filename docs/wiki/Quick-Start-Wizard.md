# Quick Start Wizard

The Quick Start wizard is the intended first-run path for the app. It is designed to get a new user into a safe working state without having to understand every advanced option first.

## What it configures

- Easy mode or Advanced mode
- iRacing Documents folder
- AI member ID
- random fallback scope for cars, helmets, and suits
- startup and background behavior
- default fallback mode and safe worker defaults

## Easy mode versus Advanced mode

### Easy mode

Choose Easy mode when the goal is:

- quick setup
- minimal visual clutter
- safe defaults
- keeping only the most important monitoring and random fallback controls visible

Easy mode still gives access to the core fallback behavior. The app does not become weaker; it simply hides most of the advanced panels.

### Advanced mode

Choose Advanced mode when the goal is:

- full control over live-session behavior
- detailed worker and lane settings
- collection pool configuration
- per-driver override management
- logs and diagnosis

You can switch between the two modes later from inside the app, so the wizard choice is not permanent.

## iRacing Documents detection

The wizard attempts to auto-detect the iRacing Documents folder. This matters because the app uses that location for:

- live-session paint output
- AI rosters
- replay-pack features
- session cleanup

If the folder is wrong, the app can still run, but the saved paints will go to the wrong place.

## AI member ID

The app uses an iRacing member ID to discover AI-related collection content and to keep the AI tab ready immediately after setup. The wizard asks for that value up front so the user does not need to dig for it later.

## Safe defaults applied by the wizard

The current 6.0.0 flow defaults to:

- Start with Windows enabled
- Keep running in background on close enabled
- auto-refresh enabled
- public online fallback available
- random helmets enabled
- random suits enabled
- safe worker mode available for general downloading

## Mapping review timing

The showroom mapping review prompt is intentionally delayed until after Quick Start completes. New users should not be interrupted by the mapping workflow before the base setup is finished.
