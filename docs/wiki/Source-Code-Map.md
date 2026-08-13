# Source Code Map

This page is a guided map of the main script so a maintainer can find the right section quickly.

## Core resource and startup helpers

Look near the top of the file for:

- resource-path helpers
- AppData-path helpers
- browser compatibility stubs
- launch-mode helpers
- single-instance and headless support

These are the functions that decide where the app runs from and how it starts.

## Key data structures

Important shared types include:

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
- `AppConfig`

If you need to understand what information a later function expects, start here.

## Session and manifest functions

Important functions in the session/manifest area include:

- `parse_session_yaml`
- `_build_session_from_parts`
- `fetch_user_files`
- `_build_fetch_context_payload`
- `_matches_context_manifest_entry`

These functions convert raw SDK and Trading Paints data into structured download work.

## RandomPool and override functions

Important functions here include:

- `archive_saved_tp_sets_to_random_pool`
- `get_random_pool_stats`
- `enforce_random_pool_limit`
- `load_driver_paint_overrides`
- `save_driver_paint_overrides`
- `remember_driver_paint_override`

This section owns durable local fallback data.

## Automatic identity and showroom functions

Important mapping and showroom functions include:

- `_load_tp_showroom_mapping`
- `_parse_tp_car_templates_html`
- `_observe_iracing_car_identity`
- `_observe_tp_manifest_directory`
- `scan_tp_showroom_mapping_review`
- `_tp_showroom_mapping_entry_for_directory`
- `_tp_showroom_mapping_entry_for_mid`
- `_tp_fetch_showroom_page_batch_http`
- `_detect_tp_showroom_total_pages_http`
- `_fetch_tp_showroom_pool_http`
- `choose_showroom_paint_direct`
- `choose_showroom_accessory_direct`

The historical function names remain for compatibility, but the data now comes from the live Trading Paints template catalog rather than JSON mapping files.

## Collection functions

Important collection helpers include:

- `parse_tp_collection_ids_from_text`
- `fetch_tp_collection_items`
- `fetch_tp_collection_pool`
- `download_tp_collection_to_random_pool`
- `archive_saved_to_tp_collection_pool`

This section is where manual collection imports and collection-backed local reuse are implemented.

## AI functions

Important AI functions include:

- `_iter_ai_roster_asset_specs`
- `_download_ai_roster_asset`
- `sync_ai_roster_collection_assets`
- `fetch_active_ai_roster_collection_files`

These functions map AI roster JSON into local synced assets.

## Fallback orchestration

The two highest-level fallback entrypoints are:

- `apply_local_tp_random_fallbacks`
- `apply_tp_showroom_fallbacks_public`

If you want to understand who gets fallback, how lanes are scheduled, or how a fallback result becomes a saved file, this is the right area.

## iRacing UI car preview functions

The always-on iRacing UI previews live in one block just above `DownloaderService`:

- `resolve_iracing_ui_preview_member_id`
- `iracing_ui_preview_manifest_items`
- `sync_iracing_ui_car_previews`
- `install_iracing_ui_car_previews`
- `clear_iracing_ui_car_previews`
- `iracing_ui_preview_protected_paths`
- `read_iracing_hide_car_numbers`

`DownloaderService._maintain_ui_previews` schedules them from the main loop, `_run_ui_preview_worker` performs the work off the loop thread, and `_reassert_ui_previews_now` restores the files right after each cleanup pass.

## Main session processing

The central session pipeline eventually converges in:

- `process_session`

This is where the app pulls together manifests, downloads, saves, row state, fallback, summaries, and cleanup.

## Service and UI classes

Important classes near the bottom of the file include:

- `ConfigStore`
- `DownloaderService`
- `WindowsTrayIcon`
- `DownloaderUI`

If the question is about user interaction, status updates, widgets, the tray menu, or background service state, you will end up in this section.

## Scrollable tab pages

Tabs are built by `DownloaderUI._add_scrollable_tab`, which returns the frame the notebook shows and the page frame the tab content is built inside. The supporting pieces are:

- `preferred_window_size` — the window size chosen for the current screen
- `scrollable_page_geometry` — how big a page is inside its viewport and which scrollbars it needs
- `mousewheel_scroll_steps` — Tk wheel events translated into scroll units
- `DownloaderUI._sync_page_scroll` — applies the geometry and shows or hides the scrollbars
- `DownloaderUI._refresh_page_scroll_regions` — re-measures pages whose content appeared or disappeared, called from `_poll_service`
- `DownloaderUI._handle_page_wheel` — routes the wheel to the page under the pointer, unless an inner list can scroll itself

A page always fills its viewport, so widgets that stretch keep stretching; only the size beyond the viewport is scrolled.
