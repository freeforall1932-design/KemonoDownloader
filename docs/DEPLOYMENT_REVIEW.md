# Deployment review — KemonoDownloader

> Updated **2026-09-09** after the v5.13.0 ship-prep pass.
>
> Companion docs: [`WORKLIST.md`](./WORKLIST.md),
> [`SESSION_HANDOFF.md`](./SESSION_HANDOFF.md),
> [`IMPROVEMENT_LOG.md`](./IMPROVEMENT_LOG.md).

---

## 1. Snapshot

| Item | Value |
|---|---|
| Repo | `freeforall1932-design/KemonoDownloader` (fork of `VoxDroid/KemonoDownloader`) |
| Advertised version | **5.13.0** (`pyproject.toml`, `app.py` `CURRENT_VERSION`, README badge, `CHANGELOG`) |
| Unreleased-until-this-cut | Favorites batch/sync/import, recent-feed opt-in, old-site crawl, full-res retry → thumbnail fallback (`has_full`) |
| `VersionChecker` repo | Still `VoxDroid/KemonoDownloader` (this fork has no releases) |
| GitHub Releases on this fork | **None** |
| Live Pawchive / favorites auth | **Not verified** (do not advertise Fetch/Sync as proven) |

---

## 2. Done in v5.13.0

- Post URL validation: known domains from `get_domains()` + `/user/` + `/post/` + HTTP 200. No `"kemono"`/`"coomer"` HTML gate.
- Creator `ValidationThread`: HTTP 200 is enough (no domain-stem HTML gate).
- Domain list packaged at `src/kemonodownloader/resources/config/domain` (Briefcase `sources` only includes that package). Repo `assets/config/domain` remains the source-checkout copy.
- `kemono_downloader-1.2.8.xpi` removed from git; `.gitignore` has `*.xpi` / `*.crx`.
- Help tab: Thumbnail Downloader, Pawchive Favorites, Fast Mode.
- README / localized READMEs / `index.html` / `assets/js/i18n.js`: six tabs.
- Browser extension: Pawchive hosts; `manifest.json` is a usable Chrome MV3 copy.
- `SECURITY.md` tracks v5.13.0+. `asyncio` dropped from `requirements.txt`. Pyproject description includes Pawchive.
- Worker `is_alive()` join timeout raised 30s → 180s. Creator `add_list_item` no longer builds the widget twice.
- Favorites / thumbnail-fallback log keys localized (ja/ko/zh). Mocked `pawchive.fetch_*` tests added.

---

## 3. Still not a binary ship

- Full Qt suite still needs a Qt-capable environment / CI (`libGL`).
- Pawchive `Cookie: session=<key>` still not live-tested with a real key.
- Old-site crawl page size / cookie format still assumed.
- No Briefcase package / `gh release` workflow on this fork.
- `VersionChecker` still points at upstream VoxDroid.

Until those exist, Pawchive support is **source-ready**. Creator/post URL add-to-queue and the packaged domain list are no longer blockers.

---

## 4. Remaining product risks (unchanged)

1. Creator retry is not strictly “after everything else” (404s go onto the live asyncio queue).
2. `has_full is False` → thumbnail; missing/`True` → full-res.
3. Degraded thumbnail is hashed under the original full-res URL.
4. `mark_creator_processed` only if `failed_files` is empty.

Live-test still required before advertising Favorites/Sync.
