# Background and Headless Modes

Nishizumi Paints is designed to keep monitoring without forcing the user to keep a large window open the whole time.

## Tray behavior

When the app is running in the tray:

- right-click opens a menu with `Open app` and `Exit`
- double-click with the left mouse button restores the main window

This makes background use practical for users who want the app always available but mostly out of sight.

## Keep running in background on close

This setting changes what happens when the user closes the main window:

- enabled: close hides to the tray and the monitor keeps running
- disabled: close actually shuts the app down

This option is exposed both in Advanced mode and in the Easy mode General box so users do not need to switch modes just to control it.

## Start with Windows

The app can register itself in the per-user Windows startup entry. The installer can set the initial value, and the app can later update the same registry entry.

## Start minimized

This is useful for users who want the app to launch on sign-in and immediately stay out of the way.

## Single-instance behavior

The script includes a single-instance lock and a signal server so a second launch does not create a separate competing monitor process.

## Headless mode

The code also contains a headless control server and launch-mode handling. Headless mode is intended for users who want monitoring behavior without the full interactive window.

That matters for:

- autostart scenarios
- service-like usage
- keeping the app available while relying mostly on logs and tray controls

## Interaction with Easy and Advanced mode

UI mode does not disable background or headless behavior. Easy mode only reduces visible complexity. The background monitor and tray logic still run the same core service underneath.
