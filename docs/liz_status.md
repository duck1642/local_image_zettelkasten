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

### Resolved in the hardening passes

- **API safety:** Mutating endpoints now require the local UI session key, CORS is allowlisted, log/review/queue paths are validated, and bad item operations return 404 instead of false success.
- **API correctness/performance:** Blocking work in the main API paths was moved through thread helpers, log tailing no longer reads whole files, review metadata avoids N+1 DB connections, and frontmatter-backed item filters paginate after filtering.
- **SQLite/search:** `INSERT OR REPLACE` was replaced with conflict updates, `source_url_norm` + index were added for duplicate checks, empty tile inserts no longer clear existing tiles, video audio duplicate search returns all matches, and dead `FlatVectorSearcher` was removed.
- **Downloader/fingerprint/tagging:** gallery-dl and yt-dlp share valid-media filtering, gallery-dl session hashes are longer, YouTube community image download records per-image failures, video frame extraction no longer leaks `CalledProcessError`, `_prepare_image()` was removed, and Pillow is pinned to `>=9.0.0`.
- **Config/logging/markdown:** config validation raises instead of exiting, config/log/tag writes use atomic writes where relevant, markdown frontmatter parsing handles BOM and line-delimited YAML fences, JSON log fields are protected, and exception text is preserved.

### Still deferred

- **Search scaling:** RAM hydration still bulk-loads pHash/tile/video signatures. This is acceptable for the current local vault size, but needs batching or a persistent index if the vault grows substantially.
- **Source URL cleanup:** Existing rows are backfilled lazily by `init_database()`. No standalone migration tool exists yet.
- **YouTube community robustness:** One failed image still makes the post incomplete and retryable by design; the downloader now records which image failed, but no partial-success policy has been added.
- **Video embedding efficiency:** V1 still extracts five frames with separate ffmpeg calls. It is safer, but not optimized.
- **Config caching:** `get_config()` still reparses YAML in many paths. Avoiding stale Settings behavior needs a deliberate cache invalidation design.
- **Remaining cleanup:** `thumbnails.py` still has a small local asset-path helper duplication, local timestamps remain mixed with SQLite UTC defaults, and `src/` has not been renamed to `backend/`.

### Notes

- Runtime vault files, notes, WD tag JSON, logs, and queues were not intentionally migrated or deleted by this pass.
- Tauri/Svelte remains the active UI. The old PySide/PyQt UI remains removed.
