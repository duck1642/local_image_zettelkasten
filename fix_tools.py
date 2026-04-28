import pathlib
import re

tools_dir = pathlib.Path('04.03_python/projects/local_image_zettelkasten/tools/maintenance')
for f in tools_dir.glob('*.py'):
    text = f.read_text(encoding='utf-8')
    new_text = re.sub(r'(SRC(?:_DIR)?\s*=\s*(?:PROJECT_ROOT(?:_PATH)?|ROOT)\s*/\s*)"src"', r'\1"backend"', text)
    if new_text != text:
        f.write_text(new_text, encoding='utf-8')
        print(f"Updated {f.name}")
