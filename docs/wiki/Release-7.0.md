# Release 7.0

Version 7.0 is the consolidated public release after 6.5.

## Main changes

- Team sessions can use the current driver's personal car, helmet, or suit when the Team item is missing.
- Team driver swaps are confirmed before repainting, then retried briefly to catch late session updates.
- The Session table supports multi-select actions with `Ctrl+click` and `Shift+click`.
- Double-clicking a Session row switches the iRacing camera to that driver's car.
- Random fallback sources can be marked as Favorite or Block from the Session tab.
- Manual overwrites store paint-history snapshots, and `Restore previous` can restore the last snapshot.
- Restore previous clears fixed-override state and reloads only affected cars.
- The Random tab is more compact and moves Step 3 controls higher.
- New or missing configs protect the local user by default.

## Recommended first checks after updating

1. Open **General** and confirm the Team fallback options you want:
   - use driver personal car when team car is missing
   - use driver personal suit when team suit is missing
   - use driver personal helmet when team helmet is missing
   - preload team drivers' personal paints
2. Open **Random** and confirm Step 1 target eligibility.
3. Choose `Online` or `Local` in Random Step 2.
4. In Random Step 3, confirm showroom source choices and Local RandomPool size limits.
5. Join or watch a session and use the Session table to inspect each row's source state.

## New Session table shortcuts

- `Ctrl+click`: toggle individual rows.
- `Shift+click`: select a range.
- Double-click row: switch the iRacing camera to that driver's car.

When multiple rows are selected, actions apply only to compatible selected rows. This lets you restore, randomize, favorite, block, or forget several drivers without forcing incompatible rows.

## Privacy notes

The 7.0 online fallback path does not need a Trading Paints login, password, cookie, token, or browser profile. Local runtime data such as settings, paint-history snapshots, RandomPool files, collection caches, and iRacing paint folders should stay out of source control.

