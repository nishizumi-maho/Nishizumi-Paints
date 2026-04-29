# Session and Download Pipeline

This page describes the main runtime pipeline from session detection to applied paints.

## 1. Startup and monitoring

The app starts the monitor service, acquires the single-instance lock, and begins watching the iRacing SDK.

At this point it can also:

- update the tray state
- check for updates
- trigger AI roster sync
- start showroom mapping review

## 2. Session detection

When the SDK exposes a usable session, the app builds an internal `Session` object containing:

- session ID
- local user and team identity
- users and AI entries
- series and league context
- car directories
- superspeedway state

## 3. Manifest stage

For each session user, the app attempts to resolve normal Trading Paints assets through:

1. session-aware manifest lookup when possible
2. single-user manifest fallback when needed

This stage decides which normal TP files already exist for the session before fallback even starts.

For Team sessions, team assets are preferred per item. If the team has no car, helmet, or suit for the active car, the matching General-tab option can retarget the current in-car driver's personal asset for that same item to the team file path.

The app also starts an experimental preload pass for Team sessions. It caches personal car, suit, and helmet files for team drivers exposed by the iRacing session data, then reuses that cache before making a fresh fallback download.

The session fingerprint includes the active driver's iRacing ID, so a driver swap in the same team car triggers a refresh instead of reusing the previous driver's files. When that happens, the log records the old and new driver and the Session tab updates the last-swap column.

## 4. Download stage

Resolved download items are queued and fetched using the configured worker mode.

This includes:

- car
- car spec
- car decal
- helmet
- suit

The download stage writes into temp files first.

## 5. Save stage

After download, the app:

- extracts bz2 payloads when needed
- saves files into the correct iRacing paths
- applies team naming when relevant
- writes superspeedway variants when required

## 6. Texture reload

Once files are in place, the app uses the iRacing SDK texture reload path. It can debounce or delay reloads if the SDK says reload is not currently safe.

## 7. Fallback resolution

Only after the normal TP stage is known does the app decide which drivers still need fallback.

Fallback can then come from:

- public showroom online fallback
- local RandomPool
- collection-backed local cache

## 8. Session-row updates

As saves and fallback actions happen, the app updates:

- row asset state
- overall row status
- per-item source, such as Team paint, Driver paint, Random, or iRacing default
- current driver
- last detected team driver swap
- last refresh time
- Trading Paints source metadata
- monitor counters and summaries

This is what keeps the Session tab and Logs tab synchronized with the actual pipeline.

## 9. Cleanup and archival

At session end, the app can:

- remove temporary session files
- optionally recycle live-session paints into the RandomPool
- preserve the local user’s livery when configured
- clear session-only state so the next session starts cleanly

## 10. Why the pipeline matters

Most user-visible bugs map to one of these stages. That is why the documentation and logs are organized around:

- manifest
- download
- save
- reload
- fallback
- cleanup
