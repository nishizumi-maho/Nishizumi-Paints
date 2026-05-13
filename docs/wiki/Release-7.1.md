# Release 7.1 Experimental

Version 7.1 experimental is a targeted follow-up to 7.0 for RandomPool and Session table fixes.

## Changes

- Showroom collection imports now keep downloadable public collection paints that were previously skipped by the online-fallback-only filter.
- The Session table `Random` button follows the Random tab source mode: Local mode uses the Local RandomPool, while Online mode continues to use public showroom randomization for car paints.
- Quick Start only asks for the iRacing Documents folder when automatic detection fails; General shows manual folder controls only after `Customize iRacing Documents folder` is enabled.
- Camera switching from the Session table now targets the selected driver with the Chase camera, avoiding the Scenic camera fallback.

## Notes

Collection imports still require public asset URLs to be available from Trading Paints. Private or unavailable assets are skipped during download.

The Local RandomPool must contain compatible files for Local random overrides. If no compatible local source exists for the selected driver, the action logs the miss and leaves the current paint unchanged.
