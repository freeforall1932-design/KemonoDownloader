# Work List — KemonoDownloader

> Tracks unfinished work, the **default per-session review/bug-hunt**, optional
> features, and "implemented but unsure" items. Companion docs:
> [`SESSION_HANDOFF.md`](./SESSION_HANDOFF.md), [`IMPROVEMENT_LOG.md`](./IMPROVEMENT_LOG.md).
>
> Last updated: **2026-09-09**.

---

## A. Immediate next steps (blockers for PR)

- [ ] Re-run the verification commands in `SESSION_HANDOFF.md` §3.
- [ ] Resolve/record the "implemented but unsure" items in §D.
- [ ] Commit on `arena/01a0651a-kemonodownloader`, push, `gh pr create`, review,
      then create the merge commit.

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

---

## D. "Implemented but unsure" (verify against real systems)

- [ ] **Pawchive favorites auth** — `Cookie: session=<key>` is taken from the
      `NiTiSon/Pawchive` client, but was **not verified against live Pawchive with
      a real key** (sandbox egress blocked; anonymous call returns `{}`). Verify
      with a real key that `GET /api/v1/account/favorites` returns the artist
      list (shape: list or `{...}`? `parse_artist_entries` tolerates several).
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
