# LMZ Architecture

## Summary

Local Media Zettelkasten (LMZ) is a local media archive and zettelkasten system for images, GIFs, and videos.

It ingests local files and external URLs, validates media, stores original assets by SHA256 hash, indexes runtime metadata in SQLite, generates Obsidian-compatible markdown notes, keeps local WD tag reports in sharded JSON cache files, and exposes a Tauri/Svelte desktop UI through a local FastAPI backend.

Runtime state stays outside source code under root-level `data/`, `logs/`, and `secrets/`.

## Project Shape

```text
local_media_zettelkasten/
  main.py
  dev.py
  pyproject.toml
  README.md
  config/
    config.yaml
  backend/
    core.py
    web_api.py
    external_ingestion.py
    fingerprint.py
    md_generator.py
    processor.py
    queue_service.py
    thumbnails.py
    utils.py
    validators.py
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
        MediaFocus.svelte
        SearchBar.svelte
        Ingestion.svelte
        ReviewView.svelte
        StatsView.svelte
        LogsView.svelte
        SettingsView.svelte
        renderers/
          masonry/
          grid/
          archive/
    src-tauri/
  tools/
    maintenance/
  data/
    input/
    review/
    queues/
    batches/
    vault/
      assets/
      notes/
    db/
    models/
    wd-tags/
    ui_cache/
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
- `cd frontend; npm run build:sidecar` builds the production Tauri sidecar.
- `cd frontend; npm run tauri build` builds the desktop app after the sidecar exists.

The old Flet and PySide/PyQt UI paths are no longer active.

## Runtime Data Flow

```text
local files / markdown URL queues / Tauri UI actions
        |
        v
backend/core.py / backend/queue_service.py / backend/web_api.py
        |
        +--> backend/external_ingestion.py
        |       +--> gallery-dl wrapper
        |       +--> yt-dlp wrapper
        |
        v
backend/processor.py
        |
        +--> MIME/extension validation
        +--> SHA256 hash
        +--> duplicate checks
        +--> pHash / video signatures
        +--> copy original to sharded vault assets
        +--> insert SQLite runtime metadata
        +--> generate sharded markdown note
        +--> optional local WD tagging
        |
        v
data/vault/assets + data/vault/notes + data/db/lmz_main.db + data/wd-tags
```

## Storage Model

Files are content-addressed:

```text
data/vault/assets/{hash[:2]}/{hash}.{ext}
data/vault/notes/{hash[:2]}/{hash}.md
data/wd-tags/{hash[:2]}/{hash}.json
```

Markdown asset links are relative to sharded notes:

```text
../../assets/{hash[:2]}/{hash}.{ext}
```

Metadata ownership:

- SQLite: runtime asset/index metadata.
- Markdown frontmatter: manual `topics`, distilled `wd_rating`, `wd_character_tags`, and `wd_tags`.
- WD JSON cache: detailed local WD tag report, including scores and frame-level video tag data.

SQLite intentionally does not store manual topics or WD tag metadata.

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
| `source_artist` | Creator/artist metadata |
| `phash` | Image perceptual hash |
| `audio_hash` | Video audio signature |
| `visual_embedding` | Video visual embedding |
| `width` | Media width |
| `height` | Media height |

### `item_tiles`

Used for fragment/tile-level pHash support.

| Column | Meaning |
| --- | --- |
| `parent_hash` | Parent item hash |
| `tile_index` | Tile order |
| `tile_phash` | Tile perceptual hash |

## Backend API

`backend/web_api.py` is the local FastAPI service used by the frontend.

Core API areas:

- Session key: `/api/session-key`.
- Vault stats and memory: `/api/stats`, `/api/system/memory`.
- Facets/search suggestions: `/api/facets`, `/api/search/suggestions`.
- Thumbnails and item data: `/api/thumbnails/{hash}`, `/api/items`, `/api/items/{hash}`.
- Item actions: update, delete, bulk delete, tag, open folder, open note.
- Logs: SSE streaming, log open, log clear, frontend UI log ingest.
- Auth status: `/api/auth/scan` writes credential availability checks to `auth.jsonl`.
- Queue ingestion: queue read/write/parse/open/retry/clear/start.
- Review workflow: review count, review item list, review actions.
- Config: `/api/config`.

Security and runtime constraints:

- Mutating endpoints require `X-LMZ-API-KEY`.
- The session key is stored under `secrets/.api_key`.
- CORS is limited to local/Tauri origins.
- Queue/log/review path inputs are allowlisted or root-checked.
- Blocking filesystem/SQLite work is routed through thread helpers on main API paths.
- Static vault/review assets are served from local runtime folders.
- Frontend API calls go through `frontend/src/lib/api.ts`.
- `config/config.yaml` stores non-secret runtime settings. `secrets/.secrets.yaml` stores external-service credentials such as Pixiv refresh token and cookie path overrides.

## Frontend Architecture

The active UI is Tauri + Svelte.

Top-level structure:

- `App.svelte`: application shell, sidebar navigation, footer, shared tab layout.
- `VaultView.svelte`: vault page state, search integration, renderer selection, selection state, inspector/focus wiring.
- `SearchBar.svelte` and `search.ts`: structured search parsing, commands, suggestions, Tab autocomplete.
- `VaultGroupTile.svelte`: shared visual tile for grouped and single media.
- `Inspector.svelte`: metadata, topics, WD tags, grouped navigation, tag/open/copy/save actions.
- `MediaFocus.svelte`: wide/fullscreen media view, grouped navigation, filmstrip, fullscreen zoom/pan.
- `Ingestion.svelte`: markdown queue editor and queue runner.
- `ReviewView.svelte`: duplicate/review workflow.
- `StatsView.svelte`: facet-count browsing.
- `LogsView.svelte`: structured/raw log viewer.
- `SettingsView.svelte`: config editing.

Shared frontend infrastructure:

- `api.ts`: central API URL and authenticated fetch helper.
- `configStore.ts`: shared config state and targeted config updates.
- `statsStore.ts`: shared queue/review stats polling.
- `ramStore.ts`: optional RAM tracker polling.
- `media.ts`: safe media type helpers.
- `selection.ts`: pure selection helpers.
- `observers.ts`: reusable intersection/resize observer helpers.
- `logger.ts`: batched frontend UI logging.

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

- `>masonry`
- `>grid`
- `>zoom-in`
- `>zoom-out`
- `>sort-newest`
- `>sort-oldest`
- `>sort-artist`
- `>media-all`
- `>media-image`
- `>media-video`
- `>toggle-inspector`
- `>ram-track`
- `>scan-auth`

## Vault Grouping

The UI groups rows by non-empty `source_url`.

Rules:

- One SQLite row represents one media file.
- One UI tile may represent multiple rows from the same source URL.
- Blank `source_url` rows are never grouped.
- Source URL grouping is UI-level; the database remains file-based.
- Grouped media index state is owned by `VaultView` so virtualization can unmount/remount tiles safely.

## Search And Facets

Search is one input with structured prefixes:

- `a:` artist.
- `@` platform.
- `#` note-frontmatter topic.
- `*` WD tag.
- `>` command.
- `;` separates filter segments.

Filter semantics:

- Different prefix types: AND.
- Repeated artists: OR.
- Repeated platforms: OR.
- Repeated topics: AND.
- Repeated WD tags: AND.
- Plain text terms: AND.

Facet counts:

- Artist/platform counts come from SQLite.
- Topic counts come from markdown frontmatter.
- WD tag counts come from markdown/cache-backed WD fields.
- `/api/facets` powers the Stats view and search dropdown counts.

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

## Ingestion Integrity

External ingestion is platform-aware and batch-safe for multi-media posts.

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

## External Authentication

External downloader authentication is config-driven but secrets-backed.

Credential storage:

- `config/config.yaml`: non-secret defaults, including relative `external_tools.cookies_path`.
- `secrets/.secrets.yaml`: sensitive overrides such as `pixiv_token` and `cookies_path`.
- `secrets/cookies.txt`: Netscape cookie jar used by gallery-dl and yt-dlp.
- `/api/config` returns and saves public config only; secret keys are stripped before UI round-trips can write `config.yaml`.

Path handling:

- Relative cookie paths resolve from the project root.
- Current default: `secrets/cookies.txt`.
- Secret values are merged into `external_tools` at runtime by `get_config()`.

Platform expectations:

- X/Twitter: cookies.
- Instagram: cookies.
- Pinterest: cookies are detected and reported if present, but usually not required.
- YouTube: cookies are optional; useful for restricted content.
- Pixiv: refresh token.

Auth visibility:

- Startup runs an auth scan.
- `POST /api/auth/scan` runs a manual scan.
- Vault command `>scan-auth` triggers the manual scan.
- Results are written to `logs/structured/auth.jsonl`.
- Logs report only availability states, never cookie or token values.

## Tagging

Local WD tagging lives under `backend/tagging/`.

Behavior:

- Public API: `tag_media(media_path, item_hash=None, config=None)`.
- Model files live under `data/models/`.
- Detailed cache lives under `data/wd-tags/{hash[:2]}/{hash}.json`.
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
- Full original assets remain in the sharded vault and are served to the frontend through backend asset routes.

## Logging

Logs live under root-level `logs/`.

Current layout:

- `logs/raw/`: terminal output and raw tracebacks.
- `logs/structured/`: JSONL streams for system, frontend UI, ingestion, auth status, and activity events.

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
- Keep `backups/` and `docs/` local/ignored.
- Keep source URL provenance stable.
- Keep manual topics and WD tags out of SQLite.
- Prefer batch-safe ingestion for multi-media posts.
- Do not reintroduce Flet or PySide UI code.
- Build the production sidecar before production Tauri packaging.
