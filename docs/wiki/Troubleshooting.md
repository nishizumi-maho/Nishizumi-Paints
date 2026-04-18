# Troubleshooting

## A driver still has no paint

Check:

- whether normal Trading Paints download succeeded
- whether the vehicle has a valid showroom mapping
- whether random fallback is enabled for that target type
- whether the asset was unavailable publicly

## The window disappeared after close

If **Keep running in background on close** is enabled, the app will stay alive in the tray instead of exiting.

Use the tray icon:

- double-click to restore
- right-click and choose **Open app**

## The app starts with Windows unexpectedly

Check both:

- the installer startup option
- the in-app **Start with Windows** setting

The app and installer now share the same Windows startup entry, so the setting should stay consistent.

## Online fallback feels slow

Review the worker mode:

- **Safe** for recommended default behavior
- **Session Total** for maximum uncapped concurrency
- **Manual** for fixed counts

## A car mapping prompt appears

That means the app found an iRacing vehicle that still needs a Trading Paints showroom match.

Use the review prompt to:

- verify the suggested vehicle
- open the TP page if needed
- accept the match
- mark it as unsupported if necessary

## A random paint was remembered and should be cleared

Use **Forget** from the Session tab for that driver and asset type.
