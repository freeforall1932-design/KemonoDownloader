# Session Handoff — KemonoDownloader

> Purpose: bring a fresh agent/model up to speed **before** creating the PR and
> merge commit for the five-feature work done on branch
> `arena/01a0651a-kemonodownloader`.
>
> Last updated: **2026-09-03** (Asia/Jakarta). Companion docs:
> [`IMPROVEMENT_LOG.md`](./IMPROVEMENT_LOG.md) and [`WORKLIST.md`](./WORKLIST.md).

---

## 1. Repo / branch facts

| Item | Value |
|---|---|
| Working dir | `/home/user/KemonoDownloader` |
| Remote `origin` | `https://github.com/freeforall1932-design/KemonoDownloader.git` (a fork of `VoxDroid/KemonoDownloader`) |
| Branch (**fixed for this session**) | `arena/01a0651a-kemonodownloader` |
| Base commit | `3e2e954` "Add files via upload" (shallow clone, single commit) |
| Push target | `git push origin arena/01a0651a-kemonodownloader` only. Never push/create other branches. |
| PR flow | Use `gh` (auth already configured). Open PR from this branch, then create the merge commit. |

The five features implemented (see §4) are **not yet committed** — everything is
staged as uncommitted working-tree changes plus untracked files.

## 2. Environment facts (recheck each session — `/tmp` does not persist)

- Python: **3.11.2**.
- A venv at `/tmp/venv` was created with
  `requests beautifulsoup4 pytest fake-useragent PyQt6 qtawesome packaging`.
  `/tmp` is **not persisted** across sessions — recreate it with:
  ```bash
  /tmp/venv/bin/pip install requests beautifulsoup4 pytest fake-useragent PyQt6 qtawesome packaging
  ```
- System `pip3 install` fails (PEP 668 externally-managed env). Always use a venv.
- **Qt cannot be imported** in this sandbox: `ImportError: libGL.so.1: cannot open
  shared object file`. `apt` cannot install it (permission denied, stale lists,
  `deb.debian.org` unreachable). **Therefore `pytest` on any Qt test cannot run
  here.** Pure-Python tests (`pawchive`, `domain_config`, `hash_db`, `language`)
  run fine.
- Network: direct `curl`/`requests` to `pawchive.pw` fails (SSL syscall error).
  The `fetch_page` tool **works** (platform proxy) — use it to inspect live APIs.
- Git identity/credential are preconfigured for `git`/`gh` — never ask for tokens.

## 3. Verified commands (run these in order before PR)

```bash
cd /home/user/KemonoDownloader

# 1. Syntax check (no Qt import needed)
/tmp/venv/bin/python -m compileall -q src/kemonodownloader

# 2. Pure-Python tests (all must pass; Qt tests are blocked here)
/tmp/venv/bin/python -m pytest \
  tests/test_domain_config.py tests/test_pawchive.py \
  tests/test_hash_db_processed.py tests/test_hash_db.py tests/test_language.py -q

# 3. Translation-key sanity (all 37 new keys must resolve, incl. ja/ko/zh for UI)
/tmp/venv/bin/python - <<'PY'
import sys; sys.path.insert(0, "src")
from kemonodownloader.kd_language import translate, language_manager
keys = ["pawchive_fav_group","pawchive_api_key_placeholder","fetch_favorites_btn",
 "sync_favorites_btn","monitor_recent_feed","favorites_json_placeholder",
 "import_favorites_json_btn","queue_pasted_json_btn","old_site_domain_placeholder",
 "old_site_cred_placeholder","crawl_old_site_btn","select_favorites_json",
 "favorites_no_api_key","favorites_fetching","favorites_syncing",
 "favorites_fetch_in_progress","favorites_fetch_failed","favorites_queued_count",
 "favorites_skipped_count","favorites_sync_done","recent_feed_fetched",
 "json_import_parsed","json_import_invalid","json_import_empty","old_site_no_domain",
 "old_site_no_cred","old_site_crawling","old_site_crawled","old_site_crawl_failed",
 "old_site_crawl_in_progress","post_already_processed","has_full_false_thumbnail",
 "file_404_requeue","file_network_requeue","thumbnail_fallback",
 "thumbnail_fallback_ok","thumbnail_fallback_failed","requeueing_downloads"]
missing = [k for k in keys if k not in language_manager.translations]
assert not missing, missing
language_manager.set_language("japanese")
assert translate("pawchive_fav_group") == "Pawchive お気に入りとインポート"
print("translation keys OK")
PY

# 4. git status (expected changed/untracked files)
git status --short
```

Expected `git status` after this session:
```
 M src/kemonodownloader/creator_downloader.py
 M src/kemonodownloader/domain_config.py
 M src/kemonodownloader/hash_db.py
 M src/kemonodownloader/kd_language.py
 M src/kemonodownloader/kd_settings.py
 M src/kemonodownloader/post_downloader.py
?? src/kemonodownloader/pawchive.py
?? tests/test_domain_config.py
?? tests/test_hash_db_processed.py
?? tests/test_pawchive.py
?? docs/            (these three handoff docs)
```

### Qt behavior was verified via a stub (no display)

Because Qt won't import, the Qt-dependent behavior (tab construction, favorites
JSON/old-site handlers, `has_full` detection, full-res requeue/fallback, settings
prefill/persist) was exercised through a **PyQt6 stub harness**. The stub lived at
`/tmp/qt_stub.py` (not persisted — see note below if you need to rebuild it) and
all assertions passed. Do **not** trust that stub as a replacement for real Qt
tests; it only proves the logic paths don't crash and branch correctly.

If you need it again, the stub approach is: fake `PyQt6.QtCore/QtGui/QtWidgets`
modules with (a) a `pyqtSignal()`-returning helper, (b) `QThread` with class-level
`finished/started/destroyed = Signal()`, (c) stateful `QLineEdit/QCheckBox/QTextEdit`,
(d) a permissive `__getattr__` returning a callable stub on all widgets/layouts,
(e) a `QSettings` fake, then `from kemonodownloader import creator_downloader` and
drive `CreatorDownloaderTab(FakeParent())`.

## 4. What was implemented (the five features + supporting changes)

1. **Full-res retry → back of queue, then thumbnail fallback.**
   `_is_full_res_url()`, `_handle_full_res_failure()`, and thumbnail fallback exist
   in **both** `creator_downloader.py` (`CreatorDownloadThread`, async queue) and
   `post_downloader.py` (`DownloadThread`, `_retry_pending` second pass in `run()`).
   `has_full is False` → `detect_files` builds thumbnail URLs directly.
2. **Favorites-only batch + Sync** (NOT `/creators`). `pawchive.py` +
   `hash_db.py` processed-posts/creators tables + UI (API key, Fetch, Sync).
3. **Recent-posts feed** (`GET /posts`), OFF by default, opt-in checkbox only.
4. **Favorites JSON import** (paste or file), no account required.
5. **Crawl favorites from old site** (`/api/v1/account/favorites?type=artist&o=`),
   domain + credential fields.

Plus: `kd_settings.py` persistence (`pawchive_api_key`,
`monitor_recent_posts_feed`), `kd_language.py` translation keys,
`domain_config.py to_thumbnail_url()`, new tests.

## 5. Sources (where facts came from)

| Fact | Source |
|---|---|
| Pawchive auth = `Cookie: session=<token>`; `/api/v1/posts?o={page*50}`; `CreatorModel` fields `id/name/service/favorited`; `PostModel` has `has_full` & `preview_state`; data host `file.pawchive.pw` | `NiTiSon/Pawchive` source via `gh api` |
| Old-site favorites JSON export shape (flat list or `{"artists":[…]}`; items have `service` + `id`) | `LeoIsamaru/Pawchive-Favorites-Importer-from-kemono` via `gh api` |
| Live `/api/v1/posts` JSON shape — **confirmed 2026-09-03** via `fetch_page`: post = `{id, user, service, title, substring, published, file{name,path}, attachments[{name,path}], preview_state, has_full, origin}`. Confirms `has_full` field **and** `user` = creator id (used by `fetch_recent_posts_creators`). | `https://pawchive.pw/api/v1/posts?o=0` |
| Anonymous `/api/v1/account/favorites` returns `{}` (auth required) | `https://pawchive.pw/api/v1/account/favorites` (fetched) |
| `/api/schema.json` & `swagger-initializer.js` → 404; only `/api/schema` HTML page is a reference | pawchive (fetched) |
| Icon names `fa5s.download/sync/file-import/layer-group/search/plus` all exist | `/tmp/venv/.../qtawesome/fonts/fontawesome5-solid-webfont-charmap-5.15.4.json` (grep-verified) |
| Existing thumbnail URL layout (`img.<domain>/thumbnail/data/…`) | `src/kemonodownloader/kd_thumbnaildl.py make_thumbnail_url` (identical logic to new `to_thumbnail_url`) |
| Existing downloader conventions (`get_session(self.settings.settings_tab)`, `_safe_emit`, `_ssl_lock`, `translate(key,*args).format`) | `creator_downloader.py`, `post_downloader.py` |

## 6. Key implementation facts to remember

- `creator_queue` is a list of `(url, checked)` tuples; append then
  `update_creator_queue_list()`.
- `_queue_artists(entries, skip_processed)` builds URLs via
  `pawchive.build_creator_url(service, id)`; `skip_processed=True` uses
  `hash_db.get_processed_creators()` (Sync path).
- `FilePreparationThread.__init__` accepts `hash_db=None`; the tab now passes
  `hash_db=self.hash_db` at construction (line ~4155).
- `CreatorDownloaderTab.__init__` lazily builds `self.hash_db` from
  `other_files_dir`; worker state `favorites_fetch_thread`/`old_site_thread`
  start as `None`.
- `FavoritesFetchThread` / `OldSiteFavoritesThread` live before
  `CancellationThread`; handlers manage them via `active_threads`.
- `translate(key, *args)` formats via `.format(*args)`; log-only keys have an
  **english-only** entry (they fall back to English in ja/ko/zh — verified).
- Post downloader `_retry_lock/_retried_files/_retry_pending` were added in
  `DownloadThread.__init__`; second pass lives inside `run()` after the first
  join loop.

## 7. What to do / what to check next (before PR)

See [`WORKLIST.md`](./WORKLIST.md) for the full checklist. Minimum bar:

1. Re-run the §3 commands; fix any failure.
2. Read the **Review & bug-hunt** section of WORKLIST (always do this every
   session) and file/comment any findings.
3. Decide on the flagged "implemented but unsure" items (esp. favorites auth,
   old-site pagination, "retry strictly after everything else" semantics).
4. Commit the work on `arena/01a0651a-kemonodownloader`, push, open the PR
   (`gh pr create`), then create the merge commit once review passes.
