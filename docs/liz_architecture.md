# LIZ Architecture

## Summary

LIZ is a local media archive and zettelkasten system for images, GIFs, and videos.

It ingests local files and external URLs, validates media, stores files by SHA256 hash, indexes runtime metadata in SQLite, generates Obsidian-compatible markdown notes, keeps WD tag suggestions in local JSON cache files, and exposes a PySide6 desktop UI for browsing, review, ingestion, settings, and metadata cleanup.

The current project uses a flat `src/` layout. Runtime state is outside source code under root-level `data/`, `logs/`, and `secrets/`.

## Current Project Shape

```text
local_image_zettelkasten/
  main.py
  gui.py
  pyproject.toml
  README.md
  config/
    config.yaml
  src/
    core.py
    external_ingestion.py
    fingerprint.py
    md_generator.py
    processor.py
    utils.py
    validators.py
    db/
    downloaders/
    logs/
    scripts/
    ui/
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
  secrets/
  backups/
  docs/
```

## Entry Points

- `python main.py` runs ingestion.
- `python gui.py` launches the PySide6 UI.
- `liz` runs `core:main` when installed.
- `liz-gui` runs `ui.app:main` when installed.

## Runtime Paths

Configured in `config/config.yaml`:

- Vault: `data/vault`
- Assets: `data/vault/assets` sharded by hash prefix
- Notes: `data/vault/notes` sharded by hash prefix
- Database: `data/db/liz_main.db`
- Queues: `data/queues`
- Batches: `data/batches`
- Logs: `logs`
- Secrets: `secrets`
- WD tag cache: `data/wd-tags` sharded by hash prefix
- Local model files: `data/models`

`utils.py` resolves paths against the project root, not against source files.

## Core Data Flow

```text
Local files / URL queues
        |
        v
core.py
        |
        +--> local file processing
        |
        +--> external_ingestion.py
                 |
                 +--> gallery-dl wrapper
                 +--> yt-dlp wrapper
        |
        v
validators.py
        |
        v
processor.py
        |
        +--> SHA256 hash
        +--> duplicate check
        +--> pHash / video signatures
        +--> copy to vault assets
        +--> insert SQLite row
        +--> generate markdown note
        +--> optional local WD tagging
        |
        v
data/vault/assets + data/vault/notes + data/db/liz_main.db
```

## Storage Model

Files are content-addressed:

```text
data/vault/assets/{hash[:2]}/{hash}.{ext}
data/vault/notes/{hash[:2]}/{hash}.md
```

The database row stores:

- SHA256 hash
- original filename
- normalized extension
- MIME type
- file size
- source URL
- platform
- artist
- pHash
- video audio hash
- video visual embedding

Manual topics and WD tags are intentionally not stored in SQLite.

Metadata ownership:

- SQLite: runtime asset/index metadata only.
- Markdown frontmatter: manual `topics`, distilled `wd_rating`, `wd_character_tags`, and `wd_tags`.
- JSON cache: detailed local WD tag report under `data/wd-tags/{hash[:2]}/{hash}.json`.

Markdown asset links are written relative to sharded notes:

```text
../../assets/{hash[:2]}/{hash}.{ext}
```

## Database Schema

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
| `platform` | Platform label |
| `source_artist` | Creator/artist metadata |
| `phash` | Image perceptual hash |
| `audio_hash` | Video audio signature |
| `visual_embedding` | Video visual embedding |

### `item_tiles`

Used for fragment/tile-level pHash support:

| Column | Meaning |
| --- | --- |
| `parent_hash` | Parent item hash |
| `tile_index` | Tile order |
| `tile_phash` | Tile perceptual hash |

## Ingestion Integrity

External ingestion is platform-bucketed and uses per-platform worker counts plus a global semaphore.

Current protected batch behavior:

- Pixiv
- X/Twitter
- Instagram
- Pinterest
- YouTube community posts

For protected platforms, downloaded media from one URL is treated as one batch. If one file fails processing, newly inserted DB rows/assets/notes from that attempt are rolled back and the URL remains retryable.

Platform specifics:

- Pixiv: strict metadata count from `gallery-dl -j`; ugoira converts through `--ugoira webm`.
- Instagram: metadata count when available; shortcode matching prevents duplicate tracking-param variants.
- Pinterest: count-only metadata; source URL identity remains exact.
- X/Twitter: no metadata prefetch; original `x.com` URL is preserved while gallery-dl receives normalized `twitter.com`.
- YouTube community: metadata inspection supports community image posts.

## UI Architecture

The UI is PySide6/QWidgets.

Main components:

- `ui.app`: creates `QApplication`, applies stylesheet, opens `MainWindow`.
- `ui.main_window`: application shell, navigation, search/commands, status bar, focus modes.
- `ui.views.vault`: grid browser, grouped source-URL tiles, hover video previews.
- `ui.views.inspector`: normal preview, metadata editing, group navigation, note-backed topics, and tag display.
- `ui.views.review`: duplicate/review workflow.
- `ui.views.ingestion`: log tailing.
- `ui.views.app_logs`: readable and raw log viewing for system, UI, and ingestion logs.
- `ui.views.settings`: config editing.
- `ui.video_widgets`: reusable video player controls.
- `ui.thumbnail_cache`: thumbnail generation under `data/ui_cache`.
- Focus media handling: wide/fullscreen mode moves only the active media widget and its relevant controls into a dedicated focus surface, while the right inspector remains a normal-mode panel.

## Vault Grouping

The vault UI groups rows by non-empty `source_url`.

Behavior:

- One DB row still represents one media file.
- One UI tile may represent multiple rows from the same source URL.
- Group tiles show a counter like `1 / 8`.
- Group tiles allow previous/next navigation.
- Clicking a group opens the currently displayed item in the inspector.
- Inspector also detects the group and provides previous/next navigation.
- Saving metadata in a grouped inspector updates every item in that source URL group and regenerates all related notes.

Blank `source_url` rows are never grouped.

## Focus Modes

Inspector media supports:

- Normal view
- Wide view
- Fullscreen view

Videos use a shared `VideoPlayerWidget`. Images use the inspector image preview. Wide/fullscreen behavior is currently being stabilized around a dedicated media focus host so image and video controls stay separated from the right inspector layout.

Normal window size is recorded immediately before entering wide/fullscreen mode and restored when returning to normal mode. This avoids using Qt's early startup size before the visible layout has settled.

## Tagging Architecture

Phase 9 V1 adds local WD tagging through `src/tagging/`.

Behavior:

- `tag_media(media_path, item_hash=None, config=None)` is the reusable tagging entry point.
- Model files are stored locally under `data/models/wd-vit-tagger-v3/`.
- Detailed tag output is cached under `data/wd-tags/{hash[:2]}/{hash}.json`.
- Markdown notes receive distilled WD fields only.
- SQLite does not store WD tags or manual topics.
- Videos use sampled frame tagging and store merged WD suggestions in the same cache shape.

## Maintenance Tools

Root-level maintenance tools live under `tools/maintenance/`.

Important tools:

- `clear_pycache.py`
- `retry_failed.py`
- `reset_db.py`
- `manage_review.py`
- `update_tools.py`
- `vault_integrity.py`
- `liz_readiness_check.py`

## Logging

Logs live under root-level `logs/`.

Primary streams:

- system logs for ingestion/runtime events
- UI logs for desktop behavior
- ingestion logs for queue/workbench activity

The App Logs view can show logs in two modes:

- Normal: parses JSONL records into readable timestamp, level, message, and compact detail rows.
- Full: shows raw JSONL records with spacing.

The selected log file can be opened externally from the UI. The UI also uses Qt logging suppression for noisy multimedia FFmpeg output.

## Packaging

`pyproject.toml` exposes:

- `liz = "core:main"`
- `liz-gui = "ui.app:main"`

Package source root is `src/`.

## Design Constraints

- Keep runtime data out of source.
- Keep credentials under `secrets/`.
- Keep `backups/` and `docs/` ignored by GitHub uploads.
- Do not reintroduce Flet.
- Keep source URL provenance stable.
- Prefer batch-safe ingestion for multi-media posts.
