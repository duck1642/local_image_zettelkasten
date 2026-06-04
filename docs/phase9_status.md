# LMZ Current Status

Last updated: 2026-05-31

## Active Phase

Phase 9 - Browser Extension Integration.

Goal: build an Edge-first browser extension that sends supported platform page URLs to LMZ online ingestion and captures right-clicked images from arbitrary sites through LMZ backend staging.

Durable Phase 8 status was moved to:

```text
docs/phase8_status.md
```

## Current Baseline

- LMZ desktop app baseline: Tauri + Svelte frontend, FastAPI/Python backend.
- Ingestion baseline: local files plus online gallery-dl/yt-dlp queues.
- Metadata ownership remains unchanged:
  - SQLite owns item identity/source/runtime fields.
  - Markdown/YAML owns editable topics and WD metadata.
  - Metadata index/facet tables are derived and rebuildable.
- Runtime data remains under `data/`; secrets remain under `secrets/`.

## Phase 9 Decisions

- Extension code lives under `tools/browser_extension/`.
- Microsoft Edge is the first target.
- Chrome is second, expected to stay close to Edge through Chromium Manifest V3.
- Firefox is deferred until Edge/Chrome are stable.
- Use `Capture`, not `local queue`, for browser-selected media.
- Online queue is only for supported platform page/post URLs first:
  - Instagram
  - X/Twitter
  - Pixiv
  - Pinterest
- Capture is for arbitrary sites:
  - user right-clicks an image.
  - extension fetches image bytes into a Blob.
  - extension stores the Blob in local browser/extension cache first.
  - when LMZ is online, extension syncs cached bytes to backend staging.
  - backend stages the file under the active vault.
  - popup collects metadata.
  - commit routes through existing LMZ ingest/review logic.
- If Blob caching fails, extension can fall back to a normal browser download under `Downloads/LMZ Capture/`, but that is a manual backup path, not the main automation queue.
- MVP is image capture only. Video capture is deferred.
- Do not promise 100% capture success. Blob/canvas/auth-gated/protected media need later fallback work.
- API keys must not be placed in preview URLs or query strings.

Full temporary design record is in:

```text
docs/lmz_roadmap.md
```

## Implemented So Far

- Added backend capture router:
  - `POST /api/capture/stage`
  - `GET /api/capture/preview/{staged_id}`
  - `DELETE /api/capture/stage/{staged_id}`
  - `POST /api/capture/commit`
- Added active-vault capture staging under `capture_staging/`.
- Added staged sidecar metadata as the backend source of truth.
- Capture commit calls existing `process_file()` with browser-capture metadata.
- Added extension-origin handling while keeping mutating requests API-key protected.
- Added backend-owned queue append endpoint:
  - `POST /api/queue/{queue_name}/append`
- Added queue-block writer that preserves `@artist`, `@platform`, URL, and `---` parser semantics.
- Added Edge Manifest V3 extension with:
  - right-click image capture into IndexedDB Blob cache.
  - right-click online page/URL staging into IndexedDB.
  - popup settings.
  - local cached preview via blob URL.
  - sync, discard, commit, download fallback, and queue append actions.
  - 100 MB automatic cache limit with large-file download/discard choice.
- Added Chrome Manifest V3 extension containing background service worker, popup UI, and styles.
- Added Firefox Manifest V3 extension containing background script, popup UI, and styles.
- Added `python-multipart` dependency.

Edge capture now caches locally first, so right-click capture works while LMZ is closed. LMZ is only needed for sync, commit, and online queue append.

## Extension Shape

```text
tools/browser_extension/
  README.md
  edge/
    manifest.json
    background.js
    popup.html
    popup.js
    styles.css
  chrome/
    README.md
    manifest.json
    background.js
    popup.html
    popup.js
    styles.css
  firefox/
    README.md
    manifest.json
    background.js
    popup.html
    popup.js
    styles.css
```

Edge, Chrome, and Firefox are runnable extension folders now.

> [!NOTE]
> **Maintenance warning**: Edge is currently ahead of Chrome and Firefox. Chrome/Firefox still use the older direct-upload flow until Edge smoke passes and the implementation is copied or shared.


## Backend Shape

Active-vault staging:

```text
data/vaults/<active_vault>/capture_staging/
```

Capture endpoints:

- `POST /api/capture/stage`
- `GET /api/capture/preview/{staged_id}`
- `DELETE /api/capture/stage/{staged_id}`
- `POST /api/capture/commit`

Implementation rule: capture commit must call existing processor/review helpers. Do not duplicate storage ID allocation, pHash checks, DB insert logic, note generation, thumbnail generation, WD tagging, or RAM index hydration.

## Immediate Work

1. Manual Edge smoke with LMZ closed, then opened for sync.
2. Test supported online page queue append for X/Pixiv/Instagram/Pinterest.
3. Test similar-image review behavior with `IMAGE_REVIEW_PHASH_THRESHOLD = 12`.
4. Test large-image path over 100 MB.
5. Test protected/CORS-blocked media download fallback.
6. After Edge smoke passes, copy or share the Edge implementation with Chrome.

## Current Risks

- Extension fetch may fail for blob URLs, canvas images, expiring CDN links, hotlink protection, and auth-gated media.
- Video capture is likely messy and should stay out of the MVP.
- Restored offline-first Edge extension has not had a fresh smoke after sync.
- IndexedDB quota and large image/GIF behavior use a 100 MB automatic cache limit, but need real-world testing.
- Download fallback copies are user-visible and should not be auto-deleted by default.

## Useful Checks

```powershell
$env:PYTHONPATH='backend'
python -B -c "import ast, pathlib; [ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path)) for path in pathlib.Path('backend').rglob('*.py')]; print('AST OK')"
python -B -c "import core, web_api, db.sqlite_operator, db.search_manager, queue_service, tagging.service; print('IMPORT OK')"
cd frontend
npm run check
git diff --check
```

## Validation Plan

- Backend capture tests pass:
  - `pytest -q tests\backend\test_browser_capture.py --basetemp test-results\pytest-capture`
- Manual Edge smoke before Chrome smoke.
- Test direct `.jpg`, `.png`, `.webp`.
- Test CDN URLs with query strings.
- Confirm failed blob/canvas/protected cases fail clearly.
- Confirm committed captures preserve `source_url`, explicit artist, and platform.
- Confirm duplicate/similar captures route to existing review behavior.
