# Online Fallback System

Online fallback is what happens when a driver does not have a usable normal Trading Paints asset for the current session.

## Primary behavior in 6.0.0

The 6.0.0 release focuses on public showroom direct downloads.

That means the app can fetch:

- car paints
- helmets
- suits

directly from public showroom sources when available.

## Accessory behavior

Cars, helmets, and suits can now be processed together by default, which was restored as the default online behavior for new and migrated configs.

## Spec maps

When available, spec maps are downloaded by default for online car fallback so the applied paint has its matching extra material data.

## Open TP behavior

Fallback assets that resolve to meaningful public showroom pages expose clickable **Open TP** actions, including helmets and suits.

## Worker modes

- **Safe**: recommended, controlled concurrency
- **Session Total**: fully uncapped for maximum speed
- **Manual**: explicit counts

## No artificial startup delay

The previous pacing between random online downloads was removed so the online fallback stage can start immediately and use the selected concurrency mode fully.
