# Session Tab

The Session tab is the live monitor view. It is where the active session becomes concrete: drivers appear, assets are tracked, overrides can be applied, and fallback decisions can be inspected per target.

## What it shows

- the current session identity
- detected users and AI entries
- car, helmet, and suit state per row
- whether a row came from normal Trading Paints, fallback, or an override
- in Team sessions, the current driver, last confirmed driver swap, and last refresh time
- row-level actions such as randomize, fix, forget, or open the Trading Paints source

Outside Team sessions the table hides the Team-only swap column and labels the driver column as `Driver`. When a Team target is detected, the table expands to show `Current driver`, `Last swap`, and `Last refresh`.

Hover the `Car`, `Suit`, or `Helmet` cells to see the reason for that source, for example Team paint, current-driver personal paint, random fallback, or iRacing default.

## Session refresh behavior

The app rebuilds this view as the iRacing SDK changes. The tab is intended to follow session transitions correctly instead of staying stuck on the previous session state.

That matters because the Session tab is also the user-facing explanation of what the download pipeline decided for each driver.

In Team sessions, driver swaps are confirmed before the app clears and reapplies team files. After a confirmed swap, the app also retries the same team target briefly so late Trading Paints or iRacing updates can still be picked up without restarting the app.

## Main actions

### Fixed override

You can force a specific paint, helmet, or suit for a single driver. That override is remembered and beats normal fallback until it is cleared.

### Random

You can ask the app to fetch a new random result for one driver. The current build is expected to:

- download the new result
- save it into the correct iRacing target path
- trigger texture reload for that car
- update the row metadata so `Open TP` points at the new source

### Forget

Forget is now meant to behave like this:

- if the driver had a fixed override but also has a real Trading Paints paint, the app returns the driver to that real Trading Paints paint and reapplies it
- if the driver was only using a fallback paint, the app simply stops remembering that fallback for future use

### Open TP

When the row has a known Trading Paints source, `Open TP` should open the correct showroom or profile page. This includes fallback helmets and suits as well as cars.

## Typical reasons to use this tab

- verify whether a driver got a real Trading Paints paint or a fallback
- force a manual paint for a rival, teammate, or AI entry
- regenerate one driver without touching the whole session
- inspect which assets were missing
- confirm that texture reload happened after a manual change

## Relationship to other tabs

- the General tab sets the worker and lane behavior
- the Random tab sets who is eligible for fallback
- the Showroom tab seeds manual pools
- the Logs tab explains why a row ended up in its final state
