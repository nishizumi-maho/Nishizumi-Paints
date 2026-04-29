# Trading Paints Unofficial API / SDK Notes

> Unofficial notes reconstructed from the current `Nishizumi_Paintsv6_nobrowser.py` client behavior.
> This is not Trading Paints documentation, it may be incomplete, and it may break if Trading Paints changes its server behavior.

## 1. Scope

The current Nishizumi Paints 6.4 codebase talks to Trading Paints in six practical ways:

1. session-aware manifest lookups for real live-session paints
2. single-user manifest fallback lookups
3. public showroom JSON and direct asset downloads for cars, helmets, and suits
4. collection and AI-roster metadata lookups
5. manual team paint manifest lookups by Team ID and car directory
6. manual member paint manifest lookups by Member ID, including all-paints folder exports

The public showroom path is now the main no-browser fallback flow. Legacy authenticated showroom endpoints still exist in the script for compatibility and historical logic, but they are no longer the primary 6.4 path.

## 2. Endpoint catalog

### 2.1 Session-aware manifest lookup

- `https://dl.tradingpaints.com/fetch.php`
- `https://fetch.tradingpaints.gg/fetch.php`

Method:

- `POST`

Purpose:

- resolve Trading Paints assets for a specific iRacing session entry using the local member, session context, and target driver/team details

### 2.1.1 Manual team paint manifest lookup

- `https://dl.tradingpaints.com/fetch.php`
- `https://fetch.tradingpaints.gg/fetch.php`

Method:

- `POST`

Purpose:

- resolve team-owned car, helmet, and suit assets for a known Team ID and car directory without using a browser login
- filter the XML response to `<teamid>{team_id}</teamid>` before accepting files
- batch all-team exports by sending comma-separated `list` entries, then filtering the returned XML per mapped car directory

### 2.2 Single-user manifest fallback

- `https://fetch.tradingpaints.gg/fetch_user.php?user={user_id}`
- `https://fetch.tradingpaints.gg/fetch_user.php?user={user_id}&ts={epoch_ms}`

Method:

- `GET`

Purpose:

- resolve paint files for one member without full session context
- the `ts` variant is used as an uncached poll when the app needs to observe a fresh manifest
- power manual **Showroom > Member ID** downloads for one selected car or every returned car, helmet, and suit for that member

### 2.3 Public showroom JSON

- `https://www.tradingpaints.com/js/showroom.php?mid={mid}&sort=popular&ad=DESC&search=&reuse=1&family=1&hasnumber=1&from=everyone&stampednums=1&official_only=0&pos={offset}&ts={epoch_ms}`

Method:

- `GET`

Purpose:

- return paged showroom data for a car or driver accessory category

### 2.4 Public showroom assets

- `https://showroom-assets.tradingpaints.gg/compressed/{asset_id}.tga.bz2`
- `https://showroom-assets.tradingpaints.gg/mips/{asset_id}.mip`

Method:

- `GET`

Purpose:

- download the actual public showroom asset files directly, without using the authenticated scheme-switching flow

### 2.5 Collection pool JSON

- `https://www.tradingpaints.com/js/myCollections.php?id={collection_id}`

Method:

- `GET`

Purpose:

- return the paints inside a Trading Paints collection so the app can seed the local RandomPool or collection cache

### 2.6 Showroom HTML pages

- `https://www.tradingpaints.com/showroom/{category}/{mid}/{slug}`
- `https://www.tradingpaints.com/showroom/view/{scheme_id}/{slug?}`

Method:

- `GET`

Purpose:

- load showroom pages
- scrape vehicle or accessory metadata for direct-link imports
- provide the human-facing page the app can open from the UI

### 2.7 AI collections and roster files

- `https://fetch.tradingpaints.gg/collections.php?user={member_id}`
- `{RosterFile}` returned by the collections response

Methods:

- `GET`

Purpose:

- list the AI collections linked to a member
- download roster JSON payloads for AI sync

### 2.8 Legacy authenticated showroom endpoints still present in the code

- `https://www.tradingpaints.com/js/setScheme.php?id={scheme_id}&sub_make=0`
- `https://www.tradingpaints.com/js/dashboard.php?cmd=loadmake&id={mid}&number=0`
- `https://www.tradingpaints.com/js/dashboard.php?cmd=delete&id=active&make={mid}&series=0&cid=0&number=0`
- `https://www.tradingpaints.com/auth`

These belong to the older authenticated showroom-switching path. They are still described here because the script retains compatibility logic, but they are not required for the main public fallback flow in 6.2.0.

## 3. Session-aware manifest payload

The app builds a form-encoded payload like this:

- `team`
  `1` for team events, otherwise `0`
- `user`
  the local member used as the requesting Trading Paints identity
- `night`
  event time string from the session
- `series`
  iRacing series ID
- `league`
  iRacing league ID
- `numbers`
  `True` or `False`
- `list`
  `{user_id}={directory}={team_id_or_0}={car_number}={paint_ext}`

Example:

```text
team=0
user=123456
night=10:00 am
series=471
league=0
numbers=False
list=987654=dallarap217=0=12=
```

### 3.1 Manual team paint payload

For manual team paint lookup, the app sends `team=1` and uses the Team ID in the `list` field:

```text
team=1
user=0
night=10:00 am
series=0
league=0
numbers=False
list=0=amvantageevogt3=404314=0=
```

The app also tries conservative variants that include an optional requesting member ID, optional driver member ID, and the resolved Trading Paints car ID when known. A response is accepted only when the XML node has the requested `teamid`. For car, decal, number, and spec files, the XML `directory` must also match the resolved iRacing car directory. Helmet and suit nodes are allowed through by Team ID because their directories are `helmets` and `suits`.

For all-team exports, multiple car requests are sent in one payload by comma-separating the `list` entries:

```text
list=404314=acuraarx06gtp=404314=0=,404314=amvantageevogt3=404314=0=
```

The app still filters every returned XML node by Team ID and by mapped car directory before saving files.

## 4. Manifest XML shape

The app parses manifests as XML and looks for repeated `.//Car` nodes.

Fields used:

- `file`
- `directory`
- `type`
- `teamid`
- `userid`
- `carid`

Recognized `type` values:

- `car`
- `car_decal`
- `car_num`
- `car_spec`
- `helmet`
- `suit`

Unknown types are ignored.

For session-aware manifest responses, the app also filters nodes to the exact live-session target, rather than blindly accepting every `<Car>` node in the payload.

## 5. Public showroom JSON behavior

### 5.1 Common parameter set

The app uses this default parameter bundle:

```text
sort=popular
ad=DESC
search=
reuse=1
family=1
hasnumber=1
from=everyone
stampednums=1
official_only=0
```

### 5.2 Pagination

- page size is treated as `24`
- `pos = page_index * 24`
- page detection can probe up to `50` pages when explicit total-page detection is enabled

### 5.3 Response shape used by the app

The client expects:

```json
{
  "output": {
    "cars": [
      { "id": "123", "title": "Example Paint" }
    ]
  }
}
```

Only `dict` items inside `output.cars` are kept.

### 5.4 Fields observed in showroom items

The app uses or inspects:

- `id`
- `title`
- `type`
- `official`
- `users`
- `bookmarks`
- `hasnumber`
- `pro_user`
- `slink`
- `showroom_link`
- `link`
- `url`

The app also attaches its own temporary metadata while building a pool:

- `_nishizumi_page_index`
- `_nishizumi_page_number`
- `_nishizumi_collection_id` for collection-derived items

## 6. Public direct download rules

### 6.1 Cars

For a public showroom car scheme, Nishizumi Paints builds two direct download candidates by default:

- `car` -> `https://showroom-assets.tradingpaints.gg/compressed/{scheme_id}.tga.bz2`
- `car_spec` -> `https://showroom-assets.tradingpaints.gg/mips/{scheme_id}.mip`

In other words, the app now attempts the spec map by default when it uses the public showroom path.

### 6.2 Helmets and suits

For accessories, the app downloads the compressed TGA directly:

- `helmet` -> `https://showroom-assets.tradingpaints.gg/compressed/{scheme_id}.tga.bz2`
- `suit` -> `https://showroom-assets.tradingpaints.gg/compressed/{scheme_id}.tga.bz2`

The public showroom accessory categories are treated as:

- `Driver / 118 / Helmets`
- `Driver / 119 / Suits`

### 6.3 Public-eligibility filters

Before using a showroom item, the app rejects candidates that look unusable for the public fallback path:

- numbered paints
- PRO paints
- non-`paint` item types
- items with no usable scheme ID

This is why the app logs “public non-PRO” behavior and may skip candidates before download.

## 7. Public random fallback behavior

The public fallback system no longer depends on an embedded browser for the standard random path.

High-level flow:

1. use the local TP showroom mapping to convert an iRacing car directory into a Trading Paints `mid/category/slug`
2. fetch one or more showroom JSON pages directly
3. filter to public usable candidates
4. avoid already-used or recently-used scheme IDs when possible
5. choose a paint according to the configured mode
6. download direct asset URLs from `showroom-assets.tradingpaints.gg`
7. save them into the normal iRacing paint layout
8. trigger texture reload through the iRacing SDK

The same pattern is used for helmets and suits, except the accessory categories use the fixed `Driver/118/Helmets` and `Driver/119/Suits` lanes.

## 8. Total-page detection

When total-page detection is enabled, the app estimates the true showroom page count with a practical probe algorithm:

1. confirm page `0`
2. probe exponentially: `1, 2, 4, 8, ...`
3. binary-search between the last good page and the first empty page
4. return `last_good + 1`

If the probe times out, the app falls back to the pages already confirmed.

## 9. Showroom mapping

The app ships with a bundled seed file and also supports a user override mapping file.

Bundled resource:

- `data/tp_showroom_mapping.seed.json`

User override file:

- `%APPDATA%\\NishizumiPaints\\tp_showroom_mapping.seed.json`

At runtime the app merges:

1. bundled seed
2. user override

The mapping review tools can also:

- scan the iRacing active-car list
- scan Trading Paints showroom pages
- score likely matches
- write pending-review reports

## 10. Collection pool behavior

Collections are now handled directly through JSON, without browser automation.

### 10.1 Collection request

The app requests:

```text
GET https://www.tradingpaints.com/js/myCollections.php?id={collection_id}&ts={epoch_ms}
```

Headers used:

- `Accept: application/json,text/javascript,*/*;q=0.8`
- `X-Requested-With: XMLHttpRequest`
- `Referer: https://www.tradingpaints.com/collections/view/{collection_id}`

### 10.2 Collection response model used by the app

The client accepts either:

- `payload.output.cars`
- or a top-level list-like payload that behaves the same way after normalization

Each usable item is expected to expose enough information for the client to derive:

- scheme ID
- vehicle or accessory identity
- title
- showroom link

### 10.3 Kind inference

Collection items are classified like this:

- `mid == 118` -> helmet
- `mid == 119` -> suit
- otherwise -> car

### 10.4 Car matching

For cars, the app prefers to map collection items back to an iRacing directory using:

1. the mapped Trading Paints MID
2. a vehicle-name fallback match

If the MID is unknown locally, the importer can still use a synthetic bucket name such as `tp_car_{mid}`.

## 11. Direct showroom links

Manual showroom-link import works by parsing:

- `https://www.tradingpaints.com/showroom/view/{scheme_id}/...`
- bare scheme IDs
- mixed text that contains either of those

The app then loads the showroom view page and scrapes:

- title
- vehicle name
- whether it is a car, helmet, or suit

That metadata is used to route the downloaded asset to the correct local destination or RandomPool bucket.

## 12. AI roster sync

### 12.1 Collections XML

The AI collections endpoint is parsed as XML and the client reads:

- `ID`
- `Name`
- `RosterFile`

### 12.2 Roster JSON

The roster file is expected to contain:

```json
{
  "drivers": [
    {
      "driverName": "Example Driver",
      "carPath": "some\\car",
      "carTgaName": "car_123.tga",
      "helmetTgaName": "helmet_123.tga",
      "suitTgaName": "suit_123.tga"
    }
  ]
}
```

The app normalizes the drivers list and writes local metadata files for the synced roster directory.

### 12.3 AI asset URL derivation

For synced AI rosters, the app derives direct download URLs from the asset ID embedded in the filenames:

- `car_123.tga` -> compressed showroom asset `123`
- `car_123_spec.mip` -> showroom MIP asset `123`
- accessory filenames follow the same `compressed/{asset_id}.tga.bz2` path

Optional AI assets can be marked unavailable when the CDN returns `401`, `403`, or `404`.

## 13. Local save conventions

For normal user targets, the current app writes:

- `paint/{directory}/car_{user_id}.tga`
- `paint/{directory}/car_spec_{user_id}.mip`
- `paint/{directory}/decal_{user_id}.tga`
- `paint/helmet_{user_id}.tga`
- `paint/suit_{user_id}.tga`

Team targets replace the user portion with `team_{team_id}`.

Manual team downloads use the same convention, for example:

- `paint/{directory}/car_team_404314.tga`
- `paint/helmet_team_404314.tga`
- `paint/suit_team_404314.tga`

Superspeedway sessions can also create `_ss` variants for car-related paint types.

## 14. Download, retry, and failure handling

Observed client behavior:

- shared `requests.Session` objects with connection pooling
- app-managed retry loops instead of relying on `requests` retry middleware
- direct download timeout windows around `(10, 90)`
- bz2 extraction after download when the URL ends in `.bz2`
- explicit handling of `401`, `403`, and `404` as unavailable asset cases

The public fallback path also tracks recent schemes and used source IDs to reduce accidental repetition within the same pass.

## 15. Legacy authenticated showroom path

The script still contains the older authenticated workflow, including:

- login-state heuristics
- persistent profile handling
- `setScheme.php`
- dashboard reload and delete calls
- manifest polling after scheme switches
- original-paint backup and restore helpers

That logic remains valuable for historical understanding and fallback compatibility, but it is no longer the main 6.2.0 architecture.

## 16. Practical guidance

If you are building against these observed behaviors:

1. treat all of this as unstable and unofficial
2. prefer the public JSON and direct-CDN path when you only need public showroom assets
3. keep a manifest fallback for normal Trading Paints session paints
4. expect `403` on unavailable public assets and handle it cleanly
5. parse manifests as XML and showroom/collection responses as JSON
6. avoid aggressive polling or scraping

## 17. What remains unknown

This client does not fully document:

- server-side rate limits
- every possible showroom JSON field
- whether the public JSON endpoints are intended for third-party tooling
- long-term stability guarantees for the asset CDN paths
- all authenticated dashboard behaviors outside the flows already used by the app
