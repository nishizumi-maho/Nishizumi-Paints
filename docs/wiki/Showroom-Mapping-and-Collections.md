# Automatic Car Identification and Collections

This page covers how Nishizumi Paints connects iRacing car directories to Trading Paints vehicles without a bundled seed or user-edited mapping.

## Automatic identity sources

The app combines:

- the iRacing SDK car name, car ID, and `CarPath`
- car directories observed in Trading Paints manifests
- the live Trading Paints template catalog at `https://www.tradingpaints.com/cartemplates`
- the live Trading Paints vehicle index at `https://www.tradingpaints.com/showroom`

The template page publishes the vehicle name and the exact `Documents/iRacing/paint/...` directory. The showroom page publishes the vehicle MID and its Oval, Road, or Driver category. The two are joined on the vehicle name to produce the bridge used by public showroom downloads.

Trading Paints groups several iRacing directories under one showroom vehicle (one `Dirt Sprint Cars` vehicle covers the 305, 360, and 410 templates). When a template name has no exact match, the directory segments are used to pick the most specific vehicle that fits, and an ambiguous match is dropped instead of guessed. A dropped template only loses public showroom features for that car; downloads still work, because they use the paint directory reported by iRacing and Trading Paints.

## New cars

The catalog is loaded automatically, cached in memory for six hours, and refreshed immediately when an unknown car directory is requested. If iRacing exposes a different directory alias, the app can match it to the Trading Paints vehicle using the SDK car name.

The last catalog that was built successfully is also saved to `%APPDATA%\NishizumiPaints\.nishizumi_tp_car_identity.json` and reused for up to 30 days whenever Trading Paints is unreachable or changes its page layout, so the app never starts with an empty catalog.

No Nishizumi Paints release, JSON edit, seed update, or review dialog is required.

## Manifest handling

Manifest `<carid>` values identify paint assets, not Trading Paints vehicle MIDs. Nishizumi Paints therefore uses manifest directories as runtime validation and never treats a paint asset ID as a vehicle ID.

## Direct showroom links

The Showroom tab can import full `showroom/view/...` links or raw scheme IDs. For cars, the automatic identity catalog places the imported asset into the correct local bucket.

## Collection imports

Collections work without browser automation. The app loads collection JSON, separates cars from helmets and suits, resolves car MIDs through the live identity catalog, and saves results into the RandomPool or collection cache.

Mixed-vehicle collections are supported.
