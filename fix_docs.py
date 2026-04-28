import pathlib

def replace_in_file(path_str, old, new):
    p = pathlib.Path(path_str)
    if p.exists():
        text = p.read_text(encoding='utf-8')
        if old in text:
            p.write_text(text.replace(old, new), encoding='utf-8')
            print(f"Updated {p.name}")

# liz_status.md
replace_in_file('04.03_python/projects/local_image_zettelkasten/docs/liz_status.md', '`src/ui/`', '`backend/ui/`')
replace_in_file('04.03_python/projects/local_image_zettelkasten/docs/liz_status.md', '`src/web_api.py`', '`backend/web_api.py`')
replace_in_file('04.03_python/projects/local_image_zettelkasten/docs/liz_status.md', '`src/core.py`', '`backend/core.py`')
replace_in_file('04.03_python/projects/local_image_zettelkasten/docs/liz_status.md', '- `src/` has not been renamed to `backend/`.', '- `src/` has been successfully renamed to `backend/`.')

# liz_roadmap.md
replace_in_file('04.03_python/projects/local_image_zettelkasten/docs/liz_roadmap.md', '- `src/` has not been renamed to `backend/`.', '- `src/` has been successfully renamed to `backend/`.')
replace_in_file('04.03_python/projects/local_image_zettelkasten/docs/liz_roadmap.md', '- Decide whether to rename `src/` to `backend/`.', '- [x] Rename `src/` to `backend/`.')

# liz_architecture.md
replace_in_file('04.03_python/projects/local_image_zettelkasten/docs/liz_architecture.md', 'src/\n', 'backend/\n')
replace_in_file('04.03_python/projects/local_image_zettelkasten/docs/liz_architecture.md', 'src/ui/', 'backend/ui/')
replace_in_file('04.03_python/projects/local_image_zettelkasten/docs/liz_architecture.md', 'src/web_api.py', 'backend/web_api.py')
replace_in_file('04.03_python/projects/local_image_zettelkasten/docs/liz_architecture.md', 'src/tagging/', 'backend/tagging/')

