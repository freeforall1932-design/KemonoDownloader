# Upstream & sibling-project landscape — where our code stands, what to take, and how to track it

> Written **2026-10-28**. Companion docs: [`UPSTREAM_RECONCILIATION.md`](./UPSTREAM_RECONCILIATION.md)
> (the v5.13.0 collision + merge plan), [`WORKLIST.md`](./WORKLIST.md),
> [`SESSION_HANDOFF.md`](./SESSION_HANDOFF.md), [`IMPROVEMENT_LOG.md`](./IMPROVEMENT_LOG.md).
>
> Question this answers: *the repo `freeforall1932-design/Kemono-Downloader` is a
> different project with the same purpose — does it (or anything else) have an
> edge over our source, what is the real state of "Kemono → Pawchive", and how do
> we keep absorbing the best of every upstream without forking into a mess?*

---

## 1. TL;DR

| Question | Answer |
|---|---|
| Is `freeforall1932-design/Kemono-Downloader` a different codebase? | **Yes, entirely.** It is our own fork (created 2026-10-27) of **`Yuvi9587/Kemono-Downloader`** — 664★, PySide6, ~40k LOC in 89 files, v10.01 (2026-10-12). Different lineage, different architecture (per-site "client" + "downloader thread" classes). |
| Does it have an edge over us? | **Yes, on breadth of sites and on download plumbing** — multi-part/`Range` resume, pause/resume/restore-session, error-retry dialog, PDF/DOCX/TXT export, "only links" + cloud (Mega/GDrive/Dropbox) direct download, WebP compression, character/scene filters, per-platform SQLite. But it is **further behind on the API itself than we are** (see §5). |
| Who is closest on API truth? | **Nobody is current.** As of today the live Pawchive API returns `file.preview_only`, `file.temp_url` + `temp_expires`, `attachments[].deferred` and `file.node`. **Our fork, upstream VoxDroid, Yuvi and kemono-dl all ignore those fields.** Only `pawstash` handles `preview_only` (by substituting the thumbnail). That is our biggest single opportunity. |
| Does anything beat us on Kenomo-family correctness? | **We already lead on three things**: `{posts: [...]}` envelope tolerance (`creator_downloader.py:646`), `has_full` → thumbnail, and a packaged dynamic domain list. Yuvi has **no** envelope handling — the current `kemono.cr/api/v1/posts` response would break it. |
| Was "Kemono renamed to Pawchive"? | **No — that framing is wrong.** Kemono's *file servers* (`n1–n4.kemono.cr`) died in April 2026 and the site stopped importing; **Pawchive** (launched ~2026-06-14 by an independent operator on Kemono's open-source code, `.st` → `.pw`) is an unofficial alternative, not a rename, and its owner denies being an official successor. Separately, **`cum.st` ("OnlyHaven")** now serves the Coomer/OnlyFans side. Details + citations in §6. |
| What should we actually do? | Keep the §7 plan: **merge upstream v5.13.0 first, renumber to v5.14.0**, then add a **`sources.py` provider registry** (multi-site, capability-flagged, mirror-aware) and the **P0 items in §8** — 2026-10 file model, per-site endpoint rules, hash-based dedupe, credential login. Track everything with the §9 watchlist + drift probe. |
| What must we *not* copy? | Code from **GPL** projects: `gallery-dl` (GPL-2.0), `pawstash` (GPL-3.0). Our repo is **MIT**. Use them for facts/behaviour only. `Yuvi9587` (MIT) and VoxDroid (MIT) are safe to port from. `kemono-dl` and `pawchive-tools` declare **no licence** → facts only. See §10. |

---

## 2. Source inventory (checked 2026-10-28)

| # | Repository | ★ | Stack | Licence | Last push | What it is | Verdict for us |
|---|---|---|---|---|---|---|---|
| A | `VoxDroid/KemonoDownloader` | 377 | PyQt6 | MIT | 2026-09-27 | **Our upstream** (v5.13.0 = Pawchive rate limiting) | **Merge as base.** See reconciliation doc. |
| B | `Yuvi9587/Kemono-Downloader` | 664 | PySide6 | **MIT** | 2026-10-22 | Feature-heavy GUI archiver, v10.01, many sites | **Port selected features** (§4.1). Best legal source of GUI ideas. |
| C | `AlphaSlayer1964/kemono-dl` | 625 | Python CLI | none declared | 2026-08-11 | Small, readable CLI: login-by-password, SHA-256 verify, `Range` resume | **Port 3 patterns** (§4.2). |
| D | `rushiaismywaifu/pawchive-tools` | 1 | Python | none declared | 2026-10-09 | Extracted **OpenAPI spec** + tested behaviour guide (2026-07-28) | **Use as the API spec** (§5). Facts only. |
| E | `pawstash/pawstash` | 43 | Rust/Tauri+Svelte | **GPL-3.0** | 2026-10-24 | Modern client; only project handling `preview_only`; e2ee sync | **Behaviour only, no code.** |
| F | `mikf/gallery-dl` | 20k★ | Python CLI | **GPL-2.0** | 2026-10-25 | Extractor framework; `kemono` extractor, `[pawchive]` request #9590 | Reference only. |
| G | `Ljzd-PRO/KToolBox` | 591 | TypeScript | — | 2026-09-10 | "Downloader for Pawchive (Kemono), high customisability" | UI/feature ideas only. |
| H | `whyamihere773/Pawchive-Downloader` | 65 | QML/PySide6 | — | 2026-10-26 | Pawchive + **`cum.st`**, yt-dlp embedded streams, Mega decryption | Confirms **`cum.st`** as the Coomer-side host. |
| I | `KarlcxChina/KemonoDownloader` | 94 | Python | — | 2026-10-14 | "KemonoDownloader (actually PawchiveDownloader)" | Confirms Pawchive-as-default framing. |
| J | `LeoIsamaru/Pawchive-Favorites-Importer-from-kemono` | 21 | Python | — | 2026-06-14 | Favorites JSON export shape | Already used (our feature 4). |

Sites in the family: `kemono.cr` (+ dead historical `.party`, `.su`), `coomer.st` (+ dead `.party`, `.su`), `pawchive.pw` (+ `.st` retired), `cum.st` / "OnlyHaven" (OnlyFans/Fansly/Patreon). A future merged site ("moxxy") is **rumoured**, unverified — treat as a name to watch, not a target.

---

## 3. Architecture comparison (why porting is cheap or expensive per item)

| | Ours / VoxDroid | Yuvi9587 | kemono-dl | pawstash |
|---|---|---|---|---|
| UI | PyQt6, 6 tabs, one file per tab (~4–6k lines each) | PySide6, single main window + per-site thread classes | none | Tauri/Svelte |
| Per-site logic | implicit: one downloader handles kemono-family; domain config drives hosts | explicit: `src/core/*_client.py` + `src/ui/classes/*_downloader_thread.py` + factory | per-site branches inside one module | explicit Rust providers (`api/providers/*.rs`) |
| Site registry | `assets/config/domain` (3 domains, fetched remotely) | hardcoded lists inside `api_client.py` + constants | hardcoded | credentials/prefixes per provider |
| Dedupe | SQLite `hash_db` (MD5 of content, keyed by URL hash) | per-platform SQLite keyed by URL stem hash | **SHA-256 verified against URL filename** | local DB |
| Resume | none (whole-file retry) | **multi-part `Range` downloader** | `Range` resume | — |
| Session state | none | **pause/resume/restore-interrupted download** | — | local-first stash |

Practical read: **Yuvi's per-site abstraction is closer to what a multi-source future needs**, but its downloader is a 3.2k-line monolith (`workers.py`) tangled with the UI. Ours is testable and policy-compliant. So: **port behaviours, not structure** — our structural answer is the registry in §7, which is deliberately smaller than either.

---

## 4. Concrete edges worth taking

### 4.1 From `Yuvi9587/Kemono-Downloader` (MIT → safe to port)

| Item | What it does | Why it matters to us | Effort | Priority |
|---|---|---|---|---|
| **Multi-part / `Range` downloader** (`src/services/multipart_downloader.py`, 299 lines) | splits a file into N ranged chunks, retries each chunk, merges; `Range: bytes=<n>-` resume | our `download_file` restarts the whole file on every retry — for 2 GB videos that is the single biggest waste; `file.pawchive.pw` **supports `Range`/`206`** (verified) | M | **P1** |
| **Pause / Resume / Restore interrupted session** | persists UI state + processed posts; "Restore Download" button | long creator runs die on a crash and lose everything | M | **P1** |
| **Error dialog with retry/export** | collects failed files, lets you retry them later | we log failures and forget them | S | **P1** |
| **`preview_state == "pending"` → single attempt, no retries, explain once** | avoids 3× retry storms on not-yet-imported posts | we now know `preview_state` exists in live Pawchive responses; combined with the new `preview_only` field this is the correct early-exit | S | **P0** |
| **`_find_valid_subdomain` (403 → try `n1..n4.<base>`)** | rotates media subdomains | kemono's `n1–n4` model; still the right idea for `node`-keyed files (§5.3) | S | **P2** |
| **Favorites-tier size-cap explanation** ("file exceeds Pawchive's per-post cap for this creator's favorites tier") | tells the user *why* a file will never appear | prevents infinite retry cycles; Pawchive's site policy is favourites-tiered (100 MB / 1 GB / 5 GB) | S | **P1** |
| Only-Links mode + cloud direct download (Mega/GDrive/Dropbox), PDF/DOCX/TXT export, WebP compression, character/scene + skip-by-size filters, manga ordering | feature breadth | our `WORKLIST` §F currently says *out of scope* (revisions/comments/tags/etc.) — **reconfirm whether that still holds**; some of these are now cheap | L | **P3 / needs approval** |
| `fox.pawchive.<suffix>` CDN fallback | tries `fox.` when `file.` fails DNS | ⚠️ **stale**: as of 2026-10-28 `fox.pawchive.pw` does not resolve; `file.pawchive.pw` does. Don't port as-is — generalise to "try the host the API implies, then its `n<node>` sibling" | — | skip |

### 4.2 From `AlphaSlayer1964/kemono-dl`

| Item | What it does | Why | Priority |
|---|---|---|---|
| **Login with username/password → session cookie** (`--pawchive-login USER PASS`) | posts to the site's web login form, keeps `session` cookie | our UI asks users to *paste a session cookie*. No official key endpoint exists (see §5.4), so a real login form is the correct UX. Big usability win. | **P0** |
| **SHA-256 verification against the URL filename** | every Pawchive file path ends in the content's SHA-256, so you can (a) verify after download, (b) skip before download if a same-hash file exists anywhere | gives cross-session, cross-folder dedupe **without hashing the whole library** — far cheaper than our MD5-everything approach | **P1** |
| `Range` resume + `--date/--datebefore` filters + output templating | CLI conventions | confirms our template approach; date filters are easy adds | P2 |

### 4.3 From `pawstash` (GPL — behaviour only)

* `preview_only` file → **use the thumbnail object** as the media URL (`resolve_thumbnail_url`), and label it as a preview in the UI.
* `deferred` attachment → render a placeholder ("file not saved yet"), never queue it as a download.
* Provider-per-site structure with per-provider credential prefixes — same idea as our §7 registry, already battle-tested.

---

## 5. Live API reality (verified today, 2026-10-28)

Everything in this section was checked against the live endpoints during this session (Pawchive is reachable through the platform proxy; the sandbox itself cannot open TLS to it).

### 5.1 Pawchive now has *two* file models

**Model 1 — classic** (still the majority):
```json
"file": {"name": "selfie_aurora.png", "node": 2, "path": "/92/99/9299….png"}
```
→ `file.pawchive.pw/data{path}?f={name}` (or the `img.` thumbnail).

**Model 2 — preview-only** (`file.preview_only: true`):
```json
"file": {"name": "00043-….png", "path": "/54/92/5492….png", "preview_only": true,
         "temp_url": "https://t1.pawchive.pw/f/<id>/00043-….png?e=1793161434&s=<sig>",
         "temp_expires": "2026-11-11T00:00:00+00:00"}
```
→ the full file is **not** at `file.pawchive.pw/data{path}`; the only usable link is the
**signed, expiring `temp_url`** (host `t1.pawchive.pw`, ~14-day expiry), otherwise the
**thumbnail**. Note `has_full: true` on these posts — **`has_full` is no longer the whole truth**.

**Model 3 — deferred** (`attachments[].deferred: true`, and **no `path` at all**): not imported yet, nothing to download. Our `detect_files` silently skips them (`isinstance(attachment, dict) and "path" in attachment`) — correct, but we should log *why* so users stop waiting.

### 5.2 Response shapes differ per site

| Endpoint | `kemono.cr` | `pawchive.pw` |
|---|---|---|
| `/api/v1/posts?o=` | **object** `{count, true_count, posts:[…]}` | **bare array** `[…]` |
| `/{service}/user/{id}/posts?o=` | bare array (historically) | bare array — **works**, though the site itself uses `/{service}/user/{id}` |
| Post detail | `{…}` or `{post: {…}}` | plain object, plus `next`/`prev`, `detail_fetched` |
| Extra fields | none | `preview_state`, `has_full`, `origin`, `file.preview_only`, `file.temp_url`, `file.temp_expires`, `file.node`, `attachments[].deferred` |

**We already handle the `{posts: […]}` envelope** (`creator_downloader.py:646-650`, plus `data`); **Yuvi does not**. Keep it and add a test.

### 5.3 `node`

`node: 2` appears on most file objects. Its host mapping is **not documented and not implemented by any client we inspected**. Kemono's historical model was `n1..n4.kemono.cr`; `pawchive.pw` currently answers on `file.pawchive.pw` and `img.pawchive.pw` (both verified up), while `fox.pawchive.pw` does not resolve. **Do not guess**: treat `node` as advisory, try `file.` first, and (P2) probe `n{node}.<domain>` before falling back — exactly the pattern in §4.1 but driven by the field instead of a fixed list.

### 5.4 Auth

* Only scheme in the OpenAPI spec: **`cookieAuth`**, cookie name `session`. No API key, no Bearer, no `/api/v1/account/login`.
* Unauthenticated `/account/favorites` → `401 {}` (the spec says 302; reality is 401 — handle both).
* The website's **`/account/keys`** page has **no v1 endpoint** (404). Our UI label *"Pawchive API key"* is therefore misleading → rename to **"Pawchive session cookie"** and offer a login form (§4.2).

### 5.5 Pagination, caching, limits (tested by pawchive-tools 2026-07-28, consistent with our probes)

* Single offset parameter `o`, **page size fixed at 50**, `o` must be a **multiple of 50**.
* `/posts` offset hard cap **50 000** (≈1000 pages); `/{service}/user/{id}` has no cap — stop on `< 50` items or `[]`.
* `/posts` is CDN-cached 60 s (`cache-control: max-age=60`, `vary: Cookie`) — our 1 req/s policy is *below* what the CDN can absorb, which is fine (be a good citizen), but it means a poller should use ≥60 s intervals to see new data.
* No `X-RateLimit-*` headers; `429` may carry `Retry-After` → **our limiter must honour `Retry-After`** and must never retry `POST` blindly (idempotency).
* `/creators` returns **12.4 MB / 90 432 creators in one shot** — useful for a local creator index, useless for polling.

### 5.6 File-server facts we can exploit

* Path layout: `/ab/cd/<sha256>.<ext>`; the **filename is the SHA-256 of the content**.
* `file.pawchive.pw` supports **`Range`** (206) → multi-part/resume is viable (§4.1).
* Thumbnails live on `img.pawchive.pw/thumbnail/data{path}` and **occasionally 502** → fall back to the original (we already fall back the other way round).
* Pawchive enforces **per-post size caps by favourites tier**: `<250` favs → 100 MB, `250–5000` → 1 GB, `>5000` → 5 GB. Files above the cap are permanently unavailable → detect once, warn once, never retry (§4.1).

### 5.7 Where our code stands against §5 (file-by-file)

| Behaviour | Ours today | Needed | Where |
|---|---|---|---|
| `{posts: […]}` envelope | ✅ handled | — | `creator_downloader.py:646` |
| `has_full is False` → thumbnail | ✅ | keep, but demote to *one* of several signals | both downloaders `detect_files` |
| `file.preview_only` → `temp_url` → thumbnail | ❌ | new resolver | `domain_config.py` + both `detect_files` |
| `temp_url` expiry check (`temp_expires`) | ❌ | skip/refresh stale links, never retry a dead signature | resolver |
| `attachments[].deferred` (no path) | implicit skip | log once per post | `detect_files` |
| `preview_state == "pending"` → 1 attempt | ❌ | early exit | `_handle_full_res_failure` |
| size-cap explanation | ❌ | one-shot message | fallback path |
| SHA-256 name → dedupe | ❌ (MD5 of bytes) | cheap pre-check | `hash_db.py` |
| `Range` resume / multi-part | ❌ | optional per-file setting | download threads |
| `Retry-After` handling | ❌ | limiter | `download_policy.py` |
| per-site endpoint/pagination rules | implicit | registry | new `sources.py` |
| `cum.st` / future sites | ❌ (3 domains only) | registry | `assets/config/domain` |

---

## 6. "Kemono ended → Pawchive": what actually happened

Timeline (community + project evidence; treat as reported, not official):

| Date | Event |
|---|---|
| 2024-08 → 2026-03 | Kemono's Patreon/Fanbox importers degrade repeatedly; DMCAs; domain churn `.party → .su → .cr`. |
| **2026-04** | **`n1–n4.kemono.cr` file servers go offline.** The catalogue stays browsable, images load from `img.kemono.cr`, but **every full-resolution download / video fails**. This is the "block any downloadable" the user remembers. ([r/Piracy megathread](https://www.reddit.com/r/Piracy/comments/1tayzgo/unofficial_information_about_the_kemonocr_site/), [itechguides](https://www.itechguides.com/what-happened-to-kemono-party-r-piracy/)) |
| 2026-04-27 | Yuvi (owner of the 664★ downloader) confirms in [issue #109](https://github.com/Yuvi9587/Kemono-Downloader/issues/109): the `n1.kemono.cr/data` links are down, VPN will not help. |
| **2026-06-14** | **`pawchive.st` launches**, by an independent operator (`purpleuniverses`), built on Kemono's open-source code. Explicitly **not** an official successor. ([r/kemono_piracy](https://www.reddit.com/r/kemono_piracy/comments/1u5bn3h/is_really_pawchivest_the_successor_of_kemono/)) |
| 2026-06-19 | `gallery-dl` site-request [#9590](https://github.com/mikf/gallery-dl/issues/9590) — "[pawchive] add initial support" commit appears. |
| 2026-06-22 → 06-23 | Registrar places `pawchive.st` on hold; site relocates. |
| **2026-07** | **`pawchive.pw` becomes primary**; `.st` redirects/serves 301 for API. `coomer`'s equivalent side surfaces as **`cum.st` ("OnlyHaven")** for OnlyFans/Fansly/Patreon. |
| 2026-08 | Kemono.cr still returns 200 for `/api/v1/posts` but the newest posts are from **Jan–Mar 2026** (verified today: `true_count` 21.7M, `published` mostly early 2026) — archive with a frozen catalogue. |
| **2026-10-28 (today)** | Pawchive serves Patreon + Fanbox + Discord, `has_full`, `preview_state`, and the new **`preview_only`/`temp_url`** file model. `pawchive.pw` up; `pawchive.st` canonical-but-301; `file.`/`img.` up; `fox.` dead. |

**Conclusions that change our product decisions**

1. **No rename happened.** Kemono still exists as a frozen catalogue; Pawchive is a *parallel* archive that re-imported a fraction of it (owner states ~10–15 % capacity, and favourites-tier size caps). Documentation must say this instead of implying a migration.
2. **Kemono is now thumbnail-only in practice.** Our `has_full` fallback and the Thumbnail tab are the *primary* Kemono paths, not a rescue path. Retire the idea that Kemono downloads just need retries.
3. **Pawchive is the primary full-res source** and should be the **default** source in the UI, with a one-click "same creator on Pawchive" jump (creator IDs are shared — this is the highest-value UX change of all, and it also fixes the ~90 % of Kemono links that would otherwise 404).
4. **Domains rotate on weeks-to-months timescales** (`.st` → `.pw` within a month). Never hardcode; keep the remote domain list authoritative and add `cum.st`. This also means upstream's `is_pawchive_url()` hardcode is a *live* bug, not a theoretical one (§6 of the reconciliation doc).
5. **A fourth site in the family is plausible** (`cum.st`, and the rumoured "moxxy"). Build for N sources, not 3.

---

## 7. Recommended architecture: one thin registry, no fork soup

Goal: absorb upstream + siblings without ever again doing a hand-merge of download logic.

```
src/kemonodownloader/sources.py          # NEW, no Qt, unit-testable
    @dataclass(frozen=True)
    class SiteSpec:
        key: str                # "pawchive", "kemono", "coomer", "cumst"
        domains: tuple[str, ...]
        api_shape: str          # "kemono_v1" | "onlyhaven_v1"
        creator_posts_path: str # "/{service}/user/{id}" | "/{service}/user/{id}/posts"
        posts_envelope: str|None# "posts" (kemono) | None (bare array)
        file_host: str          # "file.{domain}"
        image_host: str         # "img.{domain}"
        supports: Capabilities  # favorites_auth, hash_lookup, revisions, dms, temp_url, node_routing
        mirror_of: str|None     # kemono -> pawchive, coomer -> cum.st
        default_priority: int
```

Consumers:

* `domain_config.py` keeps its public API but is **implemented on top of `sources.py`** (so no call-site churn, and `get_domains()` still feeds the remote list).
* **`resolve_file_url(file_obj, spec)`** — the single place that decides (in order): `temp_url` (if `temp_expires` in the future) → `file.{domain}/data{path}?f={name}` → `img.{domain}/thumbnail/data{path}` when `preview_only` → `None` when `deferred`. `clean_file_url` / `to_thumbnail_url` become thin wrappers. **This replaces per-downloader ad-hoc logic.**
* **`resolve_mirror(url)`** — writes the same creator/post onto a sibling site: `kemono.cr/…/user/ID` → `pawchive.pw/…/user/ID`; `coomer.st/…` → `cum.st/…`. Used by a new "Auto-switch source when downloads fail" setting (default: ask once per creator).
* **`pagination(spec, endpoint)`** — encodes `o` multiple-of-50, the 50 000 cap, and the stop rule, so `pawchive.fetch_old_site_favorites`, the recent feed and creator crawling all share one implementation.
* `download_policy.py` grows `pace(spec, …)` (1 req/s for pawchive, `Retry-After` respected, `POST` never auto-retried) and stays the only throttle.

Migration order (each step is independently shippable):

1. `sources.py` with the four sites + `resolve_file_url` + tests (pure Python — runs in this sandbox).
2. Route both `detect_files`, `clean_file_url`, `to_thumbnail_url` and `pawchive.py` through it. Behaviour must not change for classic URLs → existing tests are the guard.
3. Add the 2026-10 file model (`preview_only`/`temp_url`/`deferred`) + `preview_state` early exit + size-cap notice.
4. Add `resolve_mirror` + UI affordance.
5. `hash_db` SHA-256 pre-check; then optional `Range` multipart.

---

## 8. Prioritised adoption list

**P0 — correctness against the live API (do with the v5.14.0 cut)**
1. `sources.py` registry + `resolve_file_url` (Pawchive `preview_only`/`temp_url`/`temp_expires`/`deferred`, `node` advisory). → today we (and everyone else) generate 403/404 URLs for a growing share of Pawchive posts.
2. `preview_state == "pending"` → single attempt + one-time explanation.
3. Favourites-tier size-cap notice (100 MB / 1 GB / 5 GB) instead of endless retries.
4. Rename "Pawchive API key" → "Pawchive session cookie"; add username/password login (kemono-dl pattern); keep manual paste.
5. `Retry-After` in the limiter; never auto-retry `POST`.
6. Add `cum.st` + mirror map; default source = Pawchive for kemono-family content.

**P1 — plumbing & UX**
7. Error dialog with retry/export (Yuvi). 8. Session restore for creator runs (Yuvi). 9. SHA-256 filename dedupe/verify (kemono-dl). 10. `Range` resume, multi-part optional (Yuvi + verified `206` support). 11. Per-source "site status" panel driven by `sources.py` (replaces the hand-written availability tables in README/releases).

**P2 — resilience**
12. `node`/`n<node>` host probing. 13. Recent-feed poller with ≥60 s interval honouring CDN cache. 14. `/creators` snapshot → local creator index for instant search.

**P3 — needs explicit approval (currently `WORKLIST` §F says out of scope)**
Only-Links + cloud direct download, PDF/DOCX/TXT export, WebP compression, character/skip-by-size filters, manga ordering, DMs, revisions.

---

## 9. Keeping up with N upstreams (the "streamlining" process)

**Watchlist** (check monthly, or when a user reports breakage):

| Source | Watch | Why |
|---|---|---|
| `VoxDroid/KemonoDownloader` | releases + `download_policy.py`, `kd_thumbnaildl.py`, `domain_config.py` | our base; their policy is our policy |
| `Yuvi9587/Kemono-Downloader` | releases, `src/core/workers.py`, `multipart_downloader.py`, `api_client.py` | the de-facto feature leader; MIT |
| `AlphaSlayer1964/kemono-dl` | login flow, hash verify | small, clean, current |
| `pawstash/pawstash` | `src-tauri/src/api/providers/pawchive.rs` | fastest to adopt new API fields |
| `rushiaismywaifu/pawchive-tools` | `pawchive_api_guide.md`, `pawchive_openapi.json` | the only written API truth |
| `freeforall1932-design/Kemono-Downloader` | — | **it is our own fork of Yuvi**; irrelevant as an upstream |
| live sites | `/api/v1/posts`, `/api/swagger_schema` | detect field drift before users do |

**Drift probe** — add `scripts/probe_sources.py` (pure `requests`, no Qt, safe to run in CI manually):

* for each domain in the list: `GET /api/v1/posts?o=0` → record HTTP status, whether the body is an array or an envelope, and **the union of keys** in `file`/`attachments`;
* `GET /api/v1/account/favorites` unauthenticated → expect 401;
* resolve one file from the response through `resolve_file_url` and `HEAD` it → status + `Accept-Ranges`;
* emit a small JSON diff vs the committed `docs/api_baseline.json`; CI fails on *new/removed* fields.

That is the cheapest possible early-warning system: the `temp_url` model would have been caught the day it shipped.

---

## 10. Licence & ethics guardrails

| Project | Licence | May we copy code? |
|---|---|---|
| `VoxDroid/KemonoDownloader`, `Yuvi9587/Kemono-Downloader` | MIT | **Yes** (keep attribution) |
| `mikf/gallery-dl` | GPL-2.0 | **No** — facts only |
| `pawstash/pawstash` | GPL-3.0 | **No** — facts only |
| `AlphaSlayer1964/kemono-dl`, `rushiaismywaifu/pawchive-tools` | none declared | **No** — facts only (no licence = all rights reserved) |
| our repo | MIT | — |

Also keep the upstream v5.13.0 policy as the floor: identifiable UA, ≤1 request/s to Pawchive, ≤5 concurrent Pawchive downloads, and honour `Retry-After`. Pawchive is a single-operator mirror on Cloudflare — the whole family's survival depends on not hammering it, and the favourites-tier caps mean aggressive retries are not just rude, they are pointless.

---

## 11. Open decisions

| # | Decision | Recommendation |
|---|---|---|
| L1 | Do we become effectively "Pawchive-first" in the UI (Kemono demoted to archive/thumbnail)? | **Yes** — matches reality as of 2026-10; keep Kemono fully functional, just not the default. |
| L2 | Auto-switch Kemono → Pawchive on 404/403, or prompt? | Prompt once per creator, remember the choice; silent rewriting hides what the app is doing. |
| L3 | Add `cum.st` now or when a user asks? | **Now** — it is a one-line registry entry once §7 exists, and Coomer is otherwise dead weight. |
| L4 | Are the P3 features still out of scope (`WORKLIST` §F)? | Re-confirm. Several (only-links export, text export) are cheap and Yuvi proves the demand. |
| L5 | Do we accept `Range`/multi-part complexity before or after the v5.14.0 merge? | **After** — merge + P0 first, ship a correct v5.14.0, then plumbing. |
