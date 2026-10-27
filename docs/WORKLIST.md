# Work List — KemonoDownloader

> Tracks unfinished work, the **default per-session review/bug-hunt**, optional
> features, and "implemented but unsure" items. Companion docs:
> [`SESSION_HANDOFF.md`](./SESSION_HANDOFF.md), [`IMPROVEMENT_LOG.md`](./IMPROVEMENT_LOG.md).
>
> Last updated: **2026-10-28** (v5.14.0 Pawchive-only cut).

---

## A. Immediate next steps (blockers for PR)

- [x] Re-run the verification commands in `SESSION_HANDOFF.md` §3 (Qt-free part).
- [ ] Run the **Qt-backed** suites somewhere with `libGL.so.1` (CI or a desktop
      dev box). The new sign-in widgets, the resolver-driven `detect_files()`,
      and the slot-safe thumbnail fallback are all exercised only by
      `compileall` in this sandbox.
- [ ] Confirm the sign-in flow against a real Pawchive account (needs a human):
      `login_with_password` posts to `/account/login` and reads the `session`
      cookie. If the site adds a captcha, the flow needs a friendly error.
- [ ] Open the PR from `arena/5a274714-kemonodownloader` (push only that branch).

---

## B. Default review & bug-hunt (do this EVERY session)

Mandatory pass over the code written in previous sessions — look for missing
logic, misaligned code, and breakage from earlier edits:

- [ ] `compileall` clean (`/tmp/venv/bin/python -m compileall -q src/kemonodownloader`).
- [ ] Pure-Python pytest green (Qt tests are blocked in-sandbox; see handoff).
- [ ] **Feature 1 — retry semantics**: confirm `_handle_full_res_failure` returns
      `True` only for full-res 404/network errors; 500s and thumbnails still use
      the normal retry path (verified via stub, re-check after any edit).
      Confirm the creator downloader requeues onto the *same* live queue and the
      `_requeued_files` guard prevents a third full-res attempt.
- [x] **Post downloader second pass**: `WORKER_JOIN_TIMEOUT_SECONDS` raised
      from 30s to 180s in both downloaders (daemon threads + `_destroyed` guard
      remain). Re-check in real Qt that retries still finish inside the window.
- [ ] **`has_full` tri-state**: `has_full is False` → thumbnail; `True`/missing →
      full-res. Confirm this matches intent for posts where the field is absent
      (older responses). Flag if missing-field should also default to thumbnail.
- [ ] **`fetch_recent_posts_creators`** uses `post["user"]` as creator id and
      only reads `?o=0` (first page). Confirmed `user` exists in live API; confirm
      single-page is the intended "recent feed" scope.
- [ ] **Favorites sync vs fetch flags**: Sync must skip processed+queued; Fetch
      must queue all (only dedup within queue). Confirmed via stub; re-check if
      `_queue_artists` changes.
- [ ] **Settings persistence**: `_load_fav_settings()` is called once at
      `setup_ui`; confirm a settings-change (`settings_applied`) still leaves the
      Creator-tab API key field consistent (the key is edited in the Creator tab,
      not Settings; there is no Settings UI field for it).
- [x] **Translation completeness**: Favorites / thumbnail-fallback log keys now
      have ja/ko/zh. Older log-only keys remain english-only (fallback works).
- [ ] **Signal wiring**: `FavoritesFetchThread`/`OldSiteFavoritesThread` connect
      `result`/`log`/`error`/`finished`; `finished` is auto-emitted by QThread.
      `_cleanup_*` uses `deleteLater()` and removes from `active_threads` — no
      double-free.
- [ ] **Icon names** (`fa5s.*`) exist in qtawesome 5.15.4 (verified) — recheck if
      new buttons are added.
- [ ] **No accidental breakage of existing features** — diff-review the touched
      hot paths: `detect_files` (both downloaders), `download_file` (both),
      `DownloadThread.run`, `CreatorDownloadThread.run`, `HashDB._init_db`
      (migration must not fail on pre-existing DBs).

---

## C. Unfinished work (known gaps)

- [ ] **Qt tests can't run in-sandbox** (`libGL.so.1` missing). The full Qt suite
      (`tests/test_creator_*.py`, `tests/test_post_downloader*.py`,
      `tests/test_kd_settings*.py`, etc.) has NOT been run against these changes.
      Must be run in a Qt-capable environment (CI / local dev) before merge.
- [x] **Network tests** for `pawchive.fetch_*` (mock-based) added in
      `tests/test_pawchive.py`.
- [x] **CHANGELOG / version bump** — v5.13.0 (2026-09-09).
- [x] **Favorites / thumbnail-fallback log strings** localized (ja/ko/zh).
      Remaining older log-only keys still english-only.
- [x] **Docs** for this cut: `CHANGELOG`, README/Help/i18n six-tab copy,
      `docs/DEPLOYMENT_REVIEW.md`.
- [x] **v5.14.0 Pawchive P0 work** (2026-10-28): `pawchive_files` resolver,
      content-hash dedupe (`hash_db.content_sha256`), sign-in, dynamic Pawchive
      host matching + `Retry-After`, single-read md5+sha256. See
      `docs/IMPROVEMENT_LOG.md` (2026-10-28 entry).
- [ ] **Favourites pagination** — `fetch_favorites` reads one page. If a user has
      hundreds of favourites, later pages are silently missing. Needs the same
      `o=` loop the old-site crawl uses.
- [ ] **`docs/DEPLOYMENT_REVIEW.md` / `UPSTREAM_RECONCILIATION.md`** still
      describe v5.13.0 as the current cut. Kept as historical snapshots; refresh
      only if the PR needs them current.
- [ ] **`Temp`/`deferred` retry** — deferred attachments are kept in the queue
      with an "not imported yet" notice but are never re-tried in-session. A
      "re-check deferred files" action would close that loop.

---

## D. "Implemented but unsure" (verify against real systems)

- [x] **Pawchive favorites auth shape** — anonymous `GET
      /api/v1/account/favorites` answers `401 {}`; with a session cookie it
      answers the artist list. `parse_artist_entries` tolerates both. The
      **login form** itself is still unverified against a real account (§A).
- [ ] **`?type=artist` vs default** — Pawchive accepts `type=artist` (verified
      shape-wise from `pawchive-tools`); confirm it does not change paging.
- [ ] **Old-site crawl** — `?type=artist&o={offset}` + page size 50 assumed from
      Kemono API conventions; **not verified against a live old site**. Confirm
      the credential format (full `connect.sid=` cookie vs bare key) and the
      actual page size/stop condition.
- [ ] **"Retry once after everything else finishes"** — the creator downloader
      requeues to the back of the *live* queue, so with concurrent workers the
      retry can start while other files are still streaming (not strictly "after
      everything"). The post downloader's second pass *is* strictly after the
      first pass. Decide if strict ordering matters and, if so, how to enforce it.
- [ ] **`has_full` in `post_downloader`** — ported the `use_thumbnail` logic
      symmetrically with the creator downloader, but `post_downloader`'s
      `FilePreparationThread`/`DownloadThread` were not exercised with the stub as
      deeply as the creator path. Re-verify in real Qt.
- [ ] **Degraded thumbnail stored under original URL hash** — intentional (so a
      known-degraded file is not re-tried), but confirm this doesn't cause a
      *full-res* re-attempt to be silently skipped later if the file becomes
      available again.

---

## E. Optional features / ideas (out of scope now, do NOT start without approval)

- Timer/poll loop for a true "recent posts feed monitor" (currently one-shot).
- Paginate the recent feed beyond `?o=0` when monitoring.
- Progress indicator on favorites/old-site fetch threads (they currently only
  emit `result`/`error`/`log`).
- Favorite/import history and dry-run preview (show what would be queued first).
- Test button ("validate API key") for the Pawchive API key field.
- Consolidate `to_thumbnail_url` / `make_thumbnail_url` (see IMPROVEMENT_LOG).

## F. Out of scope (confirmed by user — do NOT implement)

Revisions, comments, tags, announcements, fancards, `search_hash`, `app_version`,
flagging, and site-wide batch via `/creators`.

**Pawchive is the only supported site** (ruled 2026-10-28). Not to be added,
even on request: `kemono.cr` / `coomer.st` support, `cum.st` (that is OnlyHaven,
a different project), any multi-site registry, and any cross-site
"Kemono → Pawchive" switching or mirroring. Kemono-family payload shapes
(`node`, `path`, `{count, posts}`) stay supported only because Pawchive's own API
uses them.
