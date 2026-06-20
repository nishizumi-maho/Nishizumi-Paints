# Quick Start Wizard

The Quick Start wizard is the intended first-run path for the app. It is designed to get a new user into a safe working state without having to understand every advanced option first.

## What it configures

- Easy mode or Advanced mode
- iRacing Documents folder only when automatic detection fails
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

The wizard attempts to auto-detect the iRacing Documents folder. When detection succeeds, the wizard does not show a folder-selection page. It asks the user to choose manually only when the folder cannot be detected.

- live-session paint output
- AI rosters
- replay-pack features
- session cleanup

If the folder is wrong, the app can still run, but the saved paints will go to the wrong place. After setup, Advanced mode exposes `Customize iRacing Documents folder` in General for users who need a manual override.

## AI member ID

The app uses an iRacing member ID to discover AI-related collection content and to keep the AI tab ready immediately after setup. The wizard asks for that value up front so the user does not need to dig for it later.

In the normal flow this is the final wizard page, so the action button changes to `Finish` here.

## Safe defaults applied by the wizard

The current flow defaults to:

- Start with Windows enabled
- Keep running in background on close enabled
- auto-refresh enabled
- public online fallback available
- random helmets enabled
- random suits enabled
- safe worker mode available for general downloading

## Automatic car identity

Quick Start does not ask the user to review or edit car mappings. The live Trading Paints car catalog is refreshed automatically after setup.
