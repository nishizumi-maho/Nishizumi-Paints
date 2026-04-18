# AI Tab

The AI tab covers AI-specific workflows that do not fit cleanly into the normal live-session path.

## What the AI tab is for

- syncing AI rosters from Trading Paints collections
- managing the member ID used for AI discovery
- preparing local AI assets so iRacing can use them directly
- working with AI roster content outside the immediate live session

## AI member ID

The app uses an iRacing member ID to discover collection-backed AI content. That ID is now asked during Quick Start and can be edited here later.

## Sync model

AI roster sync works like this:

1. request the member’s available Trading Paints collections
2. identify valid AI rosters
3. download the roster JSON file
4. normalize the driver entries
5. write the synced roster into the iRacing `airosters` folder
6. optionally download the related car, helmet, suit, and spec assets

The app also writes metadata alongside the synced roster so it can track where the roster came from.

## Important practical detail

The current app does not require a Trading Paints PRO workflow for standard AI roster support. The AI path is built around the collection and public/showroom-style asset logic already present in the main app.

## Random AI behavior

The AI workflow also intersects with the Random system. The config can decide whether AI entries are eligible for:

- random cars
- random helmets
- random suits

That is why the wizard and Random tab include separate AI toggles instead of treating AI the same as real drivers.

## When to use the AI tab instead of the Session tab

Use the AI tab when the goal is:

- preparing an AI carset before launching a session
- syncing or repairing roster metadata
- managing AI-specific collection content

Use the Session tab when the goal is:

- inspecting the live AI entries that are already in the active session
