# Trading Paints Unofficial API / SDK Notes

> **Unofficial documentation** based on observed client behavior in the `Nishizumi Paints` codebase.
> This is **not** official Trading Paints documentation, may be incomplete, and may break if Trading Paints changes server behavior.
>
> Scope: this document only covers what was actually used or inferred from the app's implementation.

## 1. What this documents

From the client implementation, Trading Paints is used in three main ways:

1. **User paint manifest lookup** via a user-specific endpoint.
2. **Session-context paint manifest lookup** via a context-aware endpoint.
3. **AI roster discovery and download** via a collections endpoint and roster JSON files.

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

### 2.3 AI collections endpoint

Observed endpoint:

- `https://fetch.tradingpaints.gg/collections.php?user={member_id}`

**Method**

- `GET`

**Purpose**

- Return a list of AI collections / carsets associated with a member.

### 2.4 AI roster JSON

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

## 5. Download model

### 5.1 HTTP behavior

The client uses a shared `requests.Session` per worker thread with:

- a custom `User-Agent` of the form:
  - `nishizumi-paints/{app_version}`
- connection pooling via `HTTPAdapter`
- no requests-level retry adapter; retries are handled in application code

### 5.2 Download behavior

Each asset returned by the manifest is downloaded with:

- `GET {file_url}`
- `stream=True`
- timeout `(10, 90)`
- chunk size `1 MiB`

The file is first written into a temporary per-session directory.

### 5.3 Compression handling

If the downloaded filename ends with `.bz2`, the client decompresses it before final installation.
If it is not `.bz2`, it is moved directly into place.

This implies Trading Paints may return either:

- already-usable files, or
- bzip2-compressed paint assets

---

## 6. Local save conventions used by the client

The app installs files into the standard iRacing paint layout using the paint `type`, target ID, directory, and team/superspeedway flags.

### 6.1 Standard filenames

For a normal user target:

- `car` -> `{paints_dir}/{directory}/car_{user_id}.tga`
- `car_decal` -> `{paints_dir}/{directory}/decal_{user_id}.tga`
- `car_num` -> `{paints_dir}/{directory}/car_num_{user_id}.tga`
- `car_spec` -> `{paints_dir}/{directory}/car_spec_{user_id}.mip`
- `helmet` -> `{paints_dir}/helmet_{user_id}.tga`
- `suit` -> `{paints_dir}/suit_{user_id}.tga`

### 6.2 Team filenames

If the manifest item is treated as a team paint, the ID portion becomes:

- `team_{team_id}`

Examples:

- `car_team_55555.tga`
- `car_spec_team_55555.mip`
- `helmet_team_55555.tga`

### 6.3 Superspeedway dual-save behavior

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

## 7. Team-target behavior

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

## 8. Matching returned paints to the iRacing session

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

---

## 9. AI roster support

### 9.1 Collections list response

The AI collections endpoint is parsed as XML.
The client looks for repeated `.//Collection` nodes and reads:

- `ID`
- `Name`
- `RosterFile`

Each valid node becomes an AI roster candidate.

### 9.2 Roster JSON shape

The roster file is expected to be JSON with a top-level object containing:

- `drivers`: an array of driver objects

If `drivers` is missing or is not a list, the payload is rejected.

### 9.3 Driver fields observed / normalized by the client

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

### 9.4 Local AI roster files written by the client

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

## 10. Retry / failure behavior

### 10.1 App-level retries

The client uses application-managed retries for Trading Paints operations.
Defaults observed in the app:

- retries: `3`
- exponential backoff base: `1.0s`
- effective waits: `1x`, `2x`, `4x`, capped at `8s`

### 10.2 Context manifest fallback chain

The manifest resolution path is:

1. try contextual `fetch.php`
2. if no session context exists, use `fetch_user.php`
3. if contextual lookup fails, fall back to `fetch_user.php`

This makes `fetch_user.php` the compatibility fallback when session-aware resolution is unavailable.

---

## 11. Inferred response examples

### 11.1 Possible `fetch_user.php` / `fetch.php` XML shape

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

### 11.2 Possible AI collections XML shape

```xml
<Response>
  <Collection>
    <ID>12345</ID>
    <Name>My AI Carset</Name>
    <RosterFile>https://...</RosterFile>
  </Collection>
</Response>
```

### 11.3 Expected roster JSON shape

```json
{
  "drivers": [
    {
      "driverName": "Example Driver",
      "carNumber": "12",
      "carPath": "dallara\dw12",
      "carTgaName": "car_1.tga",
      "helmetTgaName": "helmet_1.tga",
      "suitTgaName": "suit_1.tga"
    }
  ]
}
```

---

## 12. Practical integration notes for other developers

If you are writing your own client based on these observations:

1. Prefer the **context endpoint** when you know the active iRacing session context.
2. Keep a **fallback to `fetch_user.php`** for compatibility.
3. Parse manifests as **XML**, not JSON.
4. Be prepared for **compressed asset downloads** (`.bz2`).
5. Treat `teamid` carefully, especially in team events.
6. Match car folders conservatively and allow for normalized-name fallback.
7. Do not assume all returned manifest nodes belong to your exact target entry.
8. Expect any of these endpoints, field names, or behaviors to change without notice.

---

## 13. What is still unknown from this client alone

This implementation does **not** fully document:

- authentication requirements beyond what these observed calls needed
- rate limits on the Trading Paints side
- whether additional manifest fields exist but were unused by the client
- whether other endpoint variants exist
- whether returned file URLs have expiration, signature requirements, or anti-abuse constraints
- whether the same endpoints are intended for third-party public use

---

## 14. Attribution and caution

This document was reconstructed from an application implementation that interoperates with Trading Paints.
It is meant to help developers understand observed request / response patterns.

Please use it responsibly, avoid abusive polling or scraping, and expect breakage if Trading Paints changes infrastructure.
