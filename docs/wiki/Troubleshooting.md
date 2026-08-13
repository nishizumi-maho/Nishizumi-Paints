# Troubleshooting

## Some options are cut off at the bottom of the window

They are not cut off anymore. Every tab scrolls when its content is taller than the window, so scroll the tab down with the scrollbar on its right side or with the mouse wheel.

If the wheel does not move the page, the pointer is over a list that scrolls on its own, such as the driver table, the activity log, or the collection list. Move the pointer over an empty part of the tab and the page scrolls again.

Making the window bigger, or maximizing it, removes the scrollbar as soon as everything fits.

## My paint does not show in the iRacing UI 3D car viewer

Open `General > iRacing UI car previews` and read the status line first. The most common causes are:

- the feature is turned off
- no iRacing customer ID is known yet, so nothing can be installed
- Trading Paints was unreachable on the last check
- the paint is not the active one in your Trading Paints `My Paints` section
- your paint is a Custom Number paint and `Hide car numbers` is off in `iRacing Settings > Graphics`

Press `Sync previews now` to force a fresh manifest read. The full behavior and a symptom table are on the [iRacing UI Car Previews](iRacing-UI-Car-Previews) page.

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

The no-browser work specifically tightened this path, so if it still fails, the logs around the manual random request are the key evidence.

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
