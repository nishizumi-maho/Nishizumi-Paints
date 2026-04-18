# Trading Paints Seed Review Tool Guide

This folder contains the assets used to maintain the **Trading Paints showroom mapping seed** for Nishizumi Paints.

## What this tool is for

`tp_Seed_review_cly.py` is an interactive CLI utility that helps you keep `tp_showroom_mapping.seed.json` up to date.

It does the following:

- Loads the current `tp_showroom_mapping.seed.json` seed.
- Scans Trading Paints showroom pages (Road and Oval) for available car entries.
- Scans active iRacing car filepaths from the official iRacing source.
- Shows only cars that are not already mapped and not already marked unsupported.
- Lets you review candidate mappings and choose what to do.

## Why it must be updated every season

Every iRacing season can introduce:

- New cars,
- Car renames or legacy variants,
- Changes in Trading Paints showroom entries.

Because of that, you should run this review flow every season to refresh `tp_showroom_mapping.seed.json` and avoid missing new supported cars.

## How to run

From the repository root:

```bash
python SEED/tp_Seed_review_cly.py --seed SEED/tp_showroom_mapping.seed.json
```

## Interactive options during review

When the tool presents candidates, you can use:

- `1` → mark as unsupported in Trading Paints
- `2` → accept best match
- `3..N` → accept another shown candidate
- `s` → skip for now
- `q` → save and quit

## Output behavior

- The seed file is updated in place.
- A `.bak` backup is created automatically (once) before writing.

## Recommended seasonal workflow

1. Pull latest repository changes.
2. Run the tool against `SEED/tp_showroom_mapping.seed.json`.
3. Review and confirm new mappings.
4. Validate the updated seed with your normal project checks.
5. Commit the updated seed.
