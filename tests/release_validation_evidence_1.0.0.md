# LMZ v1.0.0 release validation evidence

Date: 2026-07-13

This record covers Goal D. The validation used isolated staging directories under
`tests/.goal-d-*` and never modified the real `%USERPROFILE%\.lmz` data home or
secrets.

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
