# Changelog

All notable user-facing changes to Nishizumi Paints are documented here.

## [7.1.2] - 2026-06-07

### Fixed

- Fixed Team-session driver-swap refreshes so active-driver updates no longer cancel the whole paint pipeline, and confirmed swaps only reapply paints for changed Team targets instead of clearing and redownloading the whole session.

## [7.1.1] - 2026-05-16

### Fixed

- Fixed Trading Paints downloads for cars whose iRacing paint directory is nested, such as `mx5\mx52016`, while preserving path traversal checks.

## [7.1.0] - 2026-05-13

### Stable Release

- Fixed manual Showroom collection downloads to import every downloadable public collection paint into the Local RandomPool instead of discarding public Pro-owned or stamped-number paints with the online-fallback eligibility filter.
- Fixed the Session table `Random` action so Local mode uses the Local RandomPool when Online fallback is disabled.
- Simplified first-run iRacing Documents handling: Quick Start asks for a folder only when automatic detection fails, and General hides manual path controls behind `Customize iRacing Documents folder`.
- Trimmed Quick Start so the normal flow finishes on the iRacing ID for AI collections step, and shortened the selected iRacing ID summary text.
- Fixed Session row camera switching so selecting a driver from the Session table always switches iRacing to the Chase camera for that car.

## [7.0.0] - 2026-05-08

### Stable Release

This release consolidates the 6.5-to-7.0 work into one public release.

- Added Team-session personal paint fallback: when a team car, suit, or helmet is missing, Nishizumi Paints can use the current in-car driver's matching personal item before random fallback.
- Added per-item Team fallback controls for car, suit, and helmet, plus preloading of Team drivers' personal paints so driver swaps can reuse cached files faster.
- Added confirmed Team driver-swap handling with post-swap refresh retries, stale-file cleanup, and clearer Team Event logs.
- Added richer Session diagnostics: compact non-Team layout, Team-only current-driver/swap/refresh columns, and per-item tooltips explaining Team paint, driver paint, random fallback, or iRacing default.
- Added Session actions for random fallback management: Favorite, Block, Restore previous, Forget, Open TP, and Force refresh current car/team.
- Added paint-history snapshots before overwrites and Restore previous for car, helmet, and suit.
- Added random-paint favorites and blocklist support for public showroom and Local RandomPool sources.
- Added auto repair for failed direct Trading Paints downloads: retry, partial-file cleanup, and one final online fallback pass before local fallback.
- Added multi-select in the Session driver table so compatible fixed-paint actions can be applied to all selected drivers.
- Added double-click camera switching from the Session table through the iRacing SDK camera broadcast.
- Tightened the Random tab layout by removing extra explanatory text under Step 2 and Step 3 and moving the showroom and local pool controls higher.
- Changed new or missing configs to protect the local user by default: random paints are not applied to the local user, and random paints in Team events remain disabled unless enabled.
- Removed the stale local AI roster prefill startup path while keeping AI random fallback and local AI roster live-update behavior.
- Fixed Restore previous after random fixed overrides so override memory is cleared, restored history paints return to normal Session status, and only affected cars receive texture reloads.
- Fixed Team driver-personal restores so they register as `driver_paint`, not `override`.
- Fixed Forget so Team targets without a real Team Trading Paints asset can restore the prior driver-personal paint from history.
- Fixed repeated Team-driver preload retries for unavailable personal assets with a short per-session cooldown.
- Prevented duplicate manual random and restore jobs from launching for the same selected driver item.

## [6.5] - 2026-04-29

### Stable Release

- First stable release since 6.0, collecting the showroom source, Team, Member ID, car dropdown, all-paints folder export, and 6.4.2 dropdown UX fixes.
- Confirmed **Recycle downloaded TP car paints into the local random pool** defaults to off for new or missing config values while preserving explicit user opt-ins.

## [6.4.2] - 2026-04-29

### Fixed

- Fixed Showroom car dropdowns so selecting a car closes the menu instead of reopening it.
- Fixed Showroom car dropdowns to show the full car list when browsing and only filter the list while typing.
- Reduced dropdown height and shortened inline suggestions so the Car, Member ID, and Teams car selectors stay readable.
- Moved Member ID and Teams all-paints downloads into a separate **Download everything** area so the one-click full download is clearer.

## [6.4.1] - 2026-04-29

### Changed

- Reworked the Showroom car download tab so users choose a Trading Paints car directly instead of typing a TP car ID or slug.
- Added the same click-to-open searchable car dropdown to Showroom car, Member ID, and Teams downloads.
- Reduced the car field width and added live suggestions below each car selector while typing.
- Manual random car downloads keep using the selected Showroom source pool and randomly fetch from any enabled source.

## [6.4] - 2026-04-29

### Added

- Added **Showroom > Member ID** for downloading a member's car, helmet, and suit paints by Member ID and selected car.
- Added one-click all-paints downloads for Member ID targets, saving all returned cars plus helmet and suit into an organized member folder.
- Added one-click all-paints downloads for Teams, scanning mapped Trading Paints cars in manifest batches and saving found cars plus helmet and suit into an organized team folder.
- Added editable car dropdowns for Member ID and Teams so users can pick a Trading Paints car from the bundled mapping instead of typing IDs or directories.

## [6.3.3] - 2026-04-29

### Changed

- New and migrated default showroom source settings now enable all four sources: **Trending**, **Newest**, **Most favorited**, and **Most raced (ever)**.
- Empty showroom source selections are normalized back to all four sources instead of only **Trending**.

## [6.3.2] - 2026-04-29

### Changed

- Reverted the 6.3.1 interactive **Showroom > Teams** redesign.
- Simplified **Showroom > Teams** so users only type the required Team ID and car value.
- Team downloads now keep the optional manifest context internal instead of showing member ID and car number fields in the Teams box.

## [6.3.0] - 2026-04-29

### Added

- Added Advanced mode controls for choosing which public Trading Paints showroom sources random fallback can use:
  - Trending
  - Newest
  - Most favorited
  - Most raced (ever)
- Multiple selected showroom sources are mixed randomly per fallback attempt.

### Changed

- Random showroom fallback still defaults to **Trending** for existing and new users.
- Public showroom logs now include the source used for each random fallback paint.

## [6.2.0] - 2026-04-25

### Added

- Added a **Teams** mode to the Showroom tab for manual Trading Paints team paint downloads by Team ID and car.
- Added a no-login team manifest fallback that tries session-aware Trading Paints payload variants and reports which route returned matching team assets.
- Team downloads can save directly to the iRacing paint folder or to a one-time custom folder.

### Changed

- Team paint imports now preserve the normal iRacing team filenames: `car_team_{team_id}.tga`, `helmet_team_{team_id}.tga`, and `suit_team_{team_id}.tga`.
- Updated the release metadata, installer reference, and Trading Paints notes for the 6.2.0 workflow.

### Privacy

- Documented that the manual team downloader sends only the entered Team ID and car directory plus minimal synthetic context to Trading Paints manifest endpoints.
- Confirmed the team flow does not require or store Trading Paints login cookies, passwords, or tokens.

## [6.0.0] - 2026-04-18

### Added

- Added a Windows installer with in-place upgrade support for existing installs.
- Added an **Easy mode** that keeps the interface focused on the essential monitoring and random fallback controls.
- Added an interface mode selector to Quick Start so users can choose between **Easy mode** and **Advanced mode** on first launch.
- Added the iRacing member ID prompt to Quick Start for AI workflows.
- Added tray icon behavior with:
  - right-click menu entries for **Open app** and **Exit**
  - double-click restore for the main window
- Added the **Keep running in background on close** control to Easy mode and linked it to the same underlying setting used by Advanced mode.
- Added a **Do not apply random paints to myself** option for Advanced mode.
- Added manual public showroom download tools for:
  - direct TP car ID downloads
  - direct showroom link downloads
  - whole collection downloads

### Changed

- Promoted the browserless/public-showroom architecture to the main 6.0.0 release path.
- Standard online fallback now uses direct public showroom downloads instead of depending on the embedded browser flow.
- **Session Total** no longer applies a hard cap. It now runs uncapped against the current session totals.
- The old protective Session Total cap behavior was moved into the new default **Safe** mode.
- Online fallback defaults were refreshed so cars, helmets, and suits are processed together by default.
- Legacy settings migration now enables the restored online-together fallback behavior automatically for older configs.
- **Random helmets** and **Random suits** default to enabled.
- **Recycle downloaded TP paints into the local random pool** now defaults to disabled.
- Advanced mode now labels autostart as **Start with Windows**.
- Public showroom copy and labels were simplified across the Random and Showroom flows.
- The local random pool panel was moved to the Random tab where it sits next to the public showroom tools.
- The app’s no-browser release script is now `Nishizumi_Paintsv6_nobrowser.py`.

### Fixed

- Fixed repeated startup delays between random online fallback downloads.
- Fixed random session actions so a newly selected random paint triggers an iRacing texture reload immediately.
- Fixed several cases where the Session tab could keep stale state across session changes.
- Fixed stale cleanup/log noise when a session briefly disappeared during transitions.
- Fixed fallback sourcing so public showroom helmets and suits are used properly online.
- Fixed public showroom fallback so spec maps are downloaded by default when available.
- Fixed **Open TP** links for fallback helmets and suits.
- Fixed **Forget** behavior:
  - when removing an override, the app can restore the driver’s original Trading Paints asset when one exists
  - when removing a remembered fallback, it simply stops persisting that choice for later
- Fixed the showroom mapping seed for **BMW M2 CSR**.
- Fixed the installer/app autostart interaction so installer defaults do not get silently re-enabled on first run.
- Fixed the embedded-browser UI regression that referenced `tk.Text` without the local tkinter alias.

### Performance

- Removed the artificial pacing between online fallback downloads.
- Restored the high-parallelism **Session Total** mode for users who want maximum throughput.
- Kept **Safe** as the default recommended mode for more controlled concurrency.

### UX

- Simplified the public showroom messaging in Random step 3.
- Reduced unnecessary spacing in the Random tab showroom area.
- Reduced the slug field width in the Showroom tools.
- Improved the showroom mapping review wording so the vehicle matching prompt is easier to understand.
- Delayed the review prompt for first-time users until after Quick Start completes.
- Surfaced the core random fallback controls in Easy mode so basic users can still configure real-driver and AI fallback behavior quickly.

### Packaging

- Updated the no-browser build and installer scripts to target the 6.0.0 script name.
- Refreshed the installer defaults so **Start Nishizumi Paints when I sign in** is checked by default.

### Documentation

- Reworked the repository for a release-first layout.
- Replaced the large all-in-one README with a shorter installation-focused landing page.
- Added a full wiki/manual structure in English for the app’s tabs, workflows, and maintenance.
- Added repository security and automation documentation files.

## [5.0.0] - 2026-04-14

### Added

- Added per-driver fixed paint controls in the **Session** tab for **Car**, **Helmet**, and **Suit**.
- Added **Open TP**, **Assign link...**, **Assign current**, **Random**, and **Forget** actions for the selected session driver.
- Added **Assign current** so a user can keep the paint already visible on a driver, including a random online fallback paint that turned out to be worth keeping.
- Added Trading Paints **collection pool** support in the Online section.
- Added collection ID/URL management with **Add**, **Remove selected**, **Clear list**, **Collections**, **Cache**, and **Clean cache...** actions.
- Added collection cache cleanup by collection ID/URL, with a guarded all-cache cleanup path when the prompt is left blank.
- Added full showroom URL tracking for openable fallback, collection, and override paints.
- Added on-the-fly Session tab action updates as each driver's car, helmet, or suit becomes available.
- Added showroom mapping tools in the **Logs** tab: scan, review pending cars, open editable JSON, reset user mapping, open mapping folder, and open bundled seed.
- Added automatic TP showroom mapping startup scans to detect missing, mapped, and unsupported car mappings.
- Added same-session roster refresh handling that fetches only newly joined targets instead of reprocessing the whole session.

### Changed

- Online fallback now uses the built-in protected fast path automatically.
- Older user-facing Trading Paints speed-mode choices were removed from the setup flow and cannot be re-enabled by stale config values.
- Showroom total-page detection is now always enabled for online fallback.
- Public showroom fallback now uses the real detected page count as its random-page universe.
- **Open TP** now opens full Trading Paints showroom URLs with slugs, avoiding short `/showroom/view/{id}` links that can 404.
- **Open TP** stays disabled for real downloaded paints that only have a driver/profile context instead of a useful showroom paint URL.
- Collection fallback now runs before the normal public showroom when collection IDs are configured.
- If configured collections cannot cover a target, the normal public showroom can cover it when the collection fallback checkbox is enabled.
- Collection sources are no longer reused in the same session once they have already been assigned.
- Collection source usage is remembered across same-session roster updates, preventing repeats when new drivers join later.
- Session rows keep separate status for car, suit, and helmet instead of hiding everything behind one broad state.
- Fixed driver paints now remain marked as **override** instead of being downgraded to **downloaded** after normal session downloads finish.

### Fixed

- Fixed fixed-paint assignments losing their override status after the session download/save pass completed.
- Fixed **Open TP** not being clickable for valid random, fallback, collection, or assigned paints.
- Fixed random/collection Trading Paints links opening in a form that could return 404.
- Fixed collection fallback repeating the same few compatible paints in one session.
- Fixed collection fallback repeating paints again after a same-session roster update.
- Fixed collection exhaustion behavior so the app can continue to normal online fallback instead of recycling already-used collection sources.
- Fixed stale collection cache entries remaining configured after collection IDs are removed.

