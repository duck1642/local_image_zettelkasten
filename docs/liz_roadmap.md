# LIZ — Roadmap

---

## Phase 1 — Core Image Pipeline ✅

### Task
Build the input processor.
- Takes images from input folder
- Processes them, adds to database
- Moves them to vault folder and creates a markdown file per image

### Key Decisions
- Use SHA256 hash values as filenames for unique identity
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

## Phase 8 — Modern Management UI, Local Tagging, and API Hardening

### Task
Build a practical desktop interface for vault management, add local AI tagging, and harden the local API/runtime boundary.

### Completed
- Replaced the broken Flet/PySide direction with a Tauri + Svelte desktop UI backed by FastAPI.
- Removed old PySide UI code, `gui.py`, PySide dependencies, and the `liz-gui` entry point.
- Added a Svelte vault with masonry/grid layouts, grouped source URL tiles, infinite loading, and media filters.
- Added a Svelte inspector for metadata editing, source URL group navigation, copy/delete/open actions, and clickable WD suggestions.
- Added image/video wide and fullscreen focus behavior through the modern frontend.
- Added markdown queue ingestion workbench with Normal/Force/Failed queues, save/open/retry/clear actions, live URL counts, and ingestion locking.
- Added Svelte Review, Settings, and Logs views.
- Split logs into raw terminal output and structured JSONL streams.
- Added readable and raw log display modes in the UI.
- Added a reusable local WD tagging service with local model storage under `data/models/`.
- Added detailed WD tag cache under `data/wd-tags/{hash[:2]}/{hash}.json`.
- Added distilled WD fields to markdown frontmatter.
- Added image and video WD tagging; videos use sampled frame tagging and merged suggestions.
- Kept manual topics separate from WD tags.
- Kept SQLite free of manual topics and WD tag metadata.
- Hardened local API mutating endpoints with a local session key and allowlisted origins.
- Validated log, queue, and review paths to prevent traversal.
- Fixed false-success API behavior for missing items.
- Improved API pagination for frontmatter-backed filters.
- Moved main blocking API paths through thread helpers.
- Replaced unsafe `INSERT OR REPLACE` DB writes.
- Added indexed `source_url_norm` duplicate checks.
- Shared gallery-dl/yt-dlp valid media filtering.

### Remaining Caveats
- Search/index hydration still bulk-loads runtime signatures into RAM.
- `get_config()` still reparses YAML often; caching needs explicit invalidation.
- Video embedding still extracts five frames through separate ffmpeg calls.
- YouTube community posts still fail/retry if one expected image fails.
- Existing `source_url_norm` values are backfilled lazily on DB init, not through a standalone migration tool.
- Frontend still has Svelte accessibility warnings.
- `src/` has been successfully renamed to `backend/`.

---

## Phase 9 — Search Scaling, Config Cache, and Runtime Cleanup

### Task
Make the current Tauri/Svelte + FastAPI system scale better and remove the remaining deferred technical debt.

### Planned
- Add deliberate config caching with safe invalidation when Settings writes `config.yaml`.
- Add a proper source URL normalization maintenance tool for existing databases.
- Reduce search hydration memory pressure with batching or a persistent index strategy.
- Optimize video embedding frame extraction.
- Resolve Svelte accessibility warnings.
- Consolidate remaining duplicate helper logic.
- [x] Rename `src/` to `backend/`.

---

## Phase 10 — Reverse Search & Provenance

### Task
Recover the "Exact Source" of orphan files using pHash-based reverse lookups and auto-filling missing metadata from online databases.

---

## Phase 11 — Modular Logic & Advanced Vision

### Task
Implement the **Strategy Pattern** for switchable deduplication algorithms and upgrade tiling to a **Sliding Window** system.

---

## Phase 12 — Security & Credential Hardening

### Task
Encrypt `.secrets.yaml` and `cookies.txt` at rest and implement improved credential isolation.

---

## Phase 13 — Maintenance & Vault Health

### Task
Implement "Orphan/Ghost" integrity checks and periodic SHA256 re-verification to detect bit-rot.

