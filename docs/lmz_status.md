# LMZ Current Status

Last updated: 2026-05-06

## Current State

LMZ is a local media vault desktop app with a Tauri + Svelte frontend and a local FastAPI/Python backend.

Launch commands:

```powershell
python dev.py
python main.py
lmz
```

The old Flet and PySide/PyQt UI paths are no longer active. The Python source root is `backend/`.

## Architecture Snapshot

- Frontend: `frontend/src/` Svelte app, Tauri shell in `frontend/src-tauri/`.
- Backend API: `backend/web_api.py`.
- Ingestion CLI: `backend/core.py`, launched by `main.py` or `lmz`.
- Runtime database: `data/db/lmz_main.db`.
- Vault assets: `data/vault/assets/{hash[:2]}/{hash}.{ext}`.
- Vault notes: `data/vault/notes/{hash[:2]}/{hash}.md`.
- WD tag cache: `data/wd-tags/{hash[:2]}/{hash}.json`.
- Logs: `logs/raw/` and `logs/structured/`.
- Secrets: `secrets/`.

SQLite stores runtime asset/index metadata only. Manual topics and WD tags live outside SQLite.

## Working Areas

- Local image, GIF, and video ingestion.
- External URL ingestion through gallery-dl and yt-dlp.
- Batch-safe ingestion for Pixiv, X/Twitter, Instagram, Pinterest, and YouTube community posts.
- SHA256-based sharded vault storage.
- Markdown note generation with note-frontmatter topics.
- Local WD tagging for images and sampled video frames.
- Distilled WD fields in markdown frontmatter.
- Svelte vault UI with virtualized masonry/grid layouts.
- Structured search with prefixes, commands, suggestions, and facet counts.
- Toggleable and resizable inspector panel.
- Wide/fullscreen media focus.
- Grouped media navigation and filmstrip.
- Markdown queue ingestion workbench.
- Review, Stats, Settings, and App Logs views.
- Structured log viewer with normal/raw modes.
- Dedicated auth-status log stream for cookie/token visibility.
- Local API hardening for destructive actions.

## Recently Completed

- Project renamed to Local Media Zettelkasten / LMZ.
- Python source root renamed from `src/` to `backend/`.
- Old full-DOM masonry/grid renderers archived as non-compiled references.
- Virtualized masonry and grid renderers promoted to the active `masonry` and `grid` layouts.
- Layout/zoom config writes now use the shared frontend config store.
- Sort and media filter buttons were removed from the vault header and replaced by commands:
  - `>sort-newest`
  - `>sort-oldest`
  - `>sort-artist`
  - `>media-all`
  - `>media-image`
  - `>media-video`
- Current layout commands:
  - `>masonry`
  - `>grid`
  - `>zoom-in`
  - `>zoom-out`
- Auth status scan implemented:
  - startup auth scan writes to `logs/structured/auth.jsonl`
  - manual endpoint `/api/auth/scan`
  - vault command `>scan-auth`
  - App Logs dropdown includes `auth.jsonl (Auth)`
  - reports X, Instagram, Pinterest, YouTube, and Pixiv availability without logging secret values
- Auth config cleanup:
  - `cookies_path` now uses relative `secrets/cookies.txt`
  - Pixiv token is loaded from `secrets/.secrets.yaml`, not `config/config.yaml`
  - relative cookie paths resolve from the project root
- RAM tracker implemented:
  - backend endpoint `/api/system/memory`
  - frontend footer display
  - persisted `>ram-track` toggle
- Fullscreen media zoom/pan implemented in `MediaFocus`.
- Wide/fullscreen grouped-media filmstrip implemented in `MediaFocus`.
- Inspector toggle implemented with `I` and `>toggle-inspector`.
- Inspector resize implemented using `ui.inspector_width`.
- Vault search header split from inspector column so search belongs only to the vault/media column.
- Top vault `Add Files` button removed.
- Frontend mojibake and unused default frontend assets cleaned up.
- Svelte accessibility warnings were brought to zero in the last reviewed pass.
- Renderer performance fixes applied:
  - no `will-change` GPU layer spam
  - `translate3d(...)` positioning
  - grid row-math visibility
  - batched/log-gated renderer summaries
  - safer media MIME helpers
  - teardown cleanup for timers/SSE/fetches
- Backend hardening completed:
  - session key for mutating API calls
  - local-only CORS restrictions
  - path validation for queue/log/review endpoints
  - bulk delete API
  - safe delete ordering
  - review count endpoint
  - sidecar build path
  - practical Tauri CSP
- Review workflow wiring fixed. Done (will be checked):
  - `keep` now defers in review (no DB ingest).
  - `variant` now ingests with duplicate bypass and sidecar metadata handoff.
  - Review action API now returns action-aware success payloads and propagates non-2xx failures.
  - Review compare panes now support both image and video rendering.
- Review wiring follow-up fixes from backend smoke run. Done (will be checked):
  - Fixed `/api/review` tuple-unpack crash after review-item payload expansion.
  - Fixed review action logging argument collision in `log_system`.
  - Fixed false-failure variant behavior caused by post-commit source delete errors.
  - Added best-effort retry cleanup for review source/sidecar removal after successful variant ingest.

## Needs Validation Or Refinement

- Virtual renderer validation:
  - long-scroll masonry overlap checks
  - offscreen video unmount checks
  - grouped media active index after scroll out/in
  - zoom stability in narrow and wide windows
  - real vault testing with large item counts
- Resizable inspector polish:
  - separator should render as one clean line
  - resize handle and separator should align exactly on hover
  - inspector content should remain comfortable across the 320-760 px range
- Fullscreen zoom/pan:
  - core logic works
  - refine drag/background-close edge cases
  - verify video controls remain reliable while zoom logic is active
- Filmstrip:
  - core logic works
  - refine sizing, animation, thumbnail ergonomics, and active-state visibility
- RAM tracker:
  - core logic works
  - refine footer text, polling behavior, and unavailable frontend-memory display
- GIF behavior:
  - ingestion/storage works
  - original GIF animation should work in media focus and markdown
  - vault/inspector thumbnails are static first-frame previews
  - WD tagging and duplicate detection currently inspect only the first frame
- Production sidecar packaging:
  - build path exists
  - still needs clean-machine release validation
- Sidecar port 8000:
  - backend currently assumes port 8000
  - dynamic port binding is deferred unless this becomes a real packaging blocker
- Review workflow validation:
  - verify `keep` leaves item and sidecar in `data/review` with no DB insert.
  - verify `delete` removes item and sidecar and decrements review count.
  - verify `variant` ingests once (no re-quarantine loop) and removes source from review.
  - verify variant failure returns non-2xx and keeps the review item pending.
  - verify image/video review pairs render correctly in both panes.
- Review Windows file-lock edge case:
  - during smoke tests, some review assets remained undeletable (`WinError 5`) after successful variant ingest.
  - current behavior: DB ingest can succeed while review source cleanup fails due to external file lock.
  - needs resolved-state fallback so successfully ingested-but-locked review files are hidden from review lists/count until cleanup is possible.

## Current Frontend Ideas Merged

These were moved from `docs/frontend_ideas.md` into this status file.

Done or mostly done:

- Toggle inspector.
- Resize inspector.
- Fullscreen zoom/pan.
- Wide/fullscreen filmstrip.
- RAM tracker.

Deferred:

- Custom context menu for vault tiles.
- Interactive tag management in the inspector.
- Native drag-and-drop import.
- Animation-aware GIF handling beyond current first-frame thumbnail/tag behavior.
- Artist grouping.

## Search And Filtering

Current search syntax:

- `a:` artist
- `@` platform
- `#` note-frontmatter topic
- `*` WD tag
- `>` command
- `;` separates structured filters

Current operational commands include:

- `>masonry`, `>grid`
- `>zoom-in`, `>zoom-out`
- `>toggle-inspector`
- `>ram-track`
- `>scan-auth`
- `>sort-newest`, `>sort-oldest`, `>sort-artist`
- `>media-all`, `>media-image`, `>media-video`

Current semantics:

- Different prefix types use AND.
- Repeated `a:` artist filters use OR.
- Repeated `@` platform filters use OR.
- Repeated `#` topic filters use AND.
- Repeated `*` WD tag filters use AND.
- Plain text terms use AND.

Implemented:

- Structured filter arrays.
- Repeated query params to the backend.
- Dropdown suggestions for commands, artists, platforms, topics, and WD tags.
- Dropdown counts from `/api/facets`.
- Scrollable dropdown with mouse, ArrowUp/ArrowDown, Enter, Escape, and Tab autocomplete.
- Stats tab for global WD tag, artist, platform, and topic counts.

Deferred:

- Context-aware suggestions.
- In-memory facet cache for faster topic/WD count loading.
- Persistent search index or SQLite facet tables.
- Search chips.

## Deferred Work

- Known review issues from smoke testing:
  - Fixed: `/api/review` crashed due to tuple-unpack mismatch after review payload expansion.
  - Fixed: review action logging passed duplicate `message` arguments into `log_system`.
  - Fixed: `variant` could return failure after a successful DB commit when source delete failed post-commit.
  - Open: Windows file locks (`WinError 5`) can keep review source files undeletable even after successful variant ingest.
  - Open: when lock persists, review file cleanup can lag behind DB state unless a resolved-state fallback is added.

- Video hover preview strategy:
  - current hover preview can download the original video
  - options: file-size cap, backend preview clip endpoint, animated WebP thumbnail
- Search/index scaling:
  - RAM hydration still bulk-loads pHash, tile, URL, and video signatures
- Config caching:
  - `get_config()` still reparses YAML often
  - safe cache invalidation is needed before caching broadly
- Video embedding performance:
  - V1 still extracts five frames with separate ffmpeg calls
- YouTube community partial policy:
  - one failed expected image can still keep the post retryable
- Source URL normalization migration:
  - existing rows are backfilled lazily by `init_database()`
  - no standalone migration tool yet
- Timestamp consistency:
  - local Python timestamps and SQLite UTC defaults still coexist
- Thumbnail helper cleanup:
  - small asset-path helper duplication remains
- Tauri package alignment:
  - frontend `@tauri-apps/api` is pinned to `2.10.1` to match Rust `tauri 2.10.x`.
  - full Tauri stack upgrade to `2.11.x` is deferred as a separate stabilization pass.

## Useful Checks

```powershell
$env:PYTHONPATH='backend'
python -B -c "import core, web_api, db.sqlite_operator, db.search_manager, queue_service, tagging.service; print('IMPORT OK')"
python -B -c "import ast, pathlib; [ast.parse(path.read_text(encoding='utf-8'), filename=str(path)) for path in pathlib.Path('backend').rglob('*.py')]; print('AST OK')"
cd frontend
npm run check
npm run build
npm run build:sidecar
```

Known build note: Vite may need to run outside the sandbox because it spawns helper processes.

## Documentation Notes

- `lmz_architecture.md` contains durable architecture details.
- `lmz_roadmap.md` contains phase history and future work.
