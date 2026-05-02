# LMZ Current Status

## Current State

LMZ is a Tauri + Svelte desktop app backed by a local FastAPI service and the existing Python ingestion pipeline.

Current launch command:

```powershell
python dev.py
```

Backend ingestion still runs through:

```powershell
python main.py
lmz
```

The old Flet and PySide/PyQt UI paths are no longer active. `gui.py`, the old Python UI package, PySide dependencies, and the PySide entry point was removed.

## Working Areas

- Local file ingestion for images, GIFs, and videos.
- External URL ingestion through gallery-dl and yt-dlp.
- Batch-safe ingestion for Pixiv, X/Twitter, Instagram, Pinterest, and YouTube community posts.
- SHA256-based vault storage with sharded assets and notes.
- SQLite runtime index for asset metadata and duplicate checks.
- Markdown note generation with note-frontmatter topics.
- Local WD tag cache under `data/wd-tags/{hash[:2]}/{hash}.json`.
- Distilled WD tags in markdown frontmatter.
- Svelte vault UI with virtualized masonry/grid layouts, advanced filtering, command prefixes, and shared infinite-scroll loading.
- Svelte inspector with metadata editing, grouped source navigation, tagging action, copy/delete/open actions.
- Markdown queue ingestion workbench.
- Review view.
- Settings view.
- Structured log viewer with normal/raw modes.
- Local API hardening for destructive actions.

## Current Architecture Snapshot

- UI: Tauri + Svelte.
- Backend API: `backend/web_api.py`.
- Ingestion CLI: `backend/core.py`, launched by `main.py` or `lmz`.
- Runtime database: `data/db/lmz_main.db`.
- Vault assets: `data/vault/assets/{hash[:2]}/{hash}.{ext}`.
- Vault notes: `data/vault/notes/{hash[:2]}/{hash}.md`.
- WD cache: `data/wd-tags/{hash[:2]}/{hash}.json`.
- Logs: `logs/raw/` and `logs/structured/`.
- Secrets: `secrets/`.
- Python source root: `backend/`.

SQLite stores runtime asset/index metadata only. Manual topics and WD tags live outside SQLite.

## Recent Hardening Completed

- Structured logging system implemented with color-coded `.jsonl` streams.
- Frontend API, asset, and SSE URLs are centralized in `frontend/src/lib/api.ts`.
- Command-triggered layout changes use authenticated API requests.
- Vite dev proxy was added for `/api`, `/vault`, and `/review-assets`.
- Masonry and grid now use the same infinite-scroll loading path.
- Tauri sidecar startup logs failures instead of panicking on missing sidecar startup.
- Production sidecar build tooling was added through `npm run build:sidecar`.
- A practical Tauri CSP was added for local backend and media access.
- Mutating API endpoints require a local UI session key.
- CORS is restricted to local/Tauri origins.
- Log, queue, and review endpoints validate requested paths.
- Item update/delete/tag endpoints return 404 for missing items.
- Delete order removes DB rows before cleaning asset/note/tag files.
- API log tailing no longer reads whole log files into memory.
- Review endpoint no longer opens one DB connection per item.
- DB/frontmatter item filters paginate after frontmatter filtering.
- Blocking API work is routed through thread helpers for the main item/config/log/review paths.
- `INSERT OR REPLACE` was replaced to avoid deleting `item_tiles`.
- `source_url_norm` was added for indexed duplicate URL checks.
- Empty tile insertion no longer clears existing tile rows.
- Video audio duplicate search returns all audio matches instead of stopping after the first.
- gallery-dl and yt-dlp share valid media filtering.
- gallery-dl session hash prefix was increased from 10 to 16 hex chars.
- YouTube community downloads record per-image failures.
- Video frame extraction no longer leaks `CalledProcessError`.
- Dead `FlatVectorSearcher` and tagging `_prepare_image()` were removed.
- Markdown frontmatter parsing handles BOM and line-delimited YAML fences.
- Pillow is pinned to `>=9.0.0`.
- Python source root was renamed from `src/` to `backend/`.
- Vault layout modes were simplified to `masonry` and `grid`; old `masonry-js`/`grid-js` values are compatibility-only.
- Runtime config now uses `ui.vault_layout_mode` and `ui.vault_tile_min_width`.
- Sensitive Pixiv/cookie credentials were removed from `config/config.yaml`; `secrets/.secrets.yaml` remains the credential source.
- The old misleading Vault `Add Files` button was removed.
- Visible frontend mojibake in the ingestion dirty marker and log truncation ellipsis was fixed.
- Unused default Vite/Svelte frontend assets were removed from `frontend/src/assets/`.
- Terminal stdout/stderr logging is initialized at API startup instead of mutating streams during import.
- Backend command suggestions include `>masonry`, `>grid`, `>zoom-in`, and `>zoom-out`.
- Shared stats polling, review count, inspector action feedback, bulk delete, and infinite-scroll rechecks are implemented.
- Safe frontend media-type helpers replaced direct `mime_type.startsWith(...)` checks, so missing MIME values no longer crash tile/inspector/focus rendering.
- Search suggestion positioning now reuses one canvas/context instead of creating a new canvas on every keypress.
- Vault layout and zoom now use the shared frontend config store, so Settings saves no longer overwrite vault layout or tile size changes.
- Virtualized masonry and grid renderers are now the active `masonry` and `grid` layouts.
- Old full-DOM masonry/grid renderer snippets were archived under `frontend/src/lib/renderers/archive/stable/` as non-compiled reference files.

## Current Issues

- Production sidecar packaging has a build path, but the generated sidecar still needs release-build validation on a clean machine.
- Frontend accessibility warnings remain in Svelte build output.
- CSP is practical rather than strict and should be revisited after production packaging is stable.
- Shift-click range selection now uses renderer-emitted visual order for both masonry and grid. It still needs real-use validation on large mixed media vaults.
- **Frontend ingestion run state:** `Ingestion.svelte` starts ingestion but does not check the response status and clears the `running` flag after a fixed delay. The backend lock still protects actual ingestion, but the UI can re-enable controls while ingestion is still running or after a failed request.
- **Frontend SSE reconnect cleanup:** Ingestion and app-log EventSource reconnect timers are not cleared on component teardown. A pending reconnect can recreate a stream after leaving the view.
- **Review action response handling:** `ReviewView.svelte` removes review rows from local UI state after an API call without checking `response.ok`, so failed backend actions can look successful until reload.
- **Renderer reactive dependency clarity:** `MasonryRenderer.svelte` and `GridRenderer.svelte` call helper functions from reactive statements with hidden dependencies. This should be made explicit to avoid stale visual-order/log updates after future refactors.
- **Stats panel request ordering:** `StatsView.svelte` assigns facet responses unconditionally. Fast typing or tab switches can let an older response overwrite newer visible results.
- **API session-key retry:** `api.ts` caches the `/api/session-key` promise. If backend startup causes one failed session-key request, mutating API calls can keep failing until full app reload.
- **Vault fetch error boundaries:** `VaultView.svelte` does not check `response.ok` for item/stat requests, and stats failure can be reported as item loading failure.
- **SearchBar timer cleanup:** Search/debounce timers are not cleared on destroy. Current mounting makes this low-risk, but it should be fixed if the search component becomes conditionally mounted.
- **Sidecar Port 8000 Binding (Brittleness):** The compiled `lmz-api` binary internally hardcodes `uvicorn.run(port=8000)`. If port 8000 is occupied by another app, the backend fails to bind and the Tauri app renders a white screen. Production sidecars should dynamically bind to an available port provided by Tauri.
- **`svelte-check` Accessibility Debt:** Running `npm run check` currently reports accessibility warnings around labels, clickable divs, and media captions.
- **Virtual Renderer Validation:** Masonry and grid now use virtualized renderers. Large-vault behavior, video unmount behavior, zoom stability, and grouped-media persistence should be validated in real browsing sessions.

## Current Task

Vault view optimization:

- Current state:
  - `masonry` uses the measured virtual masonry renderer.
  - `grid` uses the virtual fixed-row grid renderer.
  - Both renderers live under `frontend/src/lib/renderers/`.
  - The old full-DOM renderer snippets are archived for analysis only and are not imported.
  - Layout/zoom changes are saved through the shared config store.
- Validation still needed:
  - Confirm masonry has no overlap after long scroll sessions.
  - Confirm offscreen video tiles unmount.
  - Confirm grouped media keeps active index after scroll out/in.
  - Confirm zoom remains stable in narrow and wide windows.
  - Make renderer visual-order and logging reactivity explicit instead of depending on helper-call side effects.

Search/filter implementation:

- Current search parsing lives in `frontend/src/lib/search.ts` and `frontend/src/lib/SearchBar.svelte`.
- Current backend item filtering lives in `backend/web_api.py`.
- Supported prefixes:
  - `a:` filters artist.
  - `@` filters platform.
  - `#` filters note-frontmatter topics.
  - `*` filters WD tags.
  - `>` triggers commands such as `>grid`, `>masonry`, `>zoom-in`, and `>zoom-out`.
- Search now uses structured filter arrays internally.
- Repeated filters are supported for WD tags, topics, platforms, and artists.
- Dropdown suggestion sources now exist for commands, artist, platform, topic, and WD tag prefixes.
- Dropdown suggestions now show global facet counts when available.
- Dropdown suggestion lists are scrollable and support mouse selection, ArrowUp/ArrowDown navigation, Enter selection, and Tab autocomplete.
- Non-command dropdowns request a larger suggestion set so high-count WD tags, artists, platforms, and topics can be browsed.
- A read-only Stats tab shows global counts for WD tags, artists, platforms, and topics.
- Use `;` as the separator for prefixed search filters because comma may appear in normal text later.
- Position the dropdown relative to the active prefix/value being typed, not just under the whole search bar.
- Use AND between different prefix types.
- Use OR within repeated `a:` artist filters.
- Use OR within repeated `@` platform filters.
- Use AND within repeated `#` topic filters.
- Use AND within repeated `*` WD tag filters.
- Use AND for plain text terms.
- Backend item filtering uses repeated query params, not comma-encoded strings.
- Backend exposes `/api/facets` for global facet count queries.
- Planned optimization: add an in-memory facet cache for Stats and dropdown counts. Markdown remains the source of truth for topics and WD tags, but backend should build topic/WD counts once and invalidate/rebuild after tagging, note update, delete, or ingestion.
- Vault layout currently uses computed JS masonry/grid with configurable tile minimum width.
- The visible UI remains a single search input; chips are still deferred.
- Future planned feature: context-aware suggestions. Example: after `*kisaki; *`, WD suggestions should come only from items already matching `*kisaki`, excluding already-selected tags.
- Possible context-aware suggestion approaches to compare later: scan current matches for V1, build an in-memory facet index for long-term speed, or add SQLite facet tables if durable indexed search becomes worth the schema cost.

## Still Deferred

- Search/index scaling: RAM hydration still bulk-loads pHash, tile, URL, and video signatures.
- Context-aware search suggestions are deferred until similar programs are reviewed.
- Config caching: `get_config()` still reparses YAML often; caching needs explicit invalidation for Settings edits.
- Video embedding performance: V1 still extracts five frames using separate ffmpeg calls.
- YouTube community partial policy: one failed expected image still makes the post incomplete and retryable.
- Source URL normalization migration: existing rows are backfilled lazily by `init_database()`, not by a standalone maintenance tool.
- Timestamp consistency: local Python timestamps and SQLite UTC defaults still coexist.
- Thumbnail helper cleanup: `thumbnails.py` still has a small asset-path helper duplication.

## Useful Checks

```powershell
$env:PYTHONPATH='backend'
python -B -c "import core, web_api, db.sqlite_operator, db.search_manager, queue_service, tagging.service; print('IMPORT OK')"
python -B -c "import ast, pathlib; [ast.parse(path.read_text(encoding='utf-8'), filename=str(path)) for path in pathlib.Path('backend').rglob('*.py')]; print('AST OK')"
cd frontend
npm run build
npm run build:sidecar
```

Known build note: Vite may need to run outside the sandbox because it spawns helper processes. Current frontend build may still report Svelte accessibility warnings.

## Documentation Notes

- `docs/` is local and ignored by GitHub uploads.
- `lmz_architecture.md` contains durable architecture details.
- `lmz_roadmap.md` contains phase history and future work.
- This file is the short current snapshot.
