# Improvement Log

> Chronological record of what was implemented and when, plus proposed
> improvements. Newest entries first. Companion docs:
> [`SESSION_HANDOFF.md`](./SESSION_HANDOFF.md), [`WORKLIST.md`](./WORKLIST.md).

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
