# AI Tab

The AI tab is dedicated to AI roster support.

## Main responsibilities

- store the iRacing member ID used for roster syncing
- sync AI rosters from Trading Paints/iRacing data
- control AI-related fallback behavior

## Why the member ID matters

AI workflows often need an explicit iRacing member ID so the app can discover and sync the correct roster data.

## Random behavior for AI

AI drivers can be included or excluded separately from real drivers for:

- random cars
- random helmets
- random suits

That separation makes it possible to be conservative in official sessions while still using broad random fallback in AI races.
