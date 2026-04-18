# Showroom Mapping and Collections

This page covers the parts of the app that connect iRacing car identifiers to Trading Paints showroom vehicles and the tools that use those mappings for manual or automated imports.

## Why mapping exists

The public showroom JSON API is organized by Trading Paints vehicle pages. The live iRacing SDK and local paint folders are organized by iRacing car directories.

The app needs a bridge between those two worlds.

That bridge is the TP showroom mapping.

## Bundled seed and user override

The repository ships a bundled seed at:

- `data/tp_showroom_mapping.seed.json`

The app can also maintain a user override copy at:

- `%APPDATA%\NishizumiPaints\tp_showroom_mapping.seed.json`

At runtime the app merges the bundled seed with the user override so local corrections can coexist with the shipped defaults.

## Startup scan and review

The app can scan:

- the iRacing active-car source
- the public Trading Paints showroom catalog

It then scores likely matches and produces pending-review items for vehicles that are still unmapped.

The review dialog lets the user:

- accept a candidate
- mark a car as not available in Trading Paints
- skip a car
- open the selected Trading Paints page
- open the JSON file directly

The review UI is intended to make the mapping decision easier, not to force the user to understand the raw JSON structure first.

## Direct showroom links

The Showroom tab can import:

- full `showroom/view/...` links
- raw scheme IDs

The app then inspects the showroom view page to determine:

- title
- vehicle name
- whether it is a car, helmet, or suit

For cars, the mapping is used again to place the imported asset into the correct local bucket.

## Collection imports

Collections now work without browser automation.

The app can:

- parse a collection URL or raw collection ID
- request the collection JSON directly
- separate car items from helmet and suit items
- map cars back to iRacing directories when possible
- save the results into the RandomPool or collection-specific cache

## Mixed-vehicle collections

Collections can contain:

- multiple cars
- helmets
- suits

The app separates those correctly and stores them under the appropriate local directories or buckets.

## Practical workflow

If a new car is missing from the mapping:

1. let the startup scan or review dialog identify it
2. accept the correct Trading Paints vehicle
3. save the mapping
4. use that car normally in public fallback, showroom imports, and collection imports
