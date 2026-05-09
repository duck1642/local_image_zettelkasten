# LMZ Current Status

Last updated: 2026-05-09

## Current Status

LMZ is a local media vault desktop app.

- Frontend: Tauri + Svelte.
- Backend: local FastAPI/Python API under `backend/`.
- Runtime model: SQLite for operational indexes; Markdown/YAML remains source of truth.
- Old Flet and PySide/PyQt UI paths are inactive.

Launch commands:

```powershell
python dev.py
python main.py
lmz
```

## Architecture Snapshot

- Frontend app: `frontend/src/`.
- Tauri shell: `frontend/src-tauri/`.
- Backend API: `backend/web_api.py`.
- Ingestion CLI: `backend/core.py`, launched by `main.py` or `lmz`.
- Runtime DB: `data/db/lmz_main.db`.
- Vault assets: `data/vault/assets/{hash[:2]}/{hash}.{ext}`.
- Vault notes: `data/vault/notes/{hash[:2]}/{hash}.md`.
- WD tag cache: `data/wd-tags/{hash[:2]}/{hash}.json`.
- Review quarantine: `data/review/`.
- Local ingest staging: `paths.local_ingest`, fallback `paths.input/local`.
- Online ingest staging: `paths.online_ingest`, fallback `paths.input/online`.
- Logs: `logs/raw/`, `logs/structured/`.
- Secrets: `secrets/`.

## Working Areas

- Local image, GIF, and video ingestion.
- External URL ingestion via gallery-dl and yt-dlp.
- Batch-safe Pixiv, X/Twitter, Instagram, Pinterest, YouTube community ingestion.
- SHA256 sharded vault storage.
- Markdown note generation with frontmatter topics and distilled WD fields.
- Local WD tagging for images and sampled video frames.
- Virtualized masonry/grid vault UI.
- Grouped media navigation, fullscreen focus, zoom/pan, filmstrip.
- Structured search with prefixes, commands, suggestions, and facet counts.
- Toggleable/resizable inspector.
- Markdown queue ingestion workbench.
- Review, Stats, Settings, and App Logs views.
- Structured/raw logs plus auth-status stream.
- RAM tracker.
- Local API hardening for destructive actions.

## Useful Checks

```powershell
$env:PYTHONPATH='backend'
python -B -c "import ast, pathlib; [ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path)) for path in pathlib.Path('backend').rglob('*.py')]; print('AST OK')"
python -B -c "import core, web_api, db.sqlite_operator, db.search_manager, queue_service, tagging.service; print('IMPORT OK')"
cd frontend
npm run check
npm run test:mock-vault
npm run test:large-vault
npm run build
npm run build:sidecar
git diff --check
```

Known build note: Vite may need to run outside the sandbox because it spawns helper processes.

VSCode-friendly test launchers:

```powershell
.\tests\test-mock-vault.bat
.\tests\test-mock-vault-headed.bat
.\tests\test-large-vault.bat
.\tests\test-large-vault-headed.bat
.\tests\test-playwright.bat
.\tests\test-playwright-headed.bat
.\tests\test-playwright-ui.bat
```

## Documentation Notes

- `docs/lmz_architecture.md`: durable architecture details.
- `docs/lmz_roadmap.md`: phase history and future work.
- Search syntax:
  - `>` command.
  - `a:` artist.
  - `p:` platform.
  - `t:` note-frontmatter topic.
  - `#` WD tag.
  - `;` separates structured filters.
- Search semantics:
  - Different prefix types use AND.
  - Repeated `a:` and `p:` use OR.
  - Repeated `t:` and `#` use AND.
  - Plain text terms use AND.
- Current commands include:
  - `>masonry`, `>grid`.
  - `>zoom-in`, `>zoom-out`.
  - `>toggle-inspector`.
  - `>ram-track`.
  - `>scan-auth`.
  - `>cleanup-review`.
  - `>sort-newest`, `>sort-oldest`, `>sort-artist`.
  - `>media-all`, `>media-image`, `>media-video`.

## Done Tasks

- Project renamed to Local Media Zettelkasten / LMZ.
- Python source root renamed from `src/` to `backend/`.
- Old full-DOM masonry/grid renderers archived; virtualized renderers are active.
- Layout/zoom config writes use the shared frontend config store.
- Vault header simplified; sort/media/layout/zoom actions moved to commands.
- Auth status scan implemented:
  - startup scan.
  - `/api/auth/scan`.
  - `>scan-auth`.
  - auth log dropdown.
  - secret values are not logged.
- Auth config cleanup:
  - `cookies_path` uses relative `secrets/cookies.txt`.
  - Pixiv token loads from `secrets/.secrets.yaml`.
  - `/api/config` strips secret keys.
  - relative cookie paths resolve from project root.
- RAM tracker implemented:
  - `/api/system/memory`.
  - footer display.
  - persisted `>ram-track`.
- Fullscreen media zoom/pan implemented.
- Wide/fullscreen grouped-media filmstrip implemented.
- Inspector toggle and resize implemented.
- Vault search header split from inspector column.
- Top vault `Add Files` button removed.
- Frontend mojibake and unused default assets cleaned up.
- Svelte accessibility warnings cleared in latest reviewed pass.
- Renderer performance fixes:
  - no `will-change` layer spam.
  - `translate3d(...)` positioning.
  - grid row-math visibility.
  - batched/log-gated summaries.
  - safer media MIME helpers.
  - cleanup for timers/SSE/fetches.
- Backend hardening:
  - session key for mutating API calls.
  - local-only CORS restrictions.
  - path validation for queue/log/review endpoints.
  - bulk delete API.
  - safe delete ordering.
  - review count endpoint.
  - sidecar build path.
  - practical Tauri CSP.
- Review workflow hardening:
  - `keep` defers without DB ingest.
  - `variant` ingests with duplicate bypass.
  - `replace` ingests first, deletes old target after.
  - cleanup failures route to `pending_cleanup`.
  - Cleanup section added.
  - `/api/review/cleanup` retries cleanup and removes orphan sidecars.
  - image/video compare panes render.
  - review asset/action URLs encode filenames.
  - unique review storage names avoid collisions.
  - clean startup always mounts `/review-assets`.
  - App Logs includes `review.jsonl`.
- Review smoke follow-ups fixed:
  - `/api/review` tuple-unpack crash.
  - review logging argument collision.
  - false failure after successful variant commit.
  - best-effort retry cleanup after variant ingest.
- Local ingestion safety:
  - originals are staged before processing.
  - originals are not moved into review.
  - double-start guard set before worker scheduling.
  - retry preserves defaults and `skip_similarity`.
  - status exposes `phase`, `run_id`, `scanned`, `staged`.
  - backend results capped to last 500.
  - folder expansion streams in the worker instead of pre-sorting/materializing the tree.
- Online queue safety:
  - `as_completed` import fixed.
  - deferred and crash-preserved URLs remain in queues.
  - stop-after-current keeps not-yet-started URLs.
  - worker/platform crashes are logged and preserved.
  - queue rewrite logs original/removed/remaining counts.
- Search prefix remap completed:
  - `>` command.
  - `a:` artist.
  - `p:` platform.
  - `t:` topic.
  - `#` WD tag.
- Metadata/index performance:
  - disposable SQLite metadata index for topics and WD tags.
  - startup repair, watchdog reindex, status endpoint, rebuild endpoint.
  - topic/WD filters, facets, suggestions, and detail metadata read through index after initial backfill.
  - legacy YAML/cache fallback remains before index readiness.
- Query/render hot path fixes:
  - SQLite indexes for date/hash, artist/date/hash, platform, source artist, MIME/date, source URL.
  - artist-sort cursor pagination fixed.
  - renderer no longer builds full visual hash arrays.
  - masonry visible lookup uses bounded binary-search scanning.
- VP-tree indexing:
  - video/audio signatures append to pending items.
  - queries search built tree plus pending signatures.
  - batch updates rebuild once after batch.
- Recent validation-finding fixes:
  - vault grouping rebuilds from updated item lists.
  - masonry cache keeps geometry but refreshes current group data.
  - fullscreen pan state resets after drag and when zoom returns to 1.
  - production API startup retry handles delayed sidecar readiness.
  - ingest paths honor `paths.local_ingest` and `paths.online_ingest`.
- Mock-vault validation harness:
  - isolated fixture lives under `tests/fixtures/mock-vault/`.
  - frontend Playwright mocks API/media/review/RAM without touching the real vault.
  - backend pytest uses `LMZ_CONFIG_PATH` and temp fixture copies.
  - batch launchers live under `tests/` for VSCode terminal use.
  - `source_url` and platform are read-only in Inspector; artist remains editable.
  - mock-vault tests cover artist edit refresh, source/platform read-only behavior, masonry stale-data prevention, fullscreen pan/backdrop behavior, review filename encoding, video path rendering, and RAM unavailable state.

## Deferred / Will Do Later

- Set 6 security hardening:
  - local API auth/origin/path review.
  - mutating endpoint protection pass.
  - secrets/runtime exposure review.
  - packaging-time security checks.
- Set 7 Tauri/runtime stabilization:
  - sidecar startup/shutdown lifecycle.
  - dynamic port/runtime coordination.
  - production path/config validation.
  - clean-machine package validation.
  - full Tauri stack alignment pass.
- Dynamic sidecar port binding; current port remains `8000`.
- Custom context menu for vault tiles.
- Interactive tag management in inspector.
- Native drag-and-drop import.
- Animation-aware GIF handling beyond first-frame thumbnail/tag behavior.
- Artist grouping.
- Context-aware search suggestions.
- In-memory facet cache for faster topic/WD counts.
- Persistent search index/facet tables beyond current derived metadata index.
- Search chips.
- Search/index scaling:
  - RAM hydration still bulk-loads pHash, tile, URL, and video signatures.
- Config caching:
  - `get_config()` still reparses YAML often.
  - safe invalidation is needed before broad caching.
- Video embedding performance:
  - V1 still extracts five frames with separate ffmpeg calls.
- Video hover preview strategy:
  - current hover preview can download original video.
  - options: file-size cap, backend preview clip endpoint, animated WebP thumbnail.
- YouTube community partial policy:
  - one failed expected image can still keep the post retryable.
- Source URL normalization migration:
  - existing rows are backfilled lazily by `init_database()`.
  - no standalone migration tool yet.
- Timestamp consistency:
  - local Python timestamps and SQLite UTC defaults still coexist.
- Thumbnail helper cleanup:
  - small asset-path helper duplication remains.
- Tauri package alignment:
  - frontend `@tauri-apps/api` is pinned to `2.10.1` to match Rust `tauri 2.10.x`.
  - full Tauri stack upgrade to `2.11.x` is deferred.

## Done But Needs Check

- Virtual renderer:
  - automated large-vault Playwright checks pass for 10k/100k masonry/grid and grouped mixed media.
  - needs real-vault smoke for offscreen video unmount behavior.
  - needs grouped media active-index smoke after scroll out/in.
  - needs narrow/wide zoom stability smoke.
- Resizable inspector:
  - verify separator renders as one clean line.
  - verify hover handle alignment.
  - verify content across 320-760 px.
- Fullscreen zoom/pan:
  - verify video controls remain reliable.
- Filmstrip:
  - verify sizing, animation, thumbnail ergonomics, active-state visibility.
- RAM tracker:
  - verify real footer polling behavior over long app sessions.
- GIF behavior:
  - original GIF animation should work in focus and markdown.
  - vault/inspector thumbnails are static first-frame previews.
  - WD tagging and duplicate detection inspect first frame.
- Production sidecar packaging:
  - build path exists.
  - needs clean-machine release validation.
- Review workflow:
  - `keep` leaves item/sidecar in review with no DB insert.
  - `delete` removes item/sidecar and decrements count.
  - `variant` ingests once and removes review source.
  - variant failure returns non-2xx and keeps item pending.
  - real image/video review pairs render in both panes.
- Review Windows file-lock edge case:
  - cleanup failures should remain visible as `pending_cleanup`.
  - Cleanup section should retry them.
- Ingestion close-flow:
  - close during local ingest prompts stop-after-current and exits after current item.
  - close during online ingest prompts stop-after-current and exits after in-flight workers settle.
  - deferred online URLs remain retryable after stop-after-current.
- Local ingestion:
  - successful local ingest leaves originals untouched.
  - similar duplicate moves only staged copy to review.
  - real large folder starts without materializing/sorting whole tree.
- Review storage:
  - same-name files quarantine to unique storage filenames.
  - sidecars retain human `original_name`.
  - staged local names display as originals.
  - `/review-assets/{filename}` works on clean startup.
- Online queue safety:
  - normal and force queues preserve only their own deferred URLs.
  - failed queue receives only real failed URLs.
  - stop-after-current leaves not-yet-started URLs in source queue.
  - platform manager crash preserves that platform bucket.
- Metadata edit flow:
  - real-vault artist edit updates tile and inspector.
  - platform/source URL stay read-only in Inspector.
- Sidecar/API startup:
  - simulated delayed backend does not permanently fail first production API calls.
- P0 data integrity:
  - Markdown-owned manual metadata implemented for `title`, `artist`, `date_added`, `topics`, and WD fields.
  - PATCH artist/topics writes DB cache and Markdown through one rollback-capable path.
  - metadata reindex reads Markdown `artist` and non-empty `date_added` back into SQLite.
  - WD YAML fields are authoritative, including explicit empty tag lists.
  - ingest note writes use `atomic_write_text`.
  - review replace preserves old manual YAML metadata onto the replacement.
  - one-time manual metadata migration script added.
  - Resolved Gemini findings:
    - Broken transactional boundaries in item PATCH.
    - Inconsistent non-atomic ingest Markdown writes.
    - WD tags resurrecting from JSON cache.
    - impossible explicit zero WD tags.
    - manual Markdown `artist` / `date_added` edits ignored and overwritten.
    - review replace destroying old manual metadata.
  - targeted backend pytest passes; needs real-vault migration/reindex smoke before closing fully.

### Useful Checks

- **Frontend Dependencies:** Run `npm outdated` in the `frontend/` directory to see a table of current vs. latest npm packages.
- **Backend Dependencies:** Run `pip list --outdated` with your Python virtual environment activated to check for updates on PyPI. Note: `yt-dlp` and `gallery-dl` are auto-updated by the maintenance script.

## Current Issues

- **[Found during Gemini's inspection]** `frontend/src/lib/MediaFocus.svelte` has no browser/HTML5 fullscreen fallback. Outside Tauri, fullscreen mode may only update LMZ UI state while native/browser fullscreen silently does nothing. Crash risk is low because Tauri fullscreen calls are guarded.

### Backend Architectural & Performance Issues (Found during Gemini's inspection)

1. **N+1 Query & Synchronous Disk I/O Block**
   - **Severity:** CRITICAL
   - **File:** `backend/web_api.py` (~line 900 in `_get_items_sync`)
   - **The Mechanism:** When the metadata index is missing/hydrating and a user filters by topic or tag, the fallback logic executes a `LIMIT 100000` SQL query. It then loops over these rows in Python, synchronously calling `load_note_topics()` and `_wd_names_for_hash()` for each row until the pagination limit is reached.
   - **Why it's broken:** Reading thousands of small `.md` and `.json` files from disk synchronously inside a single-threaded API route will entirely block the backend event loop, causing massive latency or frontend timeouts on large vaults.

2. **SQLite Connection Thrashing**
   - **Severity:** HIGH
   - **File:** `backend/processor.py` (line 230 in `process_file`) & `backend/external_ingestion.py`
   - **The Mechanism:** Every invocation of `process_file` calls `conn = init_database()`, establishing a brand-new connection. During online ingestion, `ExternalIngestor` maps `_worker_item` to a `ThreadPoolExecutor`.
   - **Why it's broken:** When downloading galleries with concurrent workers, 10+ threads are continuously spinning up, querying, committing, and tearing down hundreds of distinct SQLite connections. This causes significant, unnecessary OS-level lock contention and CPU overhead, despite WAL mode.

3. **Redundant FFmpeg Subprocesses**
   - **Severity:** MEDIUM
   - **File:** `backend/fingerprint.py` (~line 92 in `extract_sampled_video_frames`)
   - **The Mechanism:** To generate an AI visual embedding, the code calculates 5 timestamps and loops over them, calling `extract_video_frame()` each time. That function executes `subprocess.run(['ffmpeg', ...])`.
   - **Why it's broken:** Generating an embedding requires spawning 5 separate OS-level FFmpeg processes per video. Each process must independently open the video, parse the container headers, and seek to the target frame, severely slowing down video ingestion.

4. **ML Model Initialization Thrashing**
   - **Severity:** HIGH
   - **File:** `backend/tagging/service.py` (inside `tag_media`)
   - **The Mechanism:** Every invocation of `tag_media` creates a brand new `ort.InferenceSession` and loads the WD-Tagger model weights into RAM/VRAM.
   - **Why it's broken:** Loading an ONNX model is incredibly CPU and memory intensive (often taking 0.5 - 3 seconds). Doing this per-image instead of caching the session globally at the module level means a batch of 100 images forces the backend to allocate and destroy the ML model 100 separate times.

5. **O(N) Full-Table Scan for Stale Metadata**
   - **Severity:** MEDIUM (High at scale)
   - **File:** `backend/metadata_index.py` (`stale_metadata_hashes`)
   - **The Mechanism:** The watchdog/repair worker queries `SELECT ... FROM items LEFT JOIN item_metadata_files` and immediately calls `.fetchall()`. It then loops over the entire result set in Python to find stale rows.
   - **Why it's broken:** For a vault with 100,000 items, `.fetchall()` loads a 100,000-row tuple array into Python memory every time the repair worker looks for the next batch of 500 items. This causes massive RAM spikes and stalls the SQLite connection. It should stream via `.fetchmany()`.

6. **I/O Bound Thumbnail Generation CPU Locking**
   - **Severity:** LOW (Medium on UX)
   - **File:** `backend/thumbnails.py` (`generate_image_thumbnail`)
   - **The Mechanism:** Thumbnails are generated dynamically using `Image.thumbnail` from Pillow.
   - **Why it's broken:** Standard image resizing is highly CPU-bound. If a user rapidly scrolls the Masonry view and requests 100 missing thumbnails, the FastAPI thread pool (`asyncio.to_thread`) fills up with CPU-blocking tasks, potentially stalling other API endpoints (like search or queue status).

### Low-Level Backend Inconsistencies (Found during Gemini's inspection)

1. **Swallowed Exceptions (Silent Failures)**
   - **File:** `backend/utils.py` (`calculate_phash`), `backend/fingerprint.py` (`get_audio_fingerprint`, `get_visual_embedding`)
   - **Issue:** Critical errors (corrupt images, missing FFmpeg, OOM ML loading) are swallowed by bare `except Exception:` blocks that return fallback values without logging the traceback. This makes debugging edge-cases in user-provided media nearly impossible.

2. **Mixing `os.path` with `pathlib.Path`**
   - **File:** `backend/scripts/update_downloaders_and_regenerate_notes.py` (line 39)
   - **Issue:** The script uses `if not os.path.exists(DB_PATH):` instead of the modern, idiomatic `if not DB_PATH.exists():` used everywhere else in the project.

3. **Naive Subprocess Buffering**
   - **File:** `backend/fingerprint.py`
   - **Issue:** Uses `subprocess.run(..., capture_output=True)` for FFmpeg. If FFmpeg encounters a corrupt video and dumps 100,000 lines of warnings into `stderr`, Python will buffer the entire string into memory. It should route `stderr=subprocess.DEVNULL` unless explicitly parsing it to prevent memory ballooning.

### Hidden Backend Fragilities (Found during Gemini's inspection)

1. **The "Pause The World" Thread Lock**
   - **File:** `backend/db/search_manager.py`
   - **Issue:** The `SearchManager` uses a single `threading.Lock()`. When `_rebuild_deferred_indexes_locked` rebuilds the VP-Trees (which can take several seconds of pure Python math), every single API request trying to query an image or video is completely blocked. This will cause the frontend to stutter or API requests to timeout under load.

2. **Windows File-Lock Hostility**
   - **File:** `backend/web_api.py`
   - **Issue:** When the frontend renders an image/video from `/review-assets`, the Chromium webview often holds an OS-level read-lock on Windows. If the user clicks "Delete" or "Variant", `path.unlink()` will fail with a permission error. The backend catches this and pushes it to `pending_cleanup`, but it's a fragile band-aid. The frontend should actively unmount/hide the media element before sending the POST request.

3. **External Downloader Dependency Coupling & Long Timeouts**
   - **File:** `backend/downloaders/gallery_dl_wrapper.py`, `backend/downloaders/yt_dlp_wrapper.py`
   - **Issue:** `gallery-dl` and `yt-dlp` run via `subprocess.run()` with built-in OS-level timeouts (5 minutes and 10 minutes respectively). While these timeouts successfully prevent permanent thread deadlocks if a site rate-limits the downloader, waiting up to 10 minutes for a stuck subprocess to die can consume a `ThreadPoolExecutor` worker slot for a very long time, making the UI queue appear "frozen" to the user.

### Deferred Work / Will Do Later

- **Maintenance Tools UI Integration:** The current maintenance scripts for capturing cookies (`backend/scripts/auth_cookies_builder.py`) and authenticating with Pixiv (`backend/scripts/auth_pixiv_auto.py`) only run in the CLI. These need to be connected to the Svelte UI so users can manage authentication directly from the desktop application without dropping into the terminal.

## Issue Remediation Plan

### P1 Performance Hotspots

- WD ONNX session recreated per `tag_media()`.
- Metadata stale scan full `.fetchall()`.
- N+1 fallback scan for topic/WD filters when metadata index is not ready.
- SearchManager lock blocks queries during VP-tree rebuild.
- SQLite connection churn during concurrent ingestion.

### P2 UX / Runtime Robustness

- Browser/HTML5 fullscreen fallback missing.
- Windows review file-lock risk; frontend should unmount review media before actions.
- Downloader subprocess timeouts can hold worker slots for 5-10 minutes.
- Thumbnail generation bursts can saturate worker threads.

### P3 Cleanup / Observability

- Swallowed exceptions in `calculate_phash`, `get_audio_fingerprint`, and `get_visual_embedding`.
- Naive subprocess buffering.
- `os.path.exists(DB_PATH)` cosmetic script cleanup.
- Architecture/status docs drift.

### Recommended Fix Batches

1. `os.path` cleanup; logging for swallowed exceptions.
2. Windows review unmount/action flow.
3. ONNX session cache; stale metadata scan streaming; N+1 fallback mitigation.
4. SearchManager lock/rebuild strategy; SQLite connection lifecycle; downloader timeout/cancel behavior; thumbnail throttling/cache behavior.
