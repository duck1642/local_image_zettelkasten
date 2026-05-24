import argparse
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from PIL import Image, ImageDraw

# Add backend directory to sys.path
ROOT_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = ROOT_DIR / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

try:
    from runtime_context import get_runtime_context
    HAS_LMZ = True
except ImportError:
    HAS_LMZ = False


def _get_active_input_dir(vault_override: str | None = None) -> Path:
    if not HAS_LMZ:
        return Path("test_input")
    try:
        ctx = get_runtime_context()
        if vault_override:
            # Look up specified vault
            import yaml
            config_path = ctx.config_path
            if config_path.exists():
                data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
                vaults = data.get("vaults", {})
                if vault_override in vaults:
                    root = config_path.parent
                    from runtime_context import _resolve_from_root
                    v_root = _resolve_from_root(root, vaults[vault_override].get("root", f"data/vaults/{vault_override}"))
                    return v_root / "input"
        return ctx.active_vault.input_dir
    except Exception as exc:
        print(f"[WARNING] Could not load active vault context: {exc}")
        return Path("test_input")


def generate_images(target_dir: Path, count: int):
    colors = [
        (231, 76, 60),    # Red
        (46, 204, 113),   # Green
        (52, 152, 219),   # Blue
        (241, 196, 15),   # Yellow
        (155, 89, 182),   # Purple
        (52, 73, 94),     # Dark slate
        (230, 126, 34),   # Orange
    ]
    formats = ["png", "jpg", "webp"]

    for i in range(count):
        fmt = formats[i % len(formats)]
        color = colors[i % len(colors)]
        w = 600 + (i % 3) * 100
        h = 400 + (i % 4) * 50
        img = Image.new("RGB", (w, h), color=color)
        d = ImageDraw.Draw(img)
        
        # Add visual content
        d.rectangle([20, 20, w - 20, h - 20], outline=(255, 255, 255), width=3)
        d.text((40, h // 2 - 20), f"Test Image #{i+1}", fill=(255, 255, 255))
        d.text((40, h // 2 + 10), f"Dim: {w}x{h} | Format: {fmt}", fill=(255, 255, 255))
        d.text((40, h - 50), f"Generated: {datetime.now(timezone.utc).strftime('%H:%M:%S')} UTC", fill=(200, 200, 200))
        
        filename = f"test_image_{i+1:03d}.{fmt}"
        img.save(target_dir / filename)
    print(f" Generated {count} test images inside {target_dir}")


def generate_videos(target_dir: Path, count: int):
    # Check if ffmpeg is on PATH
    ffmpeg_found = shutil.which("ffmpeg") is not None
    if not ffmpeg_found:
        print("[INFO] ffmpeg not found on PATH. Writing lightweight mock video files.")
        for i in range(count):
            filename = f"test_video_{i+1:03d}.mp4"
            (target_dir / filename).write_text("LMZ Mock Video Placeholder Data", encoding="utf-8")
        return

    # Generate real small videos using ffmpeg lavfi color inputs
    colors = ["blue", "red", "green", "yellow", "purple"]
    for i in range(count):
        color = colors[i % len(colors)]
        filename = f"test_video_{i+1:03d}.mp4"
        out_path = target_dir / filename
        subprocess.run([
            "ffmpeg", "-y", "-f", "lavfi", "-i", f"color=c={color}:s=320x240:d=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out_path)
        ], capture_output=True)
    print(f" Generated {count} test videos inside {target_dir}")


def main(argv=None):
    parser = argparse.ArgumentParser(description="Generate mock test media assets for LMZ vault ingestion")
    parser.add_argument("--vault", type=str, help="Target specific vault name from config.yaml")
    parser.add_argument("--target", type=Path, help="Override output target directory path")
    parser.add_argument("--images", type=int, default=8, help="Number of test images to generate")
    parser.add_argument("--videos", type=int, default=2, help="Number of test videos to generate")
    parser.add_argument("--clean", action="store_true", help="Clear the target directory before generating assets")
    args = parser.parse_args(argv)

    if args.target:
        target_dir = args.target.expanduser().resolve()
    else:
        target_dir = _get_active_input_dir(args.vault)

    target_dir.mkdir(parents=True, exist_ok=True)

    if args.clean:
        print(f"[INFO] Cleaning target directory: {target_dir}")
        for child in target_dir.iterdir():
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)

    generate_images(target_dir, args.images)
    generate_videos(target_dir, args.videos)
    print(f"\n[SUCCESS] Seeded test files into: {target_dir}")
    print("You can now trigger ingestion from the LMZ app UI or local-ingest CLI!")


if __name__ == "__main__":
    main()
