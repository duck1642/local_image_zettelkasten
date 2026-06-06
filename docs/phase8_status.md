  # LMZ Current Status

Last updated: 2026-06-06

## Current Status

LMZ is a local media vault desktop app.

- Frontend: Tauri + Svelte.
- Backend: local FastAPI/Python API under `backend/`.
- Runtime model: SQLite owns item identity/source fields; Markdown mirrors item identity fields and remains the editable source for topics/WD metadata.
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
- Workspace DB: `data/workspace.db`.
- Shared topic library: `data/topics/`.
- Active vault root: `data/vaults/<active_vault>/`.
- Vault DB: `data/vaults/<active_vault>/db/lmz_main.db`.
- Vault assets: `data/vaults/<active_vault>/vault/assets/{hash[:2]}/{storage_id}.{ext}`.
- Vault notes: `data/vaults/<active_vault>/vault/notes/{hash[:2]}/{storage_id}.md`.
- WD tag cache: `data/vaults/<active_vault>/wd-tags/{hash[:2]}/{storage_id}.json`.
- Thumbnails: `data/vaults/<active_vault>/ui_cache/thumbnails/{hash[:2]}/{storage_id}.jpg`.
- Review quarantine: `data/vaults/<active_vault>/review/`.
- Local ingest staging: `data/vaults/<active_vault>/local_ingest/`.
- Online ingest staging: `data/vaults/<active_vault>/online_ingest/`.
- Logs: `data/vaults/<active_vault>/logs/raw/`, `data/vaults/<active_vault>/logs/structured/`.
- Secrets: `secrets/`.

## Working Areas

- Local image, GIF, and video ingestion.
- External URL ingestion via gallery-dl and yt-dlp.
- Batch-safe Pixiv, X/Twitter, Instagram, Pinterest, YouTube community ingestion.
- Browser extension capture and queue append are implemented as Phase 9 completion; see `docs/lmz_roadmap.md` and `docs/lmz_architecture.md`.
- SHA256 item identity with compact `storage_id` physical filenames.
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
  - Live hint: `/cmd; a:artist; p:platform; t:topic; #wd-tag`.
  - `/` command.
  - `a:` artist.
  - `p:` platform.
  - `t:` note-frontmatter topic.
  - `#` WD tag.
  - `;` separates structured filters.
  - Command syntax is hardcoded in frontend search parser/search UI.
- Search semantics:
  - Different prefix types use AND.
  - Repeated `a:` and `p:` use OR.
  - Repeated `t:` and `#` use AND.
  - Plain text terms use AND.

## Current Commands

- `/masonry`, `/grid`.
- `/zoom-in`, `/zoom-out`.
- `/toggle-inspector`.
- `/ram-track`.
- `/scan-auth`.
- `/cleanup-review`.
- `/sort-newest`, `/sort-oldest`, `/sort-artist`.
- `/media-all`, `/media-image`, `/media-video`.

## Done Tasks

- Historical completed work has been moved to `docs/lmz_roadmap.md`, mainly Phase 8 and Phase 9.
- Current operational completion checkpoints remain below under `Done But Needs Check`.

## Current Test Results

### 2026-05-31 Crosscheck

- Frontend `npm.cmd run check`: passes with 0 Svelte/TS warnings.
- Backend AST parse check: passes.
- Backend import smoke: passes when `LMZ_CONFIG_PATH` is pointed at the mock-vault config.
  - Note: running the import smoke against the active real config may try to open real vault logs.
- Frontend findings fix validation:
  - `npm.cmd run check`: passes.
  - `git diff --check`: passes; Git reports only normal LF/CRLF working-copy warnings.
  - `npm.cmd run test:mock-vault -- --grep "inspector drafts WD promotion"`: passes.
  - `npm.cmd run test:mock-vault -- --grep "settings"`: passes.
  - `npm.cmd run test:mock-vault -- --grep "stats"`: passes.
  - `npm.cmd run test:mock-vault -- --output test-results-full-fix`: `29 passed`.
  - Fixed stale Inspector, Settings, and Stats Playwright selectors after current UI copy/layout changes.
- Latest Inspector chip stabilization check:
  - `npm.cmd run check`: passes.
  - `npm.cmd run test:mock-vault -- --grep "inspector drafts WD promotion"`: passes.
  - Full mock-vault suite has not been rerun after the latest chip stabilization edits.

### Phase A Generated-Vault Performance Findings

- Completed real generated-vault runs:
  - Initial `800`, `10k`, and `50k`: backend/index/API plus headed Tauri WebView scrolling.
  - WD-scale reruns: `800`, `10k`, and `50k` with realistic WD pressure (`1` rating, `1` character tag, `20` general WD tags per item).
  - Facet-count optimization reruns: `800`, `10k`, and `50k` after adding precomputed topic/WD facet counts.
  - Metadata internals and artist/platform optimization reruns: `10k` and `50k` after Pass 1/2.
  - `100k`: skipped for now because `50k` exposed the scale costs clearly.
- Frontend scrolling / virtualization:
  - headed Tauri scroll tests passed at `10k` and `50k`.
  - visible tile counts stayed bounded (`50-54` masonry, `36` grid).
  - mounted video counts stayed bounded (`7` at `10k`, `2` at `50k` in sampled scroll/filter paths).
  - frontend heap stayed low (`~9.4 MB` at `10k`, `~7.4 MB` at `50k` after video filter).
  - current evidence points away from scrolling as the primary bottleneck.
- Backend/API scale:
  - read-path DB connection cleanup reduced normal `50k` item-list/filter p50s from roughly `129-252ms` to mostly single/tens of ms.
  - cached metadata counters reduced `/api/metadata-index/status` from about `228ms` p50 at `50k` with `1.1M` WD rows to low/tens of ms.
  - exact topic/WD filters use indexed metadata lookups when exact values exist.
  - WD exact filter stayed fast under realistic scale: `50k` / `1.1M` WD rows, `items-filter-wd-tag` p50 `~17ms`.
- WD/topic facets and suggestions:
  - realistic `50k` WD run before facet counts exposed the bottleneck:
    - `facets-wd-tag` p50 `~1201ms`, p95 `~2332ms`.
    - `search-suggestions-wd-tag` p50 `~831ms`.
  - precomputed facet-count table fixed the interactive counter path:
    - `800`: `17.6k` WD rows, `928` facet-count rows, `facets-wd-tag` p50 `~4ms`.
    - `10k`: `220k` WD rows, `9103` facet-count rows, `facets-wd-tag` p50 `~18ms`, WD suggestions p50 `~16ms`.
    - `50k`: `1.1M` WD rows, `30253` facet-count rows, `facets-wd-tag` p50 `~19ms`, WD suggestions p50 `~32ms`.
- Artist/platform facets and filters:
  - artist/platform facets now use the same facet-count path as topic/WD counters.
  - `50k` Pass 2 backend API rerun:
    - `items-filter-artist` p50 `~9ms`.
    - `items-filter-platform` p50 `~19ms`.
    - `facets-artist` p50 `~7ms`.
    - `facets-platform` p50 `~6ms`.
    - `search-suggestions-artist` p50 `~17ms`.
- RAM:
  - backend memory remained stable enough for these profiles (`~75 MB` at `800`, `~82-85 MB` at `10k`, `~120 MB` at `50k` after WD/facet-count runs).
  - no RAM explosion observed.
- Primary bottlenecks:
  - full metadata index rebuild remains the largest backend cost.
    - realistic WD `10k`: `~30-31s` after Pass 1/2.
    - realistic WD `50k`: `~190-193s` after Pass 1/2.
  - topic/WD filtered item queries still sometimes land in tens of ms at `50k`.
  - broad text search still uses `LIKE '%term%'` paths.
- Next optimization targets:
  - further inspect full metadata rebuild cost.
  - profile topic/WD filtered item paging.
  - evaluate FTS5 for broad text discovery.
  - rerun headed Tauri/WebView scroll tests after backend changes if needed.
  - rerun `100k` only after the above improvements.

### Remaining Optimization Sequence

- Pass 3 - remaining metadata/query scale:
  - Pass 3A low-risk cleanup is mostly implemented:
    - facet fallback scan avoids scanning when ready count tables simply have zero matches.
    - full metadata rebuild reports stage timing.
    - normal full rebuild skips deep stale validation by default.
  - Still pending:
    - inspect query plans for topic/WD filtered paging.
    - decide on composite indexes from measured plans.
    - evaluate FTS5 for broad text search.
  - defer `100k` until Pass 3A/3B results are clean.

## Deferred / Will Do Later

### Search/index improvements

- persistent search/facet tables beyond current derived metadata index if needed for scale.
- search chips.
- Search/index scaling:
  - RAM hydration still bulk-loads pHash, tile, URL, and video signatures.

### Source metadata maintenance

- source URL normalization migration tool.
- normalization is active in runtime paths (`source_url_norm` is written on ingest/update).
- existing rows are backfilled lazily by `init_database()`.
- no standalone migration/maintenance tool exists yet.



### Phase D - UI Polish

- Review panel design refinement.
- Fullscreen board/view refinements.
- Remaining Inspector fine polish and tag workflow edge cases.
- Remaining Stats/Settings fine polish after real use.
- Custom context menu for vault tiles.
- Animation-aware GIF handling beyond first-frame thumbnail/tag behavior.
- Video hover preview strategy:
  - current hover preview can download original video.
  - options: file-size cap, backend preview clip endpoint, animated WebP thumbnail.
- Video embedding performance:
  - sampled frame extraction now uses one FFmpeg subprocess per batch.
  - embedding/tagging still depends on extracting sampled original video frames.

### Phase E - Browser Extension Follow-Up

- Browser extension MVP is implemented in Phase 9.
- Remaining follow-up:
  - fuller Chrome manual smoke.
  - longer Firefox compatibility smoke.
  - more real-world capture testing for blob/canvas/auth-gated/protected media.
  - optional platform preset/alias management after real extension use settles platform names.

### Final Phase - Runtime / Packaging Hardening

- Dynamic sidecar port coordination:
  - startup handshake/API base/CSP/lifecycle.
  - remove fixed `localhost:8000` assumptions from frontend/Tauri runtime paths.
- Packaging-time security checks.
- Clean-machine release validation.

### Longer-Term Platform Gaps

- YouTube community partial policy:
  - one failed expected image can still keep the post retryable.

## Done But Needs Check

- Phase C prerequisites and tag/topic maintenance:
  - Inspector topic workflow is implemented:
    - add manual topics from Inspector through a compact `+` input.
    - reuse existing topics from an Inspector dropdown backed by all topic facets.
    - rename topics from Inspector using the shared topic maintenance modal/API.
    - topic edits remain draft-only until item metadata save.
  - Stats topic creation is implemented:
    - `POST /api/topics` creates/reuses shared topic files under `data/topics/`.
    - Stats Topics exposes a compact `+` create flow.
    - newly created unused topics appear in `All` topic scope and are selectable later from Inspector.
  - item metadata save lock timeout was fixed by skipping redundant workspace WD dictionary sync during item patch and review replacement preserve reindex paths.
  - RAM tracker precision is implemented:
    - backend `/api/system/memory` reports `backend_mb`, `runtime_mb`, `app_mb`, role breakdowns, process count, mode, warnings, and process rows.
    - runtime RAM separates backend, Tauri host, WebView2, and active subprocesses from dev tooling.
    - frontend footer shows runtime RAM, backend RAM, WebView RAM, dev-tool RAM, and JS heap without double-counting JS heap into runtime total.
    - targeted RAM aggregation tests pass for backend-only, packaged sidecar, dev launcher, project-scan, and inaccessible-process cases.
  - Phase C vault/workspace reliability pass is implemented:
    - existing dynamic workspace/vault switching paths are verified by targeted tests.
    - stale direct `DB_PATH` import was removed from the active SQLite helper.
    - vault rename/delete flows have targeted backend hardening coverage.
    - Settings exposes vault merge preview/confirm with support for destructive merging (optionally deleting source vaults on success and unlinking all copied target files on execution failure).
    - vault health audit reports missing files, orphan files/caches, bad storage IDs, hash mismatches, stale metadata rows, facet drift, broken/unused topics, review mismatches, and workspace dictionary drift.
    - vault health and repair logic is hardened to filter expected tag caches and thumbnails by image/video MIME type, and preserve skipped/failed tagging caches from being deleted as orphans.
    - vault repair can rebuild metadata/facets, rebuild thumbnails, prune derived cache orphans, reconcile review sidecars, and quarantine orphan assets/notes.
    - vault backup/export/import package flows are exposed through backend APIs and Settings controls.
    - Split/separate vault flows are deferred until the real workflow is clearer.
    - Optional metadata maintenance (hiding/ignoring WD tags) is handled.
    - Optional UX polish (search chips, richer Inspector tag editing) is reviewed and deferred.
  - runtime context layer is implemented for workspace/vault paths while preserving legacy import-time constants.
  - active-vault and workspace DB connection helpers are context-aware.
  - queues, review cache, logging, metadata watchdog paths, topics, thumbnails, downloader staging, and local ingest/review path access are context-aware.
  - SearchManager RAM indexes are context-aware per active vault DB.
  - fixed static media mounts were replaced with dynamic active-vault asset/review routes.
  - remaining long-lived ingest/metadata runtime state is switch-aware and backend switch preflight is implemented.
  - `backend/web_api.py` is split into router modules while preserving the sidecar entrypoint/facade.
  - shared metadata maintenance logic exists for topic/WD rename, delete, and merge operations.
  - frontend runtime/session store invalidates Vault, Stats, Inspector, Search, Ingestion, Review, and Logs state on vault/workspace switch.
  - large frontend Phase C surfaces were split, especially `StatsView.svelte`.
  - backend API routes are exposed for topic delete/merge and WD tag rename/delete.
  - Stats topic/WD panels expose explicit actions for topic delete/merge and WD tag rename/delete.
  - backend rewrites affected Markdown frontmatter, refreshes metadata indexes/facets, and preserves existing API search semantics.
  - targeted backend and mock-vault frontend tests pass; needs real-vault smoke for dynamic workspace/vault switching, Stats metadata actions, and metadata maintenance rollback behavior.

- Phase D UI polish/refactor work started:
  - local named Svelte icon components are active under `frontend/src/lib/icons/`.
  - icon policy is local-first: no `lucide-svelte` runtime dependency by default; selected Lucide-style SVG paths may be vendored into local components.
  - Settings UI was split into focused panels and helpers:
    - `SettingsCoreConfigPanel.svelte`
    - `SettingsMaintenancePanel.svelte`
    - `SettingsRuntimePanel.svelte`
    - `SettingsShortcutsPanel.svelte`
    - `SettingsVaultPanel.svelte`
    - `SettingsVaultToolsPanel.svelte`
    - `SettingsVaultMergePanel.svelte`
    - `SettingsVaultHealthPanel.svelte`
    - `SettingsWorkspacePanel.svelte`
    - `VaultHealthDetailsModal.svelte`
    - `settingsApi.ts`, `settingsUtils.ts`, and `settings.css`.
  - Settings now uses tabbed sections and reduced text-heavy actions while preserving existing API behavior.
  - Ingestion UI is split between `OnlineIngestion.svelte`, `LocalIngestion.svelte`, and shared `ingestion.css`.
  - Online queue metadata directives are implemented:
    - shared queue parser supports comments, `@artist: name`, `@platform: name`, URL groups, and `---`.
    - queue count, parse preview, and ingestion use the same parser.
    - explicit queue artist/platform metadata reaches online ingestion.
    - scraper-derived artist/title remains stripped before `process_file()`.
    - frontend queue editor shows grouped preview, warnings, warning line numbers, directive suggestions, and syntax help.
    - alias-aware artist matching remains deferred.
  - Inspector was split into media preview, metadata grid, topic editor, WD suggestions, and shared tag chip components.
  - Inspector topic/WD chips share `InspectorTagChip.svelte`, with rating/character/general/topic color semantics and local icon actions.
  - Frontend findings fix pass is implemented:
    - WD suggestion promotion toggle is covered by a targeted mock-vault test.
    - Real pointer-hit behavior still needs manual smoke after chip UI changes because the current targeted test uses synthetic click events.
    - Inspector save, Settings, and Stats mock-vault selectors were updated to current UI copy/layout.
    - `api.ts` retry delay now removes abort listeners after normal timeout resolution.
    - Settings static inline styles and inline emoji glyphs were moved to `settings.css` and local icon components where practical.
  - Stats UI is split into controls, facet panel, artist panel/detail/merge modal, metadata action modal, filter bar, API helpers, utilities, and `stats.css`.
  - Stats chip CSS is namespaced separately from Inspector chips to avoid cross-panel style leakage.
  - targeted frontend checks were run during refactor; still needs real-vault smoke for Settings, Stats, Inspector, and Ingestion UI paths.

- Phase B - Knowledge tools core:
  - SQLite-owned identity is active for `items.source_artist`, `items.platform`, `items.source_url`, file metadata, and storage identity.
  - Markdown mirrors artist/platform/source/date fields for readability.
  - normal metadata reindex no longer silently imports Markdown artist/platform/date back into SQLite.
  - online ingestion only trusts scraper metadata for `source_url` and `platform`; artist/title are app/user-owned metadata.
  - topics and WD tags remain Markdown/index-owned.
  - workspace-level metadata DB is active for shared artists, platforms, and WD tag dictionaries.
  - shared topic library is active under `data/topics/`.
  - artist backfill/resolver skips placeholder identity values.
  - artist aliases, links, notes, rigid kind values, rename, and merge are implemented.
  - artist merge keeps selected artist as canonical, moves aliases/links, appends source notes, rewrites affected items/notes, and deletes source artist rows.
  - platform dictionary/backfill/API are implemented as shared workspace metadata.
  - local ingest artist autocomplete and platform dropdown are wired.
  - Stats Artists panel is implemented with resizable split view.
  - Stats topic/WD panels support multi-select filtering into Vault search.
  - Stats `Used`/`All` modes work for Topics, Artists, Platforms, and WD Tags against active-vault usage plus workspace-wide libraries.
  - Stats and Inspector show topic and WD counts through facet/index data.
  - Inspector supports per-item draft topic/WD editing, WD-tag removal, and promote WD tag to manual topic.
  - topic files are created/reused on save, notes store relative links, and legacy plain topics remain readable/indexable.
  - Obsidian workspace mode uses `<ObsidianVault>/lmz/` with the same relative workspace/vault layout.
  - workspace chooser and workspace registry are implemented; env `LMZ_CONFIG_PATH` still overrides registry.
  - multiple vault support is implemented with per-workspace shared metadata and per-vault DB/assets/review/logs/cache folders.
  - topic rename is implemented from Stats Topics via explicit `...` action and backend `POST /api/topics/rename`.
  - topic rename updates shared topic file paths and rewrites linked/legacy topic refs across all registered vaults.
  - needs real-vault smoke for artist rename/merge, local ingest artist autocomplete, platform dropdown, Stats filtering handoff, Inspector edits/counts, topic rename, workspace switching, and multi-vault isolation.

- Phase A - Stability V1:
  - implementation is considered finished.
  - Batch 1 maintenance quick wins, Batch 2 runtime correctness, generated test vaults, perf harnesses, WD-scale data, metadata indexing optimizations, fast frontmatter parsing, incremental dirty-queue repair, and Settings rebuild progress are implemented.
  - generated-vault validation covered `800`, `10k`, `50k`, and targeted `100k` backend/index/API paths.
  - frontend scrolling/virtualization passed at `10k` and `50k`; backend RAM stayed stable in generated-vault runs.
  - normal incremental indexing is fast enough for personal use; full rebuild remains a maintenance/recovery path.
  - needs real-vault smoke over normal use: drag-drop ingest with WD tags, watchdog note edits, Settings rebuild progress, config edit/save, log stream, thumbnails, review replace/preserve, and one image/video ingest.

- Phase A Batch 1 - Maintenance quick wins:
  - stale `update_tools` wrapper replaced with a working maintenance entrypoint.
  - dependency maintenance flow covers checks, downloader updates, and Playwright Chromium install.
  - Settings includes maintenance actions for auth scan, metadata index rebuild, and review cleanup.
  - maintenance actions use per-action loading/status text and frontend logging.
  - thumbnail path usage was consolidated through helper-backed paths.
  - needs longer real-vault smoke for UI maintenance actions.

- Phase A Batch 2 - Runtime correctness:
  - `get_config()` now uses an mtime-keyed cache with explicit invalidation after config writes.
  - config reads return defensive copies while preserving secret merge/schema validation behavior.
  - new timestamp writes use the shared UTC `YYYY-MM-DD HH:MM:SS` helper.
  - log streaming was hardened with idle heartbeats, truncate/rotation handling, tail-on-connect, and bounded frontend reconnects.
  - targeted tests passed; needs longer real app log-stream/config-edit smoke.

- Compact storage ID runtime model:
  - SHA256 `hash` remains the item/API identity.
  - physical asset, note, WD cache, and thumbnail paths now use compact `storage_id` filenames under `hash[:2]` shard folders.
  - runtime full-hash filename fallback helpers were removed.
  - helper functions no longer open SQLite connections just to resolve storage paths.
  - API routes, inspector path/open actions, copy-file path flow, thumbnails, delete/rollback cleanup, local/online ingest, Markdown generation, WD cache, and maintenance tools now pass `storage_id` explicitly.
  - metadata index now records `storage_id` and watches compact filename stems through an in-memory `storage_id -> hash` map.
  - compact-storage migration script and old pre-storage sharding tools were removed.
  - backend pytest, AST, import, static grep, and diff whitespace checks pass.
  - needs real-vault ingest/delete/review-replace/tag/thumbnail smoke after longer use.

- Metadata index rebuild maintenance tool:
  - added `tools/maintenance/rebuild_metadata_index.py`.
  - supports `--status`, `--stale`, `--full`, `--limit`, and `--json`.
  - default run is safe status-only mode.
  - stale/full rebuilds fail fast if any item row is missing `storage_id`.
  - rebuilds persistent metadata tables only; search/RAM indexes remain out of scope.
  - status run on active vault reported `items=156`, `indexed=0`, `stale_before=156`, `stale_after=156`.
  - backend pytest, AST, import, and diff whitespace checks pass.
  - needs one real `--stale` or `--full` run when ready to populate metadata index.

- Logging stream split and rename:
  - online ingestion lifecycle logs now write to `ingest_online.jsonl`.
  - local desktop ingestion lifecycle logs now write to `ingest_local.jsonl`.
  - ingestion summaries and item audit entries now write to `ingestion_audit.jsonl`.
  - SearchManager RAM hydration, batch index updates, and VP-tree rebuild logs now write to `system.jsonl`.
  - legacy `log_ingestion` alias removed; old `ingestion.jsonl` and `activity.jsonl` support remains absent from API/UI.
  - obvious backend/tools CLI mojibake prefixes cleaned up.
  - targeted backend pytest, AST, import, static grep, and diff whitespace checks pass.
  - needs real UI verification in App Logs dropdown/live stream and real local/online ingest log smoke.

- Native drag-and-drop intake (Vault + Local Ingestion):
  - added native Tauri drop listener in `frontend/src/App.svelte` via `getCurrentWindow().onDragDropEvent(...)`.
  - drop overlay is implemented (dim background + centered text).
  - drop target gating is implemented:
    - allowed in Vault panel.
    - allowed in Ingestion panel only when mode is Local.
    - disabled for Review/Stats/Settings/Logs.
    - suppressed when hover target is `input`, `textarea`, or `contenteditable`.
  - added backend preflight endpoint `POST /api/local-ingest/drop-intake`:
    - request: `session_id`, `source_tab`, `paths`.
    - blocks with `409` when online or local ingestion is running.
    - resolves paths, accepts directories, filters files by `firewall.allowed_extensions`, dedupes by resolved absolute path.
    - returns `accepted_paths`, `skipped` (with reason codes), and summary counts.
    - logs intake summary to `ingest_local.jsonl` via `log_ingest_local(...)`.
  - Ingestion integration is implemented:
    - new `dropRequest` prop in `Ingestion.svelte`.
    - mode sync event (`modechange`) from Ingestion to App.
    - accepted drop paths switch to Ingestion Local mode and append+dedupe into staged list.
    - local ingest does not auto-start; manual start remains required.
    - local mode root now exposes `data-drop-zone="ingest-local"` for precise target checks.
  - frontend UI summary logging for drop sessions is implemented.
  - backend tests added and passing for drop intake:
    - accept supported file.
    - accept directory.
    - skip unsupported extension.
    - skip missing path.
    - dedupe repeated path.
    - block while local ingest running.
    - block while online ingest running.
  - frontend test coverage added:
    - mock-vault Playwright tests for drop-request staging, local-mode switch, append+dedupe, and no auto-start.
    - requires re-run confirmation in stable local Playwright runtime (test process hung in this environment during targeted run).
  - frontend type/svelte checks pass.

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
- Review/search-index regression fix:
  - FastAPI startup hydrates `search_manager` from SQLite, matching CLI startup behavior.
  - pending/deferred review sidecars guard against re-ingesting the same file hash.
  - new review sidecars store `file_hash` immediately.
  - Review list/count refresh no longer auto-marks pending items as `resolved_variant` just because their hash appears in DB.
  - no automatic repair was performed for the existing accidental WebP vault row or resolved sidecar.
  - validation passed:
    - backend mock-vault pytest: `54 passed`.
    - frontend type/Svelte check passes.
    - backend AST/import checks pass.
    - `git diff --check` passes.
  - needs real-vault drag-drop/restart/re-ingest smoke:
    - restart backend/Tauri after a pending review item exists.
    - re-drop the same folder.
    - confirm existing DB duplicates are skipped.
    - confirm the pending-review file reports as already pending review.
    - confirm Review panel does not silently mark it `resolved_variant`.
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
  - Manual metadata editing is implemented for `title`, `artist`, `date_added`, `topics`, and WD fields.
  - PATCH artist/topics writes DB cache and Markdown through one rollback-capable path.
  - metadata reindex reads Markdown topics/WD data; SQLite remains authoritative for item identity fields.
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
- P1 performance:
  - WD tagger caches ONNX session/model labels per model/device/provider selection.
  - metadata stale scan streams rows and status counts stale rows without building a full list.
  - topic/WD item and facet filters skip legacy disk scans when metadata index is not ready and start repair instead.
  - SearchManager queries use snapshots; VP-tree rebuild work happens outside the query lock.
  - hot ingestion paths use a lightweight SQLite connector after schema initialization.
  - Resolved Gemini findings:
    - WD ONNX session recreated per `tag_media()`.
    - metadata stale scan full `.fetchall()`.
    - N+1 fallback scan for topic/WD filters when metadata index is not ready.
    - SearchManager lock blocking queries during VP-tree rebuild.
    - SQLite connection churn during concurrent ingestion.
  - targeted backend pytest passes; needs real-vault ingest/search smoke before closing fully.
- P2 runtime robustness:
  - Media focus tries Tauri fullscreen first, then browser fullscreen fallback.
  - review `delete`, `variant`, `replace`, and cleanup retry unmount media before POST to reduce Windows file-lock failures.
  - `gallery-dl` and `yt-dlp` subprocess timeouts are configurable under `external_tools.timeouts` with previous defaults preserved.
  - thumbnails use one shared backend ensure path for ingest pregeneration, repair/backfill, and API fallback.
  - thumbnail generation is semaphore-throttled; saturated API fallback returns HTTP 503 instead of blocking worker threads.
  - sampled video frame extraction uses one FFmpeg subprocess per sampled batch.
  - Resolved Gemini findings:
    - missing browser fullscreen fallback.
    - Windows review file-lock risk before destructive actions.
    - long downloader timeout values hardcoded in wrappers.
    - thumbnail burst generation saturating API worker threads.
    - redundant per-frame FFmpeg subprocesses during video embedding extraction.
  - targeted backend/frontend checks pass; needs real-vault ingest/review/thumbnail smoke before closing fully.
- P3 cleanup / observability:
  - logger helpers support `exc_info=True`; JSON logs include tracebacks through existing formatter.
  - `calculate_phash`, `is_silent`, `get_audio_fingerprint`, `get_video_duration`, and `get_visual_embedding` now log warning tracebacks before fallback returns.
  - FFmpeg frame extraction no longer buffers stderr where stderr is not parsed.
  - audio fingerprinting keeps stdout parsing but discards unused stderr.
  - maintenance script uses `DB_PATH.exists()` instead of `os.path.exists(DB_PATH)`.
  - Resolved Gemini findings:
    - swallowed low-level media exceptions with no traceback.
    - naive FFmpeg stderr buffering in fingerprint frame extraction.
    - mixed `os.path` / `pathlib.Path` check in maintenance script.
  - backend pytest, AST, import, and diff whitespace checks pass; needs real-vault corrupt-media/log smoke before closing fully.

### Useful Checks

- **Frontend Dependencies:** Run `npm outdated` in the `frontend/` directory to see a table of current vs. latest npm packages.
- **Backend Dependencies:** Run `pip list --outdated` with your Python virtual environment activated to check for updates on PyPI. Note: `yt-dlp` and `gallery-dl` are auto-updated by the maintenance script.

## Current Issues

- Mojibake check: no actual mojibake found in project source/docs during 2026-05-31 scan; apparent warning-icon mojibake was terminal encoding.
- Vault repair/replace-delete mechanics need a focused data-flow audit:
  - After review replacement testing, metadata index rows did not reliably reflect the replacement result.
  - A repeat click/freeze scenario during similar-image review testing may have allowed duplicate replacement/commit behavior.
  - Health audit showed orphan assets, WD cache files, and thumbnails in the test vault after replace/delete-like flows.
  - At least one deleted note was removed correctly while the paired asset/cache remained, creating audit errors.
  - These findings were discovered through browser-extension similarity testing, but they likely belong to core review/delete/repair flows rather than extension code.
  - Test-vault damage can stay for now and should be used to improve repair mechanics.
- Data-flow ownership audit is needed after current findings are fixed; DB, Markdown, metadata index, RAM/search index, and frontend draft state should be mapped flow-by-flow.
- Inspector chip action UX is still not fully settled long-term:
  - WD promotion toggle is covered by targeted mock-vault tests.
  - Current test validates handler wiring through synthetic click events, not real mouse hit stability.
  - Real-vault/manual smoke should verify WD promote/unpromote, WD remove, saved topic rename/remove, and hover action behavior.

## Issue Remediation Plan

### Next Documentation / Drift Pass

- Review `docs/lmz_architecture.md` against current backend/frontend shape.
- Reconcile `docs/lmz_roadmap.md` phase notes with current status.
- Keep status doc as the operational handoff source.

### Recommended Fix Batches

1. Run focused real-vault smoke for Settings, Stats, Inspector, Ingestion.
2. Do a data-flow audit:
   - Inspector save.
   - online queue ingest.
   - local ingest.
   - review replace.
   - item delete.
   - vault health repair.
   - artist merge/rename.
   - WD tag promotion/removal.
3. Rerun full `npm.cmd run test:mock-vault` after the current Inspector chip stabilization is finalized.
4. Continue remaining real-vault validation for P0/P1/P2/P3 smoke items.
