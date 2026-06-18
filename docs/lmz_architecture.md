# LMZ Architecture

## Summary

Local Media Zettelkasten (LMZ) is a local media archive and zettelkasten system for images, GIFs, and videos.

It ingests local files and external URLs, validates media, stores original assets under compact storage IDs while keeping SHA256 as item identity, indexes runtime metadata in SQLite, generates LMZ markdown/YAML notes, keeps local WD tag reports in sharded JSON cache files, and exposes a Tauri/Svelte desktop UI through a local FastAPI backend.

Runtime state stays outside source code under a workspace root. Default mode uses the repo root as the workspace. LMZ workspace mode uses `<parent>/lmz/` as the workspace. Heavy shared model files are app-global under `data/models/`, not workspace-local.

## Product Domains

LMZ should be reasoned about by product/runtime domains first, and by file tree second.

```text
LMZ
  Vault Core
  Ingestion
  Duplicate / Review
  Metadata / Knowledge
  Search / Browse
  Media Presentation
  Operations / Maintenance
  Runtime / Packaging
  Capture / External Inputs
  Quality / Testing
```

### Vault Core

The archive truth layer.

- Per-vault asset storage under `data/vaults/<vault_id>/vault/assets/`.
- Per-vault markdown note generation under `data/vaults/<vault_id>/vault/notes/`.
- SQLite item rows and compact `storage_id` ownership.
- Workspace/vault registry and runtime active-context selection.
- Item update/delete behavior.
- Metadata ownership rules between SQLite, Markdown/YAML, and WD JSON caches.
- Backup, migration, import/export, and vault health concerns.

### Ingestion

Everything that gets media into the vault.

- Local ingest.
- Native drag/drop staging.
- Markdown URL queues.
- External downloaders through gallery-dl and yt-dlp.
- Batch-safe ingestion for multi-media posts.
- Retry/failed queue behavior.
- Source URL provenance and platform metadata.

### Duplicate / Review

The data-quality gate before or around vault insertion.

- SHA256 exact duplicate checks.
- Source URL duplicate checks.
- pHash, tile pHash, audio signatures, and video embeddings.
- RAM search indexes used by duplicate checks.
- Review quarantine files and sidecars.
- Review decisions: keep, delete, variant, replace.
- Pending cleanup and restart-safe review state.

### Metadata / Knowledge

The knowledge layer built on top of stored media.

- Manual topics.
- WD rating, character tags, and general WD tags.
- Tag counts and facet data.
- Shared workspace metadata dictionaries.
- Shared topic note library under `data/topics/`.
- Tag maintenance: rename, delete, hide/ignore, merge.
- Promote WD tag to manual topic.
- Artist database, aliases, platform handles, source links, and artist counts.
- Metadata index rebuild and repair.

### Search / Browse

How users find and scan vault contents.

- Structured search parsing and commands.
- Artist/platform/topic/WD tag filters.
- Facets and suggestions.
- Sorting and media-type filters.
- Vault grouping by source URL.
- Virtual masonry/grid browsing.
- Stats view.

### Media Presentation

How media is rendered and inspected.

- Thumbnail generation and serving.
- Vault tile media behavior.
- Inspector previews.
- Wide/fullscreen focus view.
- Filmstrip, zoom, and pan.
- GIF animation policy.
- Video preview policy.
- Future fullscreen board view.

### Operations / Maintenance

The control plane for keeping LMZ healthy.

- Structured/raw logs and App Logs UI.
- Authentication scans and auth maintenance tools.
- Dependency check/update tools.
- Metadata index rebuild.
- Thumbnail repair.
- Review cleanup.
- Vault health checks.
- Generated test-vault tooling.

### Runtime / Packaging

How the app starts, runs, and ships.

- FastAPI startup services.
- Search/index hydration.
- Tauri sidecar lifecycle.
- API key and local-only CORS/origin behavior.
- Config and secrets paths.
- Workspace registry and guarded runtime workspace/vault switching.
- Production sidecar and Tauri packaging.
- Port binding and runtime coordination.

### Capture / External Inputs

Sources outside the desktop app that submit work to LMZ.

- Browser extension capture.
- Offline-first browser extension IndexedDB cache.
- Browser extension queue append for supported online URLs.
- Backend capture staging under the active vault.
- Future clipboard/watch-folder/API integrations.
- Active page URL/media capture.
- Queue/API handoff into ingestion.

### Quality / Testing

Repeatable validation across the other domains.

- Backend pytest.
- Frontend Playwright tests.
- Mock vault fixtures.
- Generated large-vault fixtures.
- Generated-vault generator and perf harnesses under `tests/generators/` and `tests/perf/`.
- Generated vaults and perf results are disposable ignored artifacts.
- Real-vault smoke checklists.
- Performance baselines.
- Regression scenarios for review, ingest, search, and packaging.

## Project Shape

```text
local_media_zettelkasten/
  main.py
  dev.py
  pyproject.toml
  README.md
  config/
    config.yaml
    workspaces.example.yaml
  backend/
    artists.py
    core.py
    web_api.py
    external_ingestion.py
    fingerprint.py
    ingest_control.py
    md_generator.py
    metadata_maintenance.py
    metadata_index.py
    platforms.py
    processor.py
    queue_service.py
    review_cache.py
    thumbnails.py
    topics.py
    utils.py
    validators.py
    vaults.py
    workspaces.py
    workspace_db.py
    api/
      app.py
      capture.py
      common.py
      runtime.py
      ingestion.py
      library.py
      logs.py
      review.py
    db/
    downloaders/
    logs/
    scripts/
    tagging/
  frontend/
    src/
      App.svelte
      lib/
        VaultView.svelte
        VaultGroupTile.svelte
        Inspector.svelte
        InspectorMediaPreview.svelte
        InspectorMetadataGrid.svelte
        InspectorTagChip.svelte
        InspectorTopicEditor.svelte
        InspectorWdSuggestions.svelte
        MediaFocus.svelte
        SearchBar.svelte
        Ingestion.svelte
        OnlineIngestion.svelte
        LocalIngestion.svelte
        ingestion.css
        ReviewView.svelte
        ReviewWorkspace.svelte
        ReviewActionBar.svelte
        ReviewInboxList.svelte
        StatsView.svelte
        LogsView.svelte
        SettingsView.svelte
        SettingsCoreConfigPanel.svelte
        SettingsMaintenancePanel.svelte
        SettingsRuntimePanel.svelte
        SettingsShortcutsPanel.svelte
        SettingsVaultPanel.svelte
        SettingsVaultMergePanel.svelte
        SettingsVaultHealthPanel.svelte
        SettingsVaultPackagesPanel.svelte
        SettingsWorkspacePanel.svelte
        VaultHealthDetailsModal.svelte
        settingsApi.ts
        settingsUtils.ts
        settings.css
        api.ts
        configStore.ts
        layout.ts
        logger.ts
        media.ts
        observers.ts
        ramStore.ts
        runtimeStore.ts
        search.ts
        selection.ts
        statsStore.ts
        types.ts
        icons/
        stats/
          statsApi.ts
          statsUtils.ts
          types.ts
          StatsControls.svelte
          FacetStatsPanel.svelte
          ArtistStatsPanel.svelte
          ArtistDetailPanel.svelte
          ArtistMergeModal.svelte
          MetadataActionModal.svelte
          StatsFilterBar.svelte
          stats.css
        renderers/
          masonry/
          grid/
          archive/
    src-tauri/
  tools/
    browser_extension/
      README.md
      scripts/
        sync_extensions.py
      src/
        api.js
        background.js
        db.js
        icons.js
        popup.html
        popup.js
        styles.css
      edge/
      chrome/
      firefox/
    maintenance/
  tests/
    backend/
    frontend/
    fixtures/
      mock-vault/
    generators/
    generated/
    perf/
    perf-results/
    *.bat
  data/
    models/
    workspace.db
    topics/
    vaults/
      default/
        input/
        local_ingest/
        online_ingest/
        capture_staging/
        review/
        queues/
        batches/
        vault/
          assets/
          notes/
        db/
          lmz_main.db
        wd-tags/
        ui_cache/
          thumbnails/
        logs/
          raw/
          structured/
  secrets/
  backups/
  docs/
```

## Entry Points

- `python dev.py` launches the development stack.
- `python main.py` runs CLI ingestion.
- `lmz` runs the installed CLI entry point.
- `LMZ_CONFIG_PATH=<workspace>/config.yaml` overrides the workspace registry.
- `cd frontend; npm run build:sidecar` builds the production Tauri sidecar.
- `cd frontend; npm run tauri build` builds the desktop app after the sidecar exists.

The old Flet and PySide/PyQt UI paths are no longer active.

## Runtime Data Flow

```text
local files / native drag-drop / markdown URL queues / browser extension / Tauri UI actions
        |
        v
backend/core.py / backend/queue_service.py / backend/web_api.py
        |
        +--> queue parser: URLs plus optional user metadata directives
        |
        +--> backend/external_ingestion.py
        |       +--> gallery-dl wrapper
        |       +--> yt-dlp wrapper
        |
        +--> backend/api/capture.py
        |       +--> active-vault capture_staging/
        |       +--> staged file sidecar
        |
        v
backend/processor.py
        |
        +--> MIME/extension validation
        +--> SHA256 hash
        +--> duplicate checks, including pending review sidecars
        +--> pHash / video signatures
        +--> insert SQLite runtime metadata, including compact storage_id
        +--> copy original to sharded vault assets
        +--> generate sharded markdown note
        +--> optional local WD tagging
        |
        v
workspace data/topics + active vault assets/notes/db/wd-tags
```

FastAPI startup hydrates the RAM search indexes from SQLite so UI-driven local ingest and review flows have the same duplicate-search baseline as CLI ingestion.

## Storage Model

### Workspaces And Vaults

LMZ has one active workspace and one active vault at runtime.

```text
<workspace>/
  config.yaml
  data/
    workspace.db
    topics/
    vaults/<vault_id>/
      vault/assets/
      vault/notes/
      db/lmz_main.db
      review/
      wd-tags/
      ui_cache/thumbnails/
      logs/
      queues/
      batches/
      capture_staging/
      input/
      local_ingest/
      online_ingest/
```

Workspace-level data:

- `data/workspace.db`: shared artist, platform, and WD tag dictionaries.
- `data/topics/`: shared topic markdown files.

Vault-level data:

- `db/lmz_main.db`: item rows and active-vault usage/index tables.
- `vault/assets/`, `vault/notes/`: original media and item notes.
- `review/`, `wd-tags/`, thumbnails, logs, queues, and ingest staging.

The workspace registry lives at `config/workspaces.yaml` locally and is not intended for git because it may contain absolute paths. `config/workspaces.example.yaml` is the committed template. Runtime switching is supported through guarded Settings/API flows: active ingest and metadata repair state block switches, then runtime context, search state, metadata watchdogs, and frontend session state are invalidated for the new workspace/vault.

LMZ workspace mode is the same layout under `<parent>/lmz/`.

### Item Storage

Items are identified by SHA256 `hash`; physical filenames use the DB-owned compact `storage_id`.

```text
data/vaults/<vault_id>/vault/assets/{hash[:2]}/{storage_id}.{ext}
data/vaults/<vault_id>/vault/notes/{hash[:2]}/{storage_id}.md
data/vaults/<vault_id>/wd-tags/{hash[:2]}/{storage_id}.json
data/vaults/<vault_id>/ui_cache/thumbnails/{hash[:2]}/{storage_id}.jpg
data/vaults/<vault_id>/ui_cache/thumbnails/{hash[:2]}/{storage_id}_video.jpg
```

Markdown asset links are relative to sharded notes:

```text
../../assets/{hash[:2]}/{storage_id}.{ext}
```

### Metadata Ownership

- Active-vault SQLite: item identity/source fields, runtime asset metadata, and disposable derived usage/index tables.
- Workspace SQLite: shared artist, platform, and WD tag dictionaries.
- `items.hash`: permanent logical/API identity.
- `items.storage_id`: internal physical filename identity.
- Markdown frontmatter: source of truth for manual `title`, `topics`, distilled `wd_rating`, `wd_character_tags`, and `wd_tags`.
- Markdown mirrors SQLite-owned artist/platform/source/date fields for readability; online scrapers do not own artist/title metadata.
- Explicit user-provided artist/platform metadata from queue directives or local ingest defaults is app-owned item metadata.
- Downloader/scraper metadata is limited to online identity fields such as `source_url` and inferred `platform`; scraper artist/title is not trusted.
- WD JSON cache: detailed local WD tag report, including scores and frame-level video tag data. Used as fallback only when YAML has no WD fields.
- Topic markdown files under `data/topics/`: shared topic library. Item notes store relative links to these files when topics are created or saved through LMZ.

Derived SQLite metadata rows are rebuildable and are not the source of truth.

Metadata maintenance that rewrites topic/WD frontmatter is centralized in `backend/metadata_maintenance.py`. It handles topic rename/delete/merge and WD tag rename/delete across registered vaults, refreshes metadata index/facet rows, and uses best-effort note/topic-file restore when a DB or filesystem step fails mid-operation.

## SQLite Model

### `items`

| Column | Meaning |
| --- | --- |
| `hash` | SHA256 primary key |
| `original_filename` | Filename at ingestion time |
| `file_extension` | Normalized extension |
| `mime_type` | Validated media MIME |
| `size_bytes` | File size |
| `date_added` | Ingestion timestamp |
| `source_url` | Original user-facing URL |
| `source_url_norm` | Normalized URL used for duplicate checks |
| `platform` | Platform label |
| `source_artist` | App/user-owned creator/artist metadata |
| `phash` | Image perceptual hash |
| `audio_hash` | Video audio signature |
| `visual_embedding` | Video visual embedding |
| `width` | Media width |
| `height` | Media height |
| `storage_id` | Compact physical filename ID |

### `item_tiles`

Used for fragment/tile-level pHash support.

| Column | Meaning |
| --- | --- |
| `parent_hash` | Parent item hash |
| `tile_index` | Tile order |
| `tile_phash` | Tile perceptual hash |

### Metadata index tables

Used for SQL-backed topic/WD filters, facets, and suggestions.

| Table | Meaning |
| --- | --- |
| `item_metadata_files` | Storage-aware note/WD file signatures and index status per item |
| `item_topics` | Derived topic rows |
| `item_wd_tags` | Derived WD rating/character/general tag rows |

`item_topics` stores both legacy plain topics and linked topic identity:

| Column | Meaning |
| --- | --- |
| `topic` | Display label |
| `topic_norm` | Normalized label for filtering |
| `topic_rel` | Relative topic file path under `data/topics/`, when linked |
| `topic_key` | Stable identity: `rel:<path>` for linked topics or `plain:<norm>` for legacy strings |

### Workspace metadata DB

`data/workspace.db` is shared by all vaults in a workspace.

| Table | Meaning |
| --- | --- |
| `artists` | Canonical artist/person records |
| `artist_aliases` | Alternate names mapped to an artist |
| `artist_links` | Platform links and handles for artists |
| `platforms` | Canonical platform labels |
| `platform_aliases` | Alternate platform keys mapped to a platform |
| `wd_tag_dictionary` | Workspace-wide known WD tags |

Usage remains vault-local. Stats `Used` counts active-vault usage; Stats `All` merges active-vault counts with workspace-wide dictionaries/topic files.

## Backend API

`backend/web_api.py` remains the stable sidecar/import entrypoint for `uvicorn web_api:app`, tests, and PyInstaller. The FastAPI app and routes live under `backend/api/`:

- `api/app.py`: app creation, lifespan startup, middleware, root route, dynamic media routes, router inclusion.
- `api/common.py`: shared auth, runtime path helpers, dynamic file serving, local ingest compatibility proxies, review/item helper utilities.
- `api/runtime.py`: config, workspace/vault management, switch preflight usage, metadata maintenance/status, system memory.
- `api/ingestion.py`: queues, online ingest, local ingest, drag-drop intake, runtime ingest state.
- `api/capture.py`: browser-extension capture staging, preview, discard, and commit.
- `api/library.py`: items, thumbnails, facets/search suggestions, artists/platforms, topic/WD metadata actions.
- `api/logs.py`: log streaming/open/clear/UI log ingest.
- `api/review.py`: review list/count/actions/cleanup.

`web_api.py` re-exports router helpers and models used by compatibility tests and sync callers, and forwards legacy monkeypatches into the router modules.

Core API areas:

- Session key: `/api/session-key`.
- Vault stats and memory: `/api/stats`, `/api/system/memory`.
- Facets/search suggestions: `/api/facets`, `/api/search/suggestions`.
- Thumbnails and item data: `/api/thumbnails/{hash}`, `/api/items`, `/api/items/{hash}`.
- Item actions: update, delete, bulk delete, tag, open folder, open note.
- Logs: SSE streaming, log open, log clear, frontend UI log ingest.
- Auth status: `/api/auth/scan` writes credential availability checks to `auth.jsonl`.
- Queue ingestion: queue read/write/parse/open/retry/clear/start.
  - Parse preview uses the shared queue parser and returns URL count, groups, entries, and warnings.
- Queue append: `/api/queue/{queue_name}/append` appends backend-owned queue blocks for supported extension URLs.
- Local ingestion: local start/status/retry plus drag-drop preflight through `/api/local-ingest/drop-intake`.
- Browser capture: `/api/capture/stage`, `/api/capture/preview/{staged_id}`, `/api/capture/stage/{staged_id}`, and `/api/capture/commit`.
- Review workflow: review count, review item list, review actions.
- Review cleanup: `/api/review/cleanup`.
- Config: `/api/config`.
- Workspaces: `/api/workspaces`, `/api/workspaces/active`.
- Vaults: `/api/vaults`, `/api/vaults/active`, vault rename/delete/merge endpoints.
- Workspace metadata maintenance: `/api/workspace-metadata/rebuild`, `/api/workspace-metadata/prune`.
- Artist/platform dictionaries: `/api/artists`, `/api/platforms`, artist detail/edit/alias/link/merge endpoints.
- Topic/WD maintenance: `/api/topics/rename`, `/api/topics/delete`, `/api/topics/merge`, `/api/wd-tags/rename`, `/api/wd-tags/delete`.

Security and runtime constraints:

- Mutating endpoints require `X-LMZ-API-KEY`.
- The session key is stored under `secrets/.api_key`.
- CORS is limited to local/Tauri origins plus authenticated browser extension origins.
- Queue/log/review path inputs are allowlisted or root-checked.
- Browser capture staged IDs are validated as opaque IDs, not paths.
- Local drag-drop paths are preflighted by the backend before they are staged into Local Ingestion.
- Blocking filesystem/SQLite work is routed through thread helpers on main API paths.
- Static vault/review assets are served from active-vault runtime folders.
- Public workspace/vault switch endpoints run runtime-switch preflight and reject switches while local ingest, online ingest, or metadata repair is active.
- Frontend API calls go through `frontend/src/lib/api.ts`.
- `config/config.yaml` stores non-secret runtime settings. `secrets/.secrets.yaml` stores external-service credentials such as Pixiv refresh token and cookie path overrides.

## Frontend Architecture

The active UI is Tauri + Svelte.

Top-level structure:

- `App.svelte`: application shell, sidebar navigation, footer, shared tab layout.
- `VaultView.svelte`: vault page state, search integration, renderer selection, selection state, inspector/focus wiring.
- `SearchBar.svelte` and `search.ts`: structured search parsing, commands, suggestions, Tab autocomplete.
  - Live syntax hint: `/cmd; a:artist; p:platform; t:topic; #wd-tag`.
- `VaultGroupTile.svelte`: shared visual tile for grouped and single media.
- `Inspector.svelte`: orchestration owner for metadata loading/saving, topic suggestions, WD edits, grouped navigation, tag/open/copy/delete actions, and keyboard shortcuts.
  - `InspectorMediaPreview.svelte`: media preview and group navigation UI.
  - `InspectorMetadataGrid.svelte`: editable/read-only item metadata grid.
  - `InspectorTopicEditor.svelte`: manual topic chips, add input, and suggestion dropdown.
  - `InspectorWdSuggestions.svelte`: WD rating/character/general chips and promote/remove events.
  - `InspectorTagChip.svelte`: shared Inspector chip UI with local icons and color semantics.
- `MediaFocus.svelte`: wide/fullscreen media view, grouped navigation, filmstrip, fullscreen zoom/pan.
- `Ingestion.svelte`: ingestion page shell and mode switcher.
  - `OnlineIngestion.svelte`: markdown URL queue editor, `@artist:` / `@platform:` directive suggestions, grouped parser preview, warning line gutter, syntax help, queue runner, and ingestion monitor.
  - `LocalIngestion.svelte`: local file/folder staging, artist autocomplete, platform selection, drag-drop intake, and local run status. The local UI currently treats source URL as empty/local.
  - `ingestion.css`: shared ingestion layout, editor, splitter, dropdown, preview, monitor, and local staging styles.
- `ReviewView.svelte`: duplicate/review workflow orchestration.
  - `ReviewWorkspace.svelte`: current review comparison UI.
  - `ReviewActionBar.svelte`: review action buttons.
  - `ReviewInboxList.svelte`: pending/cleanup queue list and item navigation.
- `StatsView.svelte`: orchestration shell for Stats tabs, runtime-session reset, facet filtering handoff, artist flows, and topic/WD maintenance modals.
- `LogsView.svelte`: structured/raw log viewer.
- `SettingsView.svelte`: Settings page owner for config/workspace/vault loading, refresh lifecycle, tab state, confirmation modals, toast feedback, and action handlers.
  - Settings panels: core config, runtime paths, workspaces, vaults, create-merged-vault, vault health, backup/import/export packages, system maintenance, shortcuts, and vault health details modal.
  - `settingsApi.ts`, `settingsUtils.ts`, and `settings.css`: Settings API wrappers, summary helpers, and shared styles.

Shared frontend infrastructure:

- `api.ts`: central API URL and authenticated fetch helper.
- `configStore.ts`: shared config state and targeted config updates.
- `statsStore.ts`: shared queue/review stats polling.
- `runtimeStore.ts`: current workspace/vault runtime identity, session key, and post-switch UI invalidation flow.
- `ramStore.ts`: optional RAM tracker polling.
- `media.ts`: safe media type helpers.
- `selection.ts`: pure selection helpers.
- `observers.ts`: reusable intersection/resize observer helpers.
- `logger.ts`: batched frontend UI logging.
- `icons/`: local named Svelte icon components. The app does not depend on a runtime icon package by default; selected SVG paths are vendored into local components.
- `stats/`: split Stats components, API helpers, types, utilities, and CSS.

## Vault Renderers

The active vault renderers are virtualized and live under:

```text
frontend/src/lib/renderers/masonry/
frontend/src/lib/renderers/grid/
```

Old full-DOM renderer snippets are archived under:

```text
frontend/src/lib/renderers/archive/
```

They are reference files only and are not compiled into the app.

Active layout modes:

- `masonry`: measured virtual masonry renderer.
- `grid`: virtual fixed-row grid renderer.

Renderer responsibilities:

- Render only visible/overscan tiles.
- Unmount offscreen media, including videos.
- Emit visual order for Shift-click range selection.
- Preserve grouped-media active indexes through parent state.
- Respect `ui.vault_tile_min_width`.

Vault commands:

- `/masonry`
- `/grid`
- `/zoom-in`
- `/zoom-out`
- `/sort-newest`
- `/sort-oldest`
- `/sort-artist`
- `/media-all`
- `/media-image`
- `/media-video`
- `/toggle-inspector`
- `/ram-track`
- `/scan-auth`
- `/cleanup-review`

## Vault Grouping

The UI groups rows by non-empty `source_url`.

Rules:

- One SQLite row represents one media file.
- One UI tile may represent multiple rows from the same source URL.
- Blank `source_url` rows are never grouped.
- Source URL grouping is UI-level; the database remains file-based.
- Grouped media index state is owned by `VaultView` so virtualization can unmount/remount tiles safely.

## Browser Extension

The browser extension lives under `tools/browser_extension/`.

Shared source is under `tools/browser_extension/src/`; Edge, Chrome, and Firefox folders are generated from that source with:

```powershell
python tools/browser_extension/scripts/sync_extensions.py
```

Runtime model:

- IndexedDB is the source of truth for pending extension work.
- `chrome.storage.local` / extension storage is used only for lightweight settings such as API base URL and API key.
- Right-click image capture stores a Blob locally first, so capture works while LMZ is closed.
- `100 MB` is the automatic Blob cache limit; larger files require download/discard choice.
- Download fallback saves under `Downloads/LMZ Capture/` and is manual recovery, not auto-sync.
- Sync uploads cached captures to `/api/capture/stage`.
- Commit calls `/api/capture/commit`, which routes through existing processor/review/duplicate behavior.
- Online link capture stores a deferred local item first, then appends through `/api/queue/{queue_name}/append`.
- Failed extension actions are tracked on the item with `last_error`, not a separate log.

Security model:

- The extension sends `X-LMZ-API-KEY` for mutating local API calls.
- API keys are never sent in query strings.
- Preview fetches are authenticated and use object URLs in the popup.
- Normal web origins remain rejected; browser extension origins are allowed only for authenticated local API use.

Known limits:

- Image capture is the MVP. Video capture is deferred.
- Blob URLs, canvas-rendered images, auth-gated media, protected CDN URLs, and site-specific blockers may still fail.
- Instagram image capture can be blocked by the site; link queueing remains usable.

## Search And Facets

Search is one input with structured prefixes:

- `a:` artist.
- `p:` platform.
- `t:` note-frontmatter topic.
- `#` WD tag.
- `/` command.
- `;` separates filter segments.

Filter semantics:

- Different prefix types: AND.
- Repeated artists: OR.
- Repeated platforms: OR.
- Repeated topics: AND.
- Repeated WD tags: AND.
- Plain text terms: AND.

Facet counts:

- Artist/platform counts are active-vault usage counts joined to workspace dictionaries.
- Topic counts come from active-vault metadata index; `All` also reads shared `data/topics/*.md`.
- WD tag counts come from active-vault metadata index; `All` also reads `workspace.db.wd_tag_dictionary`.
- Before initial backfill completes, topic/WD filters skip disk scans and start metadata repair.
- `/api/facets` powers the Stats view and search dropdown counts.

Topic behavior:

- New/saved manual topics create or reuse `data/topics/<slug>.md`.
- Item notes store relative Markdown links to topic files.
- Legacy plain topic strings remain readable and indexable.
- Topic rename/delete/merge are explicit from Stats Topic chip actions.
- Topic maintenance rewrites linked/plain topic refs across all registered vaults and refreshes metadata index/facet rows.

WD tag behavior:

- WD rating, character tags, and general tags are read from Markdown frontmatter and indexed into active-vault metadata tables.
- WD tag rename/delete are explicit from Stats WD chip actions.
- WD maintenance can scope to rating, character, general, or all WD fields and rewrites affected note frontmatter plus metadata index/facet rows.

## Media Focus

`MediaFocus.svelte` owns wide/fullscreen viewing.

Implemented behavior:

- Wide and fullscreen modes for images and videos.
- Grouped media navigation.
- Filmstrip for grouped media in wide/fullscreen modes.
- Fullscreen-only zoom/pan core logic.
- `W`/`F` mode switching and Escape close behavior.

Refinement still expected:

- Fullscreen zoom/pan edge cases.
- Filmstrip sizing and animation polish.
- GIF animation policy in vault/inspector previews.

## Workspace And Vault Management

- `config/workspaces.yaml` stores registered workspaces and active workspace.
- `LMZ_CONFIG_PATH` overrides the registry.
- Settings can register LMZ workspaces and switch the active workspace dynamically when runtime preflight allows it.
- Workspace registry entries may use machine-local absolute `config_path` values.

Each workspace has a `config.yaml` with one active vault:

- `active_vault`: active vault id.
- `vaults`: registered vaults and relative roots inside the workspace.
- `paths.secrets`: relative secrets path for that workspace.

Vault switching is dynamic through Settings/API when runtime preflight allows it. Settings can create, rename, delete, and switch vaults. Vault merge creates a new merged vault from selected source vaults, allocates new destination `storage_id` values, skips exact hash duplicates, copies assets/notes/cache files, and leaves source vaults untouched. Vault package tools are split from health controls: backup creates workspace-local snapshots, restore creates a new vault from `.lmzbackup.zip`, export creates portable `.lmzvault.zip` packages, and import is preview-first with native package selection.

`backend/runtime_context.py` is the source of truth for active workspace/vault paths. Legacy `utils.py` constants remain available, but new code should prefer context-aware helpers or explicit `ctx` propagation. Maintenance scripts should use explicit workspace/vault selection rather than importing dynamic path globals.

## Ingestion Integrity

External ingestion is platform-aware and batch-safe for multi-media posts.

Local ingestion stages files under the active vault's `local_ingest/{run_id}/` before processing. Native drag/drop first calls the backend drop-intake preflight endpoint, then switches the UI to Local Ingestion with accepted paths staged for manual start. Re-dropping a file already pending in Review is guarded by the review sidecar hash and is reported as already pending instead of inserting or creating another review copy.

Markdown URL queues support lightweight metadata groups:

- `@artist: name`
- `@platform: name`
- `---` group separator
- full-line `#` comments

Inline comments are unsupported and produce parser warnings. Deferred queue rewrites preserve remaining grouped artist/platform metadata.

Protected batch platforms:

- Pixiv
- X/Twitter
- Instagram
- Pinterest
- YouTube community posts

For protected platforms, downloaded media from one URL is treated as one batch. If one file fails processing, newly inserted DB rows/assets/notes/tag outputs from that attempt are rolled back and the URL remains retryable.

Platform specifics:

- Pixiv: strict `gallery-dl -j` metadata count; ugoira converts through `--ugoira webm`.
- Instagram: metadata count when available; shortcode matching handles tracking-param variants.
- Pinterest: count-only metadata; source URL identity remains exact.
- X/Twitter: no metadata prefetch; original URL is preserved while gallery-dl receives its supported URL form.
- YouTube community: extracts community image attachments and records per-image download failures.
- Online downloaders pass only `source_url` and `platform` into item metadata; scraped artist/title values are ignored.

## Review Workflow

Review quarantine stores the media file under the active vault's `review/` folder plus a sidecar JSON file next to it.

Sidecar responsibilities:

- Preserve the original display name and source path.
- Store pending/deferred/cleanup/resolved state.
- Store duplicate evidence such as best match, pHash, distance, and conflict count.
- Store `file_hash` so future ingests can detect files already pending review.

Review list/count refresh is read-oriented and must not silently resolve pending sidecars just because a matching hash appears in SQLite. Resolved states are produced by explicit review actions or cleanup/reconciliation workflows, not by passive listing.

Review actions:

- `keep`: defer the item without DB ingest.
- `delete`: remove review media and sidecar.
- `variant`: ingest the review file as a new item and remove review source.
- `replace`: ingest the review file, preserve manual metadata from the old target, then delete the old target.
- cleanup retry: remove resolved/pending-cleanup review files and orphan sidecars where possible.

## External Authentication

External downloader authentication is global-directory based and platform-specific.

Credential storage:

- Credential root: `<project_root>/secrets/auth/` (overrideable by setting the `LMZ_AUTH_ROOT` environment variable).
- Cookie files: stored in Netscape cookie jar format as `<auth_root>/<platform>/cookies.txt` (supported platforms: `x`, `instagram`, `pinterest`, `youtube`, `pixiv`).
- Pixiv OAuth: refresh token is obtained via the mobile API flow and saved as `<auth_root>/pixiv/refresh_token.txt`.
- Local backend API key: stored at `secrets/.api_key` for frontend and browser extension client request authentication.

Path handling:

- Downloader wrappers (gallery-dl and yt-dlp) query the auth status of the target platform and automatically inject the platform-specific cookie path or refresh token arguments at process execution time.
- Credential files are not tracked in git and are excluded via `.gitignore` to prevent leaks.

Platform expectations:

- X/Twitter: cookies.
- Instagram: cookies.
- Pinterest: cookies are detected and reported if present, but usually not required.
- YouTube: cookies are optional; useful for restricted content.
- Pixiv: refresh token.

Auth visibility:

- Startup runs an auth scan.
- `POST /api/auth/scan` runs a manual scan.
- Vault command `/scan-auth` triggers the manual scan.
- Results are written to `logs/structured/auth.jsonl`.
- Logs report only availability states, never cookie or token values.

## Tagging

Local WD tagging lives under `backend/tagging/`.

Behavior:

- Public API: `tag_media(media_path, item_hash=None, config=None, storage_id=None)`.
- Model files live under app-level `data/models/`.
- Detailed cache lives under active vault `wd-tags/{hash[:2]}/{storage_id}.json`.
- Markdown notes receive distilled WD fields.
- Images are tagged directly.
- Videos are tagged by sampling frames and merging results.
- GIFs are currently treated as images; first-frame behavior is expected for thumbnails/tagging/dedupe.

## Thumbnails And Media Serving

Thumbnail generation lives in `backend/thumbnails.py`.

Current behavior:

- Image thumbnails are static JPEGs.
- Video thumbnails are generated via ffmpeg.
- GIF thumbnails are static first-frame previews.
- Full original assets remain in compact sharded vault paths and are served to the frontend through backend asset routes.

## Logging

Logs live under the active vault's `logs/` folder.

Current layout:

- `logs/raw/`: console output and raw tracebacks.
- `logs/structured/`: JSONL streams for system, frontend UI, local ingest, online ingest, auth status, review, and ingestion-audit events.

Frontend logging is batched through `frontend/src/lib/logger.ts`.

The UI can show readable normal logs or raw JSONL records, including `auth.jsonl`.

## Tauri Packaging

Development uses `python dev.py`, which starts the Python backend directly and launches Tauri.

Production Tauri builds expect an external sidecar named `lmz-api`.

```powershell
cd frontend
npm run build:sidecar
npm run tauri build
```

The sidecar builder uses PyInstaller against `backend/web_api.py` and writes Tauri's target-specific binary into `frontend/src-tauri/bin/`.

Known packaging caveat:

- The production sidecar still needs clean-machine release validation.
- Port 8000 binding is still static and may need dynamic binding later.

## Design Constraints

- Keep runtime data out of source.
- Keep credentials under `secrets/`.
- Keep `backups/`, `exports/`, `.tmp/`, generated test vaults, and perf outputs local/ignored.
- Keep `docs/` tracked as the durable project handoff.
- Keep runtime workspace configs and `config/workspaces.yaml` untracked.
- Keep active-vault data isolated under `data/vaults/<vault_id>/`.
- Keep workspace metadata dictionaries shared per workspace, not per vault.
- Keep source URL provenance stable.
- Keep markdown/YAML as the source of truth for manual topics and WD tags.
- Keep SQLite topic/WD rows disposable and rebuildable.
- Prefer batch-safe ingestion for multi-media posts.
- Do not reintroduce Flet or PySide UI code.
- Build the production sidecar before production Tauri packaging.
