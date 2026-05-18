  # LMZ Current Status

Last updated: 2026-05-13

## Current Status

LMZ is a local media vault desktop app.

- Frontend: Tauri + Svelte.
- Backend: local FastAPI/Python API under `backend/`.
- Runtime model: SQLite for operational indexes; Markdown/YAML remains source of truth.
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
- Runtime DB: `data/db/lmz_main.db`.
- Vault assets: `data/vault/assets/{hash[:2]}/{storage_id}.{ext}`.
- Vault notes: `data/vault/notes/{hash[:2]}/{storage_id}.md`.
- WD tag cache: `data/wd-tags/{hash[:2]}/{storage_id}.json`.
- Thumbnails: `data/ui_cache/thumbnails/{hash[:2]}/{storage_id}.jpg`.
- Review quarantine: `data/review/`.
- Local ingest staging: `paths.local_ingest`, fallback `paths.input/local`.
- Online ingest staging: `paths.online_ingest`, fallback `paths.input/online`.
- Logs: `logs/raw/`, `logs/structured/`.
- Secrets: `secrets/`.

## Working Areas

- Local image, GIF, and video ingestion.
- External URL ingestion via gallery-dl and yt-dlp.
- Batch-safe Pixiv, X/Twitter, Instagram, Pinterest, YouTube community ingestion.
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
- Current commands include:
  - `/masonry`, `/grid`.
  - `/zoom-in`, `/zoom-out`.
  - `/toggle-inspector`.
  - `/ram-track`.
  - `/scan-auth`.
  - `/cleanup-review`.
  - `/sort-newest`, `/sort-oldest`, `/sort-artist`.
  - `/media-all`, `/media-image`, `/media-video`.

## Done Tasks

- Project renamed to Local Media Zettelkasten / LMZ.
- Python source root renamed from `src/` to `backend/`.
- Old full-DOM masonry/grid renderers archived; virtualized renderers are active.
- Layout/zoom config writes use the shared frontend config store.
- Vault header simplified; sort/media/layout/zoom actions moved to commands.
- Auth status scan implemented:
  - startup scan.
  - `/api/auth/scan`.
  - `/scan-auth`.
  - auth log dropdown.
  - secret values are not logged.
- Auth config cleanup:
  - `cookies_path` uses relative `secrets/cookies.txt`.
  - Pixiv token loads from `secrets/.secrets.yaml`.
  - `/api/config` strips secret keys.
  - relative cookie paths resolve from project root.
- RAM tracker implemented:
  - `/api/system/memory`.
  - footer display.
  - persisted `/ram-track`.
- Fullscreen media zoom/pan implemented.
- Wide/fullscreen grouped-media filmstrip implemented.
- Inspector toggle and resize implemented.
- Vault search header split from inspector column.
- Top vault `Add Files` button removed.
- Frontend mojibake and unused default assets cleaned up.
- Svelte accessibility warnings cleared in latest reviewed pass.
- Renderer performance fixes:
  - no `will-change` layer spam.
  - `translate3d(...)` positioning.
  - grid row-math visibility.
  - batched/log-gated summaries.
  - safer media MIME helpers.
  - cleanup for timers/SSE/fetches.
- Backend hardening:
  - session key for mutating API calls.
  - local-only CORS restrictions.
  - path validation for queue/log/review endpoints.
  - bulk delete API.
  - safe delete ordering.
  - review count endpoint.
  - sidecar build path.
  - practical Tauri CSP.
- Review workflow hardening:
  - `keep` defers without DB ingest.
  - `variant` ingests with duplicate bypass.
  - `replace` ingests first, deletes old target after.
  - cleanup failures route to `pending_cleanup`.
  - Cleanup section added.
  - `/api/review/cleanup` retries cleanup and removes orphan sidecars.
  - image/video compare panes render.
  - review asset/action URLs encode filenames.
  - unique review storage names avoid collisions.
  - clean startup always mounts `/review-assets`.
  - App Logs includes `review.jsonl`.
- Review smoke follow-ups fixed:
  - `/api/review` tuple-unpack crash.
  - review logging argument collision.
  - false failure after successful variant commit.
  - best-effort retry cleanup after variant ingest.
- Local ingestion safety:
  - originals are staged before processing.
  - originals are not moved into review.
  - double-start guard set before worker scheduling.
  - retry preserves defaults and `skip_similarity`.
  - status exposes `phase`, `run_id`, `scanned`, `staged`.
  - backend results capped to last 500.
  - folder expansion streams in the worker instead of pre-sorting/materializing the tree.
- Online queue safety:
  - `as_completed` import fixed.
  - deferred and crash-preserved URLs remain in queues.
  - stop-after-current keeps not-yet-started URLs.
  - worker/platform crashes are logged and preserved.
  - queue rewrite logs original/removed/remaining counts.
- Metadata/index performance:
  - disposable SQLite metadata index for topics and WD tags.
  - startup repair, watchdog reindex, status endpoint, rebuild endpoint.
  - topic/WD filters, facets, suggestions, and detail metadata read through index after initial backfill.
  - legacy YAML/cache fallback remains before index readiness.
- Query/render hot path fixes:
  - SQLite indexes for date/hash, artist/date/hash, platform, source artist, MIME/date, source URL.
  - artist-sort cursor pagination fixed.
  - renderer no longer builds full visual hash arrays.
  - masonry visible lookup uses bounded binary-search scanning.
- VP-tree indexing:
  - video/audio signatures append to pending items.
  - queries search built tree plus pending signatures.
  - batch updates rebuild once after batch.
- Recent validation-finding fixes:
  - vault grouping rebuilds from updated item lists.
  - masonry cache keeps geometry but refreshes current group data.
  - fullscreen pan state resets after drag and when zoom returns to 1.
  - production API startup retry handles delayed sidecar readiness.
  - ingest paths honor `paths.local_ingest` and `paths.online_ingest`.
- Mock-vault validation harness:
  - isolated fixture lives under `tests/fixtures/mock-vault/`.
  - frontend Playwright mocks API/media/review/RAM without touching the real vault.
  - backend pytest uses `LMZ_CONFIG_PATH` and temp fixture copies.
  - batch launchers live under `tests/` for VSCode terminal use.
  - `source_url` and platform are read-only in Inspector; artist remains editable.
  - mock-vault tests cover artist edit refresh, source/platform read-only behavior, masonry stale-data prevention, fullscreen pan/backdrop behavior, review filename encoding, video path rendering, and RAM unavailable state.
- Generated test-vault harness:
  - deterministic generator lives under `tests/generators/`.
  - generated vaults default to ignored `tests/generated/NNN-name/` folders.
  - generated config, DB rows, notes, assets, thumbnails, review fixtures, logs, and manifest stay isolated.
  - backend smoke tests validate generated vault consistency and `LMZ_CONFIG_PATH` isolation.
  - Playwright generated-scale test covers generated manifest API mocks, filtering, layout switching, and synthetic video handling.

## Current Test Results

### Phase A Generated-Vault Performance Findings

- Completed real generated-vault runs:
  - Initial `800`, `10k`, and `50k`: backend/index/API plus headed Tauri WebView scrolling.
  - WD-scale reruns: `800`, `10k`, and `50k` with realistic WD pressure (`1` rating, `1` character tag, `20` general WD tags per item).
  - Facet-count optimization reruns: `800`, `10k`, and `50k` after adding precomputed topic/WD facet counts.
  - `100k`: skipped for now because `50k` exposed the scale costs clearly.
- Frontend scrolling / virtualization:
  - headed Tauri scroll tests passed at `10k` and `50k`.
  - visible tile counts stayed bounded (`50-54` masonry, `36` grid).
  - mounted video counts stayed bounded (`7` at `10k`, `2` at `50k` in sampled scroll/filter paths).
  - frontend heap stayed low (`~9.4 MB` at `10k`, `~7.4 MB` at `50k` after video filter).
  - current evidence points away from scrolling as the primary bottleneck.
- Backend/API scale:
  - read-path DB connection cleanup reduced normal `50k` item-list/filter p50s from roughly `129-252ms` to mostly single/tens of ms.
  - cheap metadata status reduced `/api/metadata-index/status` from about `6.7s` p50 at `50k` to tens/hundreds of ms depending on table sizes.
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
- RAM:
  - backend memory remained stable enough for these profiles (`~75 MB` at `800`, `~82-85 MB` at `10k`, `~120 MB` at `50k` after WD/facet-count runs).
  - no RAM explosion observed.
- Primary bottlenecks:
  - full metadata index rebuild remains the largest backend cost.
    - realistic WD `10k`: `~34s`.
    - realistic WD `50k`: `~198-201s`.
  - `/api/metadata-index/status` is improved but still not ideal at `50k` with `1.1M` WD rows: p50 `~228ms`.
  - artist/platform filters and facets still use scan/LIKE paths and should be profiled separately.
- Next optimization targets:
  - inspect/optimize full metadata index rebuild loop and stale repair scanning.
  - make metadata index status cheaper for large metadata tables.
  - profile artist/platform scan paths.
  - add dirty queue/change tracking later to avoid scan-all stale detection.
  - rerun `100k` only after the above improvements.

## Deferred / Will Do Later

### Phase A - Stability V1

- Current focus is scale performance from generated-vault testing:
  - frontend scrolling/virtualization passed at `10k` and `50k`.
  - backend RAM stayed stable through `50k`.
  - metadata index rebuild and metadata index status are the measured bottlenecks.
  - topic/facet-heavy query paths need profiling after index/status fixes.

#### Phase A Implementation Batches

- Batch 4 - Scale performance fixes:
  - make `/api/metadata-index/status` cheap or cached.
  - inspect and optimize full metadata index rebuild.
  - profile topic/facet query paths at `10k` and `50k`.
  - add practical perf regression comparisons/budgets after baseline improvements.
  - rerun `100k` only after index/status costs are improved.

### Phase B - Knowledge Tools

- Artist database:
  - artist grouping.
  - artist aliases/platform handles/source links/counts.
  - workflows that make artist maintenance easier during normal vault use.
- Tag/topic workflows:
  - fast and trustworthy WD tag counts and topic counts.
  - in-memory facet cache or equivalent faster count path if current index is not enough.
  - promote WD tag to manual topic.
  - WD tag maintenance: delete, rename, hide/ignore, and later merge.
  - interactive tag management in Inspector.
- Search/index improvements:
  - persistent search/facet tables beyond current derived metadata index if needed for scale.
  - search chips.
  - Search/index scaling:
    - RAM hydration still bulk-loads pHash, tile, URL, and video signatures.
- Source metadata maintenance:
  - source URL normalization migration tool.
  - normalization is active in runtime paths (`source_url_norm` is written on ingest/update).
  - existing rows are backfilled lazily by `init_database()`.
  - no standalone migration/maintenance tool exists yet.

### Phase C - Vault Ops

- Multiple vault support:
  - support switching/selecting vault configs for testing and normal usage.
  - keep vaults isolated through config/runtime roots.
  - merge/split/separate vault operations are useful later but should not be rushed.
- Vault health/maintenance:
  - orphan/ghost checks.
  - backup/export/import flows.
  - periodic SHA256 re-verification.

### Phase D - UI Polish

- Review panel design refinement.
- Fullscreen board/view refinements.
- Inspector polish and better tag workflows.
- Custom context menu for vault tiles.
- Animation-aware GIF handling beyond first-frame thumbnail/tag behavior.
- Video hover preview strategy:
  - current hover preview can download original video.
  - options: file-size cap, backend preview clip endpoint, animated WebP thumbnail.
- Video embedding performance:
  - sampled frame extraction now uses one FFmpeg subprocess per batch.
  - embedding/tagging still depends on extracting sampled original video frames.

### Phase E - Browser Extension

- Browser extension integration:
  - Chromium-based browsers first: Edge/Chrome.
  - Firefox after the Chromium flow is stable.
  - capture URLs/media from the active page and send them to the LMZ queue/API.
  - handle API/session auth and local backend targeting carefully.

### Final Phase - Runtime / Packaging Hardening

- Dynamic sidecar port coordination:
  - startup handshake/API base/CSP/lifecycle.
- Packaging-time security checks.
- Clean-machine release validation.

### Longer-Term Platform Gaps

- YouTube community partial policy:
  - one failed expected image can still keep the post retryable.

## Done But Needs Check

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

- Phase A Batch 3 - Generated test vaults and performance harness:
  - deterministic generated-vault tool lives under `tests/generators/`.
  - generated vaults stay under ignored `tests/generated/NNN-name/` folders with isolated config, DB, notes, assets, thumbnails, review fixtures, logs, and manifest.
  - generated configs use isolated log and thumbnail paths.
  - Playwright generated-scale coverage and headed Tauri WebView performance harness were added.
  - perf commands write structured JSON results under ignored `tests/perf-results/`.
  - real generated-vault runs passed at `800`, `10k`, and `50k`; `100k` is deferred until index/status costs improve.

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

- Virtual renderer:
  - automated large-vault Playwright checks pass for 10k/100k masonry/grid and grouped mixed media.
  - needs real-vault smoke for offscreen video unmount behavior.
  - needs grouped media active-index smoke after scroll out/in.
  - needs narrow/wide zoom stability smoke.
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
  - Markdown-owned manual metadata implemented for `title`, `artist`, `date_added`, `topics`, and WD fields.
  - PATCH artist/topics writes DB cache and Markdown through one rollback-capable path.
  - metadata reindex reads Markdown `artist` and non-empty `date_added` back into SQLite.
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

- No active low-level backend inconsistency batch after review/search-index regression fix.

## Issue Remediation Plan

### Next Documentation / Drift Pass

- Review `docs/lmz_architecture.md` against current backend/frontend shape.
- Reconcile `docs/lmz_roadmap.md` phase notes with current status.
- Keep status doc as the operational handoff source.

### Recommended Fix Batches

1. Real-vault drag-drop/restart/re-ingest smoke for review/search-index regression fix.
2. Architecture/status docs drift review.
3. Real-vault corrupt-media/log smoke for P3.
4. Real-vault validation of remaining P0/P1/P2 smoke items.
