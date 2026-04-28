# LIZ Architecture

## Summary

LIZ is a local media archive and zettelkasten system for images, GIFs, and videos.

It ingests local files and external URLs, validates media, stores files by SHA256 hash, indexes runtime metadata in SQLite, generates Obsidian-compatible markdown notes, keeps local WD tag suggestions in JSON cache files, and exposes a Tauri/Svelte desktop UI through a local FastAPI backend.

Runtime state stays outside source code under root-level `data/`, `logs/`, and `secrets/`.

## Current Project Shape

```text
local_image_zettelkasten/
  main.py
  dev.py
  pyproject.toml
  README.md
  config/
    config.yaml
  frontend/
    src/
      lib/
    src-tauri/
  backend/
    core.py
    web_api.py
    external_ingestion.py
    fingerprint.py
    md_generator.py
    processor.py
    queue_service.py
    utils.py
    validators.py
    db/
    downloaders/
    logs/
    scripts/
    tagging/
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

- `python dev.py` launches the modern Tauri/Svelte + FastAPI development stack.
- `python main.py` runs CLI ingestion.
- `liz` runs `core:main` when installed.

The old `gui.py`, old Python UI package, and `liz-gui` PySide entry point are removed.

## Core Data Flow

```text
Local files / Markdown URL queues
        |
        v
core.py / queue_service.py / web_api.py
        |
        +--> external_ingestion.py
        |        +--> gallery-dl wrapper
        |        +--> yt-dlp wrapper
        |
        v
processor.py
        |
        +--> MIME/extension validation
        +--> SHA256 hash
        +--> duplicate checks
        +--> pHash / video signatures
        +--> copy to sharded vault assets
        +--> insert SQLite runtime metadata
        +--> generate sharded markdown note
        +--> optional local WD tagging
        |
        v
data/vault/assets + data/vault/notes + data/db/liz_main.db + data/wd-tags
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

## SQLite Schema

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

Used for fragment/tile-level pHash support:

| Column | Meaning |
| --- | --- |
| `parent_hash` | Parent item hash |
| `tile_index` | Tile order |
| `tile_phash` | Tile perceptual hash |

## API Architecture

`backend/web_api.py` exposes local HTTP endpoints for the Tauri/Svelte frontend.

Important API properties:

- Mutating endpoints require `X-LIZ-API-KEY`.
- Session key is created under `secrets/.api_key`.
- CORS is limited to localhost/Tauri origins.
- Queue/log/review path inputs are allowlisted or root-checked.
- Heavy synchronous work is routed through thread helpers in the main API paths.
- Logs stream through Server-Sent Events.
- Static vault/review assets are served from local runtime folders.

Frontend API calls use `frontend/src/lib/api.ts` so mutating requests automatically include the session key.

## Ingestion Integrity

External ingestion is platform-aware and batch-safe for multi-media posts.

Protected batch platforms:

- Pixiv
- X/Twitter
- Instagram
- Pinterest
- YouTube community posts

For protected platforms, downloaded media from one URL is treated as one batch. If one file fails processing, newly inserted DB rows/assets/notes from that attempt are rolled back and the URL remains retryable.

Platform specifics:

- Pixiv: strict `gallery-dl -j` metadata count; ugoira converts through `--ugoira webm`.
- Instagram: metadata count when available; shortcode matching handles tracking-param variants.
- Pinterest: count-only metadata; source URL identity remains exact.
- X/Twitter: no metadata prefetch; original URL is preserved while gallery-dl receives its supported URL form.
- YouTube community: extracts community image attachments and records per-image download failures.

## UI Architecture

The active UI is Tauri + Svelte.

Main frontend responsibilities:

- Vault browsing with masonry/grid layouts.
- Inspector metadata editing and tag display.
- Grouped source URL navigation.
- Media focus views for wide/fullscreen image/video inspection.
- Markdown queue editor for ingestion.
- Review workflow.
- Settings editing.
- Structured log viewing.

Main backend responsibilities:

- SQLite queries and mutations.
- Thumbnail serving/generation.
- Local file and URL ingestion commands.
- WD tag triggering.
- Markdown note regeneration.
- Log streaming and log file opening.

## Vault Grouping

The vault UI groups rows by non-empty `source_url`.

Behavior:

- One DB row represents one media file.
- One UI tile may represent multiple rows from the same source URL.
- Blank `source_url` rows are never grouped.
- Source URL grouping is UI-level; the database remains file-based.

## Tagging Architecture

Local WD tagging lives under `backend/tagging/`.

Behavior:

- Public API: `tag_media(media_path, item_hash=None, config=None)`.
- Model files live under `data/models/`.
- Detailed cache lives under `data/wd-tags/{hash[:2]}/{hash}.json`.
- Markdown notes receive distilled WD fields.
- Videos are tagged by sampling frames and merging results.

## Logging

Logs live under root-level `logs/`.

Current layout:

- `logs/raw/`: terminal output and raw tracebacks.
- `logs/structured/`: JSONL streams for system, Svelte, ingestion, and activity events.

The UI can show readable normal logs or raw JSONL records.

## Design Constraints

- Keep runtime data out of source.
- Keep credentials under `secrets/`.
- Keep `backups/` and `docs/` local/ignored.
- Keep source URL provenance stable.
- Keep manual topics and WD tags out of SQLite.
- Prefer batch-safe ingestion for multi-media posts.
- Do not reintroduce Flet or PySide UI code.
