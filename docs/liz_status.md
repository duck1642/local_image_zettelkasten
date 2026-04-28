# LIZ Current Status

## Current State

LIZ is now a Tauri + Svelte desktop app backed by a local FastAPI service and the existing Python ingestion pipeline.

Current launch command:

```powershell
python dev.py
```

Backend ingestion still runs through:

```powershell
python main.py
liz
```

The old Flet and PySide/PyQt UI paths are no longer active. `gui.py`, the old Python UI package, PySide dependencies, and the `liz-gui` entry point were removed.

## Working Areas

- Local file ingestion for images, GIFs, and videos.
- External URL ingestion through gallery-dl and yt-dlp.
- Batch-safe ingestion for Pixiv, X/Twitter, Instagram, Pinterest, and YouTube community posts.
- SHA256-based vault storage with sharded assets and notes.
- SQLite runtime index for asset metadata and duplicate checks.
- Markdown note generation with note-frontmatter topics.
- Local WD tag cache under `data/wd-tags/{hash[:2]}/{hash}.json`.
- Distilled WD tags in markdown frontmatter.
- Svelte vault UI with masonry/grid layouts, advanced filtering, smart command prefixes (e.g. `>grid`), and decoupled live-search/infinite-scroll.
- Svelte inspector with metadata editing, grouped source navigation, tagging action, copy/delete/open actions.
- Markdown queue ingestion workbench.
- Review view.
- Settings view.
- Structured log viewer with normal/raw modes.
- Local API hardening for destructive actions.

## Current Architecture Snapshot

- UI: Tauri + Svelte.
- Backend API: `backend/web_api.py`.
- Ingestion CLI: `backend/core.py`, launched by `main.py` or `liz`.
- Runtime database: `data/db/liz_main.db`.
- Vault assets: `data/vault/assets/{hash[:2]}/{hash}.{ext}`.
- Vault notes: `data/vault/notes/{hash[:2]}/{hash}.md`.
- WD cache: `data/wd-tags/{hash[:2]}/{hash}.json`.
- Logs: `logs/raw/` and `logs/structured/`.
- Secrets: `secrets/`.
- Python source root: `backend/`.

SQLite stores runtime asset/index metadata only. Manual topics and WD tags live outside SQLite.
## Recent Hardening Completed

- Structured logging system implemented with color-coded `.jsonl` streams.
- Live search UI glitch fixed by decoupling `isSearching` and `isLoadingMore` states to prevent flicker.
- Layout toggle commands (`>grid`, `>masonry`) added with auto-complete dropdown and keyboard navigation.
- Mutating API endpoints now require a local UI session key.

## Current Issues

### Critical & Bugs
- **Production sidecar is a dummy:** `frontend/src-tauri/bin/dummy.rs` is a no-op loop. Production Tauri builds will not start the Python backend. Needs compilation of `web_api.py` into a real binary.
- **`App.svelte` config POST missing API key:** Command-triggered layout changes (`>grid`) use raw `fetch()` instead of `apiFetch()`. Requests are rejected by backend middleware (HTTP 403) and fail silently.
- **Infinite scroll (Masonry) stale closure:** `IntersectionObserver` in `onMount` captures initial values of `hasMore` and `isSearching`. It never refreshes its logic, preventing auto-loading more items as the user scrolls. **(Needs checking/verification)**.
- **Inconsistent pagination UI:** Infinite scroll is only implemented for Masonry view; Grid view still uses a manual "Load More" button.

### Technical Debt & Architecture
- **Hardcoded Backend URLs:** ~26 instances of `http://localhost:8000` are hardcoded across 9 Svelte files instead of using `apiUrl()` or `apiFetch()`.
- **Missing Vite Proxy:** Dev mode requires full URLs for every request. Adding a proxy to `vite.config.ts` would simplify frontend code and eliminate URL duplication.
- **Hardcoded SSE URLs:** `LogsView.svelte` and `Ingestion.svelte` use hardcoded strings for `EventSource` connections.
- **Tauri Panic on Startup:** `lib.rs` uses `.expect()` for sidecar spawning. If the binary is missing, the app crashes without a user-friendly error.
- **Logger Import Hoisting:** `logger.ts` imports `apiFetch` at the bottom of the file; technically works but is non-idiomatic.
- **CSP Disabled:** `tauri.conf.json` has `"csp": null`, providing no protection against content injection.

## Still Deferred
- Log, queue, and review endpoints validate requested paths.
- Item update/delete/tag endpoints return 404 for missing items.
- Delete order now removes DB rows before cleaning asset/note/tag files.
- API log tailing no longer reads whole log files into memory.
- Review endpoint no longer opens one DB connection per item.
- DB/frontmatter item filters paginate after frontmatter filtering.
- Blocking API work is routed through thread helpers for the main item/config/log/review paths.
- `INSERT OR REPLACE` was replaced to avoid deleting `item_tiles`.
- `source_url_norm` was added for indexed duplicate URL checks.
- Empty tile insertion no longer clears existing tile rows.
- Video audio duplicate search returns all audio matches instead of stopping after the first.
- gallery-dl and yt-dlp now share valid media filtering.
- gallery-dl session hash prefix was increased from 10 to 16 hex chars.
- YouTube community downloads now record per-image failures.
- Video frame extraction no longer leaks `CalledProcessError`.
- Dead `FlatVectorSearcher` and tagging `_prepare_image()` were removed.
- Markdown frontmatter parsing handles BOM and line-delimited YAML fences.
- Pillow is pinned to `>=9.0.0`.
- Python source root was renamed from `src/` to `backend/`.

## Still Deferred

- Search/index scaling: RAM hydration still bulk-loads pHash, tile, URL, and video signatures.
- Config caching: `get_config()` still reparses YAML often; caching needs explicit invalidation for Settings edits.
- Video embedding performance: V1 still extracts five frames using separate ffmpeg calls.
- YouTube community partial policy: one failed expected image still makes the post incomplete and retryable.
- Source URL normalization migration: existing rows are backfilled lazily by `init_database()`, not by a standalone maintenance tool.
- Timestamp consistency: local Python timestamps and SQLite UTC defaults still coexist.
- Thumbnail helper cleanup: `thumbnails.py` still has a small asset-path helper duplication.
- Frontend accessibility warnings remain in Svelte build output.

## Useful Checks

```powershell
$env:PYTHONPATH='backend'
python -B -c "import core, web_api, db.sqlite_operator, db.search_manager, queue_service, tagging.service; print('IMPORT OK')"
python -B -c "import ast, pathlib; [ast.parse(path.read_text(encoding='utf-8'), filename=str(path)) for path in pathlib.Path('backend').rglob('*.py')]; print('AST OK')"
cd frontend
npm run build
```

Known build note: Vite may need to run outside the sandbox because it spawns helper processes. Current build succeeds with Svelte accessibility warnings.

## Documentation Notes

- `docs/` is local and ignored by GitHub uploads.
- `liz_architecture.md` contains durable architecture details.
- `liz_roadmap.md` contains phase history and future work.
- This file is the short current snapshot.
