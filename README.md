# Local Media Zettelkasten

Local Media Zettelkasten (LMZ) is a desktop application for collecting, organizing, reviewing, and searching personal image and video libraries.

LMZ stores media as ordinary files, keeps metadata in SQLite and Markdown, detects duplicate or similar media, and provides a compact Tauri/Svelte interface for daily management. Library operations run locally. Internet access is only needed for online ingestion, downloader authentication, dependency installation, and downloading AI model weights.

> LMZ v1.0.0 is a Windows-focused desktop release. Keep independent backups of important libraries.

## What LMZ Does

- Imports local files and folders through drag-and-drop or file pickers.
- Downloads media from supported URLs with `gallery-dl` and `yt-dlp`.
- Supports X, Instagram, Pinterest, Pixiv, YouTube, and generic/local sources where the underlying downloader supports them.
- Deduplicates media using cryptographic and perceptual fingerprints.
- Generates sharded asset, Markdown note, thumbnail, and WD-tag cache files.
- Adds optional local WD image tags using `SmilingWolf/wd-vit-tagger-v3`.
- Organizes media by artist, platform, topic, tag, type, and date.
- Provides grid and masonry vault views with search, inspector, selection, and media focus modes.
- Sends ambiguous duplicate matches to a review workflow instead of making silent destructive decisions.
- Manages multiple workspaces and multiple vaults per workspace.
- Audits and repairs vault consistency.
- Imports, exports, backs up, restores, and merges vaults.
- Streams structured application logs and raw console output in the UI.
- Includes an optional browser-capture prototype for staging images and online queue URLs; browser release hardening is deferred beyond v1.0.0.

## Application Layout

The main window is divided into six work areas:

| Area | Purpose |
| --- | --- |
| **Vault** | Browse, search, filter, inspect, edit, and focus media. |
| **Ingestion** | Import local media or process online URL queues. |
| **Review** | Resolve possible duplicate matches and cleanup tasks. |
| **Stats** | Explore vault counts, artists, platforms, topics, and WD tags. |
| **Settings** | Manage configuration, workspaces, vaults, maintenance, and shortcuts. |
| **App Logs** | Inspect startup, active-vault, and raw console logs. |

## Requirements

### Runtime

- Python 3.11 or newer
- Node.js and npm
- Rust toolchain with Cargo; the Tauri crate currently requires Rust 1.77.2 or newer
- FFmpeg and FFprobe on `PATH` for video fingerprints, metadata, frames, and thumbnails
- A working SQLite build with FTS5 support

Python dependencies install `gallery-dl` and `yt-dlp`. On Windows, LMZ uses `python-magic-bin`; Unix-like systems use `python-magic`.

### Windows desktop development

Tauri uses Microsoft Edge WebView2. Current Windows installations normally include it. Rust development may also require the Microsoft C++ build tools expected by Tauri.

## Quick Start

From PowerShell in the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[windows,tauri]"

cd frontend
npm install
cd ..

python tools/maintenance/lmz_readiness_check.py --non-interactive
python dev.py
```

`python dev.py` starts the FastAPI backend on `127.0.0.1:8000`, starts Vite, and opens the Tauri desktop window. Stop it from the launching terminal with `Ctrl+C` or by closing the application.

For Linux or macOS development, replace the Python extras with:

```bash
pip install -e ".[unix,tauri]"
```

Platform-specific Tauri system packages are still required. These platforms receive less routine testing than Windows.

## First Run

LMZ opens a launcher before loading the management interface.

1. Select the built-in **Default** workspace, or create an external workspace.
2. Select or create a vault.
3. Open **Settings > General** and review processing and WD tagging options.
4. Open **Settings > Maintenance > Auth** to scan downloader credentials.
5. Add local files under **Ingestion > Local**, or add URLs under **Ingestion > Online**.

The WD tagger downloads its model weights the first time it is used. Disable WD tagging before ingestion if you do not want that download or do not need automatic tags.

## Core Workflows

### Local ingestion

Open **Ingestion > Local** and add files or folders. You can also drag media onto the application. Optional defaults apply an artist, platform, or source URL to the staged batch.

LMZ validates file extensions and MIME types, computes fingerprints, stores accepted media, writes notes, creates thumbnails, and updates indexes. Failed paths remain visible and can be retried from the same session.

### Online ingestion

Open **Ingestion > Online** to edit one of three queues:

- **Normal**: standard processing.
- **Force**: explicitly forced processing where supported by the ingestion rules.
- **Failed**: URLs that failed earlier; move them back to Normal or Force to retry.

The editor parses URLs before a run, groups them by artist/platform, and reports warnings. Queue directives such as `@artist:` and `@platform:` can supply metadata for following URLs. Runtime output appears in the ingestion monitor and App Logs.

Platform support depends on the installed versions of `gallery-dl` and `yt-dlp`, the source website, and valid authentication where required.

### Duplicate review

Exact duplicates are rejected during ingestion. Similar or uncertain matches can enter **Review**, where the original and candidate media can be compared before choosing the appropriate action. Review changes use the same guarded media lifecycle as normal deletion so database rows and owned files remain coordinated.

### Vault search

Search accepts plain text and semicolon-separated metadata filters:

```text
landscape
a:artist name
p:Pixiv
t:reference
#blue_hair
a:artist name; p:Pixiv; #portrait
```

Prefixes:

| Prefix | Meaning |
| --- | --- |
| `a:` | Artist |
| `p:` | Platform |
| `t:` | Topic |
| `#` | WD tag |
| `/` | Vault command |

Type `/` in the search bar to discover commands for layout, tile size, sorting, media filters, authentication scans, and review cleanup. The complete current list is available under **Settings > Shortcuts**.

## Workspaces and Vaults

A **workspace** is an independent LMZ library root. It contains its own configuration, topics, workspace metadata index, vaults, and generated operational data. A **vault** is one media collection inside that workspace.

LMZ has two workspace forms:

- **Default workspace**: stored at `%USERPROFILE%\.lmz\default` (or the `LMZ_DATA_ROOT` override).
- **External workspace**: registered from a user-selected location; LMZ does not relocate its data.

An external workspace resembles:

```text
lmz/
|-- .lmz-workspace
|-- config.yaml
`-- data/
    |-- workspace.db
    |-- topics/
    `-- vaults/
        `-- default/
            |-- db/lmz_main.db
            |-- vault/
            |   |-- assets/
            |   `-- notes/
            |-- ui_cache/thumbnails/
            |-- wd-tags/
            |-- review/
            |-- queues/
            |-- batches/
            |-- input/
            |-- local_ingest/
            |-- online_ingest/
            `-- logs/
```

Assets, notes, WD caches, and thumbnails use sharded subdirectories to avoid placing very large numbers of files in one folder.

### Shared application data

Authentication is intentionally application-scoped rather than workspace-scoped. All workspaces share credentials from `%USERPROFILE%\.lmz\app\secrets\auth\` (or the `LMZ_AUTH_ROOT` override). AI models are shared from `%USERPROFILE%\.lmz\app\models\`.

Legacy mixed-scope configurations are rejected during normal loading with a launcher error. Content adoption is explicit and content-only: fresh configs are generated, durable workspace data is staged and verified, and the source is never deleted or merged into an existing target automatically.

### Workspace deletion safety

The default or currently active workspace cannot be deleted. Switch to another workspace first.

External workspace deletion offers three modes:

| Mode | Result |
| --- | --- |
| **Unregister only** | Removes the workspace from LMZ. Files remain untouched. |
| **Delete generated data** | Removes LMZ configuration, indexes, topics, and derived vault data while preserving source assets and notes. |
| **Delete entire workspace** | Recursively removes the managed workspace root. Requires an LMZ ownership marker and exact-name confirmation. |

Deletion first stages owned paths, then updates the workspace registry. A staging or registry failure attempts to restore moved paths. If final cleanup cannot complete, LMZ keeps the staging path and reports it instead of pretending deletion fully succeeded.

## Vault Maintenance

Open **Settings > Maintenance** for these operations:

### Merge Vaults

Select at least two source vaults, choose a new target name, and preview the merge. The preview reports selected items, duplicates, importable items, and whether the source state changed. Creating the merge makes a new vault; source vaults are not modified.

### Vault Health

**Audit** checks database/file consistency, missing assets, orphan files, facet drift, and stale derived data. **Repair** is limited to the active vault and may quarantine orphan files, rebuild derived metadata, or remove stale caches. Review the confirmation before proceeding.

### Packages

- **Import package** validates an LMZ vault package before creating a new vault.
- **Export** creates a portable vault package with selectable content.
- **Backup** archives the selected vault folder.
- **Restore** validates and restores a backup through a confirmation flow.

Backups are written to `<workspace>/backups/vaults/<vault-id>/`. Portable exports are written to `<workspace>/exports/vaults/<vault-id>/`.

### System Maintenance

- **Auth** scans platform credential availability without exposing secret values.
- **Metadata index** rebuilds the searchable SQL metadata index.
- **Workspace metadata** synchronizes shared artist, platform, and WD-tag dictionaries.
- **Metadata registry** prunes entries unused across the entire workspace.
- **Review queue** cleans resolved or stale review work.

## Authentication

Downloader credentials are global to the application:

```text
%USERPROFILE%\.lmz\app\secrets\auth\
|-- x/cookies.txt
|-- instagram/cookies.txt
|-- pinterest/cookies.txt
|-- youtube/cookies.txt
`-- pixiv/
    |-- refresh_token.txt
    `-- cookies.txt
```

Cookie files must use Netscape cookie-file format. Pixiv prefers `refresh_token.txt` and falls back to Pixiv cookies. LMZ does not read authentication credentials from individual workspaces.

Set `LMZ_AUTH_ROOT` to use a different credential root, which is useful for isolated development and tests.

See [Downloader Authentication Guide](docs/auth_guide.md) for extraction and Pixiv OAuth instructions.

> Cookie files and refresh tokens grant account access. Never commit, share, screenshot, or include them in support logs.

## Browser Extension

The optional browser-capture prototype can stage images and append page URLs to the LMZ online queue. It is not part of the v1.0.0 release acceptance scope. Pending captures are retained in browser IndexedDB while LMZ is closed and synchronized when the backend is available.

Development versions exist for Edge, Chrome, and Firefox. See [Browser Extension](tools/browser_extension/README.md) for loading and synchronization instructions.

The extension and Tauri frontend authenticate mutating API requests with `%USERPROFILE%\.lmz\app\secrets\.api_key`. The backend creates this key automatically. Deleting it rotates the key on the next backend start; extension settings must then be updated.

## Logs and Diagnostics

**App Logs** separates three sources:

- **Startup logs**: structured backend, frontend, and authentication events before a vault is active.
- **Vault logs**: structured backend, frontend, local/online ingestion, review, auth, and ingest-audit events for the active vault.
- **Console**: raw backend/stdout/stderr capture from `console.log`.

The UI supports level filters, loaded-row search, live connection status, reload, open, and guarded clear actions. Search covers displayed timestamps, levels, modules, platforms, messages, extras, and raw records. The log viewer streams or tails loaded rows; it is not a full-file search engine.

To check system dependencies:

```powershell
python tools/maintenance/lmz_readiness_check.py --non-interactive
```

To update downloader packages:

```powershell
python tools/maintenance/maintenance_cli.py update-downloaders
```

## Configuration

LMZ separates app-wide behavior from workspace topology:

- `%USERPROFILE%\.lmz\app\settings.yaml` stores UI, Webview, logging,
  network, ingestion, media-processing, and tagging behavior.
- `%USERPROFILE%\.lmz\app\workspaces.yaml` registers workspace locations and
  the active workspace.
- `%USERPROFILE%\.lmz\default\config.yaml` is the built-in workspace config.
  External workspaces use `<workspace>/config.yaml`.

Workspace configs contain only `schema_version`, `active_vault`, and `vaults`
(display names and vault roots). Credentials never belong in workspace configs.
Most app-wide settings should be changed through the application UI.

Supported environment variables:

| Variable | Purpose |
| --- | --- |
| `LMZ_DATA_ROOT` | Override `%USERPROFILE%\.lmz` for development and isolated tests. |
| `LMZ_CONFIG_PATH` | Load a specific workspace config when the backend starts. |
| `LMZ_AUTH_ROOT` | Override the global authentication directory. |
| `LMZ_DISABLE_RELOAD=1` | Disable Uvicorn auto-reload, useful for automation or isolated runs. |

## Command-Line Ingestion

The legacy/direct pipeline entry point remains available:

```powershell
python main.py
```

Installing the project also creates the equivalent `lmz` command:

```powershell
lmz
```

For normal interactive use, prefer `python dev.py` and the desktop interface.

## Development

### Backend

The backend is FastAPI with SQLite storage and a process-local runtime context. API routes are grouped under `backend/api/`. Mutating requests require a valid local origin and API key. Media writers coordinate with deletion through per-storage lifecycle locks and atomic publication.

Run only the backend:

```powershell
cd backend
python web_api.py
```

### Frontend

The frontend uses Svelte 5, TypeScript, Vite, and Tauri 2.

```powershell
cd frontend
npm run check
npm run build
```

### Tests

Backend suite:

```powershell
python -m pytest tests/backend
```

Primary frontend integration suite:

```powershell
cd frontend
npm run test:mock-vault
```

Additional frontend suites:

```powershell
npm run test:playwright
npm run test:generated-vault
```

Tauri compile check:

```powershell
cargo check --manifest-path frontend/src-tauri/Cargo.toml
```

### Production build

Build the Python API sidecar before bundling Tauri:

```powershell
cd frontend
npm run build:sidecar
npm run tauri build
```

Generated frontend, Cargo, package, runtime data, logs, backups, exports, and secrets are excluded from version control.

## Repository Map

```text
backend/                 FastAPI, ingestion, storage, maintenance, and downloaders
config/                  Example configuration files only; not runtime storage
docs/                    Focused user and developer guides
frontend/                Svelte UI and Tauri desktop shell
tests/                   Backend and Playwright regression coverage
tools/browser_extension/ Browser capture and online-queue extension
tools/maintenance/       Readiness, build, fixture, and maintenance utilities
%USERPROFILE%\.lmz/      Default app, workspace, model, log, and credential data home
```

## Privacy and Data Safety

- LMZ has no required hosted library service; library files and databases remain on the local machine.
- Online ingestion sends requests to the source platform through the configured downloader.
- Enabling WD tagging may download model weights from Hugging Face.
- **Privacy blur** under General settings temporarily blurs media previews for screenshots. It does not encrypt or alter files.
- Backups, exports, logs, and browser-extension capture caches may contain sensitive paths or metadata. Handle them accordingly.
- Destructive actions use confirmations and path guards, but they are not a replacement for independent backups.

## License

LMZ is licensed under the [GNU General Public License v3.0](LICENSE).
