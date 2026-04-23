# LIZ — Architecture

## What LIZ is

Privacy-based local image/video archive system.

## Core Philosophy

- Simple to use
- Privacy first
- Everything local
- Gathers media from various platforms into one unified database
- Markdown/YAML support for Obsidian compatibility

## Core Architectural Principles

### Hash as filename
Every file is renamed to its SHA256 hash. Provides collision resistance, implicit deduplication, no naming conflicts, and deterministic lookup.

### SQLite over a full database
Lightweight, portable, no server required. Sufficient for local use.

### Obsidian as the viewer
Markdown support. Suitable for a zettelkasten-style vault.

### gallery-dl and yt-dlp instead of custom scrapers
Industry-standard tools. No need for custom scrapers.

---

## GUI Design Philosophy (Phase 8)

The LIZ Management GUI is built at the intersection of technical minimalism and fluid visual discovery.

### 1. Technical Minimalism (Opencode Aesthetic)
- **High-Contrast Dark Mode:** A data-first environment (#0d1117) designed for long curation sessions.
- **Snappy & Industrial:** Zero smooth animations or fading transitions. Every interaction is instantaneous to maintain a "Terminal-like" performance profile.
- **Unified Command Center:** A single search bar utilizing a **Prefix System** (`>`, `@`, `a:`, `#`) for both navigation and system commands.

### 2. Fluid Discovery (Pinterest Aesthetic)
- **Masonry Grid:** Assets maintain their natural aspect ratios in a responsive grid, preventing awkward cropping of Webtoons or panoramas.
- **Hover-Intelligence:** Live thumbnails that highlight and reveal SHA256 identities on hover for immediate feedback.

### 3. Asset Stewardship (Eagle.cool Aesthetic)
- **The Inspector:** A toggleable sidebar for direct editing of YAML frontmatter, ensuring assets remain structured Obsidian notes.
- **The Metadata Gate:** Drag-and-drop ingestion requires a **curation event** (mandatory metadata modal) to prevent the accumulation of "orphan" files.
- **Side-by-Side Triage:** Optimized "Visual Duel" view for managing duplicates with pHash distance metrics.

### 4. Power-User Workflow
- **Keyboard-First:** Deep support for shortcuts and prefix-based searching.
- **System Transparency:** A persistent **Status Bar** providing real-time metrics on DB health, logic state, and vault size.

---

## Data Flow

```
[Input]
  Local files → /input/
  External URLs → normal_pending_links.md (with integrity check)
                → force_pending_links.md   (bypass check)
        │
        ▼
[Ingestion]
  external_ingestion.py
  (gallery-dl / yt-dlp download to /input/)
        │
        ▼
[Validation]
  validators.py
  (MIME type check)
        │
        ▼
[Processing]
  processor.py
  (SHA256 hash generation)
        │
        ▼
[Fingerprinting]
  - Image: pHash (Perceptual Hash)
  - Video: Multi-Modal Signature (AI Semantic + Sonic)
        │
        ▼
[Storage]
  → vault/output/assets/{hash[:2]}/{hash}.ext (media file, sharded)
  → vault/input/review/                       (Duplicate quarantine)
  → db/sqlite_operator.py                     (SQLite index with Signatures)
  → md_generator.py                           (companion .md)
  → vault/output/notes/{hash}.md              (markdown file)
        │
        ▼
[Cleanup/Logging]
  delete_source parameter (removes original from /input/)
  failed_links.md (logs URLs that failed or partially failed)
```

---

## Module Responsibilities

```
program/
├── main.py                     # Root entry point (CLI)
├── gui.py                      # Root entry point (Management GUI)
├── auth_cookies.py             # Wrapper → scripts/auth_cookies_builder.py
├── auth_pixiv.py               # Pixiv auth (default: auto via Playwright, --manual: OAuth PKCE)
├── query.py                    # SQLite query CLI (uses WAL mode via sqlite_operator)
├── maintanance/                # Utility and helper scripts
│   ├── generate_test_data.py   # Generates test images
│   ├── generate_test_videos.py # Generates test videos
│   ├── manage_review.py        # Manual review manager for duplicates (CLI)
│   ├── reset_db.py             # Wrapper → scripts/reset_db.py
│   ├── retry_failed.py         # Moves URLs from failed_links.md back to normal_pending_links.md
│   └── update_tools.py         # Wrapper → scripts/update_downloaders_and_regenerate_notes.py
├── docs/                       # ⚠️ Docs are at project root, not inside program/
├── normal_pending_links.md     # URL ingestion queue (with Integrity Gate size check)
├── force_pending_links.md      # URL ingestion queue (bypasses size check)
├── failed_links.md             # Persistent log for failed/partial ingestions
├── cookies.txt                 # ⛔ Auth credentials (DO NOT TOUCH)
├── liz/                        # Core package
    ├── __init__.py
    ├── config.yaml             # Non-sensitive config
    ├── .secrets.yaml           # ⛔ Sensitive credentials
    ├── core.py                 # Main orchestrator
    ├── processor.py            # File processing pipeline (MIME-First Validation)
    ├── fingerprint.py          # Multi-Modal Signatures (CLIP + Sonic)
    ├── external_ingestion.py   # URL → download → process pipeline
    ├── md_generator.py         # Obsidian markdown note generator
    ├── utils.py                # Paths, config loader, hash function
    ├── validators.py           # MIME type detection & validation
    ├── ui/                     # Phase 8: Management GUI (PySide6/QWidgets)
    │   ├── __init__.py
    │   ├── app.py              # PySide6 App Shell & Navigation
    │   └── views/              # View Components (Vault, Review, Settings, Ingestion)
    ├── db/
    │   ├── __init__.py
    │   ├── sqlite_operator.py  # All SQLite CRUD interactions
    │   ├── searchers.py        # BK-Tree & VPTreeSearcher (RAM); FlatVectorSearcher (unused/kept for reference)
    │   ├── search_manager.py   # RAM index orchestrator (Hydration)
    │   └── liz_main.db         # SQLite database
    ├── downloaders/
    │   ├── __init__.py
    │   ├── gallery_dl_wrapper.py  # gallery-dl subprocess wrapper
    │   └── yt_dlp_wrapper.py      # yt-dlp subprocess wrapper
    ├── logs/
    │   ├── __init__.py
    │   └── logger.py           # Thread-safe JSONL logger (System & Activity)
    ├── scripts/
    │   ├── __init__.py
    │   ├── auth_cookies_builder.py  # Interactive Netscape cookie builder
    │   ├── auth_pixiv.py            # Manual Pixiv OAuth PKCE flow
    │   ├── auth_pixiv_auto.py       # Playwright-based auto Pixiv auth
    │   ├── update_downloaders_and_regenerate_notes.py  # pip update for yt-dlp/gallery-dl + regenerate_markdowns() vault repair
    │   ├── migrate_signatures.py    # Re-calc audio/visual signatures for existing vault items (Phase 6 migration)
    │   └── reset_db.py              # Wipe DB + vault contents
    ├── vault/
    │   ├── activity.jsonl      # Machine-readable vault ledger
    │   ├── assets/             # Media files (hash-named, sharded by prefix)
    │   └── notes/              # Companion markdown files
    └── input/
        └── external/           # Temp download staging area
```

### `core.py` — Main Orchestrator
- **Role:** Unified entry point. Orchestrates both External Ingestion and Local Ingestion.
- **Input:** `INPUT_DIR`, `pending_links.md`
- **Output:** Console logs, progress updates, final summary.
- **Key Features:** Skips `.md`, `.json`, `.txt` files during local scan. Cleans up empty parent directories after processing.

### `processor.py` — The Pipeline
- **Role:** Full 7-step pipeline: MIME Check → Extension Check → Hash → Dedup → Move & Rename → Index in DB → Generate Markdown → Log.
- **Input:** Raw file path, metadata dict, config dict.
- **Output:** `Tuple[bool, str]` — success flag and status message.
- **Key Features:**
  - **MIME-First Validation:** Checks `python-magic` signature before extension.
  - Normalizes `.jfif` and `.jpeg` to `.jpg`.
  - Captures file size *before* deletion (defensive coding).
  - **Atomic Rollback:** Deletes copied media and markdown if database insertion fails. Transaction only committed on full pipeline success.
  - Dynamically reads `allowed_exts` and `allowed_mimes` from `config.yaml`.

### `fingerprint.py` — Multi-Modal Signatures
- **Role:** Generates binary signatures for fuzzy matching.
- **Key Features:**
  - **Silence Guard:** Uses `volumedetect` to ignore silent tracks (below -60dB) to prevent false sonic matches.
  - **Raw Sonic:** Extracts raw integer Chromaprints for bitwise Hamming comparison.
  - **5-Point CLIP:** Samples 5 frames (10%, 30%, 50%, 70%, 90%) for robust temporal visual signatures.

### `external_ingestion.py` — URL Router
- **Role:** Handles lifecycle of external links: parsing, duplicate URL checking, platform routing, pipeline integration.
- **Input:** `pending_links.md`
- **Output:** Routes downloaded files to `processor.py`, writes failures to `failed_links.md`.
- **Key Features:**
  - Markdown link syntax supported.
  - **Persistent Failure Tracking:** Records permanent and partial failures in `failed_links.md` with timestamps and reasons.
  - **Retry Logic:** Attempts download up to 2 times before skipping.

### `utils.py` — Foundation
- **Role:** Path constants, configuration loading, secrets loading, directory setup, file hashing.
- **Input:** `config.yaml`, `.secrets.yaml`, base directory path.
- **Output:** Absolute paths, SHA256 hashes, merged config+secrets dictionary.
- **Key Features:**
  - **Dynamic Path Resolution:** Resolves `INPUT_DIR`, `VAULT_DIR`, `DB_PATH`, `LOGS_DIR` from `config.yaml` at module load time for full portability.
  - Validates `config.yaml` schema before execution.
  - Loads credentials from `.secrets.yaml` via `load_secrets()` and merges into `external_tools` at runtime.

### `validators.py` — Firewall
- **Role:** Validates file type.
- **Input:** Filepath.
- **Output:** MIME type string, boolean allowlist check.
- **Key Features:** Identifies file type via `python-magic` with fallback to extension mapping.

### `downloaders/` — Wrappers
- **Role:** Executes CLI tools, handles authentication, extracts structured metadata.
- **`gallery_dl_wrapper.py`:** Two-pass (metadata JSON → actual download). Excludes `.part`/`.zip`. Rewrites `x.com` to `twitter.com`.
- **`yt_dlp_wrapper.py`:** Video metadata extraction and download. Uses `rglob('*')` to capture media in subfolders.
- **Key Features:** Both use `get_cookie_path()` for dynamic relative pathing and have strict `session_dir` isolation to prevent zombie folders.

### `db/sqlite_operator.py` — Database Engine
- **Role:** All SQLite CRUD interactions: schema creation, duplicate checking, record inserts.
- **Input:** Database path, SHA256 hashes, file metadata.
- **Output:** SQLite connection objects, boolean duplicate flags.
- **Key Features:**
  - **Transaction Safety:** `insert_to_database` does not commit automatically — caller (`processor.py`) manages the transaction lifecycle for atomicity.
  - `INSERT OR REPLACE` handles re-ingestion without creating duplicates.
  - `LOWER()` for case-insensitive URL duplicate checking.
  - `timeout=5` (seconds) and `PRAGMA journal_mode=WAL` for concurrent thread access without locking.

### `db/search_manager.py` — RAM Index Orchestrator
- **Role:** Singleton manager for in-memory search structures.
- **Key Features:**
  - **Hydration:** Loads signatures into RAM at startup.
  - **Voter Logic:** Aggregates Sonic and Semantic matches to identify "High Confidence" double-matches.
  - **Standardized Similarity:** Returns 0.0 to 1.0 scores for all fuzzy sensors.

### `db/searchers.py` — Metric Search Engines
- **Role:** Specialized data structures for fuzzy matching.
- **Key Features:**
  - **BK-Tree:** Discrete metric space for pHash (Hamming distance).
  - **VPTreeSearcher:** High-dimensional metric space for AI vectors and raw Chromaprints (Cosine and Bitwise Hamming). Active and used by `search_manager.py`.
  - **FlatVectorSearcher:** Alternative flat-matrix searcher using vectorized dot products. **Currently unused** — kept in codebase as a reference implementation.
  - **URL Registry:** $O(1)$ RAM lookup for ingested URLs.

### `logs/logger.py` — Flight Recorder
- **Role:** Dual-stream thread-safe logging.
- **Input:** Event metadata, error strings, ingestion records.
- **Output:** `system.log` (structured JSON diagnostics) and `vault/activity.jsonl` (activity ledger).
- **Key Features:**
  - JSON Lines format — each entry is a valid JSON object on a single line.
  - Thread-safe via internal locking.
  - Log rotation at 5MB to prevent disk bloat.

### `md_generator.py` — Note Builder
- **Role:** Generates markdown files with YAML frontmatter.
- **Input:** SQLite connection, file hash, optional `asset_rel_path` for shard-aware linking.
- **Output:** Markdown string with media embed.
- **Key Features:** Includes `topics: ""` placeholder for human tagging in Obsidian. Reads `date_added` from DB with fallback to `datetime.now()`.

### `scripts/` — Maintenance & Auth
- **Role:** Manual/scheduled system tasks.
- **Key Scripts:**
  - `auth_cookies_builder.py`: Interactive Netscape cookie builder (targets `.secrets.yaml`).
  - `auth_pixiv_auto.py`: Playwright headless=false interception.
  - `reset_db.py`: Wipes DB and vault for a clean start.

---

## Key Technical Decisions

**MIME-First Validation via python-magic**
Every file is validated by its internal binary signature (magic numbers) using the industry-standard `libmagic` engine (via `python-magic`). This is significantly more reliable than manual byte-level header checks, as it performs deep structural analysis to prevent malicious files from being masqueraded as media through simple extension changes.

**SHA256 content-addressable storage**
Files renamed to their SHA256 hash. Provides collision resistance, implicit deduplication, no naming conflicts, deterministic lookup.

**SQLite with WAL Mode**
Lightweight, portable, no server required. `PRAGMA journal_mode=WAL` and connection timeouts allow concurrent reads/writes without "database locked" errors.

**Atomic Transactions**
Database records only committed after the media file is safely copied to the vault and the Markdown note is written. Any failure triggers a rollback, preventing orphaned DB records that would block future re-ingestion.

**Dynamic Configuration Paths**
All critical paths resolved dynamically against `config.yaml`. Allows vault or DB to be moved to different drives without modifying source code.

**Persistent Failure Logging**
Any URL that fails to process is recorded in `failed_links.md` with a reason and timestamp. No data lost during large batch runs.

**Credential Separation via `.secrets.yaml`**
Sensitive credentials (`pixiv_token`, `cookies_path`) stored separately from `config.yaml`. `utils.load_secrets()` loads and merges them at runtime. Isolates secrets from non-sensitive config and prepares for future encryption at rest.

**Playwright for Pixiv Auth**
3-layer network interception (request, response, route) to capture OAuth tokens automatically. Eliminates brittle manual F12 extraction.

**Structured JSONL Logging**
JSON Lines format provides machine-readability for the query CLI, prevents file corruption during crashes, supports high-concurrency writing via thread-safe handlers.

**Phase 6: RAM-Based Search Hydration**
At startup, pHashes and URLs are loaded from SQLite into memory (BK-Trees and Sets). This drops search time from $O(N)$ linear scans to $O(\log N)$ or $O(1)$, enabling the vault to scale to 1M+ items without performance degradation.

**delete_source parameter**
Centralized cleanup logic in `processor.py` rather than scattered delete calls. Prevents orphaned files on pipeline failure.

---

## Database Schema

**Table: `items`**
| Column | Type | Description |
|--------|------|-------------|
| `hash` | TEXT (PK) | SHA256 hash of file content. Primary key. |
| `original_filename` | TEXT | Original filename at time of ingestion. |
| `file_extension` | TEXT | Normalized extension (e.g., `.jpg`, `.mp4`). |
| `mime_type` | TEXT | Validated MIME type (e.g., `image/jpeg`). |
| `size_bytes` | INTEGER | File size in bytes. |
| `date_added` | DATETIME | Timestamp of ingestion (DEFAULT CURRENT_TIMESTAMP). |
| `source_url` | TEXT | Original URL (if from gallery-dl/yt-dlp). |
| `platform` | TEXT | Source platform (e.g., `pixiv`, `twitter`). |
| `source_artist` | TEXT | Creator/Artist name from metadata at download time. |
| `phash` | TEXT | Perceptual Hash (images). |
| `audio_hash` | BLOB | Raw Chromaprint integer array (videos). |
| `visual_embedding` | BLOB | 512-dimension AI vector (videos). |

**Index:** `CREATE INDEX idx_source_url ON items(source_url)` — drops URL duplicate checking from $O(N)$ to $O(\log N)$. ✅ Implemented in Phase 6.

**Table: `item_tiles` — Fragment-to-Whole Support**
| Column | Type | Description |
|--------|------|-------------|
| `parent_hash` | TEXT (FK) | References `items(hash)`. |
| `tile_index` | INTEGER | Index of the tile within the original strip. |
| `tile_phash` | TEXT | Perceptual Hash of the specific tile. |

**Constraint:** `UNIQUE(parent_hash, tile_index)` — prevents duplicate tile records on re-ingestion.

---

## Known Technical Debt

- `.secrets.yaml` is plaintext — encryption at rest planned for a future phase

---

## Testing & Validation

Run these checks after major modifications:

1. **Static Analysis:** `flake8 --select=E9,F821,F822,F823,E112,E113,E101,E999 program/`
2. **Compilation Check:** `python3 -m compileall program/`
3. **Security Audit:** `bandit -r program/liz/ -ll`
4. **Runtime Initialization:** `python3 -c "import liz.core, liz.processor, liz.external_ingestion, liz.utils, liz.db.sqlite_operator"`
5. **Database Health:** `python3 query.py stats`

---

## Last Updated
Phase 8 — Management GUI 
