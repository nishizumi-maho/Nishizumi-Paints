# Online Fallback System

The online fallback system is the part of Nishizumi Paints that fills missing liveries from public Trading Paints showroom data when a driver does not already have a usable normal Trading Paints paint.

## Main design in 6.0.0

The current release is centered on a public no-browser path:

- no embedded browser is required for the normal fallback flow
- no Trading Paints login is required for the normal public path
- public cars, helmets, and suits are all supported

The app still contains legacy authenticated showroom logic, but the public direct-download path is the primary architecture now.

## Decision order

At a high level, the app tries to resolve a driver like this:

1. normal Trading Paints manifest result if one exists
2. public online fallback if enabled and the driver is eligible
3. local RandomPool fallback if online fallback cannot provide a usable result

That is why the Random tab, General tab, and Showroom tab all affect the final outcome even though the live work happens automatically.

## Public showroom cars

For cars, the online fallback needs a mapping from the iRacing directory to the Trading Paints showroom vehicle. Once that exists, the app:

1. loads one or more showroom JSON pages
2. filters out unusable candidates
3. chooses a candidate while trying to avoid duplicates
4. downloads the public compressed car asset
5. also attempts the public spec map by default
6. saves the result
7. triggers iRacing texture reload

## Public showroom helmets and suits

Accessories use fixed Trading Paints driver categories:

- `Driver / 118 / Helmets`
- `Driver / 119 / Suits`

That means the app does not need a per-car mapping just to find public helmet and suit pools.

## Lane modes

The lane settings in the General tab control how many car groups can be processed online at the same time.

### Safe

Safe mode runs one car lane at a time. It is slower, but it keeps the public fallback stage easier to reason about.

### Manual

Manual mode runs up to the user-selected lane count.

### Session Total

Session Total runs one lane per car group with no extra protective hard cap. It is the most aggressive mode.

## Process cars, helmets, and suits together

When the advanced `process all together` option is enabled, the app can run:

- car lanes
- helmet stage
- suit stage

at the same time.

When it is disabled, the order becomes:

1. cars
2. helmets
3. suits

## Retry policy

The online fallback can give timed-out targets a final retry stage before the app gives up and falls back locally.

This is separate from the normal HTTP retry loop. It is about targets that were accepted into the online fallback process but still did not finish in time.

## Spec maps

Public online car fallback now attempts the spec map by default. If the showroom MIP URL is available, the app downloads it without needing a separate manual step.

## Repetition control

The app tries to avoid reusing the same public scheme repeatedly by tracking:

- already-used sources in the current pass
- recent schemes by directory
- already-assigned fallback choices

The goal is to reduce visible repetition within the same session and across consecutive random requests.

## Unavailable public assets

The app treats `401`, `403`, and `404` as unavailable public assets and logs that explicitly. That is why a showroom page can look valid while an actual direct asset URL is still skipped.

## Relationship to the RandomPool

If online fallback is enabled but the public path fails or runs out of usable options, the app can fall back to the local RandomPool immediately afterward.

That is why a driver may still receive a usable fallback paint even when the public showroom stage logged a skip or timeout.
