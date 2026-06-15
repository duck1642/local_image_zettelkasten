  # LMZ Current Status

Last updated: 2026-06-15

## Current Status

LMZ is a local-first media vault desktop app with launcher-mode workspace/vault selection.

- Frontend: Tauri + Svelte, with virtualized vault grid/masonry views and split feature panels.
- Backend: local FastAPI/Python API under `backend/`, launched by the desktop app or dev commands.
- Runtime model: backend may start without an active workspace; vault-dependent services activate after workspace/vault selection or relocation.
- Workspace/vault model: `config/workspaces.yaml` may contain machine-local absolute workspace config paths; workspace `config.yaml` should keep vault roots and internal paths portable/relative.
- Data model: SQLite owns item identity/source fields; Markdown mirrors identity fields and remains the editable source for topics/WD metadata.
- Active risk areas: workspace/vault control, maintenance safety, startup launcher behavior, index lifecycle, import/export, and auth clarity.
- Old Flet and PySide/PyQt UI paths are inactive.

Launch commands:

```powershell
python dev.py
python main.py
lmz
```

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

## Architecture Snapshot

- Frontend app: `frontend/src/`.
- Tauri shell: `frontend/src-tauri/`.
- Backend API: `backend/web_api.py`.
- Ingestion CLI: `backend/core.py`, launched by `main.py` or `lmz`.
- Workspace registry/config loading supports launcher mode before an active runtime exists.
- Workspace registry owns machine-local workspace config paths; each workspace config owns registered vault definitions with relative vault roots.
- Workspace DB and shared topic/metadata libraries are workspace-scoped.
- Active runtime context points at one selected workspace and one active vault.
- Active vault root contains the vault DB, files, caches, review area, ingest staging, and vault logs.
- Vault DB: `<vault_root>/db/lmz_main.db`.
- Vault assets: `<vault_root>/vault/assets/{hash[:2]}/{storage_id}.{ext}`.
- Vault notes: `<vault_root>/vault/notes/{hash[:2]}/{storage_id}.md`.
- WD tag cache: `<vault_root>/wd-tags/{hash[:2]}/{storage_id}.json`.
- Thumbnails: `<vault_root>/ui_cache/thumbnails/{hash[:2]}/{storage_id}.jpg`.
- Review quarantine: `<vault_root>/review/`.
- Local ingest staging: `<vault_root>/local_ingest/`.
- Online ingest staging: `<vault_root>/online_ingest/`.
- Vault logs: `<vault_root>/logs/raw/`, `<vault_root>/logs/structured/`.
- Startup logs: `logs/startup/raw/`, `logs/startup/structured/`.
- Secrets: workspace `paths.secrets`, usually `data/secrets/` for LMZ workspaces; app/default configs may still use `secrets/`.

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

## Deferred / Later

### Runtime / Packaging Hardening

- Dynamic sidecar port coordination: startup handshake, API base, CSP, lifecycle, and removing fixed `localhost:8000`.
- Packaging-time security checks.
- Clean-machine release validation.

### Longer-Term Platform Gaps

- YouTube community partial policy:
  - one failed expected image can still keep the post retryable.

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

## Workspace / Vault Control Backlog

### Trace Order

1. Startup / launcher failure.
2. Workspace/vault activation.
3. Vault switch stale state.
4. Maintenance safety.
5. Workspace/vault management gaps.
6. Path model audit.
7. Import/export.
8. Auth UI / auth scan.

### P1 Maintenance Safety

- Audit Settings maintenance actions: metadata rebuild, vault health audit/repair, thumbnail repair, review cleanup, auth scan, exposed update tools, backup/export/import.
- Verify launcher, missing-vault, workspace-switch, and vault-switch behavior; prevent stale imported path constants.
- Ensure destructive actions show selected workspace/vault/target path, require confirmation, refuse unsafe paths, and report partial failures.
- Ensure DB/filesystem failures surface in UI, clear loading state, and repeated clicks do not start duplicate jobs.
- Align UI actions and maintenance scripts: workspace/vault selection, missing-path warnings, no import-time dynamic paths.
- Ensure maintenance logs include action start, target context/path, result, and warnings/errors.
- Trace first: `frontend/src/lib/SettingsMaintenancePanel.svelte`, `frontend/src/lib/SettingsVaultHealthPanel.svelte`, `frontend/src/lib/SettingsVaultPackagesPanel.svelte`, maintenance/package API routes, and `tools/maintenance/`.
- Trace findings from 2026-06-13:
  - Vault delete backend guards exist, but Settings UI may bypass the non-empty-vault checkpoint by always sending `confirm=true`; inspect why the user saw no delete warning and replace with explicit delete confirmation that shows vault name, item count, and root path.
  - Create-merged-vault flow is implemented as the active merge model; old target-vault merge endpoints were removed.
  - Merged-vault flow asks for the new vault name, selected vaults, preview/dry run, then creates/imports into the new vault; source vaults remain untouched.
  - Merge can reuse vault creation, storage allocation, duplicate lookup, copy helpers, DB insert helpers, metadata refresh, and health/audit helpers where context-aware.
  - Merge should not blindly reuse normal local ingest or active-vault-only helpers because vault merge must preserve existing records and avoid source writes.
  - Exact hash duplicates should be skipped; pHash/tile/video-signature similar matches should not be auto-skipped unless confidence policy is explicitly designed.
  - Similar matches should eventually go to review/quarantine or be reported in the merge result; first pass can report them without auto-deleting or auto-skipping.
  - Vault repair destructive actions now require backend `confirm_destructive`; keep this as done-but-needs-smoke, not an open blocker.
  - Maintenance scripts can be updated opportunistically, but are lower priority than app UI/API safety.
  - Vault backup/export/import package split is implemented and safety-hardened; backup restore creates a new vault, while real-vault smoke and open-folder affordances remain.
  - Remaining browser `confirm()` usages should be reviewed and migrated case-by-case to the reusable confirmation modal for destructive or high-risk actions.
  - `ConfirmationModal` still needs focus placement/trap polish.
  - Toast z-index can appear above modals and should be normalized.

### P1 Maintenance Inspection Order

1. Vault delete UI: trace Settings event wiring and confirmation flow; require an explicit warning before `confirm=true`.
2. Vault merge: smoke create-merged-vault workflow on real vaults and design later similar-item review/reporting.
3. Vault repair: verify current backend confirmation and UI wording; update docs/tests if stale.
4. Vault backup/export/import/restore: smoke strict package creation, restore-to-new-vault, preview-first import, native file picker flow, rollback behavior, and cross-machine path safety.

### P1 Index Systems

- Audit search index activation/reset/hydration on startup, workspace load, vault switch, and vault relocation.
- Audit metadata index activation/reset/hydration and repair/watchdog lifecycle on the same transitions.
- Check review cache, RAM/search indexes, and other long-lived state for stale-vault leakage.
- Keep longer-term search/index scale work separate from runtime correctness:
  - persistent search/facet tables beyond current derived metadata index if needed for scale.
  - search chips.
  - RAM hydration still bulk-loads pHash, tile, URL, and video signatures.

### P2 Import / Export

- Backup/export/import package split is implemented, safety-hardened, and needs real-vault smoke:
  - `backup` creates confirmed workspace-local `.lmzbackup.zip` full snapshots under `backups/vaults/<id>/`.
  - restore accepts only `.lmzbackup.zip` packages and creates a new non-overwriting vault.
  - `export` creates confirmed portable `.lmzvault.zip` packages under `exports/vaults/<id>/`.
  - export includes DB/assets/notes by default and review state only when requested.
  - import is preview-first, requires fingerprint + confirmation, stages into `.tmp/imports/`, writes config last, and rolls back on failure.
  - strict `lmz-package.yaml` manifests replaced the old filename/loose-ZIP fallback.
  - backup/export skip symlinked files and validate packaged file paths remain inside the vault root.
  - import uses strict stage-to-final rename and cleans partial final roots plus staging on failure.
  - real-vault validation is intentionally deferred by user; run backup, export, restore-to-new-vault, import-to-new-vault, source-unchanged, and imported/restored-vault-open checks before closing this area.
- Remaining follow-ups:
  - backup restore replace/overwrite mode is deferred.
  - package import now uses a native file picker in Settings; persistent copy/open-folder affordances remain optional.
  - decide later whether workspace-level export/import should exist separately from vault packages.
- Ensure imports do not preserve wrong machine-specific absolute paths.
- Source URL normalization migration remains missing; runtime writes `source_url_norm` and existing rows are lazily backfilled by `init_database()`.

### P2 Settings / UI UX

- Standardize Settings panel widths; current live audit found General at 600px, Workspace/Vaults/Maintenance at 900px, and Shortcuts at 1000px.
- Make path state explicit: active, valid, missing, relocated, synced-from-another-machine risk.
- Fix confusing input boxes in workspace/vault/settings/maintenance panels.
- Keep Settings polish tied to behavior fixes; avoid broad visual-only rewrites unless the behavior is already being touched.
- Keep UI polish sparse and opportunistic while behavior fixes are active.
- Clean stale inline result state in `SettingsView.svelte` after toast migration.
- Consider an Obsidian-like Settings modal/shell later, but keep the current Settings panel for now.
- Remaining polish: Review panel, fullscreen board/view, Inspector tag edges, context menu, GIF animation policy, video preview strategy.
- Video embedding/tagging still depends on extracting sampled original video frames.

### P2 Auth

- Add clearer authentication UI.
- Improve auth scan output and per-platform state.
- Show what path/token/cookie source is being checked where possible.

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
5. Audit workspace/vault control, path model, maintenance safety, import/export, and auth flows.

## Done Tasks

- Historical completed work has been moved to `docs/lmz_roadmap.md`, mainly Phase 8 and Phase 9.
- Current operational completion checkpoints remain below under `Done But Needs Check`.

## Done But Needs Check

- P0 Stability / Startup:
  - Launcher-safe API routes stay available before workspace/vault activation.
  - Startup UI logs are available in launcher mode.
  - Native Tauri startup background matches launcher base color to avoid white WebView flash.
  - Initial launcher window is centered by Tauri config instead of visible post-mount recentering.
  - Needs longer fresh-start manual smoke because a brief WebView default dark surface can still appear before CSS loads.

- P1 Workspace / Vault Runtime:
  - Workspace creation flow is implemented with `<parent>/lmz/config.yaml`.
  - Vault creation flow is implemented and constrained to selected workspaces.
  - Workspace and vault switching activate the correct runtime context.
  - Active vault paths, DB paths, logs, search state, metadata state, review cache, RAM/search state, and frontend stores are switch-aware at implementation level.
  - Vault merge preview/confirm exists, but source-delete behavior is unsafe/misleading until the P1 maintenance finding is fixed.
  - Workspace merge remains deferred until vault merge behavior is clearer.
  - Vault/workspace internals keep relative paths where practical.
  - Config/workspace YAML keeps machine-local absolute paths where needed.
  - Relocation/recovery flows handle synced config files whose absolute paths moved across machines.
  - WD/tagger model storage is app-global at `data/models`; workspace configs must not contain `paths.models`.
  - Verified with targeted tests plus Desktop workspace/vault ingest placement smoke; needs longer real-use switching/ingest/search/log smoke before closing fully.

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
    - Settings exposes create-merged-vault preview/confirm; source vaults remain untouched and old target-vault merge endpoints are removed.
    - vault health audit reports missing files, orphan files/caches, bad storage IDs, hash mismatches, stale metadata rows, facet drift, broken/unused topics, review mismatches, and workspace dictionary drift.
    - vault health and repair logic is hardened to filter expected tag caches and thumbnails by image/video MIME type, and preserve skipped/failed tagging caches from being deleted as orphans.
    - vault repair can rebuild metadata/facets, rebuild thumbnails, prune derived cache orphans, reconcile review sidecars, and quarantine orphan assets/notes.
    - vault repair destructive actions require backend confirmation.
    - vault backup/export/import package flows are split into strict backup snapshots, restore-to-new-vault, portable exports, and preview-first imports through backend APIs and Settings controls.
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
    - `SettingsVaultMergePanel.svelte`
    - `SettingsVaultHealthPanel.svelte`
    - `SettingsVaultPackagesPanel.svelte`
    - `SettingsWorkspacePanel.svelte`
    - `VaultHealthDetailsModal.svelte`
    - `settingsApi.ts`, `settingsUtils.ts`, and `settings.css`.
  - Settings now uses tabbed sections, split maintenance panels, local icons, and reduced text-heavy actions while preserving existing API behavior.
  - Settings Maintenance polish is implemented:
    - shared `SettingsSection.svelte` and `SettingsActionRow.svelte` components were added for Settings-specific reuse.
    - Merge Vaults, Vault Health, Packages, and System Maintenance use consistent section framing and shorter action labels.
    - stale Obsidian-specific maintenance wording was replaced with generic LMZ/workspace metadata wording.
    - package import/export/backup/restore controls were split into clearer rows while preserving existing API behavior and confirmation flows.
  - Privacy blur is implemented as a frontend-only local privacy toggle:
    - persisted through `localStorage` key `lmz:privacy-blur`.
    - applied globally through the app root class and media-only CSS blur rules.
    - placed under General -> Vault Display Settings because it affects vault/media display and is not config-backed.
  - Settings visual audit at 1920px/fullscreen width was completed:
    - screenshots saved under `C:\Users\BILGIS~1\AppData\Local\Temp\lmz-settings-width-audit`.
    - confirmed width inconsistency across General, Workspace, Vaults, Maintenance, and Shortcuts.
    - Obsidian settings references support a consistent left-aligned content column rather than full-window stretching.
  - Verification during polish:
    - `cd frontend; npm.cmd run check` passed.
    - `cd frontend; npm.cmd run test:mock-vault` passed after updating selectors for current Settings labels.
    - `git diff --check` passed.
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
  - LMZ workspace mode uses `<parent>/lmz/` with the same relative workspace/vault layout.
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
- Eager startup workspace loading resolved:
  - Lazy runtime context resolution: removed eager module-level `reload_runtime_context()` call from `backend/utils.py`.
  - Launcher mode fallback: `_load_env_workspace_if_requested()` in `api/app.py` catches all config errors and keeps the server active instead of crashing.
  - Endpoint routing guards: `local_api_guard` middleware returns a clean `503 Workspace not loaded` for non-launcher requests when no context is active.
  - Active workspace registry persistence: workspace loads are validated before `set_active_workspace()` persists the selection, preventing broken selections from locking out users.
  - Svelte layout fix: restructured missing workspaces row inside `Launcher.svelte` to prevent Svelte nested `<button>` warnings.
  - Verified by dedicated backend tests in `tests/backend/test_startup_refactor.py` and 29 passing mock-vault frontend tests.
- Startup launcher polish:
  - Native Tauri startup background now matches launcher base color to avoid white WebView flash.
  - Initial launcher window is centered by Tauri config instead of a visible post-mount Svelte recenter.
  - `POST /api/logs/ui` is launcher-safe, so startup UI logs can be captured before workspace/vault activation.
  - Needs follow-up: startup can still briefly show a WebView default dark surface before `app.css` loads; likely `index.html`/unstyled document gap.
  - Targeted startup tests pass with alternate pytest temp base; needs fresh manual startup smoke before closing fully.
- API guard layer / missing vault protection:
  - `backend/api/guards.py` adds explicit workspace, active-vault, and target-vault guards.
  - Pre-runtime middleware route groups now use explicit public/log/workspace naming while keeping behavior unchanged.
  - Vault-dependent routes now fail with clean `503` instead of creating folders or blank DBs when the active vault root is missing.
  - Target-vault health/repair/backup/export paths validate the requested vault root before touching vault files.
  - Recreated ignored disposable `tests/generated/test-workspace` and initialized its empty test vault.
  - Guard regression and startup/runtime-focused backend tests pass; needs longer real-vault recovery smoke before closing fully.
- Workspace naming / portable path policy:
  - workspace creation UI/API now uses generic LMZ workspace wording while preserving `<parent>/lmz` creation semantics.
  - `POST /api/workspaces` creates/registers LMZ workspaces; legacy `/api/workspaces/obsidian` has been removed.
  - workspace config path policy keeps internal paths relative and rejects outside-workspace vault roots.
  - vault relocation stores relative roots and rejects roots outside the active workspace.
  - needs real-vault smoke for workspace creation, vault relocation, and config save validation before closing fully.

