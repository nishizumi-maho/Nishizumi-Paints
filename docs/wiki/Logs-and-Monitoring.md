# Logs and Monitoring

The Logs tab is the runtime explanation panel. If the Session tab tells you what happened to a driver, the Logs tab tells you why.

## What it shows

- the rolling activity log
- session start and session end summaries
- manifest, download, and save progress
- online fallback lane behavior
- public showroom fetch details
- RandomPool archival decisions
- AI roster sync results
- update-check results

## Why the log matters

The app has several stages that can all succeed or fail for different reasons:

- manifest resolution
- direct downloads
- save and extraction
- texture reload
- public fallback
- local fallback
- cleanup and recycling

The log is the fastest place to see which stage actually failed.

## Throughput monitoring

The app also keeps transfer statistics such as:

- requested workers
- peak active workers
- stage duration
- average file time
- throughput
- effective parallelism

These numbers are useful when tuning worker mode or checking whether `Session Total` is actually helping.

## Typical log patterns

Examples of useful patterns:

- `Processing session ...`
- `Manifest progress ...`
- `Download progress ...`
- `Save progress ...`
- `Triggered iRacing texture reload ...`
- `Trading Paints public showroom pool fetched ...`
- `Session summary ...`

When investigating a problem, match the row in the Session tab with the corresponding log lines here.
