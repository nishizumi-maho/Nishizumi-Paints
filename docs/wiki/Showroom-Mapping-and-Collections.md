# Showroom Mapping and Collections

## Showroom mapping

The app needs a reliable mapping between iRacing vehicle identifiers and Trading Paints showroom vehicle pages.

When a mapping is missing or uncertain, the review dialog helps the user choose the correct showroom entry.

## Mapping review goals

- make the correct vehicle obvious
- allow quick verification by opening the selected TP page
- mark vehicles as unsupported when needed

## Included fix

Version 6.0.0 updates the mapping seed to cover **BMW M2 CSR** correctly.

## Collections

Collections are used for two separate tasks:

1. collection-based fallback seeding
2. collection-based RandomPool downloads

The no-browser workflow supports downloading public collection assets directly when they are available publicly.

## Collection behavior

- collections can be entered by raw ID or URL
- public compatible assets are discovered and cached
- the app avoids repeats within the same session where possible
