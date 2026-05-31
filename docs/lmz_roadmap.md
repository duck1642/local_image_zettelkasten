# LMZ — Roadmap

---

## Phase 1 — Core Image Pipeline ✅

### Task

Build the input processor.
- Takes images from input folder
- Processes them, adds to database
- Moves them to vault folder and creates a markdown file per image

### Key Decisions

- Use SHA256 hash values for unique item identity. Physical filenames later moved to compact `storage_id` values to avoid Windows path-length pressure.
- Add MIME type and extension filter — check MIME type first, fall back to extension
- Using SHA256 for now; can be swapped for other algorithms later

### Resolved Research

- **Hash collisions for similar images:** SHA256 only detects exact duplicates. Similar images (e.g. different resolutions of the same image) require perceptual hashing (pHash). Addressed in Phase 5.

### What I Learned

- `def func() -> data_type:` means the function returns the given data type

---

## Phase 2 — Video & Organized Storage ✅

### Task

- Separate vault into two folders so images and markdown files are no longer mixed
- Add video support

### Key Decisions

- Split vault: `assets/` for images/videos, `notes/` for markdown files
- Use relative paths for markdown links
- Add `.mp4`, `.webm`, `.ogv`, `.gif` MIME and extension support

---

## Phase 3 — External Ingestion ✅

### Task

Fetch images/videos from various platforms by URL, download to input folder, process as usual.

### Key Decisions

- Use `gallery-dl` and `yt-dlp` — industry standard, easy to integrate

### Resolved Research

- **gallery-dl vs Instaloader for Instagram:** Went with gallery-dl for consistency. Offline archive parsing added in Phase 5 as a safer alternative for Instagram.
- **Cookies/authentication for platform access:** Addressed in Phase 5 with cookies.txt approach and `.secrets.yaml` separation.

---

## Phase 4 — Authentication & Platform Support ✅

### Task

Handle platform-specific access restrictions.

### Key Decisions

- **Pixiv:** OAuth 2.0 PKCE flow
- **Instagram/X:** `cookies.txt` containing session credentials
- **Pinterest:** No special handling needed — worked out of the box

### Resolved Research

- **Is cookies.txt safe?** Went with a semi-manual approach: a script that takes cookies from the user and writes them to `cookies.txt`. Safer than manual editing. Stored path in `.secrets.yaml` to isolate credentials from config.
- **Alternative to cookies.txt:** No better option found for gallery-dl compatibility. Mitigated risk via `.secrets.yaml` separation and a note to never commit the file. Encryption at rest planned for a future phase.

### What I Learned

- API authentication is painful

---

## Phase 5 — Bug Fixes & Hardening ✅

### Task

Fix bugs found during review. Stabilize the pipeline for high-volume use.
Add duplication check methods.

### Key Decisions

- **Pixiv Ugoira:** Downloaded as `.zip`. Use ffmpeg to convert to `.webm` or `.mp4`
- **Playwright for Pixiv auth:** Safer than manual OAuth. Dedicated browser for authentication
- **Semi-manual cookies approach:** Script takes cookies from user, saves to `cookies.txt`. Safest option available
- **Retry logic:** Retry twice then skip, to handle transient restrictions

### Resolved Research

- **Platform-ordered downloads to reduce restrictions:** Implemented platform-bucketed `ThreadPoolExecutor`. URLs grouped by platform, platform-specific delays applied.
- **X/Instagram archive extraction:** Implemented `parse_ig.py` and `parse_x.py` offline parsers. Extract links, write batches of 50 to `pending_links.md`.
- **Protecting cookies.txt from AI context:** Marked clearly in docs and file tree as `⛔ DO NOT TOUCH`. Encryption at rest deferred to a future phase.

### What I Learned

- Claude Opus is strong for bug fixing
- Gemini-Claude feedback loop made bug fixing more effective

---

## Phase 6 — Optimization & Multi-Modal Intelligence ✅

### Task

Do some optimization for searching.
Upgrade and harden duplication check methods.

### Big-O Complexity Analysis (Post-Optimization)

| Module / Operation | Complexity | Status |
| :--- | :--- | :--- |
| **Duplicate Hash Check** | $O(\log N)$ | Fast (SQLite B-Tree). |
| **Duplicate URL Check** | $O(1)$ | **Optimized.** RAM-based Set lookup. |
| **Image pHash Search** | $O(\log N)$ | **Optimized.** BK-Tree RAM index. |
| **Video Sonic Search** | $O(\log N)$ | **Optimized.** VP-Tree bitwise Hamming. |
| **Video AI Search** | $O(\log N)$ | **Optimized.** VP-Tree Cosine distance. |

### Key Decisions (Optimization)

- **RAM-Based Indexing:** Hydrate BK-Trees and URL sets into memory at startup for logarithmic scaling.
- **Advanced Concurrency:** Global Semaphore limit + per-platform `ThreadPoolExecutor` with random Jitter.
- **Multi-Modal Video:** Combined **Sonic Similarity** (Chromaprint) and **Semantic AI** (5-point frame sequence).
- **Batch Snapshot Logic:** Isolate similarity checks to "pre-ingestion" state to allow variants in the same post.
- **Transparency Normalization:** Alpha-channel flattening with presets (white/black/gray).

---

## Phase 7 — Metadata Integrity & Stabilization ✅

### Task

Fix the "Artist" metadata gap and enable platform-agnostic ingestion.
Implement an Integrity Gate to prevent corrupted downloads.
Check how paths handled. Everything must be relative to project folder

### Completed & Verified

- **The Integrity Gate:** 
    - Implemented a file-size verification system for `yt-dlp` and `gallery-dl`.
    - **Dual Mode:** `normal_pending_links.md` (Strict validation) vs `force_pending_links.md` (Bypass).
    - **Strict/Relaxed Logic:** Exact byte matching for images; 1% / 100KB buffer for videos.
- **The Artist Fix:** 
    - Platform-specific extraction for X, Pixiv, Instagram, and Pinterest.
- **Clean Slate Naming:**
    - Temporary files are now numerically indexed (`1.jpg`, `2.mp4`) to avoid emoji/special character path issues.
- **Metadata Stabilization:**
    - YouTube Video Titles are now captured and saved in the YAML frontmatter of Markdown notes.
    - Robust parsing for `yt-dlp` to handle stdout noise and scientific notation.
- **Session-Based Atomicity:**
    - Multi-file posts are now validated as a single unit. If one file fails, the entire batch is rejected to keep the Vault clean.
- **Audit Remediation (24 Fixes):**
    - Fixed DB connection leaks, VP-Tree re-indexing bugs, NoneType crashes in review menu, and performance bottlenecks in fingerprinting.

---

## Phase 8 — Tauri Vault App, Metadata System, Stability, and Scale

### Task

Build and stabilize the local-first Tauri/Svelte vault app, backend API, metadata/indexing system, workspace/vault model, and scale validation harnesses.

### Completed So Far

- Replaced the broken Flet/PySide direction with a Tauri + Svelte desktop UI backed by FastAPI.
- Removed old PySide UI code, `gui.py`, PySide dependencies.
- Renamed the Python source root from `src/` to `backend/`.
- Added a Svelte vault with virtualized masonry/grid layouts, grouped source URL tiles, infinite loading, and command-driven media/sort filters.
- Added a Svelte inspector for metadata editing, source URL group navigation, copy/delete/open actions, and clickable WD suggestions.
- Added toggleable and resizable inspector behavior.
- Added image/video wide and fullscreen focus behavior through the modern frontend.
- Added fullscreen zoom/pan core logic.
- Added wide/fullscreen grouped-media filmstrip core logic.
- Added markdown queue ingestion workbench with Normal/Force/Failed queues, save/open/retry/clear actions, live URL counts, and ingestion locking.
- Added Svelte Review, Settings, and Logs views.
- Added Stats view for WD tag, artist, platform, and topic counts.
- Added Stats topic/WD multi-select handoff into Vault search.
- Added artist editing, alias/link management, and merge workflow in Stats.
- Added Stats topic rename/delete/merge workflows and WD tag rename/delete tooling.
- Split Stats into focused components, API helpers, utilities, and CSS.
- Added color-sensitive Stats/Inspector chip styling for rating, character, topic, and general tags.
- Split logs into raw terminal output and structured JSONL streams.
- Added readable and raw log display modes in the UI.
- Added a reusable local WD tagging service with local model storage under `data/models/`.
- Added detailed WD tag cache, now stored under active-vault compact `wd-tags/{hash[:2]}/{storage_id}.json` paths.
- Added distilled WD fields to markdown frontmatter.
- Added image and video WD tagging; videos use sampled frame tagging and merged suggestions.
- Kept manual topics separate from WD tags.
- Added a disposable SQLite metadata index for topic/WD queries while keeping markdown/YAML as source of truth.
- Added precomputed metadata facet counts for topic/WD/artist/platform counters and suggestions.
- Added workspace DB `data/workspace.db` for shared artist, platform, and WD tag dictionaries.
- Added shared topic library under `data/topics/`.
- Added topic file creation/reuse, relative topic links in notes, and legacy plain topic parsing.
- Added workspace chooser, Obsidian workspace setup, and restart-based workspace selection.
- Added multiple vault support under `data/vaults/<vault_id>/`.
- Added per-workspace shared metadata with active-vault usage counts.
- Added compact `storage_id` runtime storage paths while preserving SHA256 hashes as public/API identity.
- Added a metadata index rebuild maintenance tool for status, stale repair, and full persistent metadata rebuilds.
- Added deterministic generated-vault generator under `tests/generators/`.
- Added generated configs, DB rows, notes, assets, thumbnails, review fixtures, logs, and manifests isolated under ignored `tests/generated/`.
- Added generated-scale Playwright tests for layout switching, filtering, grouped media, mixed image/video handling, cursor pagination, and overlap checks.
- Added headed Tauri WebView performance harness and split perf commands under `tests/perf/`.
- Added RAM tracking to perf runs.
- Validated generated vaults at `800`, `10k`, and `50k`; `100k` remains deferred until needed.
- Added realistic WD tag generation and validation for generated vaults.
- Added cached metadata counters, dirty queue, and bulk full metadata rebuild path.
- Added stage timing and fast default maintenance rebuild behavior.
- Added artist/platform exact-first filtering and indexed paging support.
- Hardened local API mutating endpoints with a local session key and allowlisted origins.
- Validated log, queue, and review paths to prevent traversal.
- Fixed false-success API behavior for missing items.
- Improved API pagination for frontmatter-backed filters.
- Moved main blocking API paths through thread helpers.
- Replaced unsafe `INSERT OR REPLACE` DB writes.
- Added indexed `source_url_norm` duplicate checks.
- Shared gallery-dl/yt-dlp valid media filtering.
- Centralized frontend API, asset, and SSE URL construction.
- Fixed command-triggered layout saves to use authenticated API requests.
- Added shared infinite-scroll loading for masonry and grid vault layouts.
- Promoted virtualized renderers to the active `masonry` and `grid` layouts.
- Archived old full-DOM renderer snippets as non-compiled references.
- Added frontend facet-count suggestions and command search improvements.
- Added local RAM tracker endpoint, frontend polling, footer display, and `>ram-track` toggle.
- Added a PyInstaller sidecar build path for production Tauri packaging.
- Replaced sidecar startup panics with logged errors.
- Added a practical Tauri CSP for local backend/media access.
- Added Settings maintenance actions for auth scan, metadata rebuild, review cleanup, workspace metadata rebuild, and workspace metadata prune.
- Added Settings vault tools for merge preview/merge, vault health audit/repair details, backup/export/import, create/rename/delete, and active vault selection.
- Split Settings into focused panels, shared API wrappers, utilities, and CSS.
- Added tabbed Settings navigation to reduce visible panel bloat while preserving existing tools.
- Added config cache with mtime invalidation after Settings writes.
- Added log stream heartbeats, truncate/rotation handling, tail-on-connect, and bounded frontend reconnects.
- Added native drag-and-drop preflight into Local Ingestion.
- Split Online/Local Ingestion into focused components and shared ingestion CSS.
- Added queue metadata syntax for `@artist:`, `@platform:`, full-line comments, `---` groups, grouped preview, warnings, line numbers, and help popover.
- Stripped scraper-derived online `artist`/`title` metadata while preserving app/user-owned editable artist/title metadata.
- Added Local Ingestion artist autocomplete and platform dropdown cleanup.
- Added review workflow hardening for keep/variant/replace/delete/cleanup and restart-safe pending sidecars.
- Split Inspector into focused media preview, metadata grid, topic editor, and WD suggestion components.
- Added shared Inspector tag chip component and local named Svelte icon components.
- Documented local-first icon policy while keeping external icon packs deferred unless vendored locally.
- Added mock-vault and generated-vault Playwright/backend validation harnesses.

### Still In Progress / Needs Refinement

- Virtual masonry/grid renderers passed generated-vault and headed Tauri performance runs, but still need continued real-vault validation.
- Settings, Stats, Inspector, Ingestion, workspace/vault switching, and metadata maintenance flows need more real-vault smoke after the refactors.
- Inspector chip/action UX is stable again, but still needs final manual pointer-hit and hover/focus smoke.
- Review panel needs polish after the main Inspector/Stats/Settings/Ingestion work.
- Fullscreen zoom/pan and wide/fullscreen filmstrip work, but still need UI polish.
- GIFs ingest and preserve originals, but vault/inspector previews are still static first-frame thumbnails and tagging/dedupe inspect only the first frame.
- Search/index hydration still bulk-loads runtime signatures into RAM.
- Video frame sampling now uses one ffmpeg subprocess per sampled batch; embedding/tagging still depends on sampled original frames.
- Decide video hover preview strategy.
- YouTube community posts still fail/retry if one expected image fails.
- Existing `source_url_norm` values are backfilled lazily on DB init, not through a standalone migration tool.
- Cleanup old compatibility paths after more real-vault use.
- Production sidecar packaging exists but still needs release-build and clean-machine validation.

---

## Phase 9 — Browser Extension Integration

### Task

Build a browser extension that captures active-page/media URLs and sends them to LMZ's local queue/API, reducing dependence on fragile backend scrapers.

### Planned Scope

- Start with Chromium-based browsers: Edge/Chrome.
- Capture active tab URL, selected media URLs, and page media candidates.
- Send URLs and metadata groups into the online queue/local API.
- Handle local API base discovery and session/auth safely.
- Pass source/platform metadata where reliable.
- Keep online scraper-derived `artist`/`title` out of item metadata; explicit user/app metadata remains owner.
- Defer Firefox until the Chromium flow is stable.

### Temporary Design Decisions

The extension should live under:

```text
tools/browser_extension/
```

The first target browser is Microsoft Edge because it is the primary browser in current use. Chrome should remain a near-term secondary target because the extension will start on Chromium Manifest V3. Firefox is explicitly deferred until the Edge/Chrome path is stable, because Firefox extension behavior and Manifest V3 support differ enough to distract from the MVP.

Initial folder direction:

```text
tools/browser_extension/
  README.md
  shared/
    background.js
    popup.html
    popup.js
    styles.css
    icons/
  edge/
    manifest.json
  chrome/
    manifest.json
  firefox/
    manifest.json
```

Only the Edge manifest needs to be production-real at first. Chrome can be kept close to Edge. Firefox can remain a placeholder until a later compatibility phase.

The product split is:

- **Online queue**: supported platform page/post URLs go into LMZ's existing online queue.
- **Capture**: browser-selected media is uploaded/staged through the local LMZ backend, then committed through LMZ's existing ingest/review path.

Do not call the second flow "local queue" in code or UI. "Local ingestion" already means filesystem paths selected from the local machine. Browser media is not local until LMZ receives and stages it. Use "Capture" for the extension-driven media flow.

#### Online Queue Flow

Online queue is for platforms where LMZ already has downloader logic:

- Instagram
- X/Twitter
- Pixiv
- Pinterest

The extension sends the page/post URL plus explicit user metadata. LMZ should append a queue block compatible with the current markdown queue parser, for example:

```text
@artist: creator name
@platform: X
https://x.com/creator/status/123
---
```

The backend, not the extension, should own final queue formatting. The extension should send structured JSON such as URL, queue name, artist, and platform. The backend can then preserve existing queue parser semantics and avoid duplicating queue syntax rules in extension code.

For online ingestion, the source URL is the page/post URL. Downloader-derived artist/title metadata should remain untrusted. Explicit user/app-provided artist/platform metadata is the owner.

#### Capture Flow

Capture is for unsupported or arbitrary sites.

MVP capture should start with right-click image capture only:

```text
right-click image -> extension fetches image bytes -> save Blob in extension cache -> sync to LMZ backend staging when available -> popup metadata -> commit to vault
```

Capture must work when LMZ is closed. The extension should not require the backend to be online at right-click time. The browser/extension download step and local cache write happen first; backend upload is a later sync step.

The extension-side source of truth for unsynced captures should be IndexedDB, not `chrome.storage.local`. `chrome.storage.local` is acceptable for lightweight settings, badge/popup summaries, and status pointers, but image bytes should live in IndexedDB as Blob/File data.

Normal browser download can be used as a secondary fallback/backup, not as the main automation queue:

```text
try fetch -> Blob -> IndexedDB cache
if Blob cache fails -> try chrome.downloads.download() to Downloads/LMZ Capture/
```

If the fallback only downloads to disk and no Blob is cached, the item should be marked as `downloaded` / `download_only`: useful for manual recovery, but not automatically syncable to LMZ unless a later file-picker/native-helper path is added.

Suggested extension capture states:

- `cached`: Blob is stored in IndexedDB and can sync to LMZ later.
- `downloaded`: visible backup copy was saved, but no Blob is available for automatic sync.
- `uploading`: extension is currently sending cached Blob to LMZ.
- `uploaded`: LMZ has staged the file and returned `staged_id`.
- `committed`: LMZ handled the item through ingest/review/duplicate logic.
- `failed`: last cache/sync/commit attempt failed and is retryable where possible.

Videos are deferred beyond the image MVP. Many site videos are HLS/DASH streams, blob URLs, segmented media, or protected players. A context-menu video item can be added later, but should not be part of the first stability target.

Capture payload should preserve two URLs:

- `source_url`: parent page/post URL, used for provenance and UI grouping.
- `media_url`: raw selected media URL, used only as transport/debug metadata.

The backend should stage uploaded bytes under the active vault, for example:

```text
data/vaults/<vault_id>/capture_staging/
```

Staging should include a backend-owned sidecar so extension storage and backend disk state can recover from drift:

```json
{
  "staged_id": "staged_...",
  "source_url": "https://site/page",
  "media_url": "https://cdn/site/image.jpg",
  "original_name": "image.jpg",
  "mime_type": "image/jpeg",
  "captured_at": "...",
  "platform_guess": "General Web"
}
```

The extension may also keep a lightweight staged list in `chrome.storage.local` for popup navigation and badge count, but that storage is not the source of truth for cached bytes.

Commit should call existing LMZ ingest/review behavior. It should not reimplement storage ID allocation, SHA256 insert logic, pHash checks, note generation, thumbnail generation, WD tagging, or RAM index hydration. The capture commit endpoint should validate the staged file and metadata, then route through the existing processor/review helpers.

#### Capture Limitations

Browser-assisted capture reduces scraper brittleness, but it is not guaranteed to work on every site. Avoid promising a 100% success rate.

Expected failure or later-fallback cases:

- `blob:` URLs.
- Canvas-rendered images.
- Auth-gated media where extension `fetch()` cannot reproduce the page request.
- Hotlink or referer-protected assets.
- Expiring signed CDN URLs.
- Service-worker-only assets.
- HLS/DASH video streams.
- DRM-like or protected media players.

For MVP, failed captures should produce clear errors. A later fallback can upload bytes directly from content-script/page context where possible, or add specialized handling for blob/canvas cases.

Offline/cache-specific risks:

- IndexedDB quota can fill up.
- Very large images/GIFs should have a size policy before caching.
- Downloaded fallback copies are user-visible and should not be auto-deleted unless the user opts in.
- A `downloaded` item may require manual Local Ingestion from `Downloads/LMZ Capture/`.

#### Security Decisions

The backend must allow browser extension requests without allowing arbitrary web pages.

Requirements:

- Mutating extension endpoints require `X-LMZ-API-KEY`.
- Normal webpage origins remain rejected.
- Extension origins are allowed only for authenticated local API use.
- Do not put the API key in preview URLs or query strings.

Preview should use authenticated fetch from the popup:

```javascript
const res = await fetch(previewUrl, {
  headers: { "X-LMZ-API-KEY": apiKey }
});
const blob = await res.blob();
img.src = URL.createObjectURL(blob);
```

This avoids leaking the API key through URLs, logs, browser history, or devtools traces.

If possible, later restrict allowed extension IDs instead of allowing every `chrome-extension://` origin. The API key remains the primary guard.

#### Implementation Phases

1. **Scaffold extension files**
   - Create `tools/browser_extension/`.
   - Add Edge-first Manifest V3 files.
   - Add placeholder Chrome/Firefox manifest folders.
   - Add minimal popup/background skeleton.

2. **Backend capture staging**
   - Add capture stage endpoint.
   - Add preview endpoint with header auth.
   - Add discard endpoint.
   - Store staged file plus sidecar under active-vault `capture_staging/`.
   - Validate staged IDs to prevent traversal.

3. **Basic right-click image capture**
   - Add Edge context menu for image capture.
   - Fetch selected image with browser extension permissions.
   - Store Blob/File bytes in IndexedDB first.
   - If Blob cache fails, try normal browser download to `Downloads/LMZ Capture/`.
   - Store pending item reference/status and update badge count.

4. **Stability loop**
   - Test direct `.jpg`, `.png`, and `.webp` URLs.
   - Test CDN URLs with query strings.
   - Test authenticated pages where practical.
   - Ensure blob/canvas/protected failures are clear and non-destructive.

5. **Basic popup UI**
   - Show cached capture preview from IndexedDB when not uploaded.
   - Show backend preview after upload to LMZ staging.
   - Add artist and platform fields.
   - Add sync/upload, discard, and commit actions.
   - Add connection indicator and API settings.

6. **Capture commit**
   - Upload cached Blob to backend staging when LMZ is online.
   - Commit staged file through existing LMZ processing/review path.
   - Preserve explicit artist/platform/source metadata.
   - Return `ingested`, `duplicate`, or `quarantined` status clearly.
   - Clean up staging after success where appropriate.

7. **Online queue support**
   - Add "Send page to LMZ online queue".
   - Limit to supported platform intent first.
   - Backend appends queue blocks with explicit artist/platform metadata.
   - Keep auto-start disabled unless deliberately added later.

8. **Metadata hardening**
   - Improve platform guessing from page URL.
   - Preserve original filename/extension/MIME where possible.
   - Add artist/platform autocomplete from LMZ.
   - Consider topics only after the basic metadata path is stable.

9. **UI refinement**
   - Improve error states, loading states, batch navigation, and settings.
   - Match LMZ visual language without pulling in the full Tauri frontend stack.

10. **Tests and iteration**
   - Add backend tests for stage, preview, discard, commit, auth, and traversal rejection.
   - Manual Edge smoke first.
   - Chrome smoke second.
   - Firefox compatibility later.

---

## Phase 10 — Reverse Search & Provenance

### Task

Recover the "Exact Source" of orphan files using pHash-based reverse lookups and provenance hints after the browser extension flow is usable.

---

## Phase 11 — Modular Logic & Advanced Vision

### Task

Implement the **Strategy Pattern** for switchable deduplication algorithms and upgrade tiling to a **Sliding Window** system.

---

## Phase 12 — Security & Credential Hardening

### Task

Encrypt `.secrets.yaml` and `cookies.txt` at rest and implement improved credential isolation.

---

## Phase 13 — Runtime / Packaging / Vault Health Hardening

### Task

Finish release/runtime hardening, clean-machine packaging validation, and any remaining vault-health integrity checks not already covered by Phase 8.
