# LMZ Current Work

Working tracker for the first release, application-data migration, desktop polish,
and the next-generation similarity review system.

Status: `not started` | `in progress` | `blocked` | `done`

## Work order by implementation difficulty

This table is retained as the delivery record. Remaining Settings/similarity
items are post-v1 work and do not block `1.0.0`.

| Difficulty | Release priority | Workstream | Status | Exit criteria |
| --- | --- | --- | --- | --- |
| Easiest | P2 | Application icon | completed | Final icon is exported into all required Tauri formats, visually approved, and checked in a packaged build. |
| Easy | P2 | Webview developer controls | done | App-wide config exists; Settings control context menu and developer tools; production defaults are safe. |
| Moderate | Post-v1 | Settings and logs polish | not started | Settings layout/microcopy and logging interaction behavior are verified. |
| Moderate | P0 | Test baseline repair | done | Workspace cleanup tests run outside the protected project tree and config/runtime failure paths have regression coverage. |
| Moderate | P1 | Storage lifecycle follow-up | done | Missing regression coverage and Windows lifecycle behavior are verified. |
| Hard | P0 | Release bootstrap validation | done | A clean installed build creates and opens a usable default workspace without relying on writable files in the app bundle. |
| Hard | P0 | Config and API boundary refactor | done | App-wide and workspace config have explicit schemas, storage, APIs, strict legacy rejection, and reliable frontend error handling. |
| Hard | P0 | Transactional runtime switching | done | Workspace and vault transitions share preflight/locking, commit consistently, and restore services on failure. |
| Hard | P0 | Desktop sidecar hardening | done | The desktop owns and identifies its backend; startup, shutdown, and port conflicts are safe. Browser-extension work is deferred to `docs/deferred_works.md`. |
| Very hard | P0 | `.lmz` data-home and content adoption | done | The data-root contract, fresh-install bootstrap, content-only importer, and test plan are implemented and verified. |
| Hardest | Post-v1 | Similarity-review architecture | not started | Model roles, persistence, candidate retrieval, review semantics, and migration path are specified. |

## Dependency-aware execution order

The difficulty table was not the implementation order. The release followed
this dependency sequence so later work did not build on the former mixed-config
boundary.

1. Finalize the `.lmz` data-home, config ownership, importer, and sidecar-direction contracts.
2. Implement the data root, bootstrap, config repositories, schemas, APIs, and frontend stores together.
3. Align the test suite with the new architecture and add config/runtime failure-path coverage.
4. Build the packaged app and validate first launch with a clean user profile.
5. Implement Webview developer controls as the first vertical use of app-wide settings.
6. Make workspace and vault transitions transactional.
7. Harden desktop-sidecar startup, identity, ownership, and shutdown.
8. Complete storage lifecycle regressions and the real-vault Windows smoke gate.
9. Polish Settings and logs after their persistence and API boundaries are stable.
10. Run the final install, first-launch, restart, update, and reinstall release gate.
11. Continue similarity-review architecture after the first-release foundation is stable.

Browser-extension work is intentionally outside this active release sequence;
track it in `docs/deferred_works.md`.

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
- [x] Add a direct regression test for WD repair: remove a stale wrong-shard cache, retain the canonical cache, and report a locked stale-cache cleanup failure.
- [x] Run the full backend suite: 270 passed, 1 skipped on 2026-07-11.
- [x] Run a real-vault Windows smoke test covering locked files, staged-trash cleanup, and thumbnail/delete coordination.
- [x] Remove stale generated vault artifacts with the scoped performance cleanup utility; the synthetic-vault generator now validates its output through the strict `WorkspaceConfig` schema.
- [x] Prevent multiple desktop-owned backends with the Goal B owner mutex and fixed-port lifecycle.

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
- [x] Classify MSI/WiX as a non-blocking environment limitation; v1.0.0 ships NSIS-only.

### Real-vault release gate

- [x] Verify workspace creation, switching, relocation, config save, and recovery after a missing vault path.
- [x] Verify vault maintenance and packages: audit/repair, backup, export, restore-to-new-vault, preview-first import, source unchanged, and resulting vault open.
- [x] Verify one image/video ingest, review replacement/re-ingest, metadata-index consistency, thumbnail/tagging output, and App Logs under normal use.
- [x] Accept fixed local port `8000` for v1 with verified ownership, identity, CSP/API alignment, and shutdown behavior.

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
- [x] Add an existing-target adoption mode that preserves app settings, workspace registry, app logs/cache, and secrets while swapping only staged workspace/models payloads.
- [x] Migrate the real project-root `data/` payload into `%USERPROFILE%\.lmz` with a sibling rollback backup; leave the source tree untouched.
- [x] Validate the migrated default vault: 166 items, zero missing required files, zero hash mismatches, zero stale index rows, and zero review mismatches.
- [x] Convert the real external `obsidian-main` workspace config in place with a legacy backup and register it without moving its vault data or touching secrets.
- [x] Keep generated `test-workspace` unregistered until it is explicitly identified as user-owned.

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

- Workspace switching now uses one process-wide lock/preflight path for both load APIs, stages the candidate before activation, and fully rehydrates the previous runtime on rollback. Focused failure-injection coverage is in `test_startup_refactor.py`.
- Vault create/delete/activate/relocate now share the A1 lock/preflight and
  transaction snapshot. Failed config, hydration, promotion, or cleanup paths
  restore the prior vault state; delete cleanup can remain explicitly pending.

### Work items

- [x] Use one process-wide switch lock and one preflight path for every workspace load API.
- [x] Stage and validate the candidate workspace context before activation.
- [x] Define and document the workspace registry, environment, runtime, search, metadata, and logging commit order.
- [x] Restore environment state, runtime context, search/index/watchdog services, and logging on workspace-load rollback.
- [x] Add workspace-load failure-injection and concurrent-switch tests; Goal A2 retains relocation/create/delete coverage.
- [x] Extend the same transaction protocol to active-vault, create, delete, and relocation transitions.
- [x] Defer persistent recovery of pending cleanup work to the post-v1 tracker;
  v1 retains and reports the pending path without hiding the cleanup failure.

### A2 commit protocol

1. Acquire the shared process-wide transition lock and run ingestion/metadata
   preflight.
2. Snapshot the exact workspace config bytes, registry, environment, runtime
   context, and affected filesystem paths.
3. Stage and validate candidate config/filesystem state.
4. Hydrate candidate runtime services before replacing durable config when the
   transition changes the active vault.
5. Commit config, registry, and environment in a documented order; purge delete
   staging only after config commit, otherwise retain an explicit pending path.
6. On failure, restore filesystem/config first, then fully rehydrate the prior
   runtime and logging state.

## 9. Desktop sidecar hardening

### Current status

- The packaged sidecar now carries a per-launch nonce and exposes a local identity/readiness response at `GET /api/runtime/health`.
- Tauri claims one fixed-port desktop owner, retains the sidecar child, verifies the exact nonce before frontend API use, and terminates the owned process tree on exit.

### Work items

- [x] Choose and document singleton plus verified fixed-port ownership; dynamic ports remain deferred.
- [x] Pass backend identity/readiness state from Tauri to the frontend and align API base, Vite proxy, and CSP rules.
- [x] Add readiness timeout, clear launcher error reporting, crash detection, and explicit shutdown behavior.
- [x] Add deterministic first-launch, identity, occupied-port, stale-identity, crash, timeout, second-owner, and shutdown-state tests.
- [x] Run the packaged GUI first/second-launch, occupied-listener, crash, and shutdown smoke gate.

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

## 11. v1.0.0 release-hardening plan (feature freeze)

This section is intentionally narrower than the historical roadmap. v1.0.0 is a
stability release. Do not add CLIP/ResNet/DINO/ANN/cluster-review behavior, new
metadata features, or broad UI polish while these gates are open. Prototype work
continues outside LMZ and is not part of this release. Browser-extension work is
also deferred and tracked in `docs/deferred_works.md`.

### Findings to resolve

| Finding | Evidence status | v1 disposition |
| --- | --- | --- |
| Vault/filesystem transition gap | Resolved by A1/A2 shared preflight, staging, commit, rollback, and failure-injection tests. | Closed for v1; retain the release smoke gate. |
| Desktop sidecar ownership/readiness gap | Resolved by the nonce handshake, fixed-port owner mutex, retained child, bounded readiness probe, launcher states, process-tree shutdown, and packaged GUI evidence. | Closed for v1; extension work remains separate. |
| WD stale wrong-shard regression gap | Resolved by the focused locked-stale-cache regression; the canonical cache is retained and cleanup errors are reported. | Closed for v1. |
| Real-vault release evidence gap | Resolved by Goal D staged migrated-vault/external-workspace evidence plus Goal E packaged UI flows. | Closed for v1. |
| MSI ICE failure | Reproduced as a Windows Installer/WiX environment limitation; NSIS passes. | Accepted non-blocker; v1 ships NSIS-only. |

### Goal sequence

Each goal below is independently testable. Stop after its acceptance checks pass;
do not combine goals into one open-ended refactor.

### Context retained from the release analysis

The following definitions, failure modes, expectations, and rationale are part of
the plan. They are deliberately recorded here so a later context reduction does
not turn the four release goals into only a sidecar checklist. Extension context
is maintained in `docs/deferred_works.md`.

#### A1 context — workspace switching

- **Achieves:** switching between `default` and `obsidian-main` is all-or-nothing;
  either the new workspace is fully active or the old one remains usable. Direct
  and active-workspace routes share the same safety path.
- **Terms:** a workspace is a registered LMZ project location; a vault is a media
  collection inside it; the runtime context is the in-memory active workspace,
  vault, databases, models, logs, and services; preflight is the set of checks
  before a switch; a transaction completes fully or preserves the prior state;
  rollback restores that prior state.
- **Previously confirmed failures, resolved by A1:** direct workspace load no
  longer bypasses preflight; candidate activation, registry commit, and
  environment handling now have one documented order; registry failure triggers
  full previous-service rehydration; rollback no longer uses `hydrate=False`; and
  `LMZ_CONFIG_PATH` is changed only after commit and restored on failure.
- **Expected behavior:** acquire one process-wide lock, preflight, stage and
  validate the candidate, commit registry/config/environment in a defined order,
  hydrate services, and fully restore context, environment, indexes, metadata
  workers, and logging on every failure.
- **Why it matters:** a mixed state can write ingestion to the wrong vault, return
  search results from the wrong workspace, misroute logs, or require a restart.

#### A2 context — vault and filesystem transitions

- **Achieves:** active-vault switching, relocation, creation, and deletion do not
  leave config, files, databases, or services pointing at different locations.
- **Terms:** relocation changes a physical path; a filesystem commit is the point
  where files/directories move; a config commit records the new path; partial state
  means only some of those changes succeeded.
- **Previously confirmed failures, resolved by A2:** relocation no longer writes
  durable config before candidate validation/hydration; create stages a new tree;
  delete moves the old tree to rollback staging; active-vault switching hydrates
  from a same-directory staged config; all paths share the A1 lock and restore
  config, registry, filesystem, environment, and services on failure.
- **Expected behavior:** stage and validate the candidate, keep the old path until
  commit, then update config/runtime; restore the prior path, config, services, and
  registry if any step fails.
- **Why it matters:** media is not trivially reconstructible. Partial relocation
  can disconnect database rows, thumbnails, WD tags, or review files from the
  actual media and look like data loss.

#### B context — desktop sidecar ownership and readiness

- **Terms:** Tauri is the native desktop shell; the sidecar is the packaged
  Python/FastAPI backend launched beside it; a fixed port is always `8000`; a
  readiness handshake proves initialization; backend identity proves the listener
  belongs to this LMZ instance; a singleton means one LMZ desktop owner.
- **Previously confirmed failures, now addressed:** the frontend had assumed
  `http://localhost:8000`; Tauri discarded the child handle; there was no
  identity/readiness handshake; and a second instance or unrelated listener
  could occupy the port.
- **Implemented handshake contract:** Tauri generates a per-launch nonce and passes it
  only to the child. A local unauthenticated readiness endpoint such as
  `GET /api/runtime/health` returns the LMZ service name, `ready` status, protocol
  version, and a nonce-derived identity. Tauri accepts port `8000` only after the
  response matches; the frontend starts only after that check succeeds.
- **Locked v1 decision:** use the fixed-port singleton route. Only one LMZ owns
  port `8000`; a second LMZ launch must not create another backend; an unrelated
  listener must be rejected rather than silently trusted. Dynamic ports are
  deferred.
- **Why it matters:** connecting to the wrong listener is equivalent to connecting
  to the wrong database, and an unowned child can remain running after shutdown.

#### D context — release validation closure

- **Achieves:** v1 is proven against migrated real data, not only synthetic
  fixtures, and known non-blockers are documented.
- **Terms:** a shard is a hash/storage bucket; a wrong-shard file is a derived file
  under the wrong bucket; derived data includes thumbnails, WD-tag JSON, and
  indexes; a real-vault smoke test is a short end-to-end test on migrated data; a
  synthetic fixture is generated test data; NSIS is the currently successful
  Windows installer format; MSI is blocked by the current WiX/Windows Installer
  environment.
- **WD status:** cleanup scans all shards, preserves the canonical file, reports
  locked stale files, and has direct locked wrong-shard regression coverage.
- **Completed proof:** the migrated default-vault launch/ingest/review/
  metadata/thumbnail/tag/log/restart flow; open and switch to external
  `obsidian-main` without moving data; validate install/upgrade/uninstall `.lmz`
  preservation; run final backend, frontend, and packaged gates. Prefer NSIS for
  v1 unless MSI becomes a hard requirement.

#### Goal A1 — transactional workspace switching

- [x] Route every workspace load through one preflight and process-wide switch lock.
- [x] Stage and validate the candidate context before activation.
- [x] Commit registry/config/environment changes in one documented order.
- [x] Restore `LMZ_CONFIG_PATH`, runtime context, search indexes, metadata workers, and logging on every failure path.
- [x] Add failure-injection tests for preflight rejection, candidate hydration failure, registry failure, service activation failure, rollback rehydration, and concurrent switches.

Acceptance evidence: direct and active workspace APIs behave identically; a forced
failure leaves the prior workspace usable and its services active; no environment
variable or registry entry is lost; focused tests pass. Verified with 14 startup
tests, the full relevant switching set (206 passed, 1 skipped), and the full
backend suite (277 passed, 1 skipped) on 2026-07-12.

Non-goals: dynamic sidecar ports, new similarity algorithms, UI redesign, and
database/schema changes unrelated to transition safety.

#### Goal A2 — transactional vault/filesystem transitions

- [x] Apply the same preflight and process-wide lock to active-vault, create, delete, and relocation transitions.
- [x] Stage candidate config/filesystem state before durable commit; retain rollback staging for deletion cleanup failures.
- [x] Define rollback behavior for vault create/delete/relocate and active-vault hydration/config failures.
- [x] Add focused failure-injection and shared-lock tests without rewriting A1 workspace switching.

Acceptance evidence: a forced vault transition failure leaves the previous vault,
config, files, services, and registry usable with no partial target state. Verified
with 8 focused A2 tests, 214 relevant backend tests (1 skipped), and the full
backend suite (286 passed, 1 skipped) on 2026-07-12.

#### Goal B — fixed-port desktop sidecar ownership and readiness

- [x] Enforce one LMZ desktop owner for the fixed backend port `8000`.
- [x] Retain and explicitly terminate the child process.
- [x] Add backend identity/readiness verification before the frontend accepts port `8000`.
- [x] Report occupied-port, crash, timeout, second-instance, and shutdown states clearly in the launcher.
- [x] Keep the frontend API base, Vite proxy, and CSP aligned with the fixed-port contract.
- [x] Add the local readiness/identity endpoint and verify its per-launch nonce before frontend startup.
- [x] Wait for the shell termination signal before reporting the owned sidecar as stopped.
- [x] Run the packaged GUI second-launch/occupied-listener/crash/shutdown smoke gate.

Acceptance evidence: the backend health contract test passes; native Tauri tests cover
exact nonce matching, unrelated/stale identities, second owner claims, startup
failure, timeout, crash, and shutdown state transitions, including a regression
test that waits for child termination; frontend checks/build and
fixed-base contract tests pass; and the rebuilt packaged sidecar completes two
nonce-verified first-launch/restart cycles with shutdown cleanup. An actual packaged
GUI run also kept the same nonce and created no new sidecar tree on the second launch.
An occupied-port GUI run started zero sidecar processes while a loopback listener held
port `8000`. After the process-tree cleanup fix, the rebuilt GUI close returned
gracefully and no new `lmz-api` PIDs remained; one pre-existing orphan from an earlier
run was intentionally left untouched. Earlier Codex WebView2 attempts reported
`0x800700AA` (resource in use), but the current packaged shutdown smoke passes and
the native wait regression plus process-tree cleanup tests pass.

Non-goals: dynamic ports, unrelated Tauri/UI features, and dynamic model loading.

#### Goal D — release validation closure

Goal D depends on A1, A2, and B only. Browser-extension work is deferred to
`docs/deferred_works.md` and must not block this goal. v1 uses the successful NSIS installer;
the current MSI/WiX limitation is recorded as a known non-blocker.

Validation must not mutate the real `%USERPROFILE%\.lmz` data home or inspect
secrets. Use an isolated data root and staged migrated content where possible.
Opening the registered external workspace may write expected logs or indexes, but
must never relocate its data or change its configured path.

- [x] **D1 — WD wrong-shard locked-file regression:** create a canonical WD
  cache in the correct shard and a stale copy in another shard; inject an
  `OSError` only for stale-file deletion; run repair; assert the canonical file
  is retained, the stale file remains, `stale_removed == 0`, and
  `cleanup_errors` identifies the stale path. A second run without the injected
  error must remove the stale copy.
- [x] **D2 — migrated default-vault smoke:** run against a staged copy of the
  migrated default workspace, excluding secrets and preflighting required model
  files. Verify launch, one controlled ingest, a deterministic review action,
  metadata/index consistency, thumbnail generation, WD tagging, app/vault log
  evidence, SQLite integrity, restart, and persisted state. Missing required
  models are a validation failure, not a silent skip.
- [x] **D3 — external workspace smoke:** capture the initial active workspace;
  open and switch through the registered `obsidian-main` workspace and back;
  assert runtime roots and config paths remain unchanged, no relocation occurs,
  and the initial active selection is restored.
- [x] **D4 — NSIS lifecycle:** in a dedicated Windows test profile or isolated
  data root, validate clean install, upgrade from the available `0.1.0` build,
  and uninstall. Assert the install directory is removed while `.lmz`, workspace
  data, and external registration remain; verify the installer/product metadata
  reports `1.0.0`. MSI remains documented as an environment limitation.
- [x] **D5 — release metadata, documentation, and gates:** bump all shipped
  release-facing versions to `1.0.0` (Tauri config, Cargo, frontend package and
  lockfile, and Python metadata); rebuild and verify packaged metadata. Run the
  backend, Rust, frontend, sidecar, packaged first-launch/restart, and NSIS gates,
  recording commands, outputs, artifacts, and known non-blockers. Correct stale
  release paths and legacy-migration wording in `README.md` and
  `docs/lmz_architecture.md`.

Acceptance evidence: each D1–D5 check has reproducible command output and
assertions in `tests/release_validation_evidence_1.0.0.md` and
`tests/release_validation_smoke_report_1.0.0.json`. The real-vault flows were isolated and
reversible, the final NSIS artifact identifies version `1.0.0`, and MSI plus the
deferred extension scope are explicitly recorded.

### Release goal status

**Goals A1, A2, B, and D are complete.** Their known defects are covered by
focused failure-injection, rollback, identity, ownership, shutdown, and release
validation tests. Goal C is deferred to `1.1.0` and is tracked in
`docs/deferred_works.md`.

Goal E is complete. All v1 release blockers are closed; remaining unchecked
items in this document are explicitly post-v1 product work.

## 12. Goal E — release-safe verification and cleanup

Goal E is the final verification pass before shipping `v1.0.0`. It is a
conservative audit, not a new refactor phase. The purpose is to verify the
current implementation from static code through packaged desktop behavior,
remove only high-confidence behavior-neutral redundancy, and record evidence
without mutating the real `%USERPROFILE%\.lmz` data home or inspecting secrets.

### Locked scope and safety rules

- Do not add features, change API contracts, change schemas, redesign the UI,
  add similarity/cluster-review behavior, or revisit deferred browser-extension
  work.
- Do not run automatic lint fixes, broad import rewrites, dependency upgrades,
  or repository-wide refactors during this goal.
- Use isolated temporary data roots and staged copies for all destructive or
  migration-related checks. Never use the real data home as a test fixture.
- Do not terminate a process that predates the goal, or install/uninstall the
  user's current LMZ installation, without explicit approval. Processes started
  by Goal E may be stopped by Goal E.
- Do not point the release smoke harness at the real registered external
  workspace. Use a staged external-workspace copy; Goal D remains the evidence
  for the already-completed real `obsidian-main` switch.
- Treat static-tool output as evidence to classify. Do not remove code solely
  because a tool cannot see framework registration, FastAPI decorators,
  Pydantic fields, migration entry points, or intentional compatibility code.
- Any source edit, even a small cleanup, requires the affected focused tests
  and the final release gates to be rerun.

### Known audit inputs

- `cargo test` currently passes all 7 native tests.
- `cargo clippy --all-targets -- -D warnings` reports two redundant Rust
  expressions in `frontend/src-tauri/src/lib.rs` (an unnecessary `return` and
  borrow).
- Vulture reports high-confidence candidates: two conventional unused
  `__exit__` parameters in `backend/api/common.py` and an unused
  `compare_embeddings` import in `backend/processor.py`.
- Targeted Ruff output also identifies an unused local `lower` in
  `backend/queue_service.py`; its wildcard-import warnings are architectural
  noise and are not a cleanup target for v1.
- The canonical v1 backend gate is `python -m pytest tests/backend -q`, currently
  `295 passed, 1 skipped`. The combined historical release gate reports `297
  passed, 1 skipped` because it also includes the extension-contract regression
  test; that optional result must remain separately labeled.
- Coverage measurement reports roughly 72% overall. Config/schema/runtime
  modules are substantially covered; lower coverage is concentrated in
  external downloaders, CLI scripts, and optional tagging paths. Coverage is a
  risk map, not a release percentage target.
- Coverage execution produced a small number of SQLite/file `ResourceWarning`s
  during test teardown. These must be reproduced, classified, and either
  repaired safely or explicitly recorded before sign-off.

### Subgoals and acceptance checks

#### Goal E1 — clean baseline and audit inventory

- [x] Record the starting commit, working-tree status, tool versions, and
  existing sidecar PIDs.
- [x] Confirm the only pre-existing untracked release-adjacent artifact is the
  deferred local browser-extension `.xpi`; it must not enter the v1 commit or
  installer payload.
- [x] Inventory pre-existing LMZ/Vite processes before packaged checks. Stop
  only processes created by Goal E; if an older process blocks a check, pause
  and request approval rather than killing it. Use an isolated data root for
  every automated run.
- [x] Search release documents for stale unresolved checkboxes, old counts,
  obsolete paths, and contradictory v1 scope wording; classify each as active,
  historical, superseded, or a real gap.

Acceptance evidence: a reproducible baseline record, no test writes to the real
data home, and a short inventory of findings before any cleanup edit.

#### Goal E2 — targeted static and redundancy audit

- [x] Review the two Clippy findings and apply only behavior-neutral fixes if
  they are confirmed unnecessary.
- [x] Review the Vulture candidates and rename conventional unused callback
  parameters or remove an import only after checking dynamic/framework usage.
- [x] Review the unused `lower` local and other high-confidence targeted
  findings; do not fix the broad wildcard-import Ruff output.
- [x] Search for dead release-facing routes, sidecar lifecycle helpers, config
  aliases, and duplicate wrappers using call sites, tests, and runtime wiring.
- [x] Do not remove migration tools, legacy rejection paths, framework
  decorators, or deferred prototype code merely because static analysis marks
  them as unused.

Acceptance evidence: every edit has a reason, an affected-test list, and no
unrelated formatting/import refactor; unresolved low-confidence findings are
recorded for `v1.1.0`.

#### Goal E3 — coverage and resource-lifecycle review

- [x] Re-run backend coverage with `pytest-cov` and retain the terminal report
  for the release record.
- [x] Prioritize uncovered branches only when they are on v1 paths: bootstrap,
  settings/workspace APIs, transactional switching, sidecar health, ingestion,
  review, logs, and shutdown.
- [x] Reproduce the SQLite/file `ResourceWarning`s with warning-focused runs.
- [x] Close leaked test/application resources only where the ownership is
  proven; do not hide warnings globally or add broad suppression rules.

Acceptance evidence: coverage gaps are classified by release risk, targeted
warnings are clean or explicitly documented, and no arbitrary coverage
threshold is introduced during the feature freeze.

#### Goal E4 — automated regression revalidation

- [x] Run the backend suite and the focused A1, A2, B, and D regressions.
- [x] Run Rust tests, strict Clippy, frontend type/Svelte checks, frontend
  production build, Playwright mock/generated/large-vault suites, Python
  bytecode compilation, and the fixed-base sidecar contract checks.
- [x] Rebuild the frozen Python sidecar before packaged verification.
- [x] Re-run the packaged sidecar first-launch/restart and release smoke
  harnesses with an isolated data root plus staged default and external
  workspaces. Do not use the real registered `obsidian-main` config.
- [x] If the isolated Goal D staging directories no longer exist, generate or
  copy synthetic fixtures into Goal E staging. Do not recreate staging from the
  real `.lmz` home automatically; retain Goal D as the real-data evidence.
- [x] Keep browser-extension contract tests informational only; they remain
  deferred from v1 acceptance.

Acceptance evidence: all required commands pass after the final source edit,
with exact counts, logs, reports, and known non-blockers recorded.

#### Goal E5 — manual packaged UI and native lifecycle verification

- [x] Verify clean startup, default workspace loading, icon alignment in the
  launcher/taskbar, and clear startup error states.
- [x] Verify settings persistence, app-wide config ownership, Webview developer
  mode default-off behavior, context-menu toggle, and normal-mode shortcut
  suppression across restart. `Ctrl+Shift+I` remains a native WebView2 bypass;
  the user accepted it as a v1.0.0 non-blocker and deferred it to v1.1.
- [x] Exercise the core UI flows: vault browsing, masonry/grid switching,
  search/filtering, inspector edit/revert/save, review actions, local ingest,
  logs, health/repair, backup, export, and import.
- [x] Verify fixed-port singleton behavior: second LMZ launch does not create a
  second backend; an unrelated listener is rejected; the owned sidecar exits
  with the desktop app; no new orphan process remains.
- [x] Treat native visual checks as collaborative evidence: launch or prepare
  the build, then request the user's observation for taskbar/launcher rendering
  and other behavior that automation cannot prove. Do not infer a pass.

Acceptance evidence: a manual checklist with screenshots or notes for failures,
and a clean process baseline after the final close/restart cycle.

#### Goal E6 — final release sign-off

- [x] Verify every release-facing version is `1.0.0`, the NSIS artifact metadata
  is correct, and the install/upgrade/uninstall preservation checks still pass.
  Use a dedicated install root and isolated data root; never uninstall the
  user's current installation without explicit approval.
- [x] Run `git diff --check`, stale-path/config searches, and a final status
  review; ensure no generated reports, secrets, `.lmz` content, or deferred
  extension artifacts are accidentally staged.
- [x] Record artifact paths/hashes, test commands/counts, manual results, and
  accepted non-blockers (MSI/WiX, browser-extension work, the native
  `Ctrl+Shift+I` bypass, and inspector topic-suggestion loading flicker).
- [x] Append Goal E evidence to `tests/release_validation_evidence_1.0.0.md` and
  update Goal E checkboxes only after their evidence exists. Do not commit
  unless explicitly requested.
- [x] Declare v1 ready only when all release blockers are closed; move broad
  lint debt, optional coverage expansion, and uncertain dead-code candidates to
  the post-release work log.

### Release blocker policy

Block v1.0.0 for a failed required test, data mutation outside the isolated
root, config or registry loss, wrong-listener acceptance, a new orphan sidecar,
startup/restart failure, installer/version mismatch, or an unclassified
resource leak on a release path. Treat low-confidence static warnings, optional
download/tagging coverage, MSI/WiX, the accepted native `Ctrl+Shift+I`
WebView2 bypass, inspector topic-suggestion loading flicker, and all
browser-extension work as documented non-blockers.

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
| 2026-07-12 | Real legacy project data is adopted into the existing `.lmz` home. | done | `data/` content and models were staged into `.lmz`; app settings, registry, logs/cache, and secrets were preserved; source deletion was false; the receipt records the rollback backup and `config/data` as ambiguous/ignored. |
| 2026-07-12 | External `obsidian-main` remains external under the new registry. | done | Its config now contains topology only; the legacy YAML has a sibling backup; both external vault databases pass integrity checks (164 and 28 items); the workspace remains inactive. |
| 2026-07-12 | v1 uses a fixed backend port with one LMZ owner. | decided | Keep port `8000`; prevent a second LMZ sidecar, verify backend identity/readiness, reject unrelated listeners, and terminate the owned child on shutdown. |
| 2026-07-12 | The personal browser extension ships in v1 with narrow API-key access. | superseded | The C1 hardening remains in the working tree, but all extension release work is deferred to `1.1.0`; see `docs/deferred_works.md`. |
| 2026-07-12 | Goal A1 workspace switching is transactional. | done | Direct and active load APIs share the process-wide preflight/lock; candidate activation, registry commit, environment handling, full rollback rehydration, and failure/concurrency tests pass. Vault/filesystem transitions remain Goal A2. |
| 2026-07-12 | Goal A2 vault/filesystem transitions are transactional. | done | Active-vault switching, create, delete, and relocation share A1 locking/preflight; staged config/filesystem changes roll back exact config, registry, environment, runtime services, and newly-created target files on forced failures. |
| 2026-07-12 | Goal B sidecar ownership/readiness completed. | done | Fixed port `8000`, Windows owner mutex, per-launch nonce health handshake, retained child lifecycle, process-tree shutdown, launcher error states, aligned API/CSP, and packaged GUI smoke checks pass. A pre-existing orphan process was intentionally not killed. |
| 2026-07-12 | Goal C split into shared browser behavior and browser-specific enablement. | superseded | The C1/C2 work is preserved in `docs/deferred_works.md` as the `1.1.0` extension workstream. |
| 2026-07-13 | All browser-extension work is deferred from v1.0.0. | decided | Do not make extension artifacts, origin allowlists, or extension-contract checks v1 acceptance criteria; retain the source and tests for v1.1.0. |
| 2026-07-13 | Goal D release closure scope. | decided | Depends on A1/A2/B only; uses NSIS for v1; validates WD cleanup, staged migrated-vault behavior, external workspace switching without relocation, install/upgrade/uninstall preservation, full `1.0.0` metadata, release documentation, and final evidence. Browser-extension work and MSI are non-blocking. |
| 2026-07-13 | Goal D release validation completed. | done | D1–D5 pass. Evidence is recorded in `tests/release_validation_evidence_1.0.0.md`; MSI/WiX and deferred extension work remain outside the v1 gate. |
| 2026-07-13 | Goal E uses conservative release-safe verification. | decided | Static tools are report-only; only high-confidence behavior-neutral cleanup is allowed. Use isolated data roots, classify coverage/resource warnings, rerun affected gates after edits, and defer broad lint/dead-code work. |
| 2026-07-13 | Defer the native `Ctrl+Shift+I` DevTools bypass. | accepted non-blocker | Save/persistence, context-menu gating, `F12`, `Ctrl+P`, and `Alt+Left` passed in the packaged app. Further WebView2-specific handling is deferred to v1.1. |
| 2026-07-13 | Goal E5 packaged UI/native verification completed. | done | User confirmed the full E5 checklist. Final close left no LMZ process or port-8000 listener. The recorded topic-suggestion loading-row flicker is visual polish and deferred. |
| 2026-07-13 | Goal E release-safe verification completed. | done | E1-E6 evidence passes, including final NSIS metadata/payload, isolated install-upgrade-uninstall preservation, manual packaged UI checks, and clean process/registry state. v1.0.0 is ready; no commit was created. |
