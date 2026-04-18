# Local RandomPool

The Local RandomPool is the reusable local fallback cache used when a driver needs a paint and the app either prefers local fallback or cannot complete an online fallback.

## Purpose

The RandomPool exists so the app can keep giving drivers varied fallback assets without depending entirely on a live Trading Paints lookup.

It is especially useful for:

- unreliable network conditions
- repeated sessions with the same car classes
- curated manual showroom imports
- collection-based fallback sets

## Default location

By default the pool lives under:

- `%APPDATA%\Nishizumi-Paints\RandomPool`

The app also maintains a separate collection-oriented cache under:

- `%APPDATA%\Nishizumi-Paints\CollectionPool`

## What can populate the pool

- manual showroom imports
- collection imports
- optional recycling of downloaded live-session paints

## Recycling behavior

Recycling of downloaded live-session paints is now off by default.

That means:

- manual imports remain available
- collection imports remain available
- live-session paints are removed at cleanup time instead of automatically becoming permanent local fallback material

## Size management

The pool uses:

- a total size limit
- separate category caps for cars, helmets, and suits

The app can clean older or excess content when limits are exceeded.

## Typical user actions

The Random tab lets the user:

- open the pool folder
- clean the pool now
- rebuild the pool from current files
- change the total and category caps
- enable or disable recycling

## How the app uses the pool

When a driver needs local fallback, the app:

1. looks for compatible entries by car directory or accessory type
2. tries to avoid repeating the same source too often
3. copies the selected local files into the correct iRacing target paths
4. treats the copied result like any other applied paint in the Session tab and logs

## Why the pool is separate from the install folder

The RandomPool is runtime data, not application data. Keeping it in AppData means:

- upgrades do not wipe it
- reinstalling the app does not destroy it
- the installer does not need to bundle or manage user-generated fallback content
