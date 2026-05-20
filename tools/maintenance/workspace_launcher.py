import argparse
import sys


def _backend_path():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    backend = root / "backend"
    if str(backend) not in sys.path:
        sys.path.insert(0, str(backend))


def choose_workspace() -> int:
    _backend_path()
    from workspaces import active_workspace_config_path, workspace_list

    items = workspace_list()
    valid = [item for item in items if item["exists"]]
    if not valid:
        print(str(active_workspace_config_path()))
        return 0
    if len(valid) == 1:
        print(valid[0]["config_path"])
        return 0
    print("Choose LMZ workspace:", file=sys.stderr)
    for index, item in enumerate(valid, start=1):
        active = " *" if item["active"] else ""
        print(f"{index}. {item['name']}{active} - {item['config_path']}", file=sys.stderr)
    try:
        choice = input("Workspace number: ").strip()
    except EOFError:
        return 2
    if not choice.isdigit():
        print("Invalid workspace choice.", file=sys.stderr)
        return 2
    index = int(choice)
    if index < 1 or index > len(valid):
        print("Invalid workspace choice.", file=sys.stderr)
        return 2
    print(valid[index - 1]["config_path"])
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Choose an LMZ workspace config path.")
    parser.add_argument("--choose", action="store_true")
    args = parser.parse_args(argv)
    if args.choose:
        return choose_workspace()
    return choose_workspace()


if __name__ == "__main__":
    raise SystemExit(main())
