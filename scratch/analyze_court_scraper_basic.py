import re
from collections import defaultdict
from pathlib import Path

WORKSPACE = Path(r"C:\Users\pc\PycharmProjects\Court-Scraper").resolve()
CSB_DIR = (WORKSPACE / "court_scraper_basic").resolve()
COUNTIES_DIR = (CSB_DIR / "counties").resolve()

EXCLUDE_DIRS = {
    '__pycache__', 'logs', 'test_logs', 'uploads', 'downloaded_files', 
    'deed_output', 'bin'
}

def get_py_files(root):
    py_files = []
    for item in root.iterdir():
        if item.is_file() and item.suffix == '.py':
            py_files.append(item.resolve())
        elif item.is_dir() and item.name not in EXCLUDE_DIRS and not item.name.startswith('.'):
            for p in item.rglob('*.py'):
                if not any(part in EXCLUDE_DIRS for part in p.parts):
                    py_files.append(p.resolve())
    return py_files

def extract_functions(file_path):
    funcs = []
    try:
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
    except Exception:
        return funcs

    pattern = re.compile(r'^[ \t]*(?:async\s+)?def\s+([a-zA-Z_][a-zA-Z0-9_]*)\s*\(', re.MULTILINE)
    for m in pattern.finditer(content):
        name = m.group(1)
        lineno = content[:m.start()].count('\n') + 1
        line = content[m.start():content.find('\n', m.start())]
        is_method = line.startswith('    ') or line.startswith('\t')
        funcs.append({
            'name': name,
            'lineno': lineno,
            'file': file_path,
            'file_str': str(file_path).lower(),
            'is_method': is_method
        })
    return funcs

def main():
    counties_files = sorted([f.resolve() for f in COUNTIES_DIR.rglob("*.py") if "__pycache__" not in str(f)])
    all_csb_py = get_py_files(CSB_DIR)

    print(f"Counties python files in court_scraper_basic: {len(counties_files)}")
    print(f"Total python files in court_scraper_basic: {len(all_csb_py)}")

    all_funcs = []
    for cf in counties_files:
        all_funcs.extend(extract_functions(cf))

    print(f"Total functions in court_scraper_basic/counties: {len(all_funcs)}")

    # Index tokens in all python files of court_scraper_basic
    word_re = re.compile(r'\b[a-zA-Z_][a-zA-Z0-9_]*\b')
    token_index = defaultdict(list)

    for pf in all_csb_py:
        pf_str = str(pf).lower()
        try:
            with open(pf, 'r', encoding='utf-8', errors='ignore') as f:
                lines = f.readlines()
            for idx, line in enumerate(lines, start=1):
                tokens = set(word_re.findall(line))
                for t in tokens:
                    token_index[t].append((pf_str, pf, idx, line.strip()))
        except Exception:
            pass

    unused = []
    internal_only = []
    used_externally = []

    counties_dir_str = str(COUNTIES_DIR).lower()

    for fn in all_funcs:
        name = fn['name']
        def_file_str = fn['file_str']
        def_file = fn['file']
        lineno = fn['lineno']

        if name.startswith('__') and name.endswith('__'):
            continue

        occurrences = token_index.get(name, [])
        
        usages = []
        for pf_str, pf, lnum, lstr in occurrences:
            if pf_str == def_file_str:
                if lnum == lineno or re.search(r'def\s+' + re.escape(name) + r'\b', lstr):
                    continue
            usages.append((pf_str, pf, lnum, lstr))

        if len(usages) == 0:
            unused.append(fn)
        else:
            external_usages = [u for u in usages if not u[0].startswith(counties_dir_str)]
            same_file_usages = [u for u in usages if u[0] == def_file_str]
            other_counties_usages = [u for u in usages if u[0].startswith(counties_dir_str) and u[0] != def_file_str]

            if len(external_usages) == 0:
                internal_only.append({
                    'func': fn,
                    'same_file_usages': same_file_usages,
                    'other_counties_usages': other_counties_usages
                })
            else:
                used_externally.append({
                    'func': fn,
                    'external_usages': external_usages,
                    'all_usages': usages
                })

    print(f"\n=======================================================")
    print(f"RESULTS FOR court_scraper_basic/counties")
    print(f"=======================================================")
    print(f"1. Completely Unused Functions (0 refs anywhere in court_scraper_basic): {len(unused)}")
    print(f"2. Internal-Only Functions (referenced inside counties, never outside): {len(internal_only)}")
    print(f"3. Externally Used Functions (imported/called outside counties in court_scraper_basic): {len(used_externally)}")

    # Group unused by file
    by_file_unused = defaultdict(list)
    for fn in unused:
        rel = fn['file'].relative_to(CSB_DIR)
        by_file_unused[rel].append(fn)

    print(f"\n=======================================================")
    print(f"1. COMPLETELY UNUSED FUNCTIONS BY FILE ({len(unused)} total)")
    print(f"=======================================================")
    for rel_path, funcs in sorted(by_file_unused.items(), key=lambda x: str(x[0])):
        print(f"\n[FILE] {rel_path} ({len(funcs)} unused):")
        for fn in funcs:
            type_str = "method" if fn['is_method'] else "function"
            print(f"   - Line {fn['lineno']:4d}: {fn['name']} ({type_str})")

    # Group internal-only by file
    by_file_internal = defaultdict(list)
    for item in internal_only:
        rel = item['func']['file'].relative_to(CSB_DIR)
        by_file_internal[rel].append(item)

    print(f"\n=======================================================")
    print(f"2. INTERNAL-ONLY FUNCTIONS IN COUNTIES ({len(internal_only)} total)")
    print(f"=======================================================")
    for rel_path, items in sorted(by_file_internal.items(), key=lambda x: str(x[0])):
        print(f"\n[FILE] {rel_path} ({len(items)} internal functions):")
        for item in items:
            fn = item['func']
            same_cnt = len(item['same_file_usages'])
            other_cnt = len(item['other_counties_usages'])
            if other_cnt == 0:
                print(f"   - Line {fn['lineno']:4d}: {fn['name']} (private helper: {same_cnt} local call(s))")
            else:
                other_files_names = {u[1].name for u in item['other_counties_usages']}
                print(f"   - Line {fn['lineno']:4d}: {fn['name']} (used in counties: {same_cnt} local, {other_cnt} in {', '.join(other_files_names)})")

if __name__ == "__main__":
    main()
