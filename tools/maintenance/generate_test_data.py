from PIL import Image, ImageDraw
import os
from pathlib import Path

def create_test_assets():
    test_dir = Path("test_input")
    test_dir.mkdir(exist_ok=True)


    img_a = Image.new('RGB', (500, 500), color=(73, 109, 137))
    d = ImageDraw.Draw(img_a)
    d.text((200, 250), "Base Image A", fill=(255, 255, 0))
    img_a.save(test_dir / "image_a.png")


    img_near = img_a.copy()
    d_near = ImageDraw.Draw(img_near)
    d_near.point((10, 10), fill=(255, 255, 255))
    img_near.save(test_dir / "image_a_near.png")


    img_strip = Image.new('RGB', (500, 2000), color=(40, 40, 40))
    img_strip.paste(img_a, (0, 0))
    d_strip = ImageDraw.Draw(img_strip)
    d_strip.text((100, 700), "Panel 2: More Content", fill=(200, 200, 200))
    d_strip.text((100, 1200), "Panel 3: More Content", fill=(200, 200, 200))
    d_strip.text((100, 1700), "Panel 4: End", fill=(200, 200, 200))
    img_strip.save(test_dir / "strip_a.png")


    img_panel = img_strip.crop((0, 500, 500, 1000))
    img_panel.save(test_dir / "panel_from_strip.png")

    print(f" Generated 4 test assets in {test_dir.absolute()}")

if __name__ == "__main__":
    create_test_assets()
