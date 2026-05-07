# LMZ Current Status

Last updated: 2026-05-07

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

SQLite stores runtime asset/index metadata plus a disposable derived topic/WD query index. Markdown/YAML remains the source of truth.

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

## Current Issues

### Critical

- Online ingestion can crash before work starts. Done (will be checked).
  - Cause: `as_completed(futures)` is used but `as_completed` is not imported from `concurrent.futures`.
  - Code: `backend/external_ingestion.py:4`, `backend/external_ingestion.py:65`.
- Review `replace` can destroy the existing vault item before replacement succeeds. Done (will be checked).
  - Cause: target item is deleted first, then `process_file()` runs. If ingest fails, the old item is already removed from DB/assets/notes.
  - Code: `backend/web_api.py:1513`, `backend/web_api.py:1521`.

### High

- `cleanup_failed` review items can be hidden automatically. Done (will be checked).
  - Cause: `_resolve_review_entries()` converts any review file whose hash exists in DB into `resolved_variant`, unless already in resolved states. `cleanup_failed` is not resolved, so it gets overwritten.
  - Code: `backend/web_api.py:94`, `backend/web_api.py:1385`.
- `>cleanup-review` does not clean `cleanup_failed` items. Done (will be checked).
  - Cause: cleanup loop only processes `REVIEW_RESOLVED_STATES`; `cleanup_failed` is in pending states.
  - Code: `backend/web_api.py:89`, `backend/web_api.py:1571`.
- Local ingest can move original user files into review. Done (will be checked).
  - Cause: local worker calls `process_file(... delete_source=False)`, but duplicate quarantine uses `shutil.move(filepath, dest_path)` regardless of `delete_source`.
  - Code: `backend/web_api.py:1269`, `backend/processor.py:207`.
- Local ingest can start two workers. Done (will be checked).
  - Cause: endpoint checks `LOCAL_INGEST_STATE["running"]`, then expands paths and schedules worker. `running=True` is only set inside the worker later.
  - Code: `backend/web_api.py:1303`, `backend/web_api.py:1250`.

### Medium

- Stop-after-current can drop deferred online URLs. Done (will be checked).
  - Cause: deferred URLs are collected in `all_remaining`, but final queue write always clears the source queue with `_write_back([])`.
  - Code: `backend/external_ingestion.py:73`, `backend/external_ingestion.py:88`.
- Review `keep` behavior is inconsistent in the frontend. Done (will be checked).
  - Cause: backend sets state `deferred`, which remains pending. Frontend treats the successful action as resolved and removes the item from the local list.
  - Code: `backend/web_api.py:1497`, `frontend/src/lib/ReviewView.svelte:106`.
- Review action URL can break for special filenames. Done (will be checked).
  - Cause: filename is interpolated directly into the URL path without `encodeURIComponent`.
  - Code: `frontend/src/lib/ReviewView.svelte:92`.
- Review filename collision is possible. Done (will be checked).
  - Cause: duplicate quarantine writes to `REVIEW_DIR / filepath.name`; no hash/session suffix is added.
  - Code: `backend/processor.py:206`, `backend/processor.py:250`.
- Orphan review sidecars are not cleanup candidates. Done (will be checked).
  - Cause: cleanup starts from media files only; `.json` sidecars without media are excluded before cleanup logic runs.
  - Code: `backend/web_api.py:1335`, `backend/web_api.py:1347`.
- Local retry loses metadata defaults. Done (will be checked).
  - Cause: retry endpoint reuses only `failed_paths`; it starts the worker with `{}` defaults and `skip_similarity=False`.
  - Code: `backend/web_api.py:1322`, `backend/web_api.py:1328`.
- `/review-assets` may not mount on clean startup. Done (will be checked).
  - Cause: static mount only happens if `REVIEW_DIR.exists()` at API import time. Later directory creation does not mount the route.
  - Code: `backend/web_api.py:328`.

### Low

- Documented Python AST check fails on BOM files. Done (will be checked).
  - Cause: command uses `encoding='utf-8'`; several backend files start with UTF-8 BOM.
  - Code/doc: `docs/lmz_status.md:285`, `backend/core.py:1`.
- Pixiv token is still in normal config.
  - Cause: docs say secrets-backed, but `config/config.yaml` has `external_tools.pixiv_token`.
  - Code/config: `config/config.yaml:3`.
- Docs contain old search syntax.
  - Cause: current code uses `p:`, `t:`, `#`; status doc still says repeated `@` and `*` in one section.
  - Code/doc: `frontend/src/lib/search.ts:26`, `docs/lmz_status.md:234`.
- Local folder expansion can block API. Done (will be checked).
  - Cause: recursive `path.rglob("*")` and sorting run synchronously before the background worker starts.
  - Code: `backend/web_api.py:1215`.
- Local ingest results can grow in memory. Done (will be checked).
  - Cause: backend appends every result into process-global `LOCAL_INGEST_STATE["results"]`; frontend only displays the last 120.
  - Code: `backend/web_api.py:1285`, `frontend/src/lib/Ingestion.svelte:485`.
- Topic/WD filters are expensive.
  - Cause: query loads up to 100,000 DB rows, then parses markdown/tag data in Python.
  - Code: `backend/web_api.py:656`, `backend/web_api.py:668`.
- Video VP-tree rebuilds on every add.
  - Cause: `VPTreeSearcher.add()` rebuilds the tree immediately. Batch updates repeatedly rebuild.
  - Code: `backend/db/searchers.py:25`, `backend/db/searchers.py:29`.

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
  - `/api/config` strips secret keys so Settings saves cannot write Pixiv token back to `config.yaml`
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
- Ingestion safe-exit + stop-after-current wiring completed. Done (will be checked):
  - Added close-request guard in Tauri/Svelte flow: if ingestion is running, app asks to stop after current item and exit.
  - Added backend ingest runtime endpoint for online/local running state.
  - Added backend stop-after-current endpoint for online/local ingestion workers.
  - Online worker now stops scheduling new URLs after stop is requested and lets in-flight items finish.
  - Local worker now stops before next item when stop is requested and lets current item finish.
- Review `variant` cleanup semantics hardened. Done (will be checked):
  - `variant`/`replace` no longer report full success when review file deletion fails.
  - On delete-failure after ingest, item is marked `cleanup_failed` and kept pending in review with warning response.
  - Prevents “review empty” false-positive while review file still exists.
- Review cleanup command added. Done (will be checked):
  - New vault command `>cleanup-review` triggers `POST /api/review/cleanup`.
  - Command logs cleanup `cleaned` and `failed` counts into App Logs.
- Set 1 review workflow hardening completed. Done (will be checked):
  - Review sidebar is split into Pending and Cleanup sections.
  - `keep` stays visible as `deferred`.
  - `variant` uses duplicate bypass and moves cleanup failures to `pending_cleanup`.
  - `replace` ingests first, then deletes the old target; old-delete failure keeps both vault items.
  - `delete` cleanup failure moves the item to Cleanup.
  - `/api/review/cleanup` retries pending cleanup and removes orphan sidecars.
  - Review counts now separate pending and cleanup.
  - Review action and review asset URLs encode filenames with `encodeURIComponent`.
  - `cleanup_failed` sidecars are treated as `pending_cleanup`.
  - App Logs includes `review.jsonl`.
- Logger package tracking fix completed. Done (will be checked):
  - Source package moved from ignored `backend/logs/` to tracked `backend/logger/`.
  - Backend imports now use `from logger import ...`.
  - Review structured logging moved from `web_api.py` into `backend/logger/logger.py`.
  - `.gitignore` now ignores only root runtime `/logs/`.
  - `pyproject.toml` package include now uses `"logger"`.
- Set 2 local ingestion safety completed. Done (will be checked):
  - Online temp downloads now use `data/input/online/{url_hash}/`.
  - Local ingest now stages copies under `data/input/local/{run_id}/`.
  - Local worker passes staged files to `process_file(... delete_source=True)`.
  - User originals are no longer passed directly to `process_file()`.
  - Local start marks `running=True` before worker scheduling.
  - Local retry preserves last defaults and `skip_similarity`.
  - Local status now exposes `phase`, `run_id`, `scanned`, and `staged`.
  - Backend local results are capped to the last 500.
  - Local panel displays phase/scanned/staged counters.
- Set 3 review storage safety completed. Done (will be checked):
  - Review quarantine now uses unique storage names with `review_id`, short hash, and safe original name.
  - Review sidecars now store `review_id`, `storage_name`, `original_name`, `source_path`, `staged_from`, and `state`.
  - `/api/review` returns both storage `filename` and human `display_name`.
  - Review UI displays `display_name` while using `filename` for asset/action URLs.
  - `/review-assets` is always mounted after creating `data/review`.
  - Legacy review files remain readable with best-effort sidecar defaults.
- Set 4 online queue safety completed. Done (will be checked):
  - Added missing `as_completed` import for platform-level online ingestion.
  - Online source queues now keep deferred and crash-preserved URLs instead of clearing all links.
  - Successful, skipped, and real failed URLs are removed from the source queue.
  - Worker crashes are logged to failed links and counted as errors.
  - Platform manager crashes preserve that platform bucket in the same source queue.
  - Stop-after-current preserves not-yet-started URLs in the current queue.
  - Queue rewrite logging now reports original, removed, and remaining counts.
- Search prefix remap + UI guide order updated. Done (will be checked):
  - Prefix mapping changed to: `> cmd`, `a: artist`, `p: platform`, `t: topic`, `# wd-tag`.
  - Search parser and active-segment detection updated for `p:` and `t:`.
  - Settings and search placeholder text updated to the same order.

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
  - Set 1 changed this to `pending_cleanup` + Cleanup section. Done (will be checked).
- Ingestion close-flow validation:
  - verify close while local ingest is running prompts stop-after-current and exits only after current item completes.
  - verify close while online ingest is running prompts stop-after-current and exits only after in-flight workers settle.
  - verify deferred online URLs remain in retry path after stop-after-current.
- Set 2 local ingestion validation:
  - verify successful local ingest leaves original files untouched.
  - verify similar local duplicate moves only the staged copy to review.
  - verify two rapid local starts return one success and one `409`.
  - verify local retry reuses defaults and `skip_similarity`.
  - verify large folder start returns quickly while status enters `scanning`.
  - verify online download temp folders are created under `data/input/online/`.
- Set 3 review storage validation:
  - verify two same-name files quarantine to different review storage filenames.
  - verify sidecars retain the same human `original_name`.
  - verify local staged names display as original names in Review UI.
  - verify review actions still work with encoded storage `filename`.
  - verify `/review-assets/{filename}` works on clean startup.
  - verify cleanup/orphan sidecar handling still works with `media.ext.json`.
- Set 4 online queue safety validation:
  - verify normal and force queues preserve only their own deferred URLs.
  - verify failed queue receives only real failed URLs.
  - verify stop-after-current leaves not-yet-started URLs in the source queue.
  - verify platform manager crash preserves that platform bucket.
  - verify startup import works with `as_completed`.
- Review `variant` strict cleanup validation:
  - verify successful ingest + failed review-file delete returns warning and keeps item in Cleanup (`pending_cleanup`).
  - verify successful ingest + successful review-file delete returns success and removes item from pending list.

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
- `p:` platform
- `t:` note-frontmatter topic
- `#` WD tag
- `>` command
- `;` separates structured filters

Current operational commands include:

- `>masonry`, `>grid`
- `>zoom-in`, `>zoom-out`
- `>toggle-inspector`
- `>ram-track`
- `>scan-auth`
- `>cleanup-review`
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
- Topic/WD filters and counts use the SQLite metadata index after initial backfill, with legacy YAML/cache fallback before it is ready.
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
  - Done (will be checked): Windows file locks now route review files into `pending_cleanup` instead of reporting clean success.
  - Done (will be checked): cleanup-lag handling is exposed through the Review Cleanup section.

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
python -B -c "import ast, pathlib; [ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path)) for path in pathlib.Path('backend').rglob('*.py')]; print('AST OK')"
cd frontend
npm run check
npm run build
npm run build:sidecar
```

Known build note: Vite may need to run outside the sandbox because it spawns helper processes.

## Documentation Notes

- `lmz_architecture.md` contains durable architecture details.
- `lmz_roadmap.md` contains phase history and future work.
