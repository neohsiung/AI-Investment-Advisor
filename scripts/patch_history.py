import os
import glob

files = glob.glob('wiki/**/*.md', recursive=True)

table_str = """
### 版本紀錄 (Version History)
| Date | Version | Description | Author |
| :--- | :--- | :--- | :--- |
| 2026-02-20 | v4.5 | Document audit and history alignment | Neo |
"""

count = 0
for file_path in files:
    if file_path.endswith('_Sidebar.md') or file_path.endswith('Home.md'): continue
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if "### 版本紀錄" not in content:
        lines = content.split('\n')
        h1_idx = -1
        for i, line in enumerate(lines):
            if line.startswith('# '):
                h1_idx = i
                break
        
        if h1_idx != -1:
            lines.insert(h1_idx + 1, table_str)
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write('\n'.join(lines))
            print(f"Added version history to {file_path}")
            count += 1

print(f"Total files updated: {count}")
