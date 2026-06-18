# Local Media Zettelkasten

Local media ingestion, duplicate detection, vault generation, local WD tagging, and Tauri/Svelte management UI.

## Commands

- `python dev.py` launches the FastAPI backend and Tauri/Svelte UI for development.
- `python main.py` runs the ingestion pipeline.
- `lmz` runs the ingestion pipeline when installed.
- `python tools/maintenance/clear_pycache.py` removes Python cache folders.
- `cd frontend; npm run build` builds the frontend.
- `cd frontend; npm run build:sidecar` builds the Tauri production sidecar binary.

Runtime data lives under `data/` and logs under `logs/`.

## Authentication & Credentials

External downloaders (such as `gallery-dl` and `yt-dlp`) require credentials stored under the global `secrets/auth/` directory. For a complete guide on extracting cookies and setting up Pixiv OAuth, see the [Downloader Authentication Guide](docs/auth_guide.md).
