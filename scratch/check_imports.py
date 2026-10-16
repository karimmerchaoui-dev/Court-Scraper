import os
import subprocess
import json

exclude_dirs = {'.venv', 'backups', '_deprecated', 'scratch', 'salesweb project', '.git', '__pycache__', 'unused_files', 'node_modules', '.alumnium'}

py_files = []
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.')]
    for f in files:
        if f.endswith('.py') and not f.startswith('update_'):
            py_files.append(os.path.normpath(os.path.join(root, f)))

cmd = [r'.venv\Scripts\ruff.exe', 'check', '--select', 'F401,F811', '--output-format', 'json'] + py_files
res = subprocess.run(cmd, capture_output=True, text=True)
data = json.loads(res.stdout) if res.stdout.strip() else []

for item in data:
    code = item['code']
    fn = item['filename']
    row = item['location']['row']
    msg = item['message']
    print(f"{code} | {fn}:{row} | {msg}")

print(f"Total: {len(data)}")
