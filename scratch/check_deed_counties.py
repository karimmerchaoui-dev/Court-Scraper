import re
from collections import defaultdict
from pathlib import Path

WORKSPACE = Path(r"C:\Users\pc\PycharmProjects\Court-Scraper").resolve()
DEED_DIR = (WORKSPACE / "counties" / "counties_deed").resolve()
DEED_DIR_STR = str(DEED_DIR).lower()

from find_unused_functions import extract_functions, get_py_files

all_py = get_py_files(WORKSPACE, include_backups=False)
deed_files = [f for f in DEED_DIR.glob("*.py") if "__pycache__" not in str(f)]

print(f"Deed county files: {len(deed_files)}")

# Check what each file defines and where it's used
word_re = re.compile(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b')
token_index = defaultdict(list)

for pf in all_py:
    pf_str = str(pf).lower()
    try:
        with open(pf, 'r', encoding='utf-8', errors='ignore') as f:
            for idx, line in enumerate(f, start=1):
                tokens = set(word_re.findall(line))
                for t in tokens:
                    token_index[t].append((pf, idx, line.strip()))
    except Exception:
        pass

for df in sorted(deed_files):
    funcs = extract_functions(df)
    print(f"\n--- {df.name} ---")
    for fn in funcs:
        name = fn['name']
        occ = token_index.get(name, [])
        # filter out def
        usages = [u for u in occ if not (str(u[0]).lower() == str(df).lower() and u[1] == fn['lineno'])]
        # count occurrences outside this file
        ext = [u for u in usages if str(u[0]).lower() != str(df).lower()]
        print(f"  def {name} (line {fn['lineno']}): {len(usages)} total usages ({len(ext)} outside file)")
        if ext:
            for u in ext[:3]:
                print(f"     -> {u[0].relative_to(WORKSPACE)}:{u[1]}: {u[2]}")
