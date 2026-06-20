# Automatic Car Identification and Collections

This page covers how Nishizumi Paints connects iRacing car directories to Trading Paints vehicles without a bundled seed or user-edited mapping.

## Automatic identity sources

The app combines:

- the iRacing SDK car name, car ID, and `CarPath`
- car directories observed in Trading Paints manifests
- the live Trading Paints template catalog at `https://www.tradingpaints.com/cartemplates`

The Trading Paints catalog publishes the vehicle MID, display name, and exact `Documents/iRacing/paint/...` directory in one record. This is the authoritative bridge used by public showroom downloads.

## New cars

The catalog is loaded automatically, cached in memory for six hours, and refreshed immediately when an unknown car directory is requested. If iRacing exposes a different directory alias, the app can match it to the Trading Paints vehicle using the SDK car name.

No Nishizumi Paints release, JSON edit, seed update, or review dialog is required.

## Manifest handling

Manifest `<carid>` values identify paint assets, not Trading Paints vehicle MIDs. Nishizumi Paints therefore uses manifest directories as runtime validation and never treats a paint asset ID as a vehicle ID.

## Direct showroom links

The Showroom tab can import full `showroom/view/...` links or raw scheme IDs. For cars, the automatic identity catalog places the imported asset into the correct local bucket.

## Collection imports

Collections work without browser automation. The app loads collection JSON, separates cars from helmets and suits, resolves car MIDs through the live identity catalog, and saves results into the RandomPool or collection cache.

Mixed-vehicle collections are supported.
