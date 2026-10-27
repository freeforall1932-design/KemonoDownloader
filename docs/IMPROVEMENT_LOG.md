# Improvement Log

> Chronological record of what was implemented and when, plus proposed
> improvements. Newest entries first. Companion docs:
> [`SESSION_HANDOFF.md`](./SESSION_HANDOFF.md), [`WORKLIST.md`](./WORKLIST.md).

---

## 2026-10-28 — v5.14.0: Pawchive file models, content-hash dedupe, sign-in

Committed on `arena/5a274714-kemonodownloader` on top of the upstream merge
(`98c474d`, base `463cf80`, parents fork HEAD `76869b6` + upstream
`3ebae3d` = v5.13.0). Verification: `compileall` on every touched module, 177
Qt-free tests pass (`test_pawchive`, `test_download_policy`,
`test_pawchive_files`, `test_language`); the Qt-backed suites cannot run in this
sandbox (no `libGL.so.1`).

### Why

Live API probes (2026-10-27/28) showed Pawchive attachments come in four shapes
and our code only handled one:

| shape | fields | what we did before |
| --- | --- | --- |
| classic | `node: 2` + `path` | worked |
| signed | `temp_url` + `temp_expires` | ignored, built a dead `file.` URL |
| `preview_only` | `path`, no full-res origin | fetched a 403/404 |
| `deferred` | **no `path`** | `KeyError`, aborted the post |

`preview_state: "pending"` posts (content not scraped yet) also got a full
one-request-per-second download attempt per file, all of which fail.

### Implemented

1. **`pawchive_files.py` (new, Qt-free)** — `resolve_file(post | attachment)`
   returns a `FileSource` with `kind` (`full` / `temp` / `thumbnail` /
   `unavailable`) and a machine-readable `reason`, applying the precedence
   *usable signed URL → `preview_only` → `has_full is False` → classic*.
   Plus `resolve_thumbnail`, `sha256_from_path`, `compute_digests` (one read,
   md5 + sha256), `verify_content_sha256`, `expected_sha256_for_url`,
   `temp_url_is_usable`, `size_cap_bytes`, `human_size`, `is_pending_post`,
   `is_scraped_post`.
2. **Both `detect_files()` rewritten** to consume the resolver, log one clear
   notice per pending/deferred post instead of per-file noise, and skip files
   whose content digest is already in `hash_db` before touching the network.
3. **`hash_db.py`** — nullable `content_sha256` column, in-place migration for
   existing databases, index, sha256-aware lookups; `store()` accepts the
   digest. Both downloaders compute md5+sha256 once and log
   `content_hash_mismatch` when the API's path digest differs from the bytes.
4. **Thumbnail fallbacks** now use the identifiable user agent and the
   Pawchive download limiter, and always release their slot (`finally`);
   the Creator fallback previously leaked a slot when the thumbnail 404'd.
5. **`download_policy.py` rewritten** — dynamic `[host.]pawchive.<suffix>`
   matching (the hardcoded `pawchive.pw` check disabled pacing as soon as the
   domain rotated), `Retry-After` parsing (seconds + HTTP-date, 300 s ceiling),
   metadata pacing, 5-slot limiter, and one deferred-request scheduler so a
   `429` slows both downloads and metadata calls.
6. **`pawchive.py`** — paced/retrying `_request_json`, `?type=artist`
   favourites, envelope-tolerant `extract_posts`, `login_with_password` +
   `extract_session_cookie` + `verify_session` (form login is the only option:
   there is no key API and `/api/v1/account/login` 404s), and
   `PawchiveLoginError`.
7. **Sign-in UI** in the favourites group: username/password inputs, a worker
   thread, cookie written into the (reworded) session-cookie field, and a
   dedicated "already signing in" warning instead of borrowing the
   favourites-fetch one.
8. **Version single-sourcing** — `kemonodownloader.__version__` feeds
   `app.CURRENT_VERSION` and the user agent, so they cannot drift.
9. **Tests** — `tests/test_pawchive_files.py` (39 cases),
   `tests/test_download_policy.py` (38 cases), and login/session/`401`
   coverage appended to `tests/test_pawchive.py`.

### Decisions kept for the record

- **Pawchive only.** No `kemono.cr` / `coomer.st` / `cum.st` support and no
  cross-site mirroring; `UPSTREAM_LANDSCAPE.md` §11 L1/L3 are marked rejected.
- **The resolver is the single source of truth.** `detect_files()` in both
  downloaders now shows the same behaviour; a future shape only needs a new
  branch in `pawchive_files`, not two edits in two 4000-line modules.
- **Warn, never re-download, on digest mismatch.** The file is already on disk
  under a content-addressed name; re-fetching would burn the 1 rps budget for
  bytes we cannot change.
- **Over-matching a rotated suffix is deliberate.** `pawchive.<unknown>` is
  treated as Pawchive even if it might be a lookalike, because the cost of
  pacing an unrelated host (one second) is smaller than hammering the next
  Pawchive domain unpaced.

### Still open

- `docs/DEPLOYMENT_REVIEW.md` and `docs/UPSTREAM_RECONCILIATION.md` still
  describe v5.13.0 as the fork's cut; they are historical snapshots, kept as-is.
- Qt-backed tests (`test_creator_downloader*`, `test_post_downloader*`, …) are
  unverified in this sandbox; CI needs to run them.
- Favourites pagination beyond the first page, and the "moxxy" successor site
  rumour, remain unverified (see `WORKLIST.md`).

---

## 2026-09-03 — Five-feature implementation (branch `arena/01a0651a-kemonodownloader`)

All changes below are **implemented in working tree**, verified via
`compileall`, pure-Python pytest (37 new + 63 existing pass), and a PyQt6 stub
harness. **Not yet committed / PR'd / merged.**

### Implemented

1. **Failed full-res retry → back of queue → thumbnail fallback (feature 1)**
   - `domain_config.py`: new `to_thumbnail_url(raw_path_or_url, domain_config)`
     mirroring `kd_thumbnaildl.make_thumbnail_url` (data → `img.<domain>/thumbnail/data/…`).
   - `creator_downloader.py` & `post_downloader.py` `detect_files`:
     `use_thumbnail = post.get("has_full") is False` → main file + attachments
     build thumbnail URLs (log `has_full_false_thumbnail`), avoiding guaranteed 404s.
   - `CreatorDownloadThread`: `_is_full_res_url`, `_handle_full_res_failure`
     (404/network → one `_queue.put_nowait((file_index, file_url))` requeue; second
     failure → `_download_thumbnail_fallback`; degraded file stored under the
     **original** URL's md5 so later runs skip it), `_requeued_files` guard.
   - `post_downloader.DownloadThread`: same helpers; `_retry_pending` + a second
     pass in `run()` that re-dispatches failed full-res files exactly once.

2. **Favorites-only batch + Sync (feature 2)**
   - `pawchive.py` (new, no Qt): `get_pawchive_domain`, `build_creator_url`,
     `auth_cookie_header` (`Cookie: session=<key>`), `fetch_favorites`,
     `fetch_recent_posts_creators`, `fetch_old_site_favorites`, JSON parsers.
   - `hash_db.py`: new `processed_posts` + `processed_creators` tables and
     `mark_post_processed/is_post_processed/mark_creator_processed/
     is_creator_processed/get_processed_creators`.
   - `creator_downloader.py`: Pawchive Favorites & Import UI group (API key,
     Fetch Favorites & Queue, Sync), `FavoritesFetchThread`, handlers.

3. **Recent-posts feed (feature 3)** — "Monitor recent posts feed" checkbox,
   OFF by default, only honored when the user enables it; separate from the
   favorites flow.

4. **Favorites JSON import (feature 4)** — paste area + file picker, no account
   required; tolerant parsing (flat list / `artists` / `creators` / `data` /
   `results`; `id`/`user`/`creator_id`/`artist_id` aliases).

5. **Crawl favorites from old site (feature 5)** — domain + credential fields,
   `GET https://{old_domain}/api/v1/account/favorites?type=artist&o={offset}`
   pagination (`?o=` offsets, page size 50, `max_pages=1000`), same import queue.

Supporting: `kd_settings.py` (`pawchive_api_key`, `monitor_recent_posts_feed`
default `False`, load/save + getters/setters), `kd_language.py` (37 new keys),
`tests/test_domain_config.py`, `tests/test_pawchive.py`,
`tests/test_hash_db_processed.py`.

### Proposed improvements (not yet done)

- **Deduplicate the two thumbnail builders** — `to_thumbnail_url` (domain_config)
  and `make_thumbnail_url` (kd_thumbnaildl) are identical logic; consolidate to
  one, or have kd_thumbnaildl delegate to domain_config.
- **Localize log-only strings** — new log keys are english-only; add ja/ko/zh for
  consistency with the rest of the codebase (UI strings already localized).
- **Bump CHANGELOG + version** — add a `v5.13.0`-style entry for the five
  features once committed.
- **`pawchive.py` tests for network calls** — currently only parsing/auth helpers
  are unit-tested; add `responses`/mock-based tests for `fetch_favorites`,
  `fetch_recent_posts_creators`, `fetch_old_site_favorites` (pagination loop,
  stop conditions).
- **Recent-feed "monitor"** — currently a one-shot `?o=0` fetch when enabled;
  consider a timer/poll loop if a true "monitor" is desired (see WORKLIST).
- **Post downloader retry join deadline** — the 30s `is_alive()` polling deadline
  in `run()` could return while a retry thread is still alive; consider raising
  it or joining properly (see WORKLIST review item).

---

## Prior work (upstream baseline, not authored this session)

- v5.12.0 (01 Aug 2026): Thumbnail Downloader tab, auto-rename, post-text.
- v5.11.1 (05 Jul 2026): dynamic pawchive domain suffix resolution.
- v5.11.0: pawchive / dynamic domains.
- See `CHANGELOG` for full history.
