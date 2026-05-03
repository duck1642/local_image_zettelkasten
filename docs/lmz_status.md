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

## Frontend Code Review Findings (2026-05-03)

Inspection-only senior dev pass over `frontend/src/`. Some items overlap with the Current Issues section above; they are repeated here in the standard `where / problem / solutions` template for completeness.

### Bugs / Correctness

* where: `frontend/src/lib/api.ts:5,19-29`
* problem: `apiKeyPromise` is cached forever, including rejected promises. If the first `/api/session-key` fetch fails (transient network blip, backend not yet up), every subsequent `apiFetch` POST/PATCH/DELETE rejects with the same stale error and never recovers. Overlaps with Current Issues "API session-key retry".
* solutions: On `.catch`, set `apiKeyPromise = null` so the next call retries. Or wrap with retry-with-backoff.

* where: `frontend/src/lib/renderers/masonry/masonryLayout.ts:46-51,126-131`
* problem: Layout cache is module-level mutable state (`lastCacheKey`, `lastCache`, `lastPositions`, `lastActiveIndexes`, `lastStore`). Two MasonryRenderer instances would corrupt each other's layout. `lastStore` is also written but never read.
* solutions: Move cache into a closure returned by a factory, or store on the renderer instance. Drop unused `lastStore`.

* where: `frontend/src/lib/VaultView.svelte:143-174`
* problem: `fetchItems` re-fetches `/api/stats` on every paginated append. The stat does not change just because we paged, so this is wasted work per scroll page.
* solutions: Only call `/api/stats` on `!append`, or rely on the polled stats store.

* where: `frontend/src/lib/Inspector.svelte:25-29` interacting with `frontend/src/lib/VaultView.svelte:302-307`
* problem: Reactive `$: if (item) loadFullDetails(item.hash)` fires on object identity change, not hash change. `handleUpdate` rebuilds `selectedItem` via spread, triggering a redundant `/api/items/{hash}` fetch right after a save.
* solutions: Track last loaded hash and bail if `item.hash === lastLoadedHash`.

* where: `frontend/src/lib/Inspector.svelte:175`
* problem: Keyboard handler suppresses A/D/W/F by `document.querySelector('.focus-overlay')` — DOM-snooping for state. Brittle (CSS class rename = silent break) and forces a layout query on every keypress.
* solutions: Pass `focusMode` as a prop or use a writable store.

* where: `frontend/src/lib/MediaFocus.svelte:53`
* problem: `(window as any).__TAURI__` — Tauri v2 renamed this global to `__TAURI_INTERNALS__`. Detection path is likely already broken; the non-Tauri branch never runs in Tauri v2 anyway, so it's mostly dead.
* solutions: Detect via `import.meta.env.TAURI_PLATFORM` or always call `appWindow.setFullscreen(false)` (no-ops outside Tauri are caught).

* where: `frontend/src/lib/Ingestion.svelte:94-107`
* problem: `setTimeout(() => running = false, 5000)` is a fake completion signal. The Start button re-enables after 5s regardless of whether the worker is still running, allowing double-starts on slow ingests. Also no `res.ok` check. Overlaps with Current Issues "Frontend ingestion run state".
* solutions: Drive `running` from the SSE log stream (`Ingestion cycle complete` is already detected at line 32) or a status endpoint.

* where: `frontend/src/lib/Inspector.svelte:33-56`
* problem: `abortController` is never aborted on `onDestroy`. Closing inspector mid-fetch leaves a hanging request that resolves into a destroyed component.
* solutions: Add `onDestroy(() => abortController?.abort())`.

* where: `frontend/src/lib/Inspector.svelte:185-191`
* problem: After handling A/D the function does not return, so the W/F `if` blocks still execute. Currently harmless because keys differ, but the structure is inconsistent.
* solutions: Convert the second pair into `else if` (or early return after A/D).

* where: `frontend/src/lib/VaultView.svelte:357-374,180-184`
* problem: `IntersectionObserver` with `rootMargin: '400px'` already does the "near viewport" detection that `sentinelIsNearViewport()` reimplements with `getBoundingClientRect`. Two systems doing the same job; `scheduleLoadMoreCheck` triggers manual checks anyway.
* solutions: Pick one. The IO is enough; remove the manual rect check + 50ms timer.

* where: `frontend/src/App.svelte:59-72`
* problem: `VaultView` is hidden via `class:hidden` (always mounted), but other tabs use `{#if}` (mount/unmount). Consequence: VaultView's IntersectionObserver, ResizeObserver, infinite scroll, log emission and stats poll keep running while user is on other tabs.
* solutions: Use `{#if activeTab === 'vault'}` for symmetry, or accept the always-mounted choice and document why; either way, gate observers on visibility.

* where: `frontend/src/lib/Ingestion.svelte:37-40`, `frontend/src/lib/LogsView.svelte:120-123`
* problem: SSE error handlers do `setTimeout(reconnectFn, 2000)` without storing the handle. Teardown closes the current EventSource but not the pending reconnect timer; a stream can be re-created after the view is gone. Overlaps with Current Issues "Frontend SSE reconnect cleanup".
* solutions: Store the timer handle and `clearTimeout` it on `onDestroy`.

* where: `frontend/src/lib/ReviewView.svelte:32-42`
* problem: `await apiFetch(...)` is followed by `items = items.filter(...)` with no `res.ok` check. Backend failures look successful in the UI until reload. Same pattern in `loadReview`. Overlaps with Current Issues "Review action response handling".
* solutions: Branch on `res.ok` before mutating local state; surface a toast on failure.

* where: `frontend/src/lib/StatsView.svelte:23-42`
* problem: `loadFacets` assigns `items = ...` unconditionally with no sequence/request token. Fast typing or tab switches can let an older response overwrite newer visible results. Overlaps with Current Issues "Stats panel request ordering".
* solutions: Capture a request id at call start and discard responses whose id is no longer current.

* where: `frontend/src/lib/VaultView.svelte:151-167`
* problem: Neither `/api/items` nor `/api/stats` checks `response.ok`, both inside the same try/catch. A stats failure surfaces as "Failed to fetch items"; a stats throw after items succeeded leaves fresh data plus a misleading error log. Overlaps with Current Issues "Vault fetch error boundaries".
* solutions: Separate try/catch per request, check `res.ok`, and surface stats failures distinctly.

* where: `frontend/src/lib/SearchBar.svelte`
* problem: No `onDestroy` block at all. `searchDebounceTimer` and `refreshDebounceTimer` are never cleared on teardown. Benign today because SearchBar is always mounted. Overlaps with Current Issues "SearchBar timer cleanup".
* solutions: Add `onDestroy` that clears both timers.

* where: `frontend/src/lib/renderers/grid/GridRenderer.svelte:42-43`, `frontend/src/lib/renderers/masonry/MasonryRenderer.svelte:45-46`
* problem: Reactive blocks `$: emitVisualOrder();` and `$: logSummary();` rely on Svelte's static analysis to find dependencies inside the called function. A refactor that moves the reads further away would silently break re-runs. Overlaps with Current Issues "Renderer reactive dependency clarity".
* solutions: Inline the dependency reads into the reactive statement (e.g. `$: emitVisualOrder(layout.positions)`), or use derived stores.

### Performance

* where: `frontend/src/lib/renderers/grid/GridRenderer.svelte:43-78`, `frontend/src/lib/renderers/masonry/MasonryRenderer.svelte:46,132-159`
* problem: `logSummary()` POSTs `/api/logs/ui` (via `uiLog INFO`) on every layout recompute, throttled only by 500ms. During scroll/resize this floods the backend with INFO logs that have no operational value.
* solutions: Demote to DEBUG, gate behind `import.meta.env.DEV`, or remove entirely.

* where: `frontend/src/lib/renderers/grid/GridRenderer.svelte:45-51`, `frontend/src/lib/renderers/masonry/MasonryRenderer.svelte:48-54`
* problem: `emitVisualOrder` joins every hash (64-char strings × thousands of items) into one giant string just to detect change. Allocates hundreds of KB per layout reactivity tick.
* solutions: Compare on `(positions.length, positions[0]?.group.id, positions[last]?.group.id, layout.columnCount)`, or hash the positions array length + a checksum.

* where: `frontend/src/lib/VaultView.svelte:52,218-220`
* problem: `jsVisualHashOrder` flatMaps all groups on every reactive update; `loadedHashOrder()` allocates again on every selection click.
* solutions: Memoize. Compute once when `visualHashOrder`/`groupedItems` actually changes; cache.

* where: `frontend/src/lib/VaultView.svelte:222-225,235`
* problem: `findGroupForItem` is O(groups × items) and `items.find(candidate => selectedHashes.has(...))` is O(items). Runs on every selection click. Painful at 10k+ items.
* solutions: Maintain a `Map<hash, {item, group}>` index that updates with `groupedItems`.

* where: `frontend/src/lib/VaultGroupTile.svelte:55,58`, `frontend/src/lib/renderers/grid/GridRenderer.svelte:98`, `frontend/src/lib/renderers/masonry/MasonryRenderer.svelte:185`
* problem: Both renderers pass `eagerImages={true}` unconditionally, so `loading="lazy"` is never used. Combined with `content-visibility: visible` overriding the tile's `content-visibility: auto`, every visible tile loads its image immediately, even within the 1200px overscan band.
* solutions: Set `eagerImages={false}` (let the browser handle visibility) and keep `content-visibility: auto` on tiles. Or pass `eagerImages` only for tiles that overlap the actual viewport, not the overscan band.

* where: `frontend/src/lib/VaultGroupTile.svelte:58-59`
* problem: Video tiles use `src={fullUrl}` + `preload="none"`. Hover triggers `play()` which downloads the full video for thumbnail playback. For ingested originals this can be tens of MB per hover.
* solutions: Use a short preview clip endpoint, an animated thumbnail (gif/webp), or limit to videos under N MB.

* where: `frontend/src/lib/logger.ts:3-15`
* problem: Every `uiLog` makes its own POST to `/api/logs/ui`. Combined with the layout-summary spam above, ingest/scroll sessions can produce dozens of requests per second.
* solutions: Batch with a 200-500ms flush window, or send via a single SSE/WebSocket. Drop DEBUG by default.

* where: `frontend/src/lib/Ingestion.svelte:50`, `frontend/src/lib/LogsView.svelte:133`
* problem: `logs = [...logs, entry].slice(-N)` reallocates the entire array on every log line. Under heavy log throughput this dominates the main thread.
* solutions: Mutate-and-trim with a ring buffer, or batch incoming SSE messages per animation frame.

* where: `frontend/src/lib/VaultView.svelte:69-87`
* problem: `appendToGroups` copies every existing group's items array on every page append (`{ ...g, items: [...g.items] }`). At 1000+ groups, that's a lot of O(n²)-ish allocation per scroll page.
* solutions: Use a persistent `groupsMap` kept in component state and only mutate the touched groups, or rebuild references only for groups that received new items.

### Redundancy / Code Quality

* where: `frontend/src/lib/search.ts:39`
* problem: `segment.split(/\s+/).map(t => t.trim()).filter(Boolean)` — splitting on `\s+` already removes whitespace; the `.trim()` is redundant.
* solutions: Drop `.map(trim)`.

* where: `frontend/src/lib/SearchBar.svelte:74-76`
* problem: Command filter uses two parallel `startsWith` checks that overlap. Equivalent to "starts with `query` after stripping leading `>`".
* solutions: Strip the leading `>` from `query` once, then compare.

* where: `frontend/src/lib/VaultView.svelte:51`
* problem: `$: emitStatus(...)` dispatches a custom event on every reactive update. The footer receives many no-op updates per second during scroll/measurement.
* solutions: Compare against last-emitted snapshot before dispatching.

* where: `frontend/src/lib/statsStore.ts:16-22`
* problem: `Number(next?.normal || 0)` — the `|| 0` swallows legitimate `0` after a coercion that would already produce `0`. Reads as defensive noise.
* solutions: `Number(next?.normal ?? 0) || 0` or just `Number(next?.normal) || 0`.

* where: `frontend/src/lib/renderers/grid/GridRenderer.svelte:4`
* problem: `import { onDestroy } from 'svelte'` is never used.
* solutions: Remove the import.

* where: `frontend/src/lib/Ingestion.svelte:13`
* problem: Several timer handles typed `any` (`parseTimer: any`).
* solutions: Use `number | null` or `ReturnType<typeof setTimeout>`.

* where: `frontend/src/lib/Ingestion.svelte:52`, `frontend/src/lib/LogsView.svelte:135`
* problem: Magic `setTimeout(..., 30)` to scroll-to-bottom.
* solutions: Use `tick()` then set `scrollTop`, or `requestAnimationFrame`.

* where: `frontend/src/lib/api.ts:11-17`
* problem: `assetUrl` and `eventSourceUrl` are 1-line aliases of `apiUrl` with no behavioral difference.
* solutions: Drop them and import `apiUrl`, or give them real semantics (e.g. CDN host for assets).

* where: `frontend/src/App.svelte:78`
* problem: Footer hardcodes literal text `DB: WAL` regardless of the actual backend journal mode — UI lies if this ever changes.
* solutions: Read from a status endpoint or remove.

* where: `frontend/src/lib/SearchBar.svelte:21-22`
* problem: `measureCanvas`/`measureContext` are component-local but never released. Minor leak.
* solutions: Acceptable as-is; if needed, null on `onDestroy`.

* where: `frontend/src/lib/VaultView.svelte:265-291`
* problem: `deleteSelected` calls `await fetchItems()` in both the success path and the catch path; the catch path also alerts. Net effect: an unnecessary refetch on success (it's also done after `clearSelection()` already), and double work on failure.
* solutions: Single `finally { fetchItems(); }` after the alert, and skip the success-path refetch if it's already covered.

* where: `frontend/src/lib/Inspector.svelte:23`
* problem: `let videoElement: HTMLVideoElement;` — bound only when item is a video, but typed as non-nullable. TypeScript-unsafe (passes only because Svelte's `bind:this` typings are loose).
* solutions: `let videoElement: HTMLVideoElement | undefined;` and guard usages.

* where: `frontend/src/lib/VaultView.svelte:42-44,376-393`
* problem: A lot of "observer plumbing" (`observer/observedSentinel/observedLayout`, `resizeObserver/observedLayoutHost`) duplicated in the same component. Hard to follow.
* solutions: Extract two small `use:` Svelte actions (`useIntersection`, `useResize`) for clarity and easier reuse.

## Frontend Fix Plan (2026-05-03)

Phased fix plan for the findings above. Earlier phases are lower-risk; later phases require care or backend coordination. Within a phase, batch fixes that touch the same file.

### Phase 1 — Hygiene (~30 min, zero risk)

Single-line cleanups, no behavior change. Group as one commit.

- `frontend/src/lib/renderers/grid/GridRenderer.svelte:4` — remove unused `onDestroy` import
- `frontend/src/lib/search.ts:39` — drop redundant `.map(t => t.trim())`
- `frontend/src/lib/Ingestion.svelte:13` — type `parseTimer` as `number | null`
- `frontend/src/lib/SearchBar.svelte:74-76` — strip leading `>` once, single `startsWith`
- `frontend/src/lib/statsStore.ts:16-22` — replace `Number(x || 0)` with `Number(x) || 0`
- `frontend/src/lib/Inspector.svelte:23` — `videoElement: HTMLVideoElement | undefined`
- `frontend/src/lib/Inspector.svelte:185-191` — convert second pair to `else if`
- `frontend/src/App.svelte:78` — remove "DB: WAL" hardcoded text

Validation: `npm run check` passes.

### Phase 2 — Resource Cleanup (~1 hr, low risk)

Memory leaks and orphaned timers/observers. Additive `onDestroy` hooks.

- `frontend/src/lib/Inspector.svelte:33-56` — add `onDestroy(() => abortController?.abort())`
- `frontend/src/lib/SearchBar.svelte` — add `onDestroy` clearing both debounce timers
- `frontend/src/lib/Ingestion.svelte:37-40` and `frontend/src/lib/LogsView.svelte:120-123` — store reconnect timer handle, clear on destroy
- `frontend/src/lib/api.ts:11-17` — drop `assetUrl`/`eventSourceUrl` aliases, update import sites to `apiUrl`

Validation: open/close inspector mid-fetch; switch tabs during SSE reconnect; no console errors.

### Phase 3 — Error Handling (~2 hr, medium risk)

Add `res.ok` checks and surface failures correctly. Each fix is independent.

- `frontend/src/lib/api.ts:5,19-29` — reset `apiKeyPromise = null` in `.catch`
- `frontend/src/lib/ReviewView.svelte:23-42` — check `res.ok` before mutating local state in `loadReview` and `handleAction`
- `frontend/src/lib/VaultView.svelte:151-167` — split items vs stats into separate try/catch, check `res.ok` on both
- `frontend/src/lib/StatsView.svelte:23-42` — capture request id at start, discard stale responses
- `frontend/src/lib/Ingestion.svelte:103-106` — drive `running` flag from existing SSE `Ingestion cycle complete` detection (already handled at line 32); remove `setTimeout` fake completion

Validation: kill backend mid-action and verify each error path surfaces feedback instead of silent UI desync.

### Phase 4 — Performance Quick Wins (~2 hr, low-medium risk)

High-impact, contained changes.

- `frontend/src/lib/renderers/grid/GridRenderer.svelte:53-78` and `frontend/src/lib/renderers/masonry/MasonryRenderer.svelte:132-159` — gate `logSummary` behind `import.meta.env.DEV`, demote to DEBUG (kills `/api/logs/ui` flood)
- `frontend/src/lib/renderers/grid/GridRenderer.svelte:45-51` and `frontend/src/lib/renderers/masonry/MasonryRenderer.svelte:48-54` — replace `hashes.join('|')` diff with `(positions.length, first.id, last.id, columnCount)` tuple
- `frontend/src/lib/VaultView.svelte:143-174` — only fetch `/api/stats` on `!append`
- `frontend/src/lib/Inspector.svelte:25-29` — track `lastLoadedHash`, skip refetch if same
- `frontend/src/lib/VaultView.svelte:265-291` — single `finally { fetchItems(); }` in `deleteSelected`

Validation: scroll a 1000+ vault, watch network panel — `/api/logs/ui` and `/api/stats` traffic should drop sharply.

### Phase 5 — Selection / Memoization (~3 hr, medium risk)

Hot-path allocations on user interaction.

- `frontend/src/lib/VaultView.svelte:222-225,235` — build `Map<hash, {item, group}>` index keyed off `groupedItems`; replace `find`/`findGroupForItem` with O(1) lookups
- `frontend/src/lib/VaultView.svelte:52,218-220` — memoize `jsVisualHashOrder`/`loadedHashOrder`
- `frontend/src/lib/VaultView.svelte:51` — snapshot last-emitted status, dispatch only on change
- `frontend/src/lib/VaultView.svelte:69-87` — convert `appendToGroups` to mutate a persistent `groupsMap`, only rebuild references for touched groups

Risk: changes interaction-heavy state; need shift-click range selection regression test.

Validation: click rapidly through tiles — no visible lag at 5k items.

### Phase 6 — Architectural Refactors (~4 hr, higher risk)

Touch shared infrastructure. Do these in their own commit.

- `frontend/src/lib/renderers/masonry/masonryLayout.ts:46-51,126-131` — wrap module-level cache in a `createMasonryLayoutEngine()` factory; instantiate per-renderer; drop dead `lastStore`
- `frontend/src/lib/VaultView.svelte:42-44,357-393` — extract `useIntersection` and `useResize` Svelte actions; remove duplicate near-viewport check (`IntersectionObserver` rootMargin already covers it)
- `frontend/src/App.svelte:59-72` — pick one mounting strategy: either `{#if activeTab === 'vault'}` for symmetry, or document why VaultView stays mounted and gate observers on a visibility prop
- `frontend/src/lib/Inspector.svelte:175` — replace `document.querySelector('.focus-overlay')` with prop or store
- `frontend/src/lib/renderers/grid/GridRenderer.svelte:42-43` and `frontend/src/lib/renderers/masonry/MasonryRenderer.svelte:45-46` — make reactive dependencies explicit (`$: emitVisualOrder(layout.positions)`)

Risk: masonry cache refactor can introduce visual jitter if cache invalidation is wrong. Test long scroll sessions.

### Phase 7 — Logging & SSE Throughput (~2 hr, medium risk)

- `frontend/src/lib/logger.ts:3-15` — batch `uiLog` POSTs with 300ms flush window; drop DEBUG by default in production; exempt ERROR from batching
- `frontend/src/lib/Ingestion.svelte:50` and `frontend/src/lib/LogsView.svelte:133` — replace `[...logs, entry].slice(-N)` with mutate-and-trim; batch incoming SSE frames per RAF
- `frontend/src/lib/Ingestion.svelte:52` and `frontend/src/lib/LogsView.svelte:135` — replace magic `setTimeout(_, 30)` with `tick()` or RAF

### Phase 8 — Image/Video Loading Strategy (~3 hr, needs measurement)

Behavior change with user-visible impact.

- `frontend/src/lib/VaultGroupTile.svelte:55,58` and both renderers — flip `eagerImages` default to `false`; restore `content-visibility: auto` on tile (currently overridden to `visible` in renderer `:global` style). Measure scroll perf before/after.
- `frontend/src/lib/VaultGroupTile.svelte:58-59` — video hover plays full file. Options:
  1. Cap to videos under N MB (frontend size check if available)
  2. Backend endpoint for short preview clip (requires backend work)
  3. Animated WebP/GIF thumbnail at ingestion time (requires pipeline work)

Decision needed from owner: which video preview strategy. Option 2 or 3 is the right long-term answer but blocks on backend.

### Phase 9 — Tauri / Environment (~1 hr, low risk but verify on real Tauri build)

- `frontend/src/lib/MediaFocus.svelte:53` — replace `(window as any).__TAURI__` with `import.meta.env.TAURI_PLATFORM` check, or always call `appWindow.setFullscreen(false)` and let it no-op outside Tauri

Validation: must test in actual `tauri dev` and packaged build, not just `vite dev`.

### Phase 10 — A11y Debt (~3 hr, low risk)

Listed in Current Issues "svelte-check Accessibility Debt". Mostly mechanical.

- Click-only divs: add `role="button"` + `tabindex="0"` + `on:keydown` for Enter/Space
  - `frontend/src/lib/MediaFocus.svelte:109,123`
  - `frontend/src/lib/VaultGroupTile.svelte:52`
- Labels: wrap inputs or add `for=`/`id=` pairs in `frontend/src/lib/SettingsView.svelte:50-105`
- Video tracks: add `<track kind="captions">` (can be empty) or suppress with `<!-- svelte-ignore a11y-media-has-caption -->` per element

Validation: `npm run check` shows zero warnings.

### Suggested Execution Order

1. Phases 1-2 in one sitting — pure cleanup, no risk, builds momentum
2. Phase 3 before Phase 4 — error handling first so perf changes don't mask new bugs
3. Phase 4 standalone — measurable perf wins
4. Phase 5 standalone — needs interaction testing
5. Phase 6 standalone commit — biggest blast radius
6. Phases 7-9 independently, in any order
7. Phase 10 last (or any time as filler) — pure mechanical

Total rough estimate: ~22 hours of focused work over 5-7 sittings. Phases 1-4 alone (~6 hr) cover ~70% of user-visible improvement.

### Cross-Cutting Considerations

- Tests: project has no frontend test suite visible in the tree. Consider adding a minimal Vitest harness for `search.ts`, `selection.ts`, `layout.ts`, `gridLayout.ts`, `masonryLayout.ts` before Phase 5/6 — these are pure functions and easy wins for safety.
- Validation environment: several issues (Tauri detection, eager image perf, masonry cache) only manifest in packaged builds or with large vaults. Need a 5k+ item test vault.
- Backend coordination needed for: video preview endpoint (Phase 8), DB journal mode status endpoint (Phase 1, optional), ingestion run-status endpoint as alternative to SSE-driven flag (Phase 3, optional).

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
