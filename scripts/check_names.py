import os
import glob
import re

files = glob.glob('wiki/**/*.md', recursive=True)

errors = []
for file_path in files:
    base = os.path.basename(file_path)
    if base in ['Home.md', '_Sidebar.md']:
        continue
    
    # Files must not start with a number
    if re.match(r'^\d', base):
        errors.append(f"[File starts with number] {file_path}")
    
    # Files must contain English (hyphen separated) and end with .md
    # A standard structure: 中文-English.md or 中文-Eng-lish.md
    if ' ' in base:
        errors.append(f"[File contains space] {file_path}")
        
    if not '-' in base and base != '封存-Archive.md':
        errors.append(f"[File missing hyphen separation] {file_path}")

folders = set()
for file_path in files:
    dir_path = os.path.dirname(file_path)
    if dir_path != 'wiki':
        # get the path relative to wiki
        rel_dir = os.path.relpath(dir_path, 'wiki')
        for part in rel_dir.split(os.sep):
            folders.add(part)

for folder in folders:
    # Folders must start with XX_ 
    if not re.match(r'^\d\d_', folder) and folder not in ['01_規格書-Specs', '01_設計模式-Patterns', '02_常用工具與整合-Tools_and_Integration']:
        errors.append(f"[Folder naming convention violation] wiki/{folder}")

if not errors:
    print("All file and folder names comply with the standard!")
else:
    for e in errors:
        print(e)
