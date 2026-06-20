# Runtime Paths and Files

This page documents where the app stores its runtime data and how that differs from repository files and installed binaries.

## Repository-side bundled files

The repository now keeps bundled resources in dedicated folders:

- `assets/icons/`
- `docs/wiki/`
- `archive/`
- `scripts/`

These are source-controlled files.

## Installed application files

The Windows installer places the app under:

- `%LocalAppData%\Programs\Nishizumi Paints`

That folder is for the executable and bundled runtime files, not for user-generated data.

## Main config path

The app stores the main config at:

- `%APPDATA%\NishizumiPaints\settings.json`

That file contains the saved `AppConfig` state, including UI mode, startup settings, fallback choices, worker preferences, and path overrides.

## Automatic car identity

Car identity is loaded from the live Trading Paints template catalog and cached in memory. There is no bundled showroom seed and no AppData mapping JSON.

## Additional AppData files

Examples of other runtime files include:

- `%APPDATA%\NishizumiPaints\.nishizumi_tp_recent_schemes.json`
- `%APPDATA%\NishizumiPaints\.nishizumi_driver_paint_overrides.json`
- `%APPDATA%\NishizumiPaints\.nishizumi_random_paint_preferences.json`
- `%APPDATA%\NishizumiPaints\.nishizumi_tp_login_status.json`

These are state files, not repository assets.

## Random and collection caches

Local fallback content uses different folders:

- `%APPDATA%\Nishizumi-Paints\RandomPool`
- `%APPDATA%\Nishizumi-Paints\CollectionPool`
- `%APPDATA%\Nishizumi-Paints\AiLiveries`
- `%APPDATA%\Nishizumi-Paints\DriverOverrides`
- `%APPDATA%\Nishizumi-Paints\PaintHistory`

Notice that some runtime folders use `Nishizumi-Paints` while the settings path uses `NishizumiPaints`. That is part of the current historical path layout preserved by the app.

## iRacing-side output

The app writes active live-session files into the iRacing Documents tree, especially:

- `{Documents}\iRacing\paint`
- `{Documents}\iRacing\airosters`

These are the files iRacing actually consumes.

## Temp folders

The app also uses temporary folders for:

- session downloads
- showroom staging
- collection staging
- replay-pack work

Those are not intended to be committed or packaged.
