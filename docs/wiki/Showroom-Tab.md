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

### Team ID and car

Use the **Teams** tab when you know a Trading Paints Team ID and the target car.

In 6.3.2 and newer, the Teams form only asks for the required Team ID and car value. Optional manifest context is handled internally.

Accepted car values:

- Trading Paints car ID
- Trading Paints dashboard URL
- car name from the local showroom mapping
- iRacing paint directory

The app builds session-aware team manifest payloads and filters the response to the requested Team ID. Car-related assets must also match the resolved iRacing car directory. Helmet and suit assets are saved when Trading Paints includes them for that team.

## Destinations

The Showroom tools can save to:

- the RandomPool
- a custom folder
- the iRacing paint folder for team downloads

That distinction matters because RandomPool imports are meant for app reuse, while custom-folder exports are just manual downloads for the user.

Team downloads default to the iRacing paint folder because iRacing expects team files at:

- `paint/{car_directory}/car_team_{team_id}.tga`
- `paint/helmet_team_{team_id}.tga`
- `paint/suit_team_{team_id}.tga`

## Public no-browser behavior

The no-browser release is centered on public showroom access:

- no embedded browser is required for the normal showroom importer
- no Trading Paints login is required for the main public path
- public non-numbered, non-PRO assets are the intended direct-download target

In 6.3.2, the manual team downloader follows the same no-browser posture. It uses Trading Paints manifest endpoints and does not require local Trading Paints cookies or a stored login.

## Relationship to RandomPool and collection pool

- importing to RandomPool makes the assets available to later local fallback
- importing a collection can also populate the collection-specific cache so the app can reuse curated sets later
