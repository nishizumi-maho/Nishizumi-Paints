# Troubleshooting

## The Session tab looks stale after a session change

Check the Logs tab for:

- `No active valid session detected`
- `Processing session ...`
- repeated reconnect or clear cycles

If the app is connected to the iRacing SDK and still does not rebuild the Session tab, capture the corresponding log window and report the exact sequence.

## A driver got fallback even though they should have a normal Trading Paints paint

Check whether:

- the manifest stage found matching files
- the user was filtered out by directory or team rules
- the normal asset was unavailable
- the row had a remembered override or fallback memory

The Session tab row and the Logs tab together usually explain this.

## A public showroom fallback was skipped

Common reasons:

- the mapping is missing for that car
- the candidate was numbered
- the candidate was marked PRO
- the direct asset URL returned `401`, `403`, or `404`
- the session was cancelled before the lane finished

## The app did not reuse the pool content I expected

Check:

- whether the RandomPool actually contains compatible files for that car or accessory
- whether recycling of live session paints is enabled
- whether the content only exists in the collection pool instead of the RandomPool
- whether a more preferred online path succeeded first

## A manual Random action did not visibly apply

Check for:

- a successful download
- a successful save
- a triggered texture reload
- stale row metadata pointing at the old source

The 6.1.0 work specifically tightened this path, so if it still fails, the logs around the manual random request are the key evidence.

## Helmets or suits are not getting online fallback

Verify:

- random helmets or random suits are enabled for the correct target scope
- online fallback is enabled
- the accessory stages were actually queued in the logs
- the `process all together` setting did not hide the accessory stage timing in a way you misread

## AI roster sync does not produce usable content

Check:

- the AI member ID
- whether the collection list loaded
- whether the roster JSON had a valid `drivers` list
- whether the resulting roster was written to the iRacing `airosters` folder

## The tray icon does not behave as expected

Check the General settings for:

- Start with Windows
- Start minimized
- Keep running in background on close

If background-on-close is disabled, closing the main window will terminate the app instead of hiding it to the tray.
