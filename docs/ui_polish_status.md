# UI Polish Status

Temporary working notes for Settings and Logs polish.

Last updated: 2026-06-18

## Current Focus

- Settings panel and all subpanels first.
- Logs panel second.
- Reduce text bloat with clearer hierarchy, icons, and reusable UI pieces.
- Keep changes small, direct, and easy to review.
- Completed polish work has been moved into `docs/phase8_status.md`.

## Inspection Notes

- Graphify update has been fully completed using `graphify update . --force`.
- Code graph is fresh as of today with 5,329 nodes, 9,735 edges, and 411 communities.
- Standalone HTML (`graph.html`) and collapsible D3 tree (`GRAPH_TREE.html`) visualizations have been successfully generated under `graphify-out/` (with interactive zoom/pan mechanics added to the tree).
- Backend Settings routes mostly live in `backend/api/runtime.py`.
- Logs routes live in `backend/api/logs.py`.
- Frontend Settings API wrappers live in `frontend/src/lib/settingsApi.ts`.
- Main frontend work is in `SettingsView.svelte`, `Settings*Panel.svelte`, `settings.css`, and `LogsView.svelte`.

## Settings Findings

- Maintenance polish batch is done and moved to `docs/phase8_status.md`.
- Privacy blur is done and moved to `docs/phase8_status.md`.
- Wide/fullscreen Settings width audit is done and moved to `docs/phase8_status.md`.
- General tab is usable, but explanatory microcopy is too dense.
- `AI Tagging Engine` sounds inflated. Prefer simpler `Tagging`.
- Workspace tab is the strongest panel, but path rows are visually dense.
- Vaults tab is usable, but action buttons repeat too much text.
- Settings widths are inconsistent: General 600px, Workspace/Vaults/Maintenance 900px, Shortcuts 1000px.
- Obsidian-style direction: consistent left-aligned content column, not full-window stretching.
- Future idea: large Obsidian-like Settings modal/shell, but keep current Settings panel for now.

## Logs Findings

- Logs toolbar is split into compact control and filter rows.
- Sources are separated into Startup logs, Vault logs, and Console.
- `Clear` uses the reusable `ConfirmationModal` and names its target.
- Stream state, CRITICAL/OTHER levels, and loaded-row search are implemented.
- Real local/online ingest log smoke remains useful before release.

## API / Safety Notes

- Frontend wrappers send `confirm=true` for destructive package/vault flows after UI confirmation.
- This is acceptable only if UI confirmation text is explicit.
- Destructive actions must show target context clearly.
- Avoid broad backend changes during polish unless a UI safety issue requires it.

## First Polish Batch

Done and moved to `docs/phase8_status.md` or completed:

- Clean the Maintenance tab.
- Extract small reusable Settings UI pieces where repetition is obvious.
- Replace stale Settings copy.
- Normalize action buttons with icons, short labels, and titles.
- Add frontend-only Privacy blur.
- Move Privacy blur into General -> Vault Display Settings.
- Move Logs `Clear Logs` to `ConfirmationModal`.

Still open:

1. Standardize Settings content widths.

## Screenshot References

Screenshots from the 2026-06-15 inspection were saved locally:

```text
C:\Users\BILGIS~1\AppData\Local\Temp\lmz-settings-audit
```

Files:

- `settings-general.png`
- `settings-workspace.png`
- `settings-workspace-bottom.png`
- `settings-vaults.png`
- `settings-maintenance.png`
- `settings-maintenance-bottom.png`
- `settings-shortcuts.png`
- `logs.png`

Width audit screenshots:

```text
C:\Users\BILGIS~1\AppData\Local\Temp\lmz-settings-width-audit
```

Files:

- `settings-general.png`
- `settings-workspace.png`
- `settings-vaults.png`
- `settings-maintenance.png`
- `settings-shortcuts.png`
- `measurements.json`
