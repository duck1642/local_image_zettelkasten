from pathlib import Path

import yaml


def _choose(label: str, choices: list[tuple[str, str]], default_id: str | None = None) -> str:
    print(f"\n{label}:")
    for index, (choice_id, description) in enumerate(choices, start=1):
        marker = " [default]" if choice_id == default_id else ""
        print(f"  {index}. {choice_id} - {description}{marker}")
    raw = input(f"Choose {label.lower()} [{default_id or choices[0][0]}]: ").strip()
    if not raw:
        return default_id or choices[0][0]
    if raw.isdigit():
        index = int(raw)
        if 1 <= index <= len(choices):
            return choices[index - 1][0]
    valid = {choice_id for choice_id, _ in choices}
    if raw in valid:
        return raw
    raise SystemExit(f"Unknown {label.lower()}: {raw}")


def select_runtime_context(action: str = "maintenance", *, hydrate: bool = False):
    from runtime_activation import activate_runtime_context
    from runtime_context import build_runtime_context
    from workspaces import _resolve, load_workspace_registry

    registry = load_workspace_registry()
    workspaces = registry.get("workspaces") or {}
    if not workspaces:
        raise SystemExit("No workspaces configured.")

    workspace_choices = [
        (workspace_id, f"{entry.get('name') or workspace_id} ({_resolve(entry.get('config_path') or '')})")
        for workspace_id, entry in sorted(workspaces.items())
    ]
    workspace_id = _choose("Workspace", workspace_choices, registry.get("active"))
    config_path = _resolve(workspaces[workspace_id].get("config_path") or "")
    if not config_path.exists():
        raise SystemExit(f"Workspace config not found: {config_path}")

    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    vaults = config.get("vaults") if isinstance(config.get("vaults"), dict) else {}
    if not vaults:
        raise SystemExit(f"No vaults configured in {config_path}")

    vault_choices = [
        (vault_id, f"{entry.get('name') or vault_id} ({entry.get('root') or f'data/vaults/{vault_id}'})")
        for vault_id, entry in sorted(vaults.items())
    ]
    vault_id = _choose("Vault", vault_choices, config.get("active_vault") or "default")
    ctx = build_runtime_context(config_path, active_vault_id=vault_id)
    print(f"\nSelected workspace: {workspace_id}")
    print(f"Selected vault: {ctx.active_vault.id}")
    print(f"Vault root: {ctx.active_vault.root}")
    if not ctx.active_vault.root.exists():
        print(f"[WARN] Vault root does not exist: {ctx.active_vault.root}")
    if not ctx.active_vault.db_path.exists():
        print(f"[WARN] Vault DB does not exist: {ctx.active_vault.db_path}")
    activate_runtime_context(ctx, hydrate=hydrate)
    print(f"[INFO] Runtime loaded for {action}.")
    return ctx
