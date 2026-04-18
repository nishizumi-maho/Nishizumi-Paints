# Showroom Tab

The Showroom tab is the manual import area. It exists for users who want to seed the local pools or export public assets without waiting for a live session to need them.

## Supported manual inputs

### Trading Paints car ID

Enter a public Trading Paints car ID to download public showroom paints for that vehicle.

This mode is useful when:

- you know the Trading Paints vehicle page
- you want multiple random public paints for one car
- you want to seed the RandomPool for a specific series before racing

### Showroom links or scheme IDs

Paste one or more direct showroom links, or even raw scheme IDs, and the app will inspect each one.

The app uses the showroom view page to infer:

- whether the scheme is a car, helmet, or suit
- the scheme title
- the correct source link
- the matching iRacing vehicle when possible

### Collection URL or collection ID

Enter a Trading Paints collection URL or raw collection ID and the app will load the collection JSON directly.

The collection importer is meant for:

- curated leagues
- themed packs
- seeding the RandomPool or collection pool with mixed vehicles
- importing public helmets and suits in the same collection flow

## Destinations

The Showroom tools can save to:

- the RandomPool
- a custom folder

That distinction matters because RandomPool imports are meant for app reuse, while custom-folder exports are just manual downloads for the user.

## Public no-browser behavior

The 6.0.0 no-browser release is centered on public showroom access:

- no embedded browser is required for the normal showroom importer
- no Trading Paints login is required for the main public path
- public non-numbered, non-PRO assets are the intended direct-download target

## Relationship to RandomPool and collection pool

- importing to RandomPool makes the assets available to later local fallback
- importing a collection can also populate the collection-specific cache so the app can reuse curated sets later
