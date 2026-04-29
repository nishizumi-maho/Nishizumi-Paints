# Architecture Overview

The current repository centers almost all runtime logic in one main script:

- `Nishizumi_Paintsv6_nobrowser.py`

That file is large, but it is not random. It is organized into broad sections that each own a real part of the application.

## 1. Bootstrap, constants, and resource helpers

The top of the file defines:

- app metadata
- Trading Paints endpoints
- GitHub release endpoints
- worker defaults
- runtime filenames
- resource and AppData path helpers

This section is where the repository reorganization matters, because the script now resolves bundled files from `assets/` and `data/` instead of the repo root.

## 2. Legacy browser and authenticated showroom compatibility

Even though the current app is a no-browser release, the script still keeps older authenticated showroom helpers for:

- login-state detection
- member-ID detection
- persistent profile handling
- protected restore logic

Those helpers remain because the app evolved from earlier embedded-browser generations.

## 3. Launch mode, console, single-instance, and headless control

The next major block handles:

- launch-mode preference normalization
- optional console visibility
- single-instance locking
- signal passing between launches
- headless control server commands

This is the operational shell around the app before the business logic starts.

## 4. Data model

The script then defines the dataclasses and enums that the rest of the app passes around, including:

- `PaintType`
- `SessionId`
- `SessionUser`
- `Session`
- `DownloadId`
- `DownloadFile`
- `DownloadedFile`
- `SavedFile`
- `RandomPoolEntry`
- `RandomFallbackSummary`
- monitoring snapshots

This section is the shared vocabulary of the whole app.

## 5. Session parsing and low-level helpers

The app then implements:

- argument parsing
- logging setup
- iRacing Documents detection
- retry and worker-resolution helpers
- HTTP session helpers
- YAML/session parsing
- manifest parsing

This layer supports everything above it without being tied to one UI tab.

## 6. RandomPool, overrides, and mapping infrastructure

The next large block covers:

- RandomPool size management
- RandomPool archiving
- driver override persistence
- showroom mapping load/save/merge logic
- mapping scan and review support

This is the durable local-state layer of the fallback system.

## 7. Public showroom and collection logic

Another large section implements the public direct-download architecture:

- showroom JSON page fetches
- total-page detection
- candidate filtering and selection
- direct asset URL building
- link import helpers
- collection JSON loading
- collection-pool caching

This section is the real heart of the current no-browser workflow.

## 8. AI roster logic

The script also contains a dedicated AI section for:

- collection enumeration
- roster file download
- driver normalization
- AI asset syncing
- local AI roster metadata

## 9. Main live-session pipeline

The main processing pipeline covers:

- manifest requests
- download queueing
- save queueing
- texture reload
- fallback application
- cleanup
- session summaries and throughput statistics

This is where most user-visible work actually happens.

## 10. Config and service layer

The `AppConfig`, `ConfigStore`, and `DownloaderService` section is where the script turns a saved config into a long-running monitor.

This layer owns:

- config migration and normalization
- background worker lifecycle
- status callbacks
- snapshot generation for the UI

## 11. Tray and UI layer

The script then defines:

- `WindowsTrayIcon`
- `DownloaderUI`

The tray class owns the hidden-icon behavior. The UI class owns:

- Easy mode
- Advanced tabs
- Quick Start
- settings widgets
- session table
- showroom tools
- logs view

## 12. Main entrypoint

The last section wires everything together:

- parse args
- choose launch mode
- start UI or headless mode
- run the main event loop

## Why this matters

This architecture explains why the repository documentation is split between:

- user-facing tab pages
- runtime/path pages
- source-code map pages
- API notes

The file is large, but each part exists because the app is simultaneously:

- a downloader
- a fallback engine
- a tray application
- a wizard-driven UI
- an AI roster tool
- a buildable Windows release
