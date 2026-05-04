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
- Frontend session-key promise resets on failure so mutating API calls can recover after a transient backend startup error.
- Inspector aborts in-flight fetches on teardown and skips redundant reloads via `lastLoadedHash` tracking.
- SearchBar debounce timers and Ingestion/LogsView SSE reconnect timers are cleared on component teardown.
- Ingestion run state is now driven by the SSE `Ingestion cycle complete` signal; the fake 5-second completion timer was removed and POST failures surface an alert.
- Review and Vault views check `response.ok` before mutating local state; vault items/stats fetches use separate try/catch blocks.
- Stats panel uses a request-sequence counter to discard stale facet responses on fast typing/tab switches.
- Masonry layout cache moved into a per-renderer factory closure (`createMasonryLayoutEngine`) so multiple renderer instances can no longer corrupt each other; dead `lastStore` reference removed.
- VaultView now keeps a persistent `groupsById` map plus `hashIndex` (`Map<hash, {item, group}>`) for O(1) selection lookup; append no longer copies untouched groups, status events deduplicate, and renderer visual-order changes update the index in place.
- Renderer reactive blocks receive explicit dependency args; `logSummary` is gated behind `import.meta.env.DEV` and demoted to DEBUG, eliminating the per-recompute `/api/logs/ui` flood.
- `emitVisualOrder` diffs a tuple key (`positions.length:first.id:last.id:columnCount`) instead of joining all hashes into a multi-KB string.
- Inspector focus-mode detection now reads a `focusMode` prop instead of querying `.focus-overlay` from the DOM on every keypress; A/D/W/F handlers form a clean `else if` chain.
- VaultView observer plumbing is replaced by `watchIntersection` / `watchResize` helpers in `frontend/src/lib/observers.ts`; the redundant manual near-viewport check and 50 ms polling timer were removed (the IntersectionObserver `rootMargin: 400px` already covers the case).
- VaultView always-mounted strategy is documented in `App.svelte`; observers idle when `display:none` so the cost is intentional.
- Misleading hardcoded "DB: WAL" footer text removed; `assetUrl` / `eventSourceUrl` aliases dropped in favor of `apiUrl`.

## Current Issues

- Production sidecar packaging has a build path, but the generated sidecar still needs release-build validation on a clean machine.
- Frontend accessibility warnings remain in Svelte build output.
- CSP is practical rather than strict and should be revisited after production packaging is stable.
- Shift-click range selection now uses renderer-emitted visual order for both masonry and grid. It still needs real-use validation on large mixed media vaults.
- **Sidecar Port 8000 Binding (Brittleness):** The compiled `lmz-api` binary internally hardcodes `uvicorn.run(port=8000)`. If port 8000 is occupied by another app, the backend fails to bind and the Tauri app renders a white screen. Production sidecars should dynamically bind to an available port provided by Tauri.
- **`svelte-check` Accessibility Debt:** Running `npm run check` currently reports 25 accessibility warnings around labels, clickable divs, and media captions. Slated for Phase 10.
- **Virtual Renderer Validation:** Masonry and grid now use virtualized renderers. Large-vault behavior, video unmount behavior, zoom stability, and grouped-media persistence should be validated in real browsing sessions.
- **UI logger throughput:** Every `uiLog` still POSTs `/api/logs/ui` individually; ingest/scroll sessions can produce many requests per second. Slated for Phase 7 batching.
- **Image/video loading strategy:** `VaultGroupTile` still passes `eagerImages={true}` and overrides `content-visibility: auto`. Video hover plays the full file. Slated for Phase 8 (needs decision on preview strategy).
- **Tauri detection:** `MediaFocus.svelte` still uses `(window as any).__TAURI__` (renamed to `__TAURI_INTERNALS__` in v2). Slated for Phase 9; needs real Tauri build to validate.

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

### Phase 1 — Hygiene (~30 min, zero risk) ✅ DONE

Single-line cleanups, no behavior change. Validated with `npm run check` (0 errors).

- ✅ `frontend/src/lib/renderers/grid/GridRenderer.svelte` — removed unused `onDestroy` import
- ✅ `frontend/src/lib/search.ts` — dropped redundant `.map(t => t.trim())` from text-term split
- ✅ `frontend/src/lib/Ingestion.svelte` — `parseTimer` typed as `number | null`, uses `window.setTimeout`, null-guarded on clear
- ✅ `frontend/src/lib/SearchBar.svelte` — collapsed two parallel `startsWith` checks to a single `cmd.slice(1).toLowerCase().startsWith(query)` after stripping the leading `>`
- ✅ `frontend/src/lib/statsStore.ts` — replaced `Number(x || 0)` with `Number(x) || 0` in both `queueStats` and `refreshReviewCount`
- ✅ `frontend/src/lib/Inspector.svelte` — `videoElement: HTMLVideoElement | undefined`, guarded usages
- ✅ `frontend/src/lib/Inspector.svelte` — A/D/W/F keyboard handlers unified into a single `else if` chain
- ✅ `frontend/src/App.svelte` — removed misleading hardcoded "DB: WAL" footer text

### Phase 2 — Resource Cleanup (~1 hr, low risk) ✅ DONE

Memory leaks and orphaned timers/observers — additive `onDestroy` hooks.

- ✅ `frontend/src/lib/Inspector.svelte` — `onDestroy(() => abortController?.abort())` cancels in-flight `/api/items/{hash}` fetch when the panel closes
- ✅ `frontend/src/lib/SearchBar.svelte` — `onDestroy` clears both `searchDebounceTimer` and `refreshDebounceTimer`
- ✅ `frontend/src/lib/Ingestion.svelte` and `frontend/src/lib/LogsView.svelte` — reconnect timer handle stored, `clearTimeout` invoked on `onDestroy` so closed views can no longer revive an EventSource
- ✅ `frontend/src/lib/api.ts` — `assetUrl` and `eventSourceUrl` 1-line aliases removed; `MediaFocus.svelte` and `VaultGroupTile.svelte` updated to import `apiUrl` directly

### Phase 3 — Error Handling (~2 hr, medium risk) ✅ DONE

Surfaces failures instead of silently desyncing the UI.

- ✅ `frontend/src/lib/api.ts` — `.catch` resets `apiKeyPromise = null`, so the next `apiFetch` retries fetching the session key after a transient backend startup error
- ✅ `frontend/src/lib/ReviewView.svelte` — both `loadReview` and `handleAction` check `res.ok` before mutating local state and surface a toast/log on failure
- ✅ `frontend/src/lib/VaultView.svelte` — split into separate try/catch blocks for items and stats; both verify `res.ok`; stats failures no longer surface as "Failed to fetch items"
- ✅ `frontend/src/lib/StatsView.svelte` — `requestSeq` counter increments at call start; three checkpoints (`if (seq !== requestSeq) return`) discard stale responses; the `finally` clause clears `loading` only when the current sequence still matches
- ✅ `frontend/src/lib/Ingestion.svelte` — `running` is now driven by the SSE "Ingestion cycle complete" message; the fake `setTimeout(... 5000)` was removed; POST failures show an alert and `res.ok` is checked

### Phase 4 — Performance Quick Wins (~2 hr, low-medium risk) ✅ DONE

High-impact, contained changes.

- ✅ `GridRenderer.svelte` and `MasonryRenderer.svelte` — `logSummary` now gated behind `import.meta.env.DEV` and demoted from INFO to DEBUG; the per-recompute `/api/logs/ui` flood is gone in production builds
- ✅ Both renderers — `emitVisualOrder` now diffs a compact tuple key (`positions.length:first.id:last.id:columnCount`) instead of joining all hashes into a multi-KB string per layout tick
- ✅ Both renderers — reactive blocks call helpers with explicit args (e.g. `$: emitVisualOrder(layout.positions)`), so dependency tracking no longer relies on Svelte's static lookup inside helper functions
- ✅ `frontend/src/lib/VaultView.svelte` — `/api/stats` is fetched only on the initial (`!append`) request; subsequent paginated appends skip it (already covered by the polled stats store)
- ✅ `frontend/src/lib/Inspector.svelte` — `lastLoadedHash` tracker bails out of `loadFullDetails` when the hash hasn't changed; `handleUpdate`'s spread no longer triggers a redundant `/api/items/{hash}` fetch
- ✅ `frontend/src/lib/VaultView.svelte` — `deleteSelected` now refetches via a single `finally { fetchItems(); }`, eliminating the double-refetch on success and the duplicate work on failure

### Phase 5 — Selection / Memoization (~3 hr, medium risk) ✅ DONE

Hot-path allocations on user interaction collapsed to O(1) where possible.

- ✅ `frontend/src/lib/VaultView.svelte` — persistent `groupsById: Map<string, VaultGroup>` plus `groupOrder: string[]` keep group references stable; `appendToGroups(newItems, reset)` only allocates fresh group objects for IDs that received new items, ending the O(n²) "spread every group on every page" allocation
- ✅ `frontend/src/lib/VaultView.svelte` — `hashIndex: Map<string, { item: VaultItem; group: VaultGroup }>` is rebuilt alongside `appendToGroups`; `handleSelectItem` and selection helpers now do O(1) `hashIndex.get(hash)` lookups instead of `groups.find().items.find()`
- ✅ `frontend/src/lib/VaultView.svelte` — `lastStatus` snapshot guards `emitStatus`; the footer no longer receives one custom event per layout-measurement frame, only on real changes
- ✅ `frontend/src/lib/VaultView.svelte` — visual-order tracking and `loadedHashOrder` reuse the `hashIndex` Map rather than allocating fresh `flatMap` arrays per click

Risk noted: shift-click range selection across mixed media remains slated for real-vault validation (still listed in Current Issues).

### Phase 6 — Architectural Refactors (~4 hr, higher risk) ✅ DONE

Shared infrastructure cleanup — validated with `npm run check` (0 errors, 25 a11y warnings only).

- ✅ `frontend/src/lib/renderers/masonry/masonryLayout.ts` — module-level cache (`lastCacheKey`, `lastCache`, `lastPositions`, `lastActiveIndexes`) is now wrapped in a `createMasonryLayoutEngine()` factory closure; each `MasonryRenderer` instance gets its own engine via `const computeLayout = createMasonryLayoutEngine();`. The dead `lastStore` reference was dropped. New exported type: `MasonryLayoutEngine`.
- ✅ `frontend/src/lib/observers.ts` (new file) — `watchIntersection(node, options)` and `watchResize(node, onResize)` helpers each return a `cleanup()` function. They centralize observer setup and removed the need for `bind:this` plus parallel observer state across the component.
- ✅ `frontend/src/lib/VaultView.svelte` — uses the new helpers; the duplicate `sentinelIsNearViewport` / `maybeLoadMore` / `scheduleLoadMoreCheck` machinery and the 50 ms `loadMoreCheckTimer` are gone. The `IntersectionObserver` `rootMargin: 400px` covers the near-viewport case directly.
- ✅ `frontend/src/App.svelte` — chose the always-mounted strategy and documented it: `VaultView` stays mounted (via `class:hidden`) to preserve scroll position, selection, and loaded items; observers are idle when `display:none`, so the cost is negligible. Other tabs continue using `{#if}` so they can re-fetch on demand.
- ✅ `frontend/src/lib/Inspector.svelte` — added `export let focusMode: 'normal' | 'wide' | 'fullscreen' = 'normal';`; the keyboard handler now bails with `if (focusMode !== 'normal') return;` instead of calling `document.querySelector('.focus-overlay')` on every keypress. `VaultView.svelte` passes the current focus mode through.
- ✅ Renderer reactive dependencies — already made explicit during Phase 4 (`$: emitVisualOrder(layout.positions)`, `$: logSummary(groups, visiblePositions, ...)`).

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

1. ✅ Phases 1-2 in one sitting — pure cleanup, no risk, builds momentum
2. ✅ Phase 3 before Phase 4 — error handling first so perf changes don't mask new bugs
3. ✅ Phase 4 standalone — measurable perf wins
4. ✅ Phase 5 standalone — needs interaction testing
5. ✅ Phase 6 standalone commit — biggest blast radius
6. Phases 7-9 independently, in any order — **REMAINING**
7. Phase 10 last (or any time as filler) — pure mechanical — **REMAINING**

Status (2026-05-04): Phases 1-6 complete and validated with `npm run check` (0 errors, 25 a11y warnings — Phase 10 territory). Remaining: Phase 7 (logger batching), Phase 8 (image/video loading — needs decision on video preview strategy), Phase 9 (Tauri detection — needs real Tauri build to verify), Phase 10 (a11y).

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
