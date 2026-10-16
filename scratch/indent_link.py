main_file = 'main.py'
with open(main_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

out_lines = []
in_func = False
for i, line in enumerate(lines):
    if line.startswith('@pysnooper.snoop()') and i + 1 < len(lines) and lines[i+1].startswith('def download_filing_link_nj'):
        continue
    
    if line.startswith('def download_filing_link_nj('):
        out_lines.append('def download_filing_link_nj(driver, year, docket, account, file_element, select="all", files_dir=None, _index=0):\n')
        out_lines.append('    _snoop_log = os.path.join(files_dir, f"snoop_download_filing_link_{_index}.log") if files_dir else None\n')
        out_lines.append('    with pysnooper.snoop(_snoop_log):\n')
        in_func = True
        continue
    
    if in_func:
        if line.startswith('def ') or line.startswith('# ═════════') or line.startswith('@pysnooper.snoop()'):
            in_func = False
        else:
            if line.strip() != '':
                out_lines.append('    ' + line)
            else:
                out_lines.append(line)
            continue
            
    out_lines.append(line)

with open(main_file, 'w', encoding='utf-8') as f:
    f.writelines(out_lines)
