import ast
import os

exclude_dirs = {'.venv', 'backups', '_deprecated', 'scratch', 'salesweb project', '.git', '__pycache__', 'unused_files', 'node_modules', '.alumnium'}

def find_unused_imports(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        tree = ast.parse(source, filename=filepath)
    except Exception as e:
        return []

    imported_names = {} # alias_or_name -> (line, original_name)
    all_names_used = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.asname or alias.name.split('.')[0]
                imported_names[name] = (node.lineno, alias.name)
        elif isinstance(node, ast.ImportFrom):
            # If `from x import *`, ignore
            for alias in node.names:
                if alias.name == '*':
                    continue
                name = alias.asname or alias.name
                imported_names[name] = (node.lineno, alias.name)
        elif isinstance(node, ast.Name):
            all_names_used.add(node.id)
        elif isinstance(node, ast.Attribute):
            pass

    unused = []
    # If __all__ is defined, symbols in __all__ are used
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == '__all__':
                    if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                all_names_used.add(elt.value)

    # Check which imported names are not in all_names_used (except when the name was defined as something else)
    # Note: ast.walk visits imports as ast.Name? No, alias is not ast.Name.
    # But wait, does ast.walk on an import produce ast.Name? No!
    # So if `name` appears in all_names_used, it was used in code outside alias.
    for name, (lineno, orig) in imported_names.items():
        if name not in all_names_used:
            # check if it's __name__ or something
            unused.append((lineno, name, orig))
    return unused

total_unused = 0
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in exclude_dirs and not d.startswith('.')]
    for f in files:
        if f.endswith('.py') and not f.startswith('update_'):
            full_path = os.path.normpath(os.path.join(root, f))
            unused = find_unused_imports(full_path)
            if unused:
                total_unused += len(unused)
                print(f"\n{full_path}:")
                for lineno, name, orig in sorted(unused):
                    print(f"  L{lineno}: {name} (from {orig})")

print(f"\nTotal unused imports found: {total_unused}")
