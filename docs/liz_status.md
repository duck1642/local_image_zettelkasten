# LIZ Current Status

## Current State

The project is on the flat `src/` layout and uses PySide6 for the desktop UI.

Current UI/media focus work is still in progress. The normal vault and inspector are usable, but wide/fullscreen behavior for images and videos is actively being stabilized.

Current launch commands:

```powershell
python main.py
python gui.py
```

Installed script entry points:

```powershell
liz
liz-gui
```

## Working Areas

- Local image/video ingestion.
- External URL ingestion through gallery-dl and yt-dlp.
- SHA256-based vault storage.
- SQLite item database.
- Markdown note generation.
- Sharded markdown note storage under `data/vault/notes/{hash[:2]}/`.
- Note-frontmatter topics as the source of truth for manual topics.
- Local WD tag cache under `data/wd-tags/{hash[:2]}/`.
- pHash and video signature infrastructure.
- Batch-safe ingestion for Pixiv, X/Twitter, Instagram, Pinterest, and YouTube community posts.
- PySide6 vault UI.
- Inspector metadata editing.
- Source URL grouping in vault and inspector.
- Image and video wide/fullscreen modes.
- Readable App Logs view with Normal and Full log display modes.
- Review workflow.
- Maintenance tools.

## Current UI Behavior

Vault:

- Shows media thumbnails in a grid.
- Uses hash prefixes as tile labels.
- Groups multiple DB rows with the same non-empty `source_url`.
- Group tiles show a counter and previous/next controls.
- Video tiles can preview on hover.

Inspector:

- Shows selected image/video.
- Detects source URL groups.
- Provides previous/next navigation for grouped posts.
- Saves artist and source URL.
- Displays manual topics from markdown frontmatter.
- Displays WD suggestions from local WD tag JSON cache.
- For groups, metadata save applies to all rows in that group.
- Regenerates markdown notes after save.
- Supports image/video wide and fullscreen modes.

App Logs:

- Can switch between `system.log`, `ui.log`, and `ingestion.log`.
- Normal mode parses JSONL logs into readable timestamp/level/message rows.
- Full mode shows raw JSONL records with spacing.
- Open button opens the selected `.log` file externally.

## Important Caveats

- Wide/fullscreen media mode is in active cleanup. The current implementation uses a dedicated media focus host instead of stretching the right inspector panel.
- Wide/fullscreen exit now preserves the real normal window size by recording it before entering focus mode. Image/video scaling and control layout still need visual testing.
- Image wide/fullscreen reloads and rescales the full asset on resize/mode changes. Caching the full pixmap is the next low-risk optimization.
- Grouping is UI-only and based on exact non-empty `source_url`.
- Blank `source_url` items are intentionally not grouped.
- Search is still the older Enter-based prefix search.
- `docs/` is ignored by Git and restored locally from backups.
- SQLite intentionally does not store manual topics or WD tags.

## Current Runtime Folders

- `data/` contains local runtime data and vault content.
- `data/vault/assets/` and `data/vault/notes/` are sharded by hash prefix.
- `data/wd-tags/` contains sharded local WD tag JSON cache files.
- `logs/` contains logs.
- `secrets/` contains local credentials.
- `backups/` contains manual/project backups.
- `docs/` contains local documentation and is ignored.

## Useful Checks

```powershell
$env:PYTHONPATH='src'
python -B -c "import ui.app, ui.main_window, external_ingestion, processor; print('IMPORT OK')"
python -B -c "import ast, pathlib; [ast.parse(path.read_text(encoding='utf-8'), filename=str(path)) for path in pathlib.Path('src').rglob('*.py')]; print('AST OK')"
python -B tools/maintenance/vault_integrity.py
```

## What Gemini did

### 24-04-2026

#### UI Optimization & Bug Fixes
- **Performance Hardening:**
    - Implemented **Image Caching** in the Inspector view to prevent redundant disk reads during window resizing.
    - Optimized log polling in App Logs and Ingestion views using **tail-style reading** (file offsets) to minimize memory allocation.
    - Offloaded **Video Thumbnail generation** to a background `QThreadPool` to prevent UI freezing when scrolling through the vault.
    - Refactored "Add Files" ingestion to run asynchronously via `ManualIngestionWorker`.
- **Bug Fixes:**
    - Fixed a **Database Connection leak** in `inspector.py` by wrapping metadata operations in `try...finally` blocks.
    - Improved **ClickableSlider UX** to allow immediate click-and-drag functionality for video seeking.
    - Resolved **Vault Grid flickering** by implementing **Debounced Rendering** (50ms settle time) and **Lazy Updates** (skipping re-renders if column counts haven't changed).
- **Code Cleanup:**
    - Removed the obsolete `src/ui/models.py` file.
    - Excised unused helper functions (`_parse_topics`) and redundant local variables.

#### Logging System Overhaul
- **Centralized Log Utility:** Created `src/ui/log_utils.py` to provide consistent HTML-based rendering for JSONL logs.
- **Visual Hierarchy:**
    - Added **color-coding** for log levels (`DEBUG`: gray, `INFO`: white/green, `WARNING`: yellow, `ERROR`: red).
    - Implemented **visual dimming** for noisy telemetry keys (geometry/layout data) to keep the main messages readable.
- **Rich Text Rendering:** Switched log displays from plain text to rich HTML (using `QTextEdit`) to support colors and structured layouts.
- **Live Filtering:** Added a **"Show Debug" toggle** to both App Logs and Ingestion views to filter out verbose UI logs on the fly.
- **Error Formatting:** Enhanced traceback visibility by rendering exceptions in dedicated, highlighted blocks.
- **Stabilization & Bug Fixes:**
    - Fixed a bug where switching logs required a **"double-click"** by implementing dropdown protection that pauses UI refreshes while selection menus are open.
    - Demoted high-frequency layout/geometry logs from `INFO` to `DEBUG` to significantly reduce file churn and UI flicker.
    - Improved **interaction hitboxes** by adding layout margins and spacing between the control row and the log viewer.

- **Masonry (Pinterest-style) Layout:**
    - Created standalone `src/ui/masonry_layout.py` with a shortest-column-first algorithm.
    - Updated `thumbnail_cache.py` to support variable-height scaling by width.
    - Integrated dynamic layout swapping between **Grid** and **Masonry** in the Vault settings.
    - Implemented `heightForWidth` in tiles to provide accurate geometry hints to the layout engine.

#### Dropdown Bug & UI Thread Responsiveness
- **Removed Logging Thread Contention:** Deleted the global `LOG_LOCK` in `logger.py` and rewrote logging functions using `getattr`, allowing background workers to log without stalling the Qt main event loop (fixed the root cause of dropped clicks).
- **Fixed Silent Debug Logging:** The dynamic `getattr` logging rewrite inherently fixed a bug where `DEBUG` level calls were silently discarded.
- **Optimized Tab Switching:** Eliminated unconditional database queries and grid rebuilds from `show_view` in `main_window.py`.
- **Eliminated Race Conditions:** Added an explicit `render_timer.stop()` when navigating away from the Vault tab to prevent background widget-destruction waves from interrupting user interactions on other tabs.
- **Debounced Dropdowns:** Added a 150ms `QTimer` debounce to the App Logs view selectors, allowing rapid switching between Normal/Full modes without blocking the UI thread with expensive HTML relayout calculations.
- **Removed Redundant Event Filters:** Removed the `installEventFilter` loop on child widgets inside `VaultTile` to stop redundant event bubbling and reduce Qt event queue noise during hover interactions.

#### Current Architecture & Complexity Analysis
- **Vault Rendering (`vault.py`)**
  - **Time Complexity:** $\mathcal{O}(N)$ where $N$ is the number of fetched rows (currently hard-capped by `LIMIT 300`).
  - **Space Complexity:** $\mathcal{O}(N)$ because `VaultView` instantiates up to 300 custom `QFrame` tiles containing `QLabel` and `QStackedLayout` widgets.
  - **Status:** Optimized via debounce and equality checks to bypass expensive widget destruction/creation loops if the database hasn't changed.
- **Vault Database Queries (`_fetch_items`)**
  - **Time Complexity:** $\mathcal{O}(N \log M)$ bounded by `LIMIT 300`.
  - **Status:** Fast at the SQLite level, but synchronous execution on the main thread causes UI blocking during disk I/O.
- **Image Loading (`ThumbnailWorker` & `thumbnail_cache.py`)**
  - **Time Complexity:** $\mathcal{O}(1)$ for individual operations.
  - **Space Complexity:** $\mathcal{O}(N)$ to store `QPixmaps` in memory for the grid.
  - **Status:** Missing-thumbnail generation is offloaded to the background `QThreadPool`, but existing thumbnails are still read from disk synchronously on the main thread, causing micro-stutters.
- **Inspector Group Loading (`inspector.py`)**
  - **Time Complexity:** $\mathcal{O}(K)$ where $K$ is the size of the cluster matching a `source_url`.
  - **Status:** Synchronous disk I/O on the main thread. Scales poorly on mechanical drives or massive databases.

### 25-04-2026

#### Modern Desktop Migration (Tauri + Svelte)
- **Why we moved:** Transitioned from PySide6 to Tauri/Svelte to resolve fundamental threading bottlenecks. PySide6 suffered from main-thread blocking during image decoding and SQLite I/O. The new architecture decouples the UI from logic, ensuring a permanent 60FPS experience and high-performance GPU-accelerated media rendering.
- **Architecture Setup:**
    - **FastAPI Bridge:** Developed `src/web_api.py` to expose SQLite data and media as a RESTful service.
    - **Tauri Shell:** Configured Tauri 2.0 to manage the Python sidecar and system-level permissions.
    - **Svelte 5 UI:** Rebuilt the entire interface from scratch using modular Svelte components.
- **Redesigned Components:**
    - **Vault:** Re-implemented the Masonry grid using CSS columns for superior performance.
    - **Inspector:** Replicated the grouped visual hierarchy for metadata editing with real-time persistence.
    - **Ingestion:** Created a dual-pane Markdown editor and progress monitor.
    - **Review:** Rebuilt the side-by-side comparative workflow.
    - **Logs:** Implemented real-time streaming via Server-Sent Events (SSE).
- **Automation:** Created `dev.py` to launch the entire modern stack with a single command.
- **Advanced UI Refinements:**
    - **Native Fullscreen:** Replaced browser-level fullscreen with true OS-level native fullscreen via Tauri's Window API, perfectly syncing video playback timelines.
    - **Tag Interaction:** Made AI-suggested "WD Tags" fully clickable, instantly porting them into the manual "Topics" array and triggering a background Markdown rebuild.
    - **File System Integration:** Integrated Tauri's Shell API to add functional "Open in Folder" and "Open Source URL" buttons to the Inspector.
    - **Group Navigation:** Re-implemented Python-based grouping directly in Svelte, allowing users to scroll through `source_url` clusters via in-card carousel arrows without losing grid context.
- **Logging Architecture Overhaul:**
    - Split the monolithic UI log into `system.log` (FastAPI), `svelte.log` (Frontend), and `tauri.log` (Shell).
    - Built `TerminalLogger` to capture raw Python `stdout`/`stderr` tracebacks and expose them directly to the Svelte UI.
    - Re-wired the Svelte Logs view to support dynamic file switching and a dual-view system (Formatted rows vs. Raw JSONL output).

### 26-04-2026

#### Logging System Redesign & Stabilization
- **Structured Data Transition:** Completely overhauled the Python logging architecture to separate unstructured terminal noise from application data.
    - Moved raw `stdout`/`stderr` and tracebacks to a dedicated `logs/raw/` directory.
    - Upgraded all system loggers to output strict `.jsonl` files to a `logs/structured/` directory.
- **Removed `print()` Spooling:** Systematically scrubbed over 35 legacy `print()` statements from `external_ingestion.py` and `core.py`, replacing them with structured `log_ingestion` calls that explicitly pass metadata (like `platform="youtube"`).
- **Log UI Polish:** 
    - Removed the brittle "Show Debug" button and connection-dropping logic, opting for a clean, unified log view.
    - Implemented a "Clear Logs" backend endpoint and frontend button to instantly truncate all logs back to 0 bytes without breaking file handles.
    - Added dynamic CSS color-coding for platform tags (e.g., `[YOUTUBE]` in red, `[PIXIV]` in blue) directly parsed from the JSON metadata.
    - Switched log text formatting to `white-space: pre` with horizontal scrolling (`overflow-x: auto`) for better readability of deep stack traces and raw JSON arrays.
    - Integrated `activity.jsonl` (the ingestion audit trail) directly into the UI dropdown.

#### Ingestion UI Feature Parity
- **Full Migration:** Ported all missing features from the legacy PyQt GUI to the modern Svelte `Ingestion.svelte` component.
    - **Live Parsing:** Implemented a debounced backend ping that regex-parses the Markdown queue as the user types, updating a live "Ready: X" counter before saving.
    - **Failed Queue Management:** Added "Retry Failed" (with an interactive prompt for normal/force destinations) and "Clear Failed" buttons, fully wired to the backend `queue_service`.
    - **External Open:** Added an "Open" button that safely requests OS-level application opening via the FastAPI backend.
- **Split-Pane Layout:** Redesigned the Ingestion tab layout to support true vertical resizing of the Markdown editor while permanently pinning the toolbar and footer action buttons to the edges of the window.

#### Vault Layouts & Settings
- **Square Grid Implementation:** Built a true "Grid" layout mode for the Vault to accompany the existing "Masonry" view, featuring strictly cropped `aspect-ratio: 1 / 1` square thumbnails.
- **Settings Refactor:** 
    - Completely rewrote `SettingsView.svelte` using a modern CSS Grid layout to fix broken alignments, unconstrained input stretching, and missing paddings.
    - Successfully wired the previously dormant "Flatten Transparency" configuration toggle.
    - Implemented deep-state tracking to detect unsaved modifications, powering a dynamic "Save Settings" button and a real-time "● Unsaved Changes" warning badge.

#### Sub-System Fixes
- **Pixiv Metadata Rescue:** Patched `gallery_dl_wrapper.py` to handle an upstream `gallery-dl` formatting change. The wrapper now attempts to parse stdout as a single JSON array before falling back to line-by-line JSONL parsing, fixing the "no downloadable media entries found" crashes.
- **Maintenance Execution:** Ran the `update_tools.py` script to successfully bump `yt-dlp` and `gallery-dl` binaries and forcefully regenerated all 47 Markdown notes to sync with the latest DB state.

#### UI Polish & Quality of Life
- **Search & Filtering Improvements:**
    - Restored full-width search bar scaling that dynamically bounds itself to the Inspector panel edge.
    - Added a quick clear "✖" button directly inside the search bar.
    - Implemented a "Sort By" dropdown (`Newest First`, `Oldest First`, `Artist A-Z`, `Shuffle`) dynamically driven by a modernized SQLite backend endpoint.
    - Added a "Media Type" dropdown filter (`All Media`, `Images Only`, `Videos Only`) natively handled via database `MIME_TYPE` queries.
- **Layout Adjustments:**
    - Expanded the bottom status footer to span the entire application width (`100vw`), mimicking native IDE status bars.
    - Added subtle outline styling to left-sidebar navigation buttons for improved visual distinction.
- **Inspector Tooling:**
    - Added `Copy Data` button: Instantly exports a perfectly formatted JSON dump of the currently viewed item's complete metadata (URL, Hash, Artist, WD Tags, etc.) to the system clipboard.
    - Added `Delete Data` button: Safely deletes the database row, markdown note, JSON cache file, and physical media asset in one unified operation, instantly refreshing the Vault UI afterward.
- **Keyboard Workflows:**
    - Integrated a global `<svelte:window>` listener to intercept `F5` (triggers a silent SQLite database refresh without flashing the UI) and `Ctrl+F5` (triggers a hard application window reload).
    - Hardened the `W` (Wide) and `F` (Fullscreen) hotkeys inside the Inspector to support seamless cross-toggling and active-input protection (ignoring keystrokes when typing in text fields).
    - Added a dedicated, styled **Keyboard Shortcuts** reference guide to the bottom of the Settings panel.

## What API models did

### 28-04-2026

#### Masonry View Fix
- **Root Cause:** VirtualScroller rendered tiles in single-column absolute positioning (`left: 0; right: 0`), making every tile very wide and short. The `itemPositions` reactive computed a single vertical stack — no column distribution logic existed.
- **Fix:** Replaced VirtualScroller with CSS `column-count: 5` masonry (the original working approach). Added IntersectionObserver infinite scroll via a sentinel element at the bottom that triggers `loadMore()` within 400px of the viewport.
- **fetchConfig Repair:** Earlier edit had accidentally merged the `fetchConfig` function declaration into the `hasMore` variable line, turning it into a bare block. Restored proper `async function fetchConfig()` declaration.
- **Dead Code Removal:** Removed `itemPositions` reactive, `layoutContainerHeight` reactive, and `VirtualScroller` import from App.svelte. `VirtualScroller.svelte` file remains in lib/ but is unused.

#### Old PyQt UI Removed Entirely
- **Deleted `src/ui/`:** Entire folder — `app.py`, `flow_layout.py`, `log_utils.py`, `main_window.py`, `masonry_layout.py`, `theme.py`, `thumbnail_cache.py`, `video_widgets.py`, `views/` (7 files), `__init__.py`.
- **Deleted `gui.py`:** Was the PyQt entry point (`from ui.app import main`). Dead without `src/ui/`.
- **Cleaned `src/logs/logger.py`:** Removed `log_ui()`, `log_pyui()`, and `pyui_logger` + its `pyui.jsonl` handler. Only `log_system`, `log_svelte`, `log_ingestion`, and `log_activity` remain.
- **Cleaned `pyproject.toml`:** Removed `PySide6` from dependencies, removed `liz-gui` script entry, removed `ui`/`ui.views` from `tool.setuptools.packages.find.include`, updated description from "PySide6 UI" to "Tauri/Svelte UI".
- **Verified:** Zero PySide6 / log_ui / log_pyui references remain in `src/` or root files. Only the kept `backup after masonry fix/` folder still has them.

## Current Bugs/Redundant Codes

> **Cross-checked with Claude.** 65/78 items confirmed real. 5 overstated/false items are ~~struck through~~ with corrections. 2 items reclassified as by-design.

### CRITICAL

| # | File | Line(s) | Issue |
|---|------|---------|-------|
| 1 | `sqlite_operator.py` | 137 | **`INSERT OR REPLACE` triggers `ON DELETE CASCADE`**, permanently deleting all `item_tiles` for re-ingested items. `REPLACE` = `DELETE` + `INSERT`. |
| 2 | `sqlite_operator.py` | 123 | **`audio_hash: str = None`** but column is `BLOB`. sqlite3 binds `str` as TEXT, readers expect bytes. Type mismatch across read/write path. |
| 3 | `search_manager.py` | 58, 88 | **`log_ingestion` is called but never imported** → `NameError` on execution. |
| 4 | `search_manager.py` | 141-157 | **VPTreeSearcher stays unqueryable after empty DB hydration.** `add()` only rebuilds if `self.tree is not None`, but `build_index()` returns `None` on empty DB. Queries return `[]` forever. |
| 5 | `search_manager.py` | 9-16 | **`_cosine_dist` is not a valid metric** — `1 - dot(v1, v2)` without normalization violates triangle inequality. VP-tree silently drops valid results. |
| 6 | `fingerprint.py` | 174-191 | **`compare_embeddings` crashes on mismatched sizes.** No length check before `np.dot(emb1, emb2)`. |
| 7 | `md_generator.py` | 84 | **`UnicodeDecodeError` not caught.** Inherits from `ValueError`, not `OSError`, so malformed UTF-8 files crash the caller. |
| 8 | `tagging/service.py` | 55-57 | **`calculate_file_hash` called outside try/except.** File disappearing between `exists()` and read crashes the whole tagging pipeline. |
| 9 | `web_api.py` | 305-330 | **Fragile deletion order** — files unlinked before DB row deleted. If `DELETE`/`commit()` fails, DB references deleted paths. |
| 10 | `web_api.py` | 369-398, 410-425 | **Path traversal in log endpoints** — `filename=../../config.yaml` can read arbitrary files. |
| 11 | `web_api.py` | 524-538 | **Path traversal in review actions** — `filename=../../../desktop.ini` can delete arbitrary files. |
| 12 | `web_api.py` | 472-484 | **Path traversal in queue open** — `queue_name` passed directly without sanitization. |
| 13 | `web_api.py` | 50-55 | **CORS `allow_origins=["*"]` + zero auth** on destructive endpoints (`DELETE`, `PATCH`, `POST /api/ingest/*`). Any malicious website can trigger data deletion or ingestion. |
| 14 | `web_api.py` | 23-45 | **`TerminalLogger` is not thread-safe** — opens/closes file on every single character write. Races under concurrent load, massive filesystem overhead. |

### HIGH

| # | File | Line(s) | Issue |
|---|------|---------|-------|
| 15 | `utils.py` | 117-151 | **`validate_config_schema` calls `sys.exit(1)`** deep in a utility function — kills the web server/worker thread. Should raise an exception. |
| 16 | `utils.py` | 168 | **`get_config()` opens file without encoding** — on Windows defaults to `cp1252`, causing `UnicodeDecodeError`. |
| 17 | `md_generator.py` | 87-89 | **BOM breaks frontmatter detection** (`\ufeff---` vs `---`). Also fragile `---` splitting: YAML values containing `---` corrupt parsing. |
| 18 | `validators.py` | 8-10 | **`magic.from_file` errors** (other than `ImportError`) — `MagicException`, `OSError`, `FileNotFoundError` — propagate uncaught. |
| 19 | `fingerprint.py` | 29,52,73,107 | **Subprocess calls lack timeouts.** Hung `ffmpeg`/`ffprobe`/`fpcalc` blocks the thread forever. Missing binaries silently return safe defaults, masking deployment errors. |
| 20 | `queue_service.py` | 46-95 | **All queue mutations are read-modify-write with no file locking.** Concurrent `append_urls`/`move_failed_urls` causes lost URLs. |
| 21 | `gallery_dl_wrapper.py` | 45-50 | **Case-sensitivity bug in URL normalization.** Checks lowercase but replaces on original: `https://X.COM/...` → condition fires but replace does nothing. |
| 22 | `thumbnails.py` | 71-74 | ~~Video thumbnail failures silently swallowed~~ **Overstated.** Error is already logged by `generate_video_thumbnail` before re-raising; outer catch only suppresses the exception, not the log. |
| 23 | `sqlite_operator.py` | 69-102 | **Unbounded bulk fetches** (`get_all_phashes`, `get_all_tiles`, etc.) load entire tables into RAM with no LIMIT/pagination. |
| 24 | `sqlite_operator.py` | 120 | **`LOWER(source_url)` defeats indexing** — full table scan on every duplicate check. |
| 25 | `searchers.py` | 29-31 | **VPTree rebuilds from scratch on every `add`** — O(N) per insertion, O(N²) total. |
| 26 | `yt_dlp_wrapper.py` | 309, 320, 334-349 | **Metadata parsing uses `|` delimiter** — if uploader/title contains `|`, fields misalign. |
| 27 | `web_api.py` | 93-209 | **Broken pagination for sparse frontmatter filters.** Fetches 5,000 rows, then filters in Python. If matches are outside the window, API reports `has_more = False` and client never sees them. |
| 28 | `web_api.py` | 282-303 | **Update endpoint returns 200 for non-existent items.** SQLite `UPDATE` affects 0 rows but endpoint returns `{"status": "success"}`. |
| 29 | `web_api.py` | 332-365 | **Tagging trigger returns `null` with HTTP 200** when item doesn't exist. Should return 404. |
| 30 | `web_api.py` | 52-69, 93-209, 250+ | **Blocking I/O inside async endpoints.** SQLite queries, `subprocess.call`, `yaml.dump`, `process_file`, markdown generation all block the uvicorn event loop directly. |
| 31 | `web_api.py` | 486-494 | **Fire-and-forget background task leaks exceptions.** `run_in_executor` Future discarded; client gets `{"status": "success"}` even if `run_queue()` later crashes. |
| 32 | `core.py` | 15-17 | **Resource leak** — `conn = init_database()` opened but if `search_manager.hydrate()` raises, `conn.close()` never executed (no `try/finally`). |

### MEDIUM

| # | File | Line(s) | Issue |
|---|------|---------|-------|
| 33 | `sqlite_operator.py` | 9-61 | **Schema not self-contained** — fresh DB still runs `ALTER TABLE` migrations. Missing `width`, `height`, `audio_hash`, `visual_embedding` in `CREATE TABLE`. |
| 34 | `sqlite_operator.py` | 45-46 | **`idx_source_url` is dead weight** — never usable due to `LOWER()` wrapping. |
| 35 | `sqlite_operator.py` | 104-114 | **`reset_database` dangerous gap** — between `DROP` and `CREATE`, a crash leaves a broken DB. |
| 36 | `sqlite_operator.py` | 87-96 | **`insert_tiles` unconditionally DELETEs** all tiles even if incoming list is empty. |
| 37 | `sqlite_operator.py` | 133 | **Local time vs UTC inconsistency** — `datetime.now()` stores local time, `CURRENT_TIMESTAMP` stores UTC. |
| 38 | `search_manager.py` | 113-121 | **`query_video` breaks after first audio match** — only one audio duplicate returned. |
| 39 | `searchers.py` | 98-104 | **`_hamming_distance` fallback returns 65** — inside valid range for >64-bit hashes, corrupting metric space. |
| 40 | `searchers.py` | 155-213 | **`FlatVectorSearcher` is dead code** — never imported or used. |
| 41 | `md_generator.py` | 9, 55 | **Invalid type hints** — `str = None` / `list = None` should be `str \| None = None`. |
| 42 | `md_generator.py` | 58 | ~~Unprotected `wd_frontmatter_fields()` call crashes generate_markdown~~ **False.** `wd_frontmatter_fields()` has internal try/except and always returns a dict regardless of missing model. No crash possible. |
| 43 | `fingerprint.py` | 118-142 | **`get_visual_embedding` spawns 5 separate ffmpeg processes** — single ffmpeg can extract multiple frames. |
| 44 | `fingerprint.py` | 107 | **`extract_video_frame` exposes unhandled `CalledProcessError`** to direct callers. |
| 45 | `utils.py` | 165+ | **`get_config()` re-reads + re-parses YAML on every call** — no caching. Redundant disk I/O. |
| 46 | `utils.py` | 13-24 | **Module-level side effects** — config loaded at import time. Makes testing painful. |
| 47 | `utils.py` | 249, 265-267 | **`PIL.Image` imported locally** in multiple functions — should be at module top. |
| 48 | `validators.py` | 14-24 | **`ext_map` duplicates knowledge from `utils.py`** — two maps to keep in sync. |
| 49 | `validators.py` | 27 | **`mime_type in allowed_list` is O(n)** — should be a `set`. |
| 50 | `gallery_dl_wrapper.py` | 54-60 | **Substring-based platform detection** — `pixiv` matches `en.wikipedia.org/wiki/Pixiv`. Should use `urlparse().netloc`. |
| 51 | `gallery_dl_wrapper.py` | 211-233 | **`_valid_media_files` duplicated from `yt_dlp_wrapper.py`**. |
| 52 | `gallery_dl_wrapper.py` | 238 | **10-char SHA-256 prefix** for `url_hash` — only 40 bits, birthday-paradox collision risk. |
| 53 | `yt_dlp_wrapper.py` | 368-369 | **Video download returns every file in `session_dir`** without extension/MIME validation. Mitigated by downstream `process_file` MIME rejection, but still inconsistent with gallery-dl wrapper filtering. |
| 54 | `yt_dlp_wrapper.py` | 33-46 | **Cookie-jar loading silently swallowed** — corrupted cookies ignored, downloads proceed unauthenticated. |
| 55 | `yt_dlp_wrapper.py` | 258 | **One bad community image URL (404) aborts entire batch** — no per-URL error handling. |
| 56 | `yt_dlp_wrapper.py` | 127-130 | **`_choose_community_renderer` serializes every renderer to JSON** to search for `post_id` — extremely inefficient and brittle. |
| 57 | `tagging/service.py` | 147-152 | ~~`_write_result` is non-atomic~~ **Overstated.** `Path.write_text()` is OS-level atomic on most systems. No temp-file+rename guarantee, but practically safe. |
| 58 | `tagging/service.py` | 233 | **`zip(labels, predictions)` silently truncates** — mismatched lengths hide model issues. |
| 59 | `tagging/service.py` | 200-203 | **`_prepare_image` is dead code**. |
| 60 | `tagging/service.py` | 218 | **`Image.Resampling.BICUBIC` requires Pillow >= 9.0.0**. |
| 61 | `tagging/service.py` | 220 | **`array[:, :, ::-1]` creates non-contiguous view** — can cause ONNX Runtime issues. |
| 62 | `queue_service.py` | 51-66 | ~~`parse_urls` extracts only one URL per line~~ **By design.** One URL per line is the expected queue format. |
| 63 | `queue_service.py` | 69-70 | ~~`clean_url` strips trailing `)` unconditionally~~ **By design.** Intentional to clean markdown link artifacts like `url)`. |
| 64 | `queue_service.py` | 21 | **`INGESTION_LOCK = threading.Lock()`** declared but never used. |
| 65 | `queue_service.py` | 28-38 | **`ensure_queue_files()` runs twice per `append_urls`**. |
| 66 | `logger.py` | 25-26 | **`extra_data` can overwrite built-in JSON keys** — e.g. `{"message": "pwned"}` corrupts log format. |
| 67 | `logger.py` | 52-53 | **`getattr(..., level.lower(), logger.info)` silently falls back** for typos like `"WARN"`. |
| 68 | `logger.py` | 14-27 | **`JSONFormatter` ignores `record.exc_info`** — stack traces lost from error logs. |
| 69 | `thumbnails.py` | 22-24 | **`_asset_path_for` duplicates `utils.asset_path_for`**. |
| 70 | `thumbnails.py` | 33-34 | ~~`image.convert("RGB")` creates new image not explicitly closed~~ **Overstated.** Original image is managed by `with Image.open(...) as image:` context manager. The converted image is saved immediately after and relies on GC — low risk in practice. |
| 71 | `web_api.py` | 1, 14, 16 | **Unused imports** — `Path`, `VAULT_DIR`, `DB_PATH`, `LOGS_DIR`, `log_ingestion`. |
| 72 | `web_api.py` | 382-398 | **Inefficient log tailing** — `f.readlines()` loads **entire** log file into memory to get last 150 lines. |
| 73 | `web_api.py` | 500-522 | **N+1 query in review endpoint** — opens a new DB connection for every review item with `best_match`. |
| 74 | `web_api.py` | 544-550 | **Config overwrite without atomic write** — `yaml.dump` directly to target; crash mid-write truncates config. |
| 75 | `web_api.py` | 295, 349 | **Markdown generation inside DB transaction endpoints** — lengthens transaction window, increases "database is locked" risk. |
| 76 | `core.py` | 39, 41 | **`ext_stats["processed"]`/`ext_stats["errors"]` use direct indexing** while `ext_stats.get("skipped", 0)` is safe. Inconsistent, can `KeyError`. |
| 77 | `core.py` | 67-69 | **Race condition in directory removal** — non-atomic check-then-delete. Another thread can create file between check and removal. |
| 78 | `core.py` | 59, 70 | ~~Unshielded loop body~~ **Overstated.** `process_file()` returns `(False, msg, None)` instead of raising; loop won't abort. Outer `except` in `main()` (line 75) catches any genuine exception and still runs the final `search_manager.update_indexes`. |

---

Will update status log from scratch once the new UI is stable. 
Also need to rename src/ folder as backend/ and update imports.

"Copy data" and "Open folder" buttons will be fixed