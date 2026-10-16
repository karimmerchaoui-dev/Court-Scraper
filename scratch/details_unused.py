from pathlib import Path

WORKSPACE = Path(r"C:\Users\pc\PycharmProjects\Court-Scraper").resolve()
COUNTIES_DIR = (WORKSPACE / "counties").resolve()

from find_unused_functions import get_py_files

all_py = get_py_files(WORKSPACE, include_backups=False)
counties_files = [f for f in COUNTIES_DIR.glob("*.py") if "__pycache__" not in str(f) and 'copy' not in f.name.lower()]

# We want to check unused functions in top-level counties files
with open(r"C:\Users\pc\PycharmProjects\Court-Scraper\scratch\find_unused_functions.py") as f:
    pass

unused, internal, ext = __import__('find_unused_functions').analyze(include_backups=False)

print("\n" + "="*80)
print("DETAILED BREAKDOWN OF TOP-LEVEL UNUSED FUNCTIONS IN COUNTIES/*.py")
print("="*80)

for fn in unused:
    if fn['file'].parent == COUNTIES_DIR:
        rel = fn['file'].relative_to(WORKSPACE)
        # Read the function signature / body snippet
        try:
            with open(fn['file'], 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            start = max(0, fn['lineno'] - 1)
            snippet = "".join(lines[start:start+5]).strip()
        except:
            snippet = ""
        print(f"\n[FILE] {rel}:{fn['lineno']}")
        print(f"   Function: {fn['name']}")
        print(f"   Snippet:\n     " + "\n     ".join(snippet.splitlines()))
