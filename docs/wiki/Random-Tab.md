# Random Tab

The Random tab controls how fallback paints are chosen and where they come from.

## Step 1: Who should get fallback paints

You can enable random fallback separately for:

- real drivers
- AI drivers
- cars
- helmets
- suits

In Easy mode, the most important fallback toggles are surfaced directly so non-technical users do not need to switch to Advanced mode.

## Step 2: Online fallback lanes

Version 6.0.0 exposes three worker strategies:

### Safe

Safe is the default recommended mode.

It uses adaptive concurrency with protective caps and is meant to avoid excessive load while still being fast.

### Session Total

Session Total is the maximum-throughput mode.

It is intentionally uncapped relative to the current session totals. If a user chooses this mode, the app assumes they want maximum parallelism.

### Manual

Manual mode lets advanced users define their own manifest, download, and save worker counts.

## Step 3: Public showroom

This area describes the public showroom online fallback path and sits next to the local RandomPool tools.

Online fallback means the app can use a random public Trading Paints showroom asset when a driver has no usable normal Trading Paints paint.

## Local RandomPool

The local RandomPool is the last fallback layer when online sources are unavailable, exhausted, or disabled.

The user can:

- open the pool
- clean it
- rebuild it from current files
- choose whether downloaded session paints should be recycled into it

In 6.0.0, recycling defaults to disabled.
