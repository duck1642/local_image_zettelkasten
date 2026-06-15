# UI Polish Status

Temporary working notes for Settings and Logs polish.

Last updated: 2026-06-15

## Current Focus

- Settings panel and all subpanels first.
- Logs panel second.
- Reduce text bloat with clearer hierarchy, icons, and reusable UI pieces.
- Keep changes small, direct, and easy to review.

## Inspection Notes

- Graphify update was attempted with `graphify . --update --no-viz`.
- Update failed because semantic extraction needs an LLM API key.
- Existing graph is usable but stale from 2026-06-14.
- Backend Settings routes mostly live in `backend/api/runtime.py`.
- Logs routes live in `backend/api/logs.py`.
- Frontend Settings API wrappers live in `frontend/src/lib/settingsApi.ts`.
- Main frontend work is in `SettingsView.svelte`, `Settings*Panel.svelte`, `settings.css`, and `LogsView.svelte`.

## Settings Findings

- General tab is usable, but explanatory microcopy is too dense.
- `AI Tagging Engine` sounds inflated. Prefer simpler `Tagging`.
- Workspace tab is the strongest panel, but path rows are visually dense.
- Vaults tab is usable, but action buttons repeat too much text.
- Maintenance tab is the highest-value cleanup target.
- Maintenance stacks merge, health, packages, and system actions into one long page.
- Backup / Import / Export is compressed and hard to parse.
- Import row icon-only actions need clearer labels or tooltips.
- System Maintenance structure is good, but copy is stale.
- `Sync Workspace` still says `Obsidian Zettel tags`; replace with generic LMZ wording.
- Shortcuts tab is acceptable. Privacy blur fits there.

## Logs Findings

- Logs panel is functional but dense.
- Toolbar has too many equally weighted controls.
- Source/file labels are verbose.
- `Clear Logs` still uses browser `confirm()`.
- `Clear Logs` should move to reusable `ConfirmationModal`.
- Log output readability is acceptable; toolbar is the main issue.

## API / Safety Notes

- Frontend wrappers send `confirm=true` for destructive package/vault flows after UI confirmation.
- This is acceptable only if UI confirmation text is explicit.
- Destructive actions must show target context clearly.
- Avoid broad backend changes during polish unless a UI safety issue requires it.

## First Polish Batch

1. Clean the Maintenance tab.
2. Extract small reusable Settings UI pieces where repetition is obvious.
3. Replace stale Settings copy.
4. Normalize action buttons with icons, short labels, and titles.
5. Move Logs `Clear Logs` to `ConfirmationModal`.
6. Polish Logs toolbar after Settings maintenance cleanup.

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
