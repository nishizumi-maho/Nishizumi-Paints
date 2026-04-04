# Trading Paints Unofficial API / SDK Notes

> **Unofficial documentation** based on observed client behavior in the `Nishizumi Paints` codebase.
> This is **not** official Trading Paints documentation, may be incomplete, and may break if Trading Paints changes server behavior.
>
> Scope: this document only covers what was actually used or inferred from the app's implementation.

## 1. What this documents

From the client implementation, Trading Paints is used in **five** main ways:

1. **User paint manifest lookup** via a user-specific endpoint.
2. **Session-context paint manifest lookup** via a context-aware endpoint.
3. **Authenticated showroom discovery** via a JSON showroom endpoint.
4. **Authenticated showroom scheme switching / restore** via dashboard-side AJAX endpoints.
5. **AI roster discovery and download** via a collections endpoint and roster JSON files.

The app then downloads the returned paint asset URLs, stores them temporarily, and installs them into the standard iRacing paint layout.

---

## 2. Observed endpoints

### 2.1 Context manifest endpoints

The app tries these endpoints, in order:

- `https://dl.tradingpaints.com/fetch.php`
- `https://fetch.tradingpaints.gg/fetch.php`

**Method**

- `POST`

**Purpose**

- Return paint assets for a **specific iRacing session context**.
- Allows the client to tell Trading Paints which local member is requesting, whether the session is team-based, the event time, series, league, number-texture preference, and the target car/driver entry it wants to resolve.

### 2.2 Fallback user manifest endpoint

Observed endpoint:

- `https://fetch.tradingpaints.gg/fetch_user.php?user={user_id}`

**Method**

- `GET`

**Purpose**

- Return paint assets for a **single Trading Paints / iRacing user** without full session context.
- Used as a fallback if contextual lookup is unavailable or fails.

### 2.3 Fast uncached user manifest endpoint variant

Observed endpoint shape:

- `https://fetch.tradingpaints.gg/fetch_user.php?user={user_id}&ts={epoch_ms}`

**Method**

- `GET`

**Purpose**

- Force a fresh manifest poll after a showroom `setScheme` change.
- Used by the online showroom fallback to detect when the connected account's manifest has started exposing updated car asset URLs.

**Observed request headers**

- `Cache-Control: no-cache, no-store, max-age=0`
- `Pragma: no-cache`
- `Accept: application/xml,text/xml;q=0.9,*/*;q=0.8`

### 2.4 Authenticated showroom page

Observed page shapes:

- `https://www.tradingpaints.com/showroom/{category}/{mid}/{slug}`
- `https://www.tradingpaints.com/showroom/filter/from=everyone,sort=popular,ad=DESC,pos=0`

**Method**

- `GET`

**Purpose**

- Used as the authenticated browser entrypoint for the online showroom workflow.
- Also used by the client to sanity-check whether the saved browser profile still looks logged in.

### 2.5 Showroom JSON page endpoint

Observed endpoint shape:

- `https://www.tradingpaints.com/js/showroom.php?mid={mid}&sort=popular&ad=DESC&search=&reuse=1&family=1&hasnumber=1&from=everyone&stampednums=1&official_only=0&pos={offset}&ts={epoch_ms}`

**Method**

- `GET`

**Purpose**

- Return a **JSON page of showroom schemes** for a specific car.
- Used to build the online random pool of candidate schemes.

### 2.6 Set active showroom scheme endpoint

Observed endpoint:

- `https://www.tradingpaints.com/js/setScheme.php?id={scheme_id}&sub_make=0`

**Method**

- `GET`

**Purpose**

- Switch the **currently connected Trading Paints account** to the chosen showroom paint.
- Used both for online fallback selection and for restore-to-original when restore is enabled.

### 2.7 Delete active custom paint endpoint

Observed endpoint:

- `https://www.tradingpaints.com/js/dashboard.php?cmd=delete&id=active&make={mid}&series=0&cid=0&number=0`

**Method**

- `GET`

**Purpose**

- Remove the currently active custom paint for that car from the connected Trading Paints account.
- Used to restore the special **no custom paint** state.

### 2.8 Dashboard reload / state refresh endpoint

Observed endpoint:

- `https://www.tradingpaints.com/js/dashboard.php?cmd=loadmake&id={mid}&number=0`

**Method**

- `GET`

**Purpose**

- Refresh / reload dashboard car state after a change such as delete or upload.
- Used as part of no-paint restore verification.

### 2.9 AI collections endpoint

Observed endpoint:

- `https://fetch.tradingpaints.gg/collections.php?user={member_id}`

**Method**

- `GET`

**Purpose**

- Return a list of AI collections / carsets associated with a member.

### 2.10 AI roster JSON

The collections response includes a `RosterFile` URL.
The client performs:

- `GET {RosterFile}`

**Purpose**

- Download the roster JSON payload for an AI roster.

---

## 3. Session-context request format (`fetch.php`)

### 3.1 POST fields observed

The client builds a form-encoded payload with these fields:

- `team`
  - `"1"` if the session is team racing, otherwise `"0"`
- `user`
  - the local iRacing / Trading Paints member ID requesting the context lookup
- `night`
  - raw event time string from the session, e.g. `"10:00 am"`
- `series`
  - iRacing series ID as a string
- `league`
  - iRacing league ID as a string
- `numbers`
  - `"True"` or `"False"`, depending on whether number textures are enabled
- `list`
  - a compact descriptor of the target entry in the form:
    - `{user_id}={directory}={team_id_or_0}={car_number}={paint_ext}`

### 3.2 Example request body

```text
team=0
user=123456
night=10:00 am
series=471
league=0
numbers=True
list=987654=dallaradw12=0=12=
```

### 3.3 Notes on `list`

Observed construction:

```text
{user_id}={directory}={team_id or 0}={number or '0'}={paint_ext or ''}
```

Likely meaning:

- `user_id`: target remote user being resolved
- `directory`: iRacing car directory / paint folder key
- `team_id`: nonzero when the entry belongs to a team target
- `number`: car number text
- `paint_ext`: observed as custom paint extension text when available

---

## 4. Manifest XML shape

Both manifest flows (`fetch.php` and `fetch_user.php`) are parsed as XML.
The client looks for repeated `.//Car` nodes.

### 4.1 Fields observed inside each `<Car>` node

- `file`
  - downloadable asset URL
- `directory`
  - iRacing paint folder name / car path key
- `type`
  - paint type string, lowercased by the client
- `teamid`
  - team target ID when relevant
- `userid`
  - user target ID when relevant
- `carid`
  - used by the contextual manifest filter

### 4.2 Paint types currently recognized by the client

The client recognizes exactly these `type` values:

- `car`
- `car_decal`
- `car_num`
- `car_spec`
- `helmet`
- `suit`

Unknown `type` values are skipped.

### 4.3 Contextual filtering rules

For `fetch.php`, the client does **not** trust every `<Car>` node blindly.
It filters the XML like this:

- `carid` must exist and must not be `0`
- if the session entry has a team ID:
  - accept entries where either:
    - `userid == expected_user_id`, or
    - `teamid == expected_team_id`
- otherwise:
  - require both:
    - `userid == expected_user_id`
    - `teamid == 0`

This means the context endpoint is treated as a session-aware manifest that may contain more than one candidate node, and the client narrows it to the requested target.

---

## 5. Authenticated showroom JSON behavior

### 5.1 Default showroom query parameters observed

The app currently uses this default parameter set when talking to the showroom JSON API:

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

### 5.2 Pagination model observed

Observed behavior:

- showroom page size is treated as **24 schemes per page**
- `page_index` is zero-based in the client
- `pos = page_index * 24`

So, for example:

- page 0 -> `pos=0`
- page 1 -> `pos=24`
- page 2 -> `pos=48`

### 5.3 Response shape used by the client

The endpoint is parsed as JSON.
The client expects:

- top-level object
- `output`
- `output.cars`
- `cars` must be a list of scheme objects

If `output.cars` is missing or not a list, the page is treated as empty.

### 5.4 Scheme fields observed / used

The client currently uses or inspects fields such as:

- `id`
  - scheme ID used with `setScheme.php`
- `title`
  - title shown in logs
- `official`
  - treated as `"1"` when the app is filtering for official schemes
- `users`
  - used by the `popular` choice mode
- `bookmarks`
  - secondary popularity signal in the `popular` choice mode

The client also attaches its own internal metadata when building the pool:

- `_nishizumi_page_index`
- `_nishizumi_page_number`

### 5.5 Random page selection behavior observed

Observed behavior in the current client:

- by default, the showroom randomizer samples from a fixed ceiling of **20 pages**
- pages are chosen randomly without repeating already-used pages in the same session/car workflow
- when optional total-page detection is enabled, the client can probe the showroom to detect the **real total number of pages** for that car first
- after detection, the client can use the detected total as the random-page universe instead of the fixed ceiling

### 5.6 Detected total pages algorithm

Observed behavior:

- starts at page 0
- probes exponentially upward (1, 2, 4, 8, ...)
- then binary-searches the last existing page
- returns `last_good + 1` as the total page count

This is a practical page-count estimation algorithm, not an official page-count endpoint.

---

## 6. Authenticated browser profile and login behavior

### 6.1 Persistent browser profile

The client uses a **persistent Chromium / Chrome profile** for authenticated Trading Paints showroom flows.

Observed purpose:

- keep Trading Paints login cookies across runs
- allow the user to log in once, then reuse the saved profile for later showroom fallback operations

### 6.2 Login confirmation model

Observed behavior:

- login starts from `https://www.tradingpaints.com/auth`
- the browser profile is launched in non-headless mode for login
- the app can require a manual **"I logged in"** confirmation before it checks the current browser state

### 6.3 Login-state heuristics observed

The app treats Trading Paints as authenticated when one or more of these conditions are found:

- a dashboard URL is open
- a showroom URL is open and does not look like a login page
- page or response text contains markers such as:
  - `event-logged-in=true`
  - `logout`
  - `sign out`
  - `my schemes`
  - `my profile`
  - `account settings`
  - `dashboard`

The app rejects authentication if the page still looks like Steam / OAuth sign-in flow, including markers such as:

- `sign in with steam`
- `login with steam`
- `log in with steam`
- `connect through steam`
- `steamcommunity.com/openid`
- `oauth`

### 6.4 Profile status persisted by the client

The app also stores a small local login-status file for the saved profile.
Observed fields:

- `ok`
- `message`
- `updated_at`

This is app-side state, not a Trading Paints server response.

---

## 7. Showroom scheme capture and restore behavior

### 7.1 Current active scheme capture

The client tries to determine the currently active showroom paint from dashboard HTML, especially from dashboard pages such as:

- `https://www.tradingpaints.com/dashboard/{mid}/{slug}/simstamped`
- `https://www.tradingpaints.com/dashboard/{mid}/{slug}`

It looks for a block such as:

- `#active_scheme_showroom`

and then extracts a showroom link like:

- `/showroom/view/{scheme_id}/...`

### 7.2 Scheme ID extraction patterns observed

The client currently recognizes scheme IDs from text patterns such as:

- `/showroom/view/{id}`
- `setScheme.php?id={id}`
- `data-scheme-id="{id}"`
- JSON-like keys such as `scheme_id`, `schemeId`, `selectedScheme`

### 7.3 Set active scheme behavior

After choosing a showroom scheme, the client sends:

- `GET /js/setScheme.php?id={scheme_id}&sub_make=0`

with request headers such as:

- `X-Requested-With: XMLHttpRequest`
- `Accept: application/json, text/javascript, */*; q=0.01`
- `Referer: showroom or dashboard page`

### 7.4 Restore-to-original behavior

When restore is enabled, the client can:

1. remember the original showroom scheme ID and showroom link
2. later call `setScheme.php` again for that original scheme ID
3. verify restore either by:
   - dashboard/showroom state, or
   - manifest matching against baseline asset URLs

### 7.5 Restore-to-no-paint behavior

A distinct **no custom paint** state was also observed.
The client can restore that state by using:

- `GET /js/dashboard.php?cmd=delete&id=active&make={mid}&series=0&cid=0&number=0`
- optionally followed by
- `GET /js/dashboard.php?cmd=loadmake&id={mid}&number=0`

This implies Trading Paints distinguishes between:

- a specific active showroom/custom scheme, and
- no active custom paint at all

---

## 8. Direct manifest polling after `setScheme`

### 8.1 High-level behavior

The online showroom fallback does **not** passively sniff downloads.
Instead, it:

1. chooses a showroom scheme
2. calls `setScheme.php`
3. polls the connected account's `fetch_user.php` manifest
4. waits for the manifest to expose updated car-related asset URLs
5. downloads those asset URLs explicitly

### 8.2 Baseline comparison model

The client snapshots a **baseline URL map** before changing the connected account's paint.
It then polls until one of these happens:

- the manifest exposes a different URL map than baseline
- timeout expires

Observed car-related baseline keys include:

- `car`
- `car_spec`
- `car_decal`

### 8.3 Important integration nuance: member ID vs local session user

The manifest polling member is **not always** the same as the iRacing local user in the current session.

Observed behavior in the current app:

- if a `manifest_member_id` override is configured, it is used
- otherwise the local iRacing user ID is used

This matters for secondary / mule workflows:

- the app may race on one local iRacing account
- but use a different Trading Paints account's manifest for showroom switching and capture

If the wrong member ID is polled, `setScheme` can succeed while the app still fails to capture fresh files.

### 8.4 Timeouts observed

Observed current behavior:

- normal showroom direct-manifest polling uses a larger timeout window (for example around 35 seconds in the current app branch)
- `mule fast mode` shortens the process by skipping slow dashboard-confirmation loops and going directly to manifest polling, often with a shorter manifest wait budget

---

## 9. Mule / secondary-account behavior observed

This is not a server API endpoint, but it is an important integration discovery from the client.

### 9.1 Primary-account behavior

If the connected Trading Paints account is the same account you normally use, the app may:

- change the connected account's active showroom paint temporarily
- capture the new manifest assets
- restore the original paint afterward

### 9.2 Secondary / mule-account behavior

The client supports a dedicated secondary account used only to switch paints for capture.
In that mode, the app may:

- require an explicit Trading Paints member ID override for the mule account
- skip original-scheme capture
- skip final restore
- reuse the showroom/browser context across the whole session
- rely directly on manifest polling after each `setScheme`

### 9.3 Auto-enable rule observed

The client can auto-treat the workflow as mule mode when:

- `manifest_member_id` is set, and
- it differs from the local iRacing user ID

This is app-side logic, but it is important for understanding why the same Trading Paints API behavior can succeed in one account setup and fail in another.

---

## 10. Download model

### 10.1 HTTP behavior

The client uses a shared `requests.Session` per worker thread with:

- a custom `User-Agent` of the form:
  - `nishizumi-paints/{app_version}`
- connection pooling via `HTTPAdapter`
- no requests-level retry adapter; retries are handled in application code

### 10.2 Download behavior

Each asset returned by the manifest is downloaded with:

- `GET {file_url}`
- `stream=True`
- timeout `(10, 90)`
- chunk size `1 MiB`

The file is first written into a temporary per-session directory.

### 10.3 Compression handling

If the downloaded filename ends with `.bz2`, the client decompresses it before final installation.
If it is not `.bz2`, it is moved directly into place.

This implies Trading Paints may return either:

- already-usable files, or
- bzip2-compressed paint assets

---

## 11. Local save conventions used by the client

The app installs files into the standard iRacing paint layout using the paint `type`, target ID, directory, and team/superspeedway flags.

### 11.1 Standard filenames

For a normal user target:

- `car` -> `{paints_dir}/{directory}/car_{user_id}.tga`
- `car_decal` -> `{paints_dir}/{directory}/decal_{user_id}.tga`
- `car_num` -> `{paints_dir}/{directory}/car_num_{user_id}.tga`
- `car_spec` -> `{paints_dir}/{directory}/car_spec_{user_id}.mip`
- `helmet` -> `{paints_dir}/helmet_{user_id}.tga`
- `suit` -> `{paints_dir}/suit_{user_id}.tga`

### 11.2 Team filenames

If the manifest item is treated as a team paint, the ID portion becomes:

- `team_{team_id}`

Examples:

- `car_team_55555.tga`
- `car_spec_team_55555.mip`
- `helmet_team_55555.tga`

### 11.3 Superspeedway dual-save behavior

For car-related paint types in superspeedway sessions, the client writes both:

- the normal filename, and
- an `_ss` variant

Examples:

- `car_12345.tga`
- `car_12345_ss.tga`
- `car_spec_12345.mip`
- `car_spec_12345_ss.mip`

Car-related types in this rule are:

- `car`
- `car_decal`
- `car_num`
- `car_spec`

---

## 12. Team-target behavior

The client treats these paint types as capable of using team targets:

- `car`
- `car_decal`
- `car_num`
- `car_spec`
- `helmet`
- `suit`

If the manifest reports a nonzero `teamid` for one of those types, the client may rewrite the target so the saved file uses the team ID instead of the individual user ID.

This is especially important in team racing sessions.

---

## 13. Matching returned paints to the iRacing session

The client does not just accept every returned paint.
After it gets manifest items, it decides whether each item belongs to the current session entry.

Observed matching rules:

- `helmet` and `suit` are always accepted for the entry
- car-related files are accepted when `directory` matches the session user's car directory
- if the directory differs only by normalization, it is still accepted

Normalization behavior:

- lowercase
- replace non-alphanumeric characters with `_`
- collapse repeated `_`
- trim leading / trailing `_`

This is a practical compatibility layer for minor naming differences.

The showroom/direct-manifest path adds another directory matcher for car-related files:

- raw directory
- canonicalized directory
- space-separated variant

This is used when comparing baseline and updated manifest items for the connected account.

---

## 14. AI roster support

### 14.1 Collections list response

The AI collections endpoint is parsed as XML.
The client looks for repeated `.//Collection` nodes and reads:

- `ID`
- `Name`
- `RosterFile`

Each valid node becomes an AI roster candidate.

### 14.2 Roster JSON shape

The roster file is expected to be JSON with a top-level object containing:

- `drivers`: an array of driver objects

If `drivers` is missing or is not a list, the payload is rejected.

### 14.3 Driver fields observed / normalized by the client

The client preserves most roster driver fields but also normalizes a few values, including:

- `carId`
- `carClassId`
- `carDesign`
- `carPath`
- `carNumber`
- `driverName`
- `carTgaName`
- `helmetTgaName`
- `suitTgaName`

Observed normalization behavior:

- certain special car IDs may get a default `carDesign` of `"0,"`
- `carPath` has spaces converted back to backslashes when canonicalized for local AI roster files

### 14.4 Local AI roster files written by the client

For each synced roster, the app writes:

- `roster.json`
- `notes.txt`
- `.nishizumi_ai_roster.json`

The metadata file stores values such as:

- `roster_id`
- `name`
- `roster_file`
- `is_local`
- `source_roster_id`
- `source_name`

---

## 15. Retry / failure behavior

### 15.1 App-level retries

The client uses application-managed retries for Trading Paints operations.
Defaults observed in the app:

- retries: `3`
- exponential backoff base: `1.0s` or `1.5s` in some newer showroom branches
- effective waits: `1x`, `2x`, `4x`, capped at `8s`

### 15.2 Context manifest fallback chain

The manifest resolution path is:

1. try contextual `fetch.php`
2. if no session context exists, use `fetch_user.php`
3. if contextual lookup fails, fall back to `fetch_user.php`

This makes `fetch_user.php` the compatibility fallback when session-aware resolution is unavailable.

### 15.3 Showroom fallback failure modes observed

Observed failure classes include:

- login/profile not confirmed for the persistent browser profile
- `setScheme` returning non-OK HTTP status
- manifest never changing away from baseline before timeout
- manifest exposing no car assets before timeout
- wrong `manifest_member_id` / wrong connected account

The app reports these as user-visible fallback failures rather than pretending the scheme application succeeded.

---

## 16. Inferred response examples

### 16.1 Possible `fetch_user.php` / `fetch.php` XML shape

This is **illustrative**, not guaranteed:

```xml
<Response>
  <Car>
    <userid>987654</userid>
    <teamid>0</teamid>
    <carid>123</carid>
    <directory>dallaradw12</directory>
    <type>car</type>
    <file>https://...</file>
  </Car>
  <Car>
    <userid>987654</userid>
    <teamid>0</teamid>
    <directory>dallaradw12</directory>
    <type>car_spec</type>
    <file>https://...</file>
  </Car>
</Response>
```

### 16.2 Possible showroom JSON shape

This is **illustrative**, not guaranteed:

```json
{
  "output": {
    "cars": [
      {
        "id": "885148",
        "title": "BMW M2 CS Racing",
        "official": "0",
        "users": "12",
        "bookmarks": "3"
      }
    ]
  }
}
```

### 16.3 Possible AI collections XML shape

```xml
<Response>
  <Collection>
    <ID>12345</ID>
    <Name>My AI Carset</Name>
    <RosterFile>https://...</RosterFile>
  </Collection>
</Response>
```

### 16.4 Expected roster JSON shape

```json
{
  "drivers": [
    {
      "driverName": "Example Driver",
      "carNumber": "12",
      "carPath": "dallara\\dw12",
      "carTgaName": "car_1.tga",
      "helmetTgaName": "helmet_1.tga",
      "suitTgaName": "suit_1.tga"
    }
  ]
}
```

---

## 17. Practical integration notes for other developers

If you are writing your own client based on these observations:

1. Prefer the **context endpoint** when you know the active iRacing session context.
2. Keep a **fallback to `fetch_user.php`** for compatibility.
3. Parse manifests as **XML**, not JSON.
4. Parse showroom pages as **JSON**, not HTML, when you are using `js/showroom.php`.
5. Be prepared for **compressed asset downloads** (`.bz2`).
6. Treat `teamid` carefully, especially in team events.
7. Match car folders conservatively and allow for normalized-name fallback.
8. Do not assume all returned manifest nodes belong to your exact target entry.
9. If you automate showroom switching, you will probably need an authenticated persistent browser session.
10. If you automate a secondary / mule account, do not assume the local session user ID is the correct manifest polling member ID.
11. Expect any of these endpoints, field names, or behaviors to change without notice.

---

## 18. What is still unknown from this client alone

This implementation does **not** fully document:

- official authentication requirements beyond what these observed calls needed
- rate limits on the Trading Paints side
- whether additional showroom JSON fields exist but were unused by the client
- whether additional dashboard-side mutation endpoints exist
- whether returned file URLs have expiration, signature requirements, or anti-abuse constraints
- whether the same endpoints are intended for third-party public use
- whether `setScheme.php` has hidden parameters or server-side anti-abuse conditions beyond what was observed here

---

## 19. Attribution and caution

This document was reconstructed from an application implementation that interoperates with Trading Paints.
It is meant to help developers understand observed request / response patterns.

Please use it responsibly, avoid abusive polling or scraping, and expect breakage if Trading Paints changes infrastructure.
