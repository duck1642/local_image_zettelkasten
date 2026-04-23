# LIZ — Current Status

## Phase 8 — Management GUI ✅ (Completed & Verified)
### Current Focus
1.  **Tagging Ontology:** Implementing local AI feature extraction (WD Tagger + Local-LLM) to transform the vault into a Knowledge Graph.
2.  **Reverse Search:** Recovering exact sources for orphan files via pHash reverse lookups.

### Decision Log

#### Completed & Verified (Phase 8)
- **Management Center:** Implemented a full, snappy PySide6/QWidgets-based GUI (`gui.py`) following the "Opencode" high-contrast dark mode aesthetic.
- **Dynamic Vault Selection:** Added a PySide6/QWidgets `FilePicker` dialog to dynamically select a unified Vault folder on startup if not present in `config.yaml`.
- **Universal Drag & Drop Ingestion:** Replaced planned `.json` sidecars for primary ingestion with an interactive `ManualIngestionModal`. Strict curation enforced by requiring the `Artist` field. 
- **Quarantine / Review System:** Visual side-by-side duplicate duel mode with pHash distance metrics correctly utilizing `.json` sidecars for state tracking.
- **Power-User Search:** Unified command center with prefix routing (`>`, `@`, `a:`, `#`).
- **Dynamic Configuration:** Extracted GUI prefix configurations into `config.yaml` for customizability.
- **Metadata Extraction Polish:** Rewrote the `_extract_artist` logic for X, Pixiv, Instagram, and Pinterest to robustly parse nested dictionaries and string representations.
- **Maintenance Restructuring:** Consolidated `generate_test_data.py`, `generate_test_videos.py`, `manage_review.py`, `retry_failed.py`, `reset_db.py`, and `update_tools.py` into a single `maintanance/` folder for better organization. Addressed security warnings (e.g. SHA-256 for URLs).

#### Done (Previous Phases)
- **Audit Remediation:** All 24 issues identified in the LIZ Audit Report (Bugs, Logic, Quality) have been implemented and verified.
- **The Integrity Gate:** Strict (Image) vs Relaxed (Video) size validation logic implemented in `external_ingestion.py`.
- **Session Atomicity:** Guaranteed that multi-file posts are rejected as a unit if any single file fails validation.
- **RAM Index Sync Hardening:** Wrapped batch sync in `try-except` to ensure link write-back persists even during memory errors.


#### Pending / Next Steps (Phase 9+)
- 🚩 **Tagging Ontology:** WD Tagger + Local-LLM pipeline.
- 🚩 **Reverse Search & Provenance:** pHash-based reverse lookup for missing metadata.
- 🚩 **Security:** Encryption for `.secrets.yaml`.