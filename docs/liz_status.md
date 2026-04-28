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

The old Flet and PySide/PyQt UI paths are no longer active. `gui.py`, `src/ui/`, PySide dependencies, and the `liz-gui` entry point were removed.

## Working Areas

- Local file ingestion for images, GIFs, and videos.
- External URL ingestion through gallery-dl and yt-dlp.
- Batch-safe ingestion for Pixiv, X/Twitter, Instagram, Pinterest, and YouTube community posts.
- SHA256-based vault storage with sharded assets and notes.
- SQLite runtime index for asset metadata and duplicate checks.
- Markdown note generation with note-frontmatter topics.
- Local WD tag cache under `data/wd-tags/{hash[:2]}/{hash}.json`.
- Distilled WD tags in markdown frontmatter.
- Svelte vault UI with masonry/grid layouts.
- Svelte inspector with metadata editing, grouped source navigation, tagging action, copy/delete/open actions.
- Markdown queue ingestion workbench.
- Review view.
- Settings view.
- Structured log viewer with normal/raw modes.
- Local API hardening for destructive actions.

## Current Architecture Snapshot

- UI: Tauri + Svelte.
- Backend API: `src/web_api.py`.
- Ingestion CLI: `src/core.py`, launched by `main.py` or `liz`.
- Runtime database: `data/db/liz_main.db`.
- Vault assets: `data/vault/assets/{hash[:2]}/{hash}.{ext}`.
- Vault notes: `data/vault/notes/{hash[:2]}/{hash}.md`.
- WD cache: `data/wd-tags/{hash[:2]}/{hash}.json`.
- Logs: `logs/raw/` and `logs/structured/`.
- Secrets: `secrets/`.

SQLite stores runtime asset/index metadata only. Manual topics and WD tags live outside SQLite.

## Recent Hardening Completed

- Mutating API endpoints now require a local UI session key.
- CORS is restricted to local/Tauri origins.
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

## Still Deferred

- Search/index scaling: RAM hydration still bulk-loads pHash, tile, URL, and video signatures.
- Config caching: `get_config()` still reparses YAML often; caching needs explicit invalidation for Settings edits.
- Video embedding performance: V1 still extracts five frames using separate ffmpeg calls.
- YouTube community partial policy: one failed expected image still makes the post incomplete and retryable.
- Source URL normalization migration: existing rows are backfilled lazily by `init_database()`, not by a standalone maintenance tool.
- Timestamp consistency: local Python timestamps and SQLite UTC defaults still coexist.
- Thumbnail helper cleanup: `thumbnails.py` still has a small asset-path helper duplication.
- Frontend accessibility warnings remain in Svelte build output.
- `src/` has not been renamed to `backend/`.

## Useful Checks

```powershell
$env:PYTHONPATH='src'
python -B -c "import core, web_api, db.sqlite_operator, db.search_manager, queue_service, tagging.service; print('IMPORT OK')"
python -B -c "import ast, pathlib; [ast.parse(path.read_text(encoding='utf-8'), filename=str(path)) for path in pathlib.Path('src').rglob('*.py')]; print('AST OK')"
cd frontend
npm run build
```

Known build note: Vite may need to run outside the sandbox because it spawns helper processes. Current build succeeds with Svelte accessibility warnings.

## Documentation Notes

- `docs/` is local and ignored by GitHub uploads.
- `liz_architecture.md` contains durable architecture details.
- `liz_roadmap.md` contains phase history and future work.
- This file is the short current snapshot.
