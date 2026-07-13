# LMZ v1.0.0 release validation evidence

Date: 2026-07-13

This record covers Goals D and E. The validation used isolated staging
directories under `tests/.goal-d-*` and `tests/.goal-e-*` and never modified the
real `%USERPROFILE%\.lmz` data home or secrets.

## D1 — WD wrong-shard lifecycle

Command:

```text
python -m pytest tests/backend/test_mock_vault_isolation.py -k wd_repair_reports_locked_wrong_shard -q
```

Result: `1 passed`.

The test retains the canonical cache, reports the locked stale path, then removes
the stale wrong-shard cache on retry.

## D2/D3 — migrated default and external workspace smoke

Harness: `tests/release_validation_smoke.mjs`

The final run used the data-only staged copy of the migrated default workspace
(`166` existing items) and the registered external config at
`F:/ARCHIVE/main/lmz/config.yaml`.

Evidence: `tests/release_validation_smoke_report_1.0.0.json`

Passed checks:

- default launch and runtime activation;
- one local ingest (`166 -> 167` items);
- deterministic review variant (`167 -> 168` items);
- metadata patch and full index rebuild (`168 indexed`, `0` errors, `0` dirty);
- thumbnail response and WD cache creation;
- migrated health repair removed one inherited orphan thumbnail;
- post-repair health: `0` issues, no missing files, hash mismatches, stale rows,
  facet drift, or workspace dictionary drift;
- SQLite integrity before and after restart: `ok`;
- app and vault log files present;
- external workspace open/switch/back with unchanged external config and restored
  initial active workspace;
- restart reopened the staged default workspace with all `168` items.

## D4 — NSIS installer lifecycle

Artifacts:

- baseline: `frontend/src-tauri/target/debug/bundle/nsis/LMZ_0.1.0_x64-setup.exe`;
- release: `frontend/src-tauri/target/release/bundle/nsis/LMZ_1.0.0_x64-setup.exe`.

The baseline was installed into `tests/.goal-d-installer-20260713`, launched with
the isolated data root `tests/.goal-d-installer-data-20260713`, upgraded to
`1.0.0`, launched again, and silently uninstalled.

Results:

- clean install exit code: `0`;
- upgrade exit code: `0`;
- installed product version: `1.0.0`;
- both launches stayed alive for the validation window;
- sentinel survived upgrade, launch, and uninstall;
- install directory removed after uninstall;
- isolated data root remained.

## D5 — metadata and automated gates

Release-facing metadata is `1.0.0` in Tauri, Cargo/Cargo.lock, frontend package
and lockfile, and Python metadata. The synchronized Chrome/Edge/Firefox
manifests are retained as deferred C1 artifacts and are not part of the v1
release payload or acceptance scope.

Passed gates:

- `python -m pytest tests/backend tests/test_browser_extension_contract.py -q`
  — `297 passed, 1 skipped`;
- `cargo test --manifest-path frontend/src-tauri/Cargo.toml` — `7 passed`;
- `npm.cmd run check` — zero Svelte/TypeScript diagnostics;
- `npm.cmd run build` — passed;
- `npm.cmd run test:mock-vault` — `41 passed`;
- `npm.cmd run test:generated-vault` — `5 passed`;
- `npm.cmd run build:sidecar` — passed;
- `node tests/packaged_sidecar_first_launch.mjs ...` — first launch and restart
  passed; install directory unchanged;
- `npm.cmd run tauri build -- --bundles nsis` — produced
  `LMZ_1.0.0_x64-setup.exe`;
- `python -m compileall -q backend tools` — passed;
- `git diff --check` — passed.

The extension-contract portion of the combined backend command was run for
pre-v1 regression confidence. It is not a v1 acceptance gate; Goal C is tracked
in `docs/deferred_works.md` for `1.1.0`.

Documentation corrections were applied to `README.md` and the local architecture
document for `.lmz` paths and strict legacy behavior.

## Known non-blockers

- MSI/WiX ICE validation remains unavailable in this Windows session; v1 is NSIS-only.
- All browser-extension release work, including C1 packaging and C2
  Edge/Firefox origin verification, remains post-v1.
- Existing build warnings (Tauri identifier suffix, Vite ineffective dynamic imports,
  and non-fatal PyInstaller hidden-import warnings) did not fail packaging or tests.

No commit was created.

## Goal E1 — baseline and inventory

Goal E started from branch `polishing` at
`73cf13f823c6df2043c165b4cf97574c62363687`. The baseline contained the expected
Goal E documentation edit and the protected untracked
`tools/browser_extension/lmz-capture.xpi`; the extension remained outside all
v1 payloads and staging.

The isolated root was `tests/.goal-e-20260713-112927/`. No LMZ app, sidecar,
Python process, or port-8000 listener existed at the baseline. Pre-existing Node
PIDs `1152` and `2656` were inventoried and never terminated. Tool versions and
the pre-edit artifact inventory are retained in `reports/baseline.md` under that
root.

## Goal E2 — targeted static audit

The report-only static pass reproduced the expected findings, inspected their
call sites, and applied only behavior-neutral cleanup:

- strict Clippy's needless return/borrow findings were removed;
- conventional unused context-manager parameters were prefixed with `_`;
- proven unused processor imports, one queue local, one top-level vault import,
  and redundant f-string prefixes were removed;
- compatibility startup wrappers, FastAPI/Pydantic registrations, migration and
  legacy-rejection paths, deferred prototypes, and dynamic surfaces were kept.

Final results: strict Clippy passed; Vulture at 80% reported no findings;
targeted Ruff `F811,F821,F822,F823,F841,F541` passed; focused backend tests
reported `11 passed`; Rust reported `7 passed`; and the route audit found `102`
method/path registrations with zero duplicates. No API, schema, persistence,
security, or intended user behavior changed.

## Goal E3 — coverage and resource lifecycle

The final warning-focused backend coverage gate reported `296 passed, 1
skipped`, `72%` total coverage, and no warning summary. Strict lifecycle runs
reported `6 passed` for guards and `198 passed, 1 skipped` for mock-vault tests
with `ResourceWarning` and `PytestUnraisableExceptionWarning` treated as errors.

The narrow ownership fixes close discarded SQLite connections and explicitly
shut down LMZ-owned terminal logging, handlers, and metadata watchdogs. Coverage
was used as a risk map: configuration/runtime/media foundations are strongly
covered; external downloader, optional tagging/model, maintenance-script, and
CLI gaps remain advisory post-release work rather than a new v1 threshold.

## Goal E4 — final automated gates

Final post-edit evidence:

- canonical backend: `296 passed, 1 skipped`, coverage `72%`, no warning summary;
- focused A1/A2/B/D selectors: `15 passed`;
- Rust: `7 passed`; strict Clippy passed;
- fixed-port sidecar contract: `3 passed`;
- Python bytecode compilation passed;
- Svelte/TypeScript check: zero diagnostics; production build passed;
- Playwright mock vault: `42 passed` with no retries;
- generated vault: `5 passed`; large vault: `5 passed`;
- frozen sidecar rebuilt successfully;
- packaged first launch/restart passed with ETag exposure to the Tauri origin;
- final synthetic release smoke passed all eight steps with `14` items, zero
  health issues, SQLite `ok`, unchanged external config, restart persistence,
  nonce-matched readiness, and no remaining process/listener.

Known Vite dynamic-import advisories and optional/OS-specific PyInstaller
warnings remained non-fatal and are classified as non-blockers. Extension tests
remain informational and deferred to v1.1.0.

## Goal E5 — manual packaged UI/native verification

The user completed the packaged checklist against the isolated Goal E data root:
clean startup/default workspace, launcher/taskbar icon, settings ownership and
persistence, Webview controls, context menu, normal-mode shortcut suppression,
masonry/grid, search/filtering, inspector save/revert, review, local ingest,
logs, health/repair, backup/export/import, restart persistence, singleton and
wrong-listener behavior, and clean sidecar shutdown all passed.

Accepted v1 non-blockers: native WebView2 `Ctrl+Shift+I` can still bypass the
developer-mode setting, and an empty topic-suggestion request briefly shows a
loading row. Both are deferred; neither changes data or blocks core operation.

## Goal E6 — final NSIS packaging and sign-off

Final build command:

```text
cd frontend
npm.cmd run tauri build -- --bundles nsis
```

Artifact:
`frontend/src-tauri/target/release/bundle/nsis/LMZ_1.0.0_x64-setup.exe`

- size: `270,778,679` bytes;
- PE file/product version: `1.0.0`;
- SHA-256: `E18A114F95437A217ABFCA49450F086EE9DAD5F6A44FD3FB15408BBED198C7A7`.

The final `app.exe` is `11,942,400` bytes, reports version `1.0.0`, and has
SHA-256 `07DDBB1706A0E1947722C59EC24BCBF21C66870E0F5D15E22255D15BA63CD62D`.
Release-facing Tauri, Cargo/Cargo.lock, npm, and Python metadata all report
`1.0.0`. 7-Zip payload inspection found only NSIS support files, `app.exe`, and
`lmz-api.exe`; no mutable config/data/log/secrets/models or extension artifact
is bundled.

Final isolated installer run:
`tests/.goal-e-20260713-112927/installer/lifecycle-final-20260713-165706`.

- initial LMZ process/listener/registration counts: `0/0/0`;
- baseline install exit `0`, installed version `0.1.0`, packaged launch passed;
- upgrade exit `0`, installed version `1.0.0`, bundled sidecar startup passed;
- silent uninstall exit `0`;
- dedicated install root removed;
- isolated data home and preservation sentinel retained unchanged;
- final LMZ process/listener/registration counts: `0/0/0`.

The release copy lives under `release/v1.0.0/` with a matching
`SHA256SUMS.txt`; `/release/` is intentionally ignored to prevent accidental
binary commits. MSI/WiX and all browser-extension work remain explicit
non-blockers. Generated Goal E data/reports and the deferred `.xpi` remain
unstaged. Final `git diff --check` passed, the staged diff is empty, and stale
path/config matches were classified as retained legacy input, rejection tests,
historical decisions, or synthetic temporary paths. No commit was created.
