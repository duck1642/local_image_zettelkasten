# LMZ Current Work

Working tracker for the first release, application-data migration, desktop polish,
and the next-generation similarity review system.

Status: `not started` | `in progress` | `blocked` | `done`

## Work order by implementation difficulty

Release priority is separate from difficulty: the `.lmz` data home and bootstrap remain P0.

| Difficulty | Release priority | Workstream | Status | Exit criteria |
| --- | --- | --- | --- | --- |
| Easiest | P2 | Application icon | completed | Final icon is exported into all required Tauri formats, visually approved, and checked in a packaged build. |
| Easy | P2 | Webview developer controls | done | App-wide config exists; Settings control context menu and developer tools; production defaults are safe. |
| Moderate | P2 | Settings and logs polish | not started | Settings layout/microcopy and logging interaction behavior are verified. |
| Moderate | P0 | Test baseline repair | in progress | Workspace cleanup tests run outside the protected project tree and config/runtime failure paths have regression coverage. |
| Moderate | P1 | Storage lifecycle follow-up | not started | Missing regression coverage and Windows lifecycle behavior are verified. |
| Hard | P0 | Release bootstrap validation | in progress | A clean installed build creates and opens a usable default workspace without relying on writable files in the app bundle. |
| Hard | P0 | Config and API boundary refactor | done | App-wide and workspace config have explicit schemas, storage, APIs, strict legacy rejection, and reliable frontend error handling. |
| Hard | P0 | Transactional runtime switching | not started | Workspace/vault switches use one preflight and lock, commit consistently, and completely restore services on failure. |
| Hard | P0 | Desktop sidecar hardening | not started | The desktop owns and identifies its backend; startup, shutdown, port conflicts, and extension authentication are safe. |
| Very hard | P0 | `.lmz` data-home and content adoption | done | The data-root contract, fresh-install bootstrap, content-only importer, and test plan are implemented and verified. |
| Hardest | P1 | Similarity-review architecture | not started | Model roles, persistence, candidate retrieval, review semantics, and migration path are specified. |

## Dependency-aware execution order

The difficulty table is not the implementation order. Follow this sequence to avoid
building new settings and release fixes on the current mixed config boundary.

1. Finalize the `.lmz` data-home, config ownership, importer, and sidecar-direction contracts.
2. Implement the data root, bootstrap, config repositories, schemas, APIs, and frontend stores together.
3. Align the test suite with the new architecture and add config/runtime failure-path coverage.
4. Build the packaged app and validate first launch with a clean user profile.
5. Implement Webview developer controls as the first vertical use of app-wide settings.
6. Make workspace and vault transitions transactional.
7. Harden desktop-sidecar startup, identity, ownership, shutdown, and extension authentication.
8. Complete storage lifecycle regressions and the real-vault Windows smoke gate.
9. Polish Settings and logs after their persistence and API boundaries are stable.
10. Run the final install, first-launch, restart, update, and reinstall release gate.
11. Continue similarity-review architecture after the first-release foundation is stable.

## 1. Application icon

### Candidate directions

- [x] Masonry Active Tile — uneven local-media tiles with one blue active tile. **Selected.**

### Delivery

- [x] Select a direction.
- [x] Produce a high-resolution source asset with a transparent canvas, one blue active tile, and three light-slate outlined tiles.
- [x] Export all required PNG, ICO, ICNS, Windows tile, Android, and iOS variants.
- [x] Visually verify and approve the icon in the debug Windows package.

### Validation

- [x] `npm run check` passes with zero errors and warnings.
- [x] Debug Tauri build completes and packages the Windows app.
- [x] Final icon committed in `1306b70` (`feat(icon): finalize masonry app icon`).

## 2. Webview developer controls

Dependency: do not persist these controls through the former workspace-scoped
`/api/config`. Implement them after the app-wide config repository and API exist.

- [x] Add a persisted Settings toggle for developer tools, default off.
- [x] Gate `Ctrl+Shift+I` and `F12` in Tauri/Rust behind that setting.
- [x] Add a separate persisted toggle for the webview context menu, default off.
- [x] Prevent browser print/navigation shortcuts in normal application mode.
- [x] Verify production packaging and release-default behavior.

## 3. Settings and logs polish

- [ ] Standardize Settings content width and responsive layout across all tabs.
- [ ] Simplify Settings terminology and dense microcopy, starting with `AI Tagging Engine`.
- [ ] Run a live local/online-ingestion log smoke test: streaming, Startup/Vault/Console source switching, and source-specific clearing.
- [ ] Review confirmation-modal focus management and toast/modal stacking.

## 4. Storage lifecycle follow-up

- [x] Isolate workspace-cleanup fixtures from the protected runtime/install root.
- [x] Re-run the workspace cleanup suite after repairing the fixture boundary; it now passes as part of the full backend suite.
- [ ] Add a direct regression test for WD repair: remove a stale wrong-shard cache, retain the canonical cache, and report a locked stale-cache cleanup failure.
- [x] Run the full backend suite: 270 passed, 1 skipped on 2026-07-11.
- [ ] Run a real-vault Windows smoke test covering locked files, staged-trash cleanup, and thumbnail/delete coordination.
- [ ] Decide whether LMZ must prevent multiple backend processes. If it does, enforce a singleton or add inter-process lifecycle coordination; the current lock pool protects one process only.

## 5. Release bootstrap validation

### Resolved issue

The former frozen-app path resolution used the executable directory as `PROJECT_ROOT`,
which made mutable config files depend on install-directory write access. The packaged
app now bootstraps the canonical `.lmz` data home atomically and leaves its install
directory unchanged.

### Work items

These are early diagnosis tasks. Final release acceptance runs only after the `.lmz` data home,
config/API, runtime-switch, and sidecar work is complete.

- [x] Collect the current packaged-build error/output and identify the exact first-run failure.
- [x] Reproduce with a clean Windows user-data profile and no pre-existing LMZ config.
- [x] Replace the temporary default-workspace fix with the strict data-home bootstrap.
- [x] Define a release acceptance test covering clean packaged first launch and restart; final installer update/reinstall coverage remains in the release gate.

### Acceptance checks

- [x] First launch succeeds with no existing LMZ data.
- [x] A default workspace is visible and can be opened.
- [x] The application does not need write access to its install directory.
- [x] Restart preserves workspace selection and user data.

### Latest validation evidence (2026-07-11)

- [x] Frozen sidecar rebuilt from the project venv with the new data-home modules.
- [x] Debug NSIS bundle created at `target/debug/bundle/nsis/LMZ_0.1.0_x64-setup.exe`.
- [x] Frozen sidecar created and loaded a clean isolated default workspace without writing beside the binary.
- [x] Packaged desktop reproduction found and fixed the first-run Tauri logger crash caused by opening `app/logs` before atomic bootstrap.
- [x] Re-run the fixed packaged desktop through clean first launch and restart using an isolated user-profile data root; both cycles loaded the same default workspace and left the install directory unchanged.
- [x] Final automated gates pass: 270 backend tests (1 skipped), 51 Playwright tests, zero Svelte/TypeScript diagnostics, and Python bytecode compilation.
- [x] Final packaged report: `C:\Users\Bilgisayar\lmz-packaged-app-first-launch-20260712-j\app\packaged-first-launch-report.json`.
- [ ] MSI packaging remains an environment issue: WiX ICE validation cannot access Windows Installer in the current session. NSIS packaging succeeds.

### Real-vault release gate

- [ ] Verify workspace creation, switching, relocation, config save, and recovery after a missing vault path.
- [ ] Verify vault maintenance and packages: audit/repair, backup, export, restore-to-new-vault, preview-first import, source unchanged, and resulting vault open.
- [ ] Verify one image/video ingest, review replacement/re-ingest, metadata-index consistency, thumbnail/tagging output, and App Logs under normal use.
- [ ] Decide whether the fixed local sidecar port is acceptable for v1; otherwise design the startup handshake, API-base, CSP, and lifecycle changes for dynamic ports.

## 6. `.lmz` data-home and content adoption

### Target data layout

```text
%USERPROFILE%\.lmz\
├── app\
│   ├── settings.yaml
│   ├── workspaces.yaml
│   ├── secrets\
│   ├── logs\
│   ├── models\
│   └── cache\
└── default\
    ├── config.yaml
    ├── data\
    ├── backups\
    └── exports\
```

The application bundle contains only immutable code, frontend assets, and the sidecar.
The live environment resolves from the OS home directory (`~/.lmz` cross-platform),
never from a hard-coded `C:\Users\<name>` path. `LMZ_DATA_ROOT` overrides the root for
development and tests. The dot prefix is a naming convention only; LMZ does not set
the Windows Hidden attribute, and uninstall never deletes `.lmz` automatically.

The built-in workspace uses `.lmz/default` to preserve path budget. External workspaces
remain user-selected and may live anywhere. Startup, launcher, sidecar, and app-wide
logs live under `app/logs`; workspace/vault operational logs remain with their vaults.

### Configuration ownership

- `app/settings.yaml`: every editable behavior choice, including UI, privacy blur, Webview controls, logging, network behavior, ingestion concurrency, accepted media, image processing, and complete tagging configuration.
- `app/workspaces.yaml`: registered workspace IDs, names, config paths, and active workspace selection.
- `<workspace>/config.yaml`: workspace/vault topology only: active vault, vault definitions, names, and roots.
- `settings.yaml` and `workspaces.yaml` remain separate and use independent schemas, versions, validation, backups, locking, and atomic writes.
- App-wide settings start from canonical fresh defaults; no values are imported from legacy workspace configs.
- SHA-256 is a code-level workspace-format invariant, not a setting. Changing the content-hash algorithm requires an explicit format migration.

### YAML schema contracts

`app/settings.yaml`:

```yaml
schema_version: 1
ui:
  vault_layout_mode: masonry
  vault_tile_min_width: 140
  inspector_visible: true
  inspector_width: 400
  privacy_blur: false
  ram_tracking_enabled: false
webview:
  devtools_enabled: false
  context_menu_enabled: false
logging:
  level: INFO
network:
  proxy: ""
  user_agent: "..."
ingestion:
  concurrency:
    global_max_workers: 10
    platforms: {}
  accepted_media:
    extensions: [.jpg, .jpeg, .png, .webp, .mp4]
    mime_types: [image/jpeg, image/png, image/webp, video/mp4]
  processing:
    flatten_transparency: true
    background_preset: white
    custom_color: [255, 255, 255]
tagging:
  enabled: true
  model_repo: SmilingWolf/wd-vit-tagger-v3
  device: auto
  display_source: yaml
  threshold: 0.35
  max_tags: 30
  fail_ingestion_on_error: false
  video:
    enabled: true
    frame_count: 5
    merge_min_frames: 2
    merge_high_confidence: 0.75
```

`app/workspaces.yaml`:

```yaml
schema_version: 1
active_workspace: default
workspaces:
  default:
    name: Default
    config_path: default/config.yaml
```

Relative registry paths resolve from `.lmz`; external workspace paths may be absolute.
Registry identity never authorizes deletion without the ownership marker.

`<workspace>/config.yaml`:

```yaml
schema_version: 1
active_vault: default
vaults:
  default:
    name: Default
    root: data/vaults/default
```

Vault roots remain workspace-relative and cannot escape the workspace.

### Schema behavior

- [x] Use strict Pydantic models as the canonical schemas and reject unknown fields.
- [x] Require `schema_version: 1`; known optional leaves may use canonical defaults.
- [x] Never replace malformed YAML or schema failures with silent defaults.
- [x] Generate missing app files only during first-run bootstrap.
- [x] Treat missing external workspace configs as errors.
- [x] Keep secrets and physical model/log locations out of settings files and the app-settings API response.

### Strict legacy-config behavior

- [x] Normal runtime loading rejects mixed-scope legacy workspace configs.
- [x] The launcher reports a clear unsupported-legacy-config state instead of a generic load failure.
- [x] Do not add an automatic converter, compatibility loader, or silent legacy cleanup.
- [x] Existing project-root data remains untouched until the user explicitly invokes content adoption.

### Recommended fresh-install flow

1. Resolve `%USERPROFILE%\.lmz` or `LMZ_DATA_ROOT`.
2. Create `app/` and `default/` from canonical schemas and defaults.
3. Generate fresh `settings.yaml`, `workspaces.yaml`, and `default/config.yaml`.
4. Create an empty default vault and set the default workspace active.
5. Launch the workspace selector/application without writing to the install directory.

### Explicit content-only importer

- [x] Detect old project-root data and offer an explicit import through `lmz-adopt-content`; never start automatically.
- [x] Refuse to merge when the final `.lmz` root already exists.
- [x] Build the complete target under a sibling `.lmz-migrating-<id>` staging root.
- [x] Generate fresh app settings, workspace registry, and workspace config from canonical schemas.
- [x] Extract only legacy vault topology: vault IDs, display names, roots, and active-vault selection. Ignore every legacy app-wide setting.
- [x] Copy workspace databases, topics, complete vault trees, backups, and exports.
- [x] Copy app secrets and downloaded models; start fresh app/startup logs.
- [x] Report ambiguous legacy `config/data/` content but never merge it automatically.
- [x] Copy SQLite databases through the SQLite backup mechanism and require `PRAGMA integrity_check` success.
- [x] Build and verify a full-hash manifest for durable copied files before cutover.
- [x] Atomically promote the staged root only after every validation passes.
- [x] Write a migration receipt under `app/` without secret values.
- [x] On failure, remove only the staging target; never modify or delete the source tree.

### Bootstrap and importer acceptance checks

- [x] Fresh install works without a bundled mutable config directory.
- [x] Existing project-root data is never silently moved, rewritten, or deleted.
- [x] Content adoption preserves durable workspace data while resetting all app-wide behavior to fresh defaults.
- [x] A failed or interrupted import leaves the old source usable and no partial `.lmz` active.
- [x] Legacy workspace configs are rejected during normal loading with a clear launcher state.
- [x] External workspaces remain supported.
- [x] Development and tests can run against an isolated data root.

## 7. Config and API boundary refactor

### Implemented boundary

- The former mixed `/api/config` contract and frontend config store are removed.
- App settings, runtime session, workspace registry, and workspace topology now have explicit owners.
- Strict repositories reject corruption and protect full-document writes with ETags, locks, backups, and atomic replacement.
- Privacy blur and the other editable app behaviors persist in `app/settings.yaml`.

### Work items

- [x] Define versioned `AppSettings`, `WorkspaceRegistry`, and `WorkspaceConfig` schemas with one canonical defaults source.
- [x] Add central repositories for validated reads, atomic updates, backups, locking, and explicit corruption errors.
- [x] Remove `GET/POST /api/config`; there is no public compatibility alias.
- [x] Add pre-runtime `GET/PUT /api/app/settings` for the complete typed settings document.
- [x] Return a content-based `ETag` from settings GET, require `If-Match` on PUT, and return `412 Precondition Failed` for stale writes.
- [x] Keep workspace and vault topology behind domain APIs; do not expose raw replacement of `workspaces.yaml` or workspace `config.yaml`.
- [x] Add `GET /api/runtime/session`; return `loaded: false` in launcher mode instead of injecting `_runtime` into settings.
- [x] Change frontend API helpers and config stores to reject failed HTTP responses and preserve unsaved state on failure.
- [x] Add stale-save/version-conflict handling and tests.
- [x] Replace the mixed frontend config store with separate app-settings and runtime-session stores.
- [x] Move privacy blur, all UI behavior, accepted-media policy, processing, and tagging into `app/settings.yaml`.
- [x] Replace backend `get_config()` consumers with explicit `get_app_settings()` or `get_workspace_config()` access.
- [x] Add parity tests proving generated defaults match the schemas and canonical template.

## 8. Transactional runtime switching

### Known gaps

- Direct `/api/workspaces/{id}/load` bypasses the switch preflight used by the active-workspace endpoint.
- Runtime services can activate before the registry commit; rollback restores the previous context without fully rehydrating its services.
- `LMZ_CONFIG_PATH` is removed before a switch succeeds.
- Vault create/delete/activate/relocate operations can commit filesystem or config changes before all later steps succeed.

### Work items

- [ ] Use one process-wide switch lock and one preflight path for every workspace/vault transition.
- [ ] Stage and validate the candidate context before exposing it globally.
- [ ] Define the registry, config, filesystem, and service commit order.
- [ ] Restore environment state, runtime context, search/index/watchdog services, and logging on every rollback path.
- [ ] Add failure-injection tests for registry/config writes, service hydration, relocation, create/delete, and concurrent switch/ingestion attempts.
- [ ] Persist recoverable cleanup work instead of returning a one-time pending path only.

## 9. Desktop sidecar hardening

### Known gaps

- The packaged sidecar and frontend assume fixed port `8000` without a backend identity/readiness handshake.
- The spawned child handle is not retained for explicit lifecycle ownership.
- A second app instance or unrelated listener can cause the frontend to connect to the wrong backend.
- CORS accepts every syntactically valid browser-extension origin, while the session-key endpoint exposes the mutation key.

### Work items

- [ ] Choose and document either singleton plus verified fixed-port ownership or a dynamic-port startup handshake.
- [ ] Pass backend identity/API-base information from Tauri to the frontend and align CSP rules.
- [ ] Add readiness timeout, clear launcher error reporting, crash detection, and explicit shutdown behavior.
- [ ] Restrict extension access to paired/approved clients and define key rotation/re-pairing behavior.
- [ ] Test first launch, second instance, occupied port, sidecar crash, stale API key, and app shutdown.

## 10. Similarity review system

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
| 2026-07-09 | Default workspace should live in AppData rather than the application bundle. | superseded | Replaced by the `%USERPROFILE%\.lmz` data-home decision on 2026-07-10. |
| 2026-07-09 | Developer tools should be user-switchable from Settings and default off. | proposed | `Ctrl+Shift+I` is the intended shortcut. |
| 2026-07-09 | Prototype CLIP/ResNet50 and cluster review are inputs to a refactored LMZ subsystem, not a direct copy. | proposed | ANN retrieval and model provenance are required for large vaults. |
| 2026-07-10 | Masonry Active Tile is the selected application icon. | decided | User-tuned geometry: one blue top-right tile with three light-slate outlined tiles on a transparent canvas; source lives under `frontend/src-tauri/icons/concepts-v3/`. |
| 2026-07-10 | Application icon work is complete. | done | User approved the debug build; generated platform assets and the work log were committed in `1306b70`. |
| 2026-07-10 | The data-home/config foundation must precede Webview developer controls. | decided | The former `/api/config` was workspace-scoped; app-wide toggles now use `.lmz/app/settings.yaml`. |
| 2026-07-10 | LMZ uses `%USERPROFILE%\.lmz` as its durable data home. | decided | `.lmz/app` owns app state; `.lmz/default` is the built-in workspace; `LMZ_DATA_ROOT` remains an override. |
| 2026-07-10 | App settings and the workspace registry remain separate. | decided | `settings.yaml` owns app behavior; `workspaces.yaml` owns registered paths and active selection. |
| 2026-07-10 | All editable ingestion, media-processing, and tagging behavior is app-wide. | decided | Workspace `config.yaml` contains only active-vault and vault topology; moving a workspace does not carry machine behavior. |
| 2026-07-10 | SHA-256 is a workspace-format invariant. | decided | The hash algorithm is removed from YAML and cannot be changed as an ordinary setting. |
| 2026-07-10 | `/api/config` is replaced by typed settings and runtime APIs. | decided | Use full-document `GET/PUT /api/app/settings` with ETag/If-Match and `GET /api/runtime/session`; topology remains behind workspace/vault domain APIs. |
| 2026-07-10 | Legacy mixed-scope configs are rejected during normal loading. | decided | App settings start fresh; no compatibility loader or config converter will be implemented. |
| 2026-07-10 | Old data uses explicit content-only adoption. | decided | Fresh configs are generated; topology and durable payloads are staged, verified, and copied without deleting the source. |
| 2026-07-10 | Release work follows dependency order rather than implementation difficulty. | decided | Finalize architecture, implement data/config foundations together, align tests, validate packaging, then continue remaining workstreams. |
| 2026-07-11 | The strict `.lmz` data/config boundary is implemented. | done | Backend suite: 270 passed, 1 skipped; frontend check/build and all 51 Playwright tests pass. |
| 2026-07-11 | Webview controls use app-wide settings. | done | Devtools and context menu default off; Ctrl+Shift+I/F12 are gated; browser print/navigation shortcuts are suppressed; the final debug package starts cleanly with safe defaults. |
| 2026-07-11 | Clean packaged `.lmz` first launch and restart pass. | done | Final debug desktop validation created the canonical data home in an isolated user-profile root, opened the default workspace twice, preserved data, and left the binary directory unchanged. |
