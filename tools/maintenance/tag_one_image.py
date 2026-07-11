import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = PROJECT_ROOT / "backend"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

from tagging import tag_media
from utils import get_app_settings
import utils


def find_first_image() -> Path | None:
    for path in utils.ASSETS_DIR.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".jfif"}:
            return path
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("image", nargs="?")
    parser.add_argument("--device", choices=["auto", "cpu", "cuda"])
    args = parser.parse_args()

    from runtime_context import has_runtime_context
    if not has_runtime_context():
        from scripts.workspace_select import select_runtime_context
        select_runtime_context("tag_one_image")

    image_path = Path(args.image).resolve() if args.image else find_first_image()
    if not image_path:
        print("[ERROR] No image found.")
        return 1

    config = get_app_settings()
    if args.device:
        config.setdefault("tagging", {})["device"] = args.device

    item_hash = image_path.stem if len(image_path.stem) == 64 else None
    result = tag_media(image_path, item_hash=item_hash, config=config)
    print(f"status: {result.status}")
    print(f"provider: {result.provider or 'none'}")
    if result.error:
        print(f"error: {result.error}")
    if result.rating:
        print(f"{result.rating['score']:.4f} rating {result.rating['label']}")
    for tag in result.character_tags[:20]:
        print(f"{tag['score']:.4f} character {tag.get('display_name', tag['name'])}")
    for tag in result.tags[:20]:
        print(f"{tag['score']:.4f} general {tag.get('display_name', tag['name'])}")
    return 0 if result.status in {"ok", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
