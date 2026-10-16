
main_file = 'counties/nj_helpers.py'
with open(main_file, 'r', encoding='utf-8') as f:
    lines = f.readlines()

out_lines = []
in_func = False
for i, line in enumerate(lines):
    if line.startswith('@pysnooper.snoop()') and i + 1 < len(lines) and lines[i+1].startswith('def extract_property_details'):
        continue
    
    if line.startswith('def extract_property_details('):
        out_lines.append('def extract_property_details(driver, case_id, report_cases, files_dir=None):\n')
        out_lines.append('    if files_dir:\n')
        out_lines.append('        _snoop_log = os.path.join(files_dir, "snoop_extract_property_details.log")\n')
        out_lines.append('        snooper = pysnooper.snoop(_snoop_log)\n')
        out_lines.append('    else:\n')
        out_lines.append('        snooper = pysnooper.snoop()\n')
        out_lines.append('    with snooper:\n')
        in_func = True
        continue
    
    if in_func:
        if line.startswith('def ') or line.startswith('# ═════════') or line.startswith('@pysnooper.snoop()'):
            in_func = False
        else:
            if line.strip() != '':
                out_lines.append('        ' + line)
            else:
                out_lines.append(line)
            continue
            
    out_lines.append(line)

with open(main_file, 'w', encoding='utf-8') as f:
    f.writelines(out_lines)
