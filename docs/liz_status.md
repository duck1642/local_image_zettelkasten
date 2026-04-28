# LIZ Current Status

## Current State

LIZ is a Tauri + Svelte desktop app backed by a local FastAPI service and the existing Python ingestion pipeline.

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
- Svelte vault UI with masonry/grid layouts, advanced filtering, command prefixes, and shared infinite-scroll loading.
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

## Current Issues

- Production sidecar packaging has a build path, but the generated sidecar still needs release-build validation on a clean machine.
- Frontend accessibility warnings remain in Svelte build output.
- CSP is practical rather than strict and should be revisited after production packaging is stable.

## Still Deferred

- Search/index scaling: RAM hydration still bulk-loads pHash, tile, URL, and video signatures.
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
- `liz_architecture.md` contains durable architecture details.
- `liz_roadmap.md` contains phase history and future work.
- This file is the short current snapshot.
