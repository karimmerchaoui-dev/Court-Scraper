import re
from collections import defaultdict
from pathlib import Path

WORKSPACE = Path(r"C:\Users\pc\PycharmProjects\Court-Scraper").resolve()
COUNTIES_DIR = (WORKSPACE / "counties").resolve()

from find_unused_functions import extract_functions, get_py_files

all_py = get_py_files(WORKSPACE, include_backups=False)
counties_files = sorted([f for f in COUNTIES_DIR.rglob("*.py") if "__pycache__" not in str(f)])

# Build token index
word_re = re.compile(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b')
token_index = defaultdict(list)

for pf in all_py:
    try:
        with open(pf, 'r', encoding='utf-8', errors='ignore') as f:
            for idx, line in enumerate(f, start=1):
                tokens = set(word_re.findall(line))
                for t in tokens:
                    token_index[t].append((pf, idx, line.strip()))
    except Exception:
        pass

print("=== COMPLETE AUDIT OF ALL FUNCTIONS IN 'counties' ===\n")

for cf in counties_files:
    rel = cf.relative_to(WORKSPACE)
    funcs = extract_functions(cf)
    if not funcs:
        continue
    print(f"\n--- File: {rel} ({len(funcs)} functions) ---")
    for fn in funcs:
        name = fn['name']
        lineno = fn['lineno']
        
        if name.startswith('__') and name.endswith('__'):
            continue
            
        occ = token_index.get(name, [])
        usages = [u for u in occ if not (str(u[0]).lower() == str(cf).lower() and u[1] == lineno)]
        ext_usages = [u for u in usages if not str(u[0]).lower().startswith(str(COUNTIES_DIR).lower())]
        local_usages = [u for u in usages if str(u[0]).lower() == str(cf).lower()]
        other_county_usages = [u for u in usages if str(u[0]).lower().startswith(str(COUNTIES_DIR).lower()) and str(u[0]).lower() != str(cf).lower()]

        if len(usages) == 0:
            status = "[UNUSED] (0 refs in codebase)"
        elif len(ext_usages) == 0 and len(other_county_usages) == 0:
            status = f"[LOCAL ONLY] ({len(local_usages)} local calls)"
        elif len(ext_usages) == 0:
            status = f"[COUNTIES INTERNAL ONLY] ({len(local_usages)} local, {len(other_county_usages)} other county files)"
        else:
            files_ext = {u[0].name for u in ext_usages}
            status = f"[USED EXTERNALLY] ({len(ext_usages)} calls across: {', '.join(files_ext)})"

            
        print(f"  Line {lineno:4d}: {name:<40} -> {status}")
