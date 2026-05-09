#!/usr/bin/env python3
"""Wiki Validation Script — 檢核 wiki/ 是否遵循 .agent/rules/wiki-standard.md"""
import os, re, sys

WIKI_ROOT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "wiki")
ALLOWED_DIRS = {
    "00_Product_Strategy", "01_System_Architecture", "02_Frontend_UX",
    "03_Backend_Intelligence", "04_Data_Storage", "05_Quality_Assurance",
    "06_SRE_Observability", "Archive", "Archive/Legacy-Root", "Archive/Project-History"
}
DUPLICATE_DIR_MAP = {
    "02_Tools_and_Integration": "05_Quality_Assurance/Tools-and-Integration",
    "02_常用工具與整合-Tools_and_Integration": "05_Quality_Assurance/Tools-and-Integration",
    "01_設計模式-Patterns": "05_Quality_Assurance/Patterns",
    "01_規格書-Specs": "00_Product_Strategy/Specs",
    "Legacy_Root": "Archive/Legacy-Root",
    "Project_History": "Archive/Project-History",
    "04_架構觀點": "Archive/Project-History",
    "05_工程手冊": "Archive/Project-History",
}

def validate():
    errors = []
    warnings = []
    
    # 1. Home.md exists
    home = os.path.join(WIKI_ROOT, "Home.md")
    if not os.path.exists(home):
        errors.append("[FAIL] Home.md not found in wiki root")
    else:
        print(f"[PASS] Home.md exists")
    
    # 2. _Sidebar.md exists
    sidebar = os.path.join(WIKI_ROOT, "_Sidebar.md")
    if not os.path.exists(sidebar):
        errors.append("[FAIL] _Sidebar.md not found in wiki root")
    else:
        print(f"[PASS] _Sidebar.md exists")
    
    # Walk all files
    root_files = []
    for root_dir, dirs, files in os.walk(WIKI_ROOT):
        for f in files:
            if not f.endswith(".md") and not f.endswith(".gitkeep"):
                continue
            rel = os.path.relpath(os.path.join(root_dir, f), WIKI_ROOT)
            
            # 3. No Chinese chars
            if re.search(r'[\u4e00-\u9fff]', f):
                errors.append(f"[FAIL] Chinese chars in filename: {rel}")
            
            # 4. No numeric prefix
            if re.match(r'^\d+[\.\-_]', f):
                errors.append(f"[FAIL] Numeric prefix in filename: {rel}")
            
            # Track root files for rule 6
            if os.path.dirname(rel) == ".":
                root_files.append(rel)
    
    # 6. All non-Archive files should be in subdirs
    allowed_root = {"Home.md", "_Sidebar.md", "_Footer.md"}
    for rf in root_files:
        if rf not in allowed_root:
            warnings.append(f"[WARN] Root-level file (should be in subdir): {rf}")
    
    # 7. Duplicate dir check
    all_dirs = set()
    for root_dir, dirs, files in os.walk(WIKI_ROOT):
        for d in dirs:
            p = os.path.relpath(os.path.join(root_dir, d), WIKI_ROOT)
            all_dirs.add(p)
            if d in DUPLICATE_DIR_MAP:
                warnings.append(f"[WARN] Duplicate/misnamed dir: {p} → should use {DUPLICATE_DIR_MAP[d]}")
    
    # Summary
    print(f"\n{'='*50}")
    print(f"Results: {len(errors)} errors, {len(warnings)} warnings")
    
    for e in errors:
        print(f"  {e}")
    for w in warnings:
        print(f"  {w}")
    
    return len(errors) == 0

if __name__ == "__main__":
    success = validate()
    sys.exit(0 if success else 1)
