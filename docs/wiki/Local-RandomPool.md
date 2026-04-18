# Local RandomPool

The Local RandomPool is the app’s reusable local fallback cache.

## What it stores

- car paints
- helmets
- suits

## Why it matters

Even with online fallback enabled, the RandomPool still matters because it is the final backup when:

- online downloads fail
- public showroom assets are unavailable
- a session changes before an online fallback finishes

## Managing pool growth

The app tracks separate category sizes and an overall pool size.

## Recycling

In 6.0.0, recycling downloaded session paints into the RandomPool is disabled by default.

That means:

- manual showroom/collection downloads stay where you intentionally saved them
- live session downloads are not automatically archived into the pool unless the user opts in

## Manual maintenance

The UI can:

- open the pool folder
- clean the pool immediately
- rebuild the pool from the currently available files
