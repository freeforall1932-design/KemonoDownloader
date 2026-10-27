# Upstream reconciliation — our v5.13.0 vs upstream v5.13.0

> Written **2026-10-27**. Companion docs: [`SESSION_HANDOFF.md`](./SESSION_HANDOFF.md),
> [`WORKLIST.md`](./WORKLIST.md), [`IMPROVEMENT_LOG.md`](./IMPROVEMENT_LOG.md),
> [`DEPLOYMENT_REVIEW.md`](./DEPLOYMENT_REVIEW.md).
>
> Scope: how to reconcile the five-feature work in this fork (labelled v5.13.0)
> with the **original project's own v5.13.0**, released upstream on 2026-09-27.
> Sibling-project comparison and the live API drift found on 2026-10-28 are in
> [`UPSTREAM_LANDSCAPE.md`](./UPSTREAM_LANDSCAPE.md) — read both before merging;
> the merge plan below still stands, but §6.3 (`is_pawchive_url`) is now a **live**
> bug, not a theoretical one (Pawchive already rotated `.st` → `.pw`), and
> `cum.st` should join the domain list.

---

## 1. TL;DR

| Question | Answer |
|---|---|
| Did upstream release a v5.13.0 too? | **Yes.** `VoxDroid/KemonoDownloader` v5.13.0 (2026-09-27) = Pawchive rate limiting + 403 resilience. Our fork's v5.13.0 (2026-09-09) = favorites/sync/import, recent feed, old-site crawl, full-res retry → thumbnail fallback. **Two different releases share one version number.** |
| Does the code collide? | **Almost not at all, textually.** A real 3-way merge of our tree onto upstream `main` (`3ebae3d`) conflicts in **`CHANGELOG` only**. All of `creator_downloader.py`, `post_downloader.py`, `kd_settings.py`, `kd_language.py`, `README.md`, `pyproject.toml` auto-merge; the merged tree compiles and all 511 translation keys resolve in all four languages. |
| Does it collide **semantically**? | **Yes, in 5 places.** Upstream introduced a *policy* (`download_policy.py`: identifiable UA, 1 req/s pacing, max 5 concurrent) that our new network paths bypass, and our `pawchive.py` literally impersonates Chrome — the exact behaviour upstream removed. `is_pawchive_url()` also hardcodes `pawchive.pw` and so defeats the dynamic-domain support this fork depends on. |
| Recommended reconciliation | **Adopt upstream v5.13.0 as the new base and renumber our work to v5.14.0.** One merge commit (unrelated histories, `CHANGELOG` resolved by hand), then the 5 semantic fixes in §6. |
| Effort | ~1 session: merge + version bump + 5 small code integrations + 1 new test file (`tests/test_download_policy.py`, which upstream shipped without). |

Do **not** ship our work as "v5.13.0": it would be a second, different v5.13.0,
break `SECURITY.md` version tracking, make issue reports ambiguous, and collide
on the badge/CHANGELOG/`CURRENT_VERSION` surface.

---

## 2. Facts established this session

### 2.1 The two releases

| | Upstream | This fork |
|---|---|---|
| Version | **5.13.0** | **5.13.0** (collision) |
| Date | 2026-09-27 | 2026-09-09 |
| Base | `v5.12.0` (`463cf80`) | identical: `463cf80` (verified byte-for-byte except our edits) |
| Commits | `1f86596` (policy) + `3ebae3d` (release/format) | committed in merge commit `76869b6`; described in `SESSION_HANDOFF.md` §4 |
| Content | Pawchive identifiable UA, ≤1 new file request/s, ≤5 concurrent Pawchive downloads, Settings info button, README ethical-use copy | Favorites fetch/sync, JSON import, recent-feed opt-in, old-site crawl, `has_full` → thumbnail, full-res retry → back-of-queue → thumbnail fallback, packaged domain list, six-tab docs |
| Files touched | `download_policy.py` (new), `creator_downloader.py`, `post_downloader.py`, `kd_settings.py`, `kd_language.py`, `app.py`, `pyproject.toml`, `README.md`, `CHANGELOG` | `pawchive.py` (new), `creator_downloader.py`, `post_downloader.py`, `hash_db.py`, `domain_config.py`, `kd_settings.py`, `kd_language.py`, `kd_help.py`, `app.py`, `pyproject.toml`, READMEs, `index.html`, `assets/js/i18n.js`, browser-extension manifests, `requirements.txt`, docs, 3 test files |

Both releases are *additive*, but both rewrite the same hot function body
(`CreatorDownloadThread.download_file` / `DownloadThread.download_file`) and
both extend the same settings/language tables — that is why the semantic
integration, not the git merge, is the work.

### 2.2 Why our repo has no common ancestor

This fork's git history is a single imported snapshot ("Add files via upload"),
so `git merge upstream/main` needs `--allow-unrelated-histories`. Our tree
matches upstream `463cf80` (`v5.12.0`) plus our edits — verified by diffing
against a `463cf80` worktree; every differing path is one we intentionally
touched. In practice this means the reconciliation doubles as **the moment the
fork acquires real upstream lineage**, after which future syncs are ordinary
3-way merges.

### 2.3 Merge rehearsal (already run, throws away nothing)

Method: scratch clone + upstream `463cf80` as base commit + our tree committed on
top + `git merge up/main`.

```
Auto-merging CHANGELOG
CONFLICT (content): Merge conflict in CHANGELOG
Auto-merging README.md
Auto-merging pyproject.toml
Auto-merging src/kemonodownloader/creator_downloader.py
Auto-merging src/kemonodownloader/kd_language.py
Auto-merging src/kemonodownloader/kd_settings.py
Auto-merging src/kemonodownloader/post_downloader.py
```

Post-merge checks on the rehearsal tree:

* `python -m compileall -q src/kemonodownloader` → clean.
* Translation table: **511 keys, no duplicate key names**, all of our new keys and
  upstream's `pawchive_policy_info_title` / `pawchive_policy_info_text` present
  in `english`/`japanese`/`korean`/`chinese-simplified`.
* Settings: upstream's `pawchive_policy_info_button` (created ~line 294,
  tooltip set in `retranslate` ~line 1321) and our
  `pawchive_api_key` / `monitor_recent_posts_feed` defaults + getters/setters
  (~line 57 / 1468) coexist with no duplicate `QSettings` keys.
* `README.md` keeps both contributions (upstream's resource-limit bullet **and**
  our Pawchive Favorites workflow section).
* `WORKER_JOIN_TIMEOUT_SECONDS = 180` (ours) survives; upstream never changed it.
* `requirements.txt`: no new dependency from upstream (only `threading`/`time`).

---

## 3. What upstream added (must be preserved verbatim)

New module `src/kemonodownloader/download_policy.py`:

| Symbol | Behaviour |
|---|---|
| `IDENTIFIABLE_USER_AGENT = "KemonoDownloader/5.13.0 (+mailto:izeno.contact@gmail.com)"` | honest UA instead of Chrome impersonation |
| `PAWCHIVE_MAX_ACTIVE_DOWNLOADS = 5` | global cap across **both** downloaders |
| `PAWCHIVE_REQUEST_INTERVAL = 1.0` | ≥1s between *request starts* (retries included) |
| `is_pawchive_url(url)` | `pawchive.pw` or `*.pawchive.pw` — **hardcoded** |
| `get_request_headers(headers, url)` | swaps in the identifiable UA for Pawchive |
| `_PawchiveDownloadLimiter.acquire(is_running)` / `.release()` | lock + `time.monotonic()` pacing, cancellation-aware (returns `False` when `is_running()` goes false) |
| `acquire_pawchive_download(url, is_running)` / `release_pawchive_download(url)` | no-ops for non-Pawchive URLs |

Wiring: `CreatorDownloadThread.download_file` acquires **before** `_ssl_lock`
and releases in `finally`; `DownloadThread.download_file` uses
`request_slot_acquired` + release in the outer `finally`. Settings gets an info
button (`show_pawchive_policy_info`). README gains a resource-limits bullet.

---

## 4. What we added (must be preserved)

From `SESSION_HANDOFF.md` §4, with line numbers **in the rehearsal merge tree**:

| Feature | Where |
|---|---|
| 1. `has_full is False` → thumbnail URL in `detect_files` | `creator_downloader.py` ~962, `post_downloader.py` ~948 |
| 1. Full-res 404/network → requeue once → thumbnail fallback | creator `_handle_full_res_failure` 2082 / `_download_thumbnail_fallback` 2150; post `_handle_full_res_failure` 1804 / `_download_thumbnail_sync` 1859, second pass in `run()` ~2036 |
| 2. Pawchive favorites + sync | `pawchive.py`, `hash_db.py` (`processed_posts`/`processed_creators`), Creator tab group + `FavoritesFetchThread` |
| 3. Recent-posts feed (opt-in, OFF) | `pawchive.fetch_recent_posts_creators`, `CreatorDownloaderTab` checkbox |
| 4. Favorites JSON import | `pawchive.parse_favorites_json_text`, paste box + file picker |
| 5. Old-site favorites crawl | `pawchive.fetch_old_site_favorites`, domain + credential fields |
| Supporting | `domain_config.to_thumbnail_url`, packaged `resources/config/domain`, six-tab docs, `WORKER_JOIN_TIMEOUT_SECONDS = 180`, 37 language keys, 3 test files |

---

## 5. Conflict register

### 5.1 Textual (git)

| File | Conflict | Resolution |
|---|---|---|
| `CHANGELOG` | two `## v5.13.0` sections at the same offset | keep upstream's entry as `v5.13.0`; move ours to a new `v5.14.0` section on top (exact text in §7) |
| everything else | none | accept auto-merge |

### 5.2 Version surface (must be renumbered)

Collisions that auto-merge *silently* because both sides say `5.13.0`:
`pyproject.toml:4`, `app.py:36 CURRENT_VERSION`, `README.md:43` badge,
`SECURITY.md:5,9,10`, `CHANGELOG:3`, `docs/DEPLOYMENT_REVIEW.md` (§1, §2),
`tests/test_language.py:273` (docstring), plus our new
`download_policy.IDENTIFIABLE_USER_AGENT` which embeds `KemonoDownloader/5.13.0`
— after the bump it would advertise the *wrong* version to Pawchive.

### 5.3 Semantic (the actual work)

| # | Severity | Finding | Why it matters | Fix |
|---|---|---|---|---|
| **S1** | blocker | Our `pawchive.py` sets `DEFAULT_USER_AGENT` to a Chrome string (line 27, used by `_browser_headers`, line 66 → `_request_json`, line 144). | Directly contradicts the policy upstream shipped *because of* 403s/ethics. Also un-paced: `fetch_old_site_favorites` pages up to `max_pages=1000` with no interval. | Use `download_policy.IDENTIFIABLE_USER_AGENT` and route every request through a pacer (§6.1). |
| **S2** | blocker | Our thumbnail-fallback requests (`creator._download_thumbnail_fallback`, `post._download_thumbnail_sync`) build headers from `get_headers().copy()` and call `session.get` directly. | They escape both the UA override and the 5-slot/1 s cap — i.e. the degraded-fallback path, exactly the "retry burst" case the policy exists for, is unthrottled. | Wrap with `get_request_headers(...)` + `acquire`/`release` (§6.2). |
| **S3** | high | `download_policy.is_pawchive_url()` hardcodes `pawchive.pw`. | v5.11.1 made Pawchive domains dynamic (`get_domains()`, `pawchive.<suffix>`, `file.pawchive.<suffix>`). If upstream rotates the suffix, capacity pacing and the identifiable UA silently stop applying, and our `to_thumbnail_url` output (`img.pawchive.<suffix>`) is not matched. | Derive the match set from `get_domains()` plus a `pawchive.` fallback (§6.3). |
| **S4** | medium (scope) | `kd_thumbnaildl.py` (upstream's v5.12.0 Thumbnail tab) uses its own Chrome UA (lines ~474, ~660) and does bulk thumbnail downloads with no pacing. | Upstream's changelog claims the policy applies "across the Post and Creator Downloaders" — the Thumbnail tab is a real hole in the same claim, and it is a tab **we now document as a headline feature**. | Decide (§8, D2): wire it, or document the exclusion. Recommend wiring at least the UA + pacer. |
| **S5** | medium | `IDENTIFIABLE_USER_AGENT` embeds the version string. | After renumbering it lies; after every future bump it drifts. | Add `__version__` to the (currently empty) `src/kemonodownloader/__init__.py` and build the UA from it (§6.4). |
| **S6** | low | Pacing vs the 180 s join windows. | `WORKER_JOIN_TIMEOUT_SECONDS` deadlines are computed *after* dispatch, so 1 req/s mostly stretches dispatch, not the deadline. But the post-downloader's single-file second pass has its own 180 s window, and a large batch of pawsive 404 retries is dispatched from inside it. | Keep 180 s; re-verify in a Qt-capable environment with a ≥200-file Pawchive 404 batch. Note as residual risk. |
| **S7** | info (verified OK) | `release_pawchive_download` in `post_downloader` sits in the outer `finally` (lines 1782–1783) and is guarded by `request_slot_acquired`. | Our `_handle_full_res_failure` early `return` (1728) and the normal success `return` both still release the slot → no leak, no double release. | none |
| **S8** | info (verified OK) | Creator path acquires before `_ssl_lock`, releases in `finally`; a cancelled acquire raises a plain `Exception`. | Our fallback logic only triggers from `requests.RequestException` + 404/`None` status, so cancellation is never misread as "full-res gone → thumbnail". | none |
| **S9** | info (verified OK) | Retries/pacing semantics. | Upstream states retries are paced too; our creator requeue and post second pass re-enter `download_file`, so they acquire a fresh slot and wait for the next 1 s tick — matches upstream's stated intent. | none |
| **S10** | info (verified OK) | Settings, i18n, README, deps, `WORKER_JOIN_TIMEOUT_SECONDS`. | See §2.3. | none |
| **S11** | note | Upstream shipped **no tests** for `download_policy.py`, and our repo has tests upstream lacks (`test_pawchive.py`, `test_domain_config.py`, `test_hash_db_processed.py`). | CI (`.github/workflows/ci.yml`) runs pre-commit + full pytest + pyright on every PR; nothing guards the limiter. | Add `tests/test_download_policy.py` (§7.3). |

---

## 6. Recommended code integration

Import order note: `download_policy` currently imports only stdlib. Importing
`domain_config.get_domains` is safe (no Qt) and `pawchive.py` already does it.

### 6.1 Pace Pawchive *metadata* requests (favorites / recent feed / old-site crawl)

Files: `src/kemonodownloader/download_policy.py`, `src/kemonodownloader/pawchive.py`.

Add a metadata pacer that shares the interval with the download limiter but has
no concurrency cap (metadata calls are one-at-a-time from a worker thread):

```python
# download_policy.py
_metadata_lock = threading.Lock()
_next_metadata_at = 0.0


def pace_pawchive_request(is_running: Callable[[], bool] = lambda: True) -> bool:
    """Block until the next allowed Pawchive metadata request slot."""
    global _next_metadata_at
    while is_running():
        with _metadata_lock:
            now = time.monotonic()
            if now >= _next_metadata_at:
                _next_metadata_at = now + PAWCHIVE_REQUEST_INTERVAL
                return True
            wait_for = _next_metadata_at - now
        time.sleep(min(max(wait_for, 0.05), 0.1))
    return False
```

In `pawchive.py`: delete the Chrome `DEFAULT_USER_AGENT`, import
`IDENTIFIABLE_USER_AGENT` + `pace_pawchive_request` + `get_request_headers`, and
call them inside `_request_json()` so *every* fetch (including each
`fetch_old_site_favorites` page and each `?o=` page) is paced and honestly
identified. Keep the existing optional-`session` parameter untouched.
`tests/test_pawchive.py` asserts on the old UA in places — update those asserts
to `IDENTIFIABLE_USER_AGENT`.

### 6.2 Route the thumbnail fallbacks through the policy

`creator_downloader.py` (`_download_thumbnail_fallback`, ~2150) and
`post_downloader.py` (`_download_thumbnail_sync`, ~1859):

```python
headers = get_request_headers(headers, thumb_url)
if not acquire_pawchive_download(thumb_url, lambda: self.is_running):
    return False                      # cancelled
try:
    ... session.get(thumb_url, headers=headers, ...) ...
finally:
    release_pawchive_download(thumb_url)
```

Keep the acquire **outside** the `_ssl_lock` (same reason as upstream) and keep
the existing "degraded file hashed under the original full-res URL" behaviour.

### 6.3 Make `is_pawchive_url` suffix-agnostic

```python
from kemonodownloader.domain_config import get_domains

def is_pawchive_url(url: str) -> bool:
    hostname = (urlparse(url).hostname or "").lower()
    if not hostname:
        return False
    for domain in get_domains():
        if domain.startswith("pawchive.") and (
            hostname == domain or hostname.endswith("." + domain)
        ):
            return True
    # Forward-compatible: a rotated pawchive.<suffix> still gets paced.
    return hostname.startswith("pawchive.") or ".pawchive." in hostname
```

Add a test that monkeypatches `get_domains()` to return `pawchive.st` and asserts
`is_pawchive_url("https://file.pawchive.st/data/aa/bb/x.png") is True` — that is
the regression upstream's hardcode would have introduced here.

### 6.4 Single source of truth for the version

* `src/kemonodownloader/__init__.py` (currently empty):
  `__version__ = "5.14.0"`.
* `app.py`: `from kemonodownloader import __version__ as CURRENT_VERSION`
  (keeps the existing `CURRENT_VERSION` name used in labels and tests).
* `download_policy.py`: `IDENTIFIABLE_USER_AGENT = f"KemonoDownloader/{__version__} (+mailto:izeno.contact@gmail.com)"`.
* `pyproject.toml` version stays literal (Briefcase requires a literal); keep
  the two in sync via a comment, or a tiny test asserting they match.

### 6.5 Thumbnail tab (`kd_thumbnaildl.py`) — decision D2

Recommended minimal version: in `ThumbnailDownloadThread`, replace the two
hardcoded Chrome UA blocks with `get_request_headers({...}, url)` and wrap the
`stream=True` thumbnail GET (line ~669) in
`acquire_pawchive_download`/`release_pawchive_download`, plus the pacer on the
metadata GETs. If you would rather not expand scope, add one sentence to the
Settings info text/README saying the policy covers the Post, Creator and
Thumbnail downloaders only where noted — but then the claim and the code drift.

---

## 7. Mechanical reconciliation (ordered, copy-pasteable)

### 7.1 Git

```bash
cd /home/user/KemonoDownloader
git remote add upstream https://github.com/VoxDroid/KemonoDownloader.git   # once
git fetch upstream main
git merge --allow-unrelated-histories --no-commit upstream/main
# resolve CHANGELOG per §7.2, then:
git add -A && git commit -m "Merge upstream v5.13.0 (Pawchive rate limiting) into fork baseline"
```

Rationale for merge over rebase: our history is one squashed snapshot, so a
rebase has nothing to replay; the merge is what gives this fork a common
ancestor with upstream for all future syncs. Rehearsed conflict count: **1**.

### 7.2 `CHANGELOG` resolution (top of file)

```markdown
# Kemono Downloader Release Notes

## v5.14.0 (unreleased)
**feat: Pawchive favorites batch/sync/import, old-site crawl, recent-feed opt-in, and full-res retry → thumbnail fallback**

Fork release on top of upstream v5.13.0. Everything below was written against
upstream v5.12.0 and reconciled with upstream v5.13.0 (Pawchive rate limiting);
see `docs/UPSTREAM_RECONCILIATION.md`.

- <keep our existing v5.13.0 bullet list verbatim here, reworded only where it
  mentions version numbers: `SECURITY.md` tracks v5.14.0+>
- Pawchive requests introduced by this fork (favorites, sync, recent feed,
  old-site crawl) and the thumbnail-fallback downloads now use the upstream
  `download_policy` identifiable user agent, 1 request/second pacing and the
  5-download cap. `is_pawchive_url` follows the dynamic domain list.

## v5.13.0 (27 September 2026)
**fix: responsible Pawchive request pacing and improved resilience to HTTP 403 responses**
<upstream's four bullets, unchanged>

## v5.12.0 (01 August 2026)
...
```

### 7.3 Version bump checklist → `5.14.0`

| File | Line / spot |
|---|---|
| `src/kemonodownloader/__init__.py` | add `__version__ = "5.14.0"` |
| `src/kemonodownloader/app.py` | `CURRENT_VERSION` (36) → derive from `__version__` |
| `src/kemonodownloader/download_policy.py` | `IDENTIFIABLE_USER_AGENT` (8) → f-string |
| `pyproject.toml` | `version` (4) |
| `CHANGELOG` | new section (§7.2) |
| `README.md` | version badge (43) |
| `SECURITY.md` | supported-version sentence + table rows (5, 9, 10) |
| `docs/DEPLOYMENT_REVIEW.md` | "Advertised version", "Done in v5.13.0" heading |
| `docs/SESSION_HANDOFF.md` | §1 base commit / branch facts, §3 expectations |
| `docs/WORKLIST.md` | §A blockers |
| `tests/test_language.py` | 273 docstring ("Help sections added in 5.13.0") — cosmetic |

### 7.4 New tests (`tests/test_download_policy.py`, upstream has none)

1. `get_request_headers` swaps the UA for `pawchive.pw`, `file.`/`img.` hosts and
   leaves `kemono.cr` headers untouched (including the caller's dict not being
   mutated).
2. Rate cap: 8 threads that call `acquire` without releasing → at most
   `PAWCHIVE_MAX_ACTIVE_DOWNLOADS` succeed; releasing lets the rest through.
3. Pacing: monkeypatch `time.monotonic`/`time.sleep` and assert the second
   acquire is not granted before `PAWCHIVE_REQUEST_INTERVAL` elapsed.
4. Cancellation: `acquire(..., lambda: False)` returns `False` immediately.
5. `release` on a non-acquired/non-pawchive URL is a no-op and never drives the
   counter negative.
6. Domain rotation: monkeypatched `get_domains()` → `pawchive.st` host matched.
7. `pawchive.py` UA = `IDENTIFIABLE_USER_AGENT`; pacer called once per page in a
   mocked multi-page old-site crawl.

### 7.5 Verification gates

1. `python -m compileall -q src/kemonodownloader`.
2. Pure-Python tests: `test_domain_config`, `test_pawchive`, `test_hash_db*`,
   `test_language`, `test_download_policy`.
3. `pre-commit run --all-files` (black/isort/ruff/mypy/pyright — CI runs it).
4. Push the arena branch, open the PR, let CI run the full Qt suite
   (`QT_QPA_PLATFORM=offscreen` on the GitHub runners) — it cannot run in this
   sandbox (`libGL.so.1`).
5. Re-verify in real Qt: favorites Fetch/Sync with a real key, old-site crawl
   pagination, and a >200-file Pawchive batch (pacing vs the 180 s join windows).

---

## 8. Decisions needed

| # | Decision | Recommendation |
|---|---|---|
| **D1** | Version for our release | **5.14.0** (features on top of upstream's v5.13.0). `5.13.1` would imply a patch to upstream's release, which ours is not. |
| **D2** | Wire `kd_thumbnaildl.py` into the policy? | **Yes**, UA + pacer + download slot — it is a documented headline tab and the only remaining unthrottled Pawchive file path. |
| **D3** | Keep `VersionChecker` pointed at `VoxDroid/KemonoDownloader`? | **Keep** for now (fork has no releases). With 5.14.0 local it will not nag; it will only prompt when upstream ships v5.15.0, which is the desired "upstream moved ahead" signal. Document it in `DEPLOYMENT_REVIEW.md`. |

---

## 9. Residual risks after reconciliation

1. Still no Qt run in-sandbox — the merged `download_file` bodies (the riskiest
   auto-merge) are only proven by compile + CI.
2. Pawchive favorites auth (`Cookie: session=<key>`) and old-site crawl page
   size remain unverified against live sites (`WORKLIST.md` §D).
3. Rate limiting changes throughput expectations for Pawchive batches: with the
   5-slot cap and 1 req/s start pace, large creator batches are now intentionally
   slow. README/Help should say so (upstream's bullet already does).
4. Pacing makes the "retry once after everything else" timing in the creator
   downloader even less strict at wall-clock level; semantics unchanged
   (`WORKLIST.md` §D).
