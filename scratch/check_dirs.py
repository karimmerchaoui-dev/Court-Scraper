from pathlib import Path

WORKSPACE = Path(r"c:\Users\pc\PycharmProjects\Court-Scraper").resolve()

# List top-level directories and count python files in each
for item in WORKSPACE.iterdir():
    if item.is_dir():
        py_count = len(list(item.rglob("*.py")))
        if py_count > 0:
            print(f"{item.name}: {py_count} .py files")
