# LMZ Current Work

Working tracker for the first release, application-data migration, desktop polish,
and the next-generation similarity review system.

Status: `not started` | `in progress` | `blocked` | `done`

## Work order by implementation difficulty

Release priority is separate from difficulty: AppData and bootstrap remain P0.

| Difficulty | Release priority | Workstream | Status | Exit criteria |
| --- | --- | --- | --- | --- |
| Easiest | P2 | Application icon | in progress | A selected source icon is exported into all required Tauri formats and checked in a packaged build. |
| Easy | P2 | Webview developer controls | not started | Settings control context menu and developer tools; production defaults are safe. |
| Moderate | P2 | Settings and logs polish | not started | Settings layout/microcopy and logging interaction behavior are verified. |
| Moderate | P1 | Storage lifecycle follow-up | not started | Missing regression coverage and Windows lifecycle behavior are verified. |
| Hard | P0 | Release bootstrap validation | not started | A clean installed build creates and opens a usable default workspace without relying on writable files in the app bundle. |
| Very hard | P0 | AppData workspace design and migration | not started | The data-root contract, fresh-install bootstrap, legacy migration, and test plan are agreed. |
| Hardest | P1 | Similarity-review architecture | not started | Model roles, persistence, candidate retrieval, review semantics, and migration path are specified. |

## 1. Application icon

### Candidate directions

- [x] Masonry Active Tile — uneven local-media tiles with one blue active tile. **Selected.**

### Delivery

- [x] Select a direction.
- [x] Produce a high-resolution source asset with a transparent canvas, one blue active tile, and three light-slate outlined tiles.
- [x] Export all required PNG, ICO, ICNS, Windows tile, Android, and iOS variants.
- [ ] Visually verify the icon after installing or running the debug Windows package.

## 2. Webview developer controls

- [ ] Add a persisted Settings toggle for developer tools, default off.
- [ ] Gate `Ctrl+Shift+I` in Tauri/Rust behind that setting.
- [ ] Add a separate persisted toggle for the webview context menu, default off.
- [ ] Prevent browser print/navigation shortcuts in normal application mode.
- [ ] Verify production packaging and release-default behavior.

## 3. Settings and logs polish

- [ ] Standardize Settings content width and responsive layout across all tabs.
- [ ] Simplify Settings terminology and dense microcopy, starting with `AI Tagging Engine`.
- [ ] Run a live local/online-ingestion log smoke test: streaming, Startup/Vault/Console source switching, and source-specific clearing.
- [ ] Review confirmation-modal focus management and toast/modal stacking.

## 4. Storage lifecycle follow-up

- [ ] Add a direct regression test for WD repair: remove a stale wrong-shard cache, retain the canonical cache, and report a locked stale-cache cleanup failure.
- [ ] Run the full backend suite and a real-vault Windows smoke test covering locked files, staged-trash cleanup, and thumbnail/delete coordination.
- [ ] Decide whether LMZ must prevent multiple backend processes. If it does, enforce a singleton or add inter-process lifecycle coordination; the current lock pool protects one process only.

## 5. Release bootstrap validation

### Known issue

The current frozen-app path resolution uses the executable directory as `PROJECT_ROOT`.
The default workspace and workspace registry therefore expect mutable `config/` files
next to the installed application. That is unsafe for installed applications and may
fail when the install directory is not writable.

### Work items

- [ ] Collect the current packaged-build error/output and identify the exact first-run failure.
- [ ] Reproduce with a clean Windows user-data profile and no pre-existing LMZ config.
- [ ] Review the existing temporary default-workspace fix.
- [ ] Define a release acceptance test covering install, first launch, restart, update, and uninstall/reinstall.

### Acceptance checks

- [ ] First launch succeeds with no existing LMZ data.
- [ ] A default workspace is visible and can be opened.
- [ ] The application does not need write access to its install directory.
- [ ] Restart preserves workspace selection and user data.

### Real-vault release gate

- [ ] Verify workspace creation, switching, relocation, config save, and recovery after a missing vault path.
- [ ] Verify vault maintenance and packages: audit/repair, backup, export, restore-to-new-vault, preview-first import, source unchanged, and resulting vault open.
- [ ] Verify one image/video ingest, review replacement/re-ingest, metadata-index consistency, thumbnail/tagging output, and App Logs under normal use.
- [ ] Decide whether the fixed local sidecar port is acceptable for v1; otherwise design the startup handshake, API-base, CSP, and lifecycle changes for dynamic ports.

## 6. AppData workspace migration

### Target data layout

```text
%LOCALAPPDATA%\LMZ\
├── state\workspaces.yaml
├── workspaces\default\
├── models\
├── logs\
└── secrets\
```

The application bundle contains immutable code, frontend assets, the sidecar, and an
optional default-workspace template. It does not contain the live default workspace.

### Design decisions to make

- [ ] Confirm the Windows data root and its cross-platform equivalent.
- [ ] Decide whether to use a Python platform-directory library or a Tauri-provided data-root environment variable.
- [ ] Define which data is application-scoped: registry, logs, models, credentials, and API key.
- [ ] Migrate the app-global downloader credentials and `secrets/.api_key` without exposing secret values; browser-extension users need a clear re-pairing/rotation path if the API key changes.
- [ ] Define which data is workspace-scoped: vaults, databases, notes, derived media data, queues, and review data.
- [ ] Decide how legacy project-root default data is handled: offer copy migration, leave in place, or both.
- [ ] Define failure/rollback behavior for an interrupted migration.
- [ ] Keep `LMZ_DATA_ROOT` as a development and test override.

### Recommended fresh-install flow

1. Resolve the application-data root.
2. Create the state and default-workspace directories if missing.
3. Materialize the default-workspace template into AppData.
4. Create/update the AppData registry and set `default` active.
5. Launch the workspace selector/application.

### Migration acceptance checks

- [ ] Fresh install works without a bundled mutable config directory.
- [ ] Existing project-root data is never silently moved or deleted.
- [ ] Legacy data can be detected and migrated safely.
- [ ] External workspaces remain supported.
- [ ] Development and tests can run against an isolated data root.

## 7. Similarity review system

### Existing LMZ behavior

- Images: SHA-256 exact match, pHash, and tile pHash candidates.
- Videos: audio fingerprint plus CLIP-derived visual embedding.
- Review: pair-based pending-review workflow.

### Prototype reviewed

Source: `F:\ARCHIVE\main\software\python\snippets\media_similarity_checker`

- [x] SHA-256 and pHash scan path.
- [x] ResNet50 and CLIP image embeddings, lazy loaded with CUDA detection.
- [x] Cached embeddings in SQLite.
- [x] Basic connected-component cluster review.
- [x] Cluster decisions converted to pair decisions.
- [x] Execution conflict guard for contradictory keep/remove decisions.
- [ ] Prototype tests re-run in an environment with an accessible pytest temp directory.

### Constraints before LMZ integration

- [ ] Do not treat semantic CLIP similarity as evidence for automatic deletion.
- [ ] Store model ID, vector dimension, dtype, normalization/version, and generation time with every embedding.
- [ ] Preserve raw model scores; do not reduce all evidence to one integer distance.
- [ ] Allow multiple algorithms to contribute evidence simultaneously.
- [ ] Replace dense all-pairs embedding comparison with approximate-nearest-neighbor candidate retrieval before reranking.
- [ ] Define model-specific thresholds and a calibration dataset.
- [ ] Define backfill, cancellation, progress, resource limits, and failure behavior.

### Proposed evidence roles

| Evidence | Role |
| --- | --- |
| SHA-256 | Exact duplicate; safe automatic rejection during ingestion. |
| pHash / wHash / tiles | Cheap near-duplicate candidate generation. |
| ResNet50 or DINO-style embeddings | Visual-neighbor candidates and possible duplicate reranking. |
| CLIP / SigLIP | Semantic grouping only; manual cluster review. |
| LPIPS / ORB / SIFT | Optional second-pass verification for selected candidates, crops, or repost variants. |

### Cluster-review rules

- [ ] A cluster is a navigation and review aid, not a claim that every member is mutually duplicate.
- [ ] Similarity edges retain their algorithm and score evidence.
- [ ] Keep/remove choices remain reversible until the explicit execution step.
- [ ] The execution layer continues to block conflicting file intents.
- [ ] Semantic and duplicate-oriented clusters are visibly separated in the UI.

## Decisions log

| Date | Decision | Status | Notes |
| --- | --- | --- | --- |
| 2026-07-09 | Default workspace should live in AppData rather than the application bundle. | proposed | Requires the migration contract above before implementation. |
| 2026-07-09 | Developer tools should be user-switchable from Settings and default off. | proposed | `Ctrl+Shift+I` is the intended shortcut. |
| 2026-07-09 | Prototype CLIP/ResNet50 and cluster review are inputs to a refactored LMZ subsystem, not a direct copy. | proposed | ANN retrieval and model provenance are required for large vaults. |
| 2026-07-10 | Masonry Active Tile is the selected application icon. | decided | User-tuned geometry: one blue top-right tile with three light-slate outlined tiles on a transparent canvas; source lives under `frontend/src-tauri/icons/concepts-v3/`. |
