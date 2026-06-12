import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
BACKEND_DIR = PROJECT_ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from workspace_setup import lmz_workspace_config, main, setup_lmz_workspace  # noqa: E402,F401


if __name__ == "__main__":
    raise SystemExit(main())
