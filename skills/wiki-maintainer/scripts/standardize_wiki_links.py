import os
import re

wiki_dir = "wiki"
# Regex to find markdown links: [label](path)
link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')

# Manual Mappings for tricky cases
MANUAL_MAPPINGS = {
    "02_系統設定與金鑰管理-System-Configuration": "系統設定與金鑰管理-System-Configuration",
    "環境安裝-Environment-Local-Dev": "環境設定與本地開發-Environment-Local-Dev",
    "前端與服務架構-Frontend-Service-Architecture": "前端架構與UX層-Frontend-UX-Layer",
    "Environment-Local-Dev": "環境設定與本地開發-Environment-Local-Dev",
    "System-Landscape": "系統全景圖-System-Landscape",
    "Wiki-Standard": "文件規範-Wiki-Standard",
    "Database-Git-Standards": "資料庫設計與代碼規範-Database-Git-Standards",
    "Future-Roadmap-Specs": "未來演進規格-Future-Roadmap-Specs",
    "Evolutionary-Roadmap": "產品演進藍圖-Evolutionary-Roadmap",
    "Prompt-Engineering-Specs": "提示詞工程規範-Prompt-Engineering-Specs",
    "Architectural-Philosophies": "架構哲學-Architectural-Philosophies",
    "Sentinel-Council-Architecture": "哨兵與評議會架構-Sentinel-Council-Architecture",
    "Channel-Setup": "互動頻道設定-Channel-Setup",
}

# Get all valid page names (filenames without .md)
valid_pages = []
for root, dirs, files in os.walk(wiki_dir):
    for file in files:
        if file.endswith(".md"):
            valid_pages.append(file[:-3])

def find_best_match(path):
    basename = os.path.basename(path)
    if basename.endswith(".md"):
        basename = basename[:-3]
    
    # Priority 1: Manual Mapping
    if basename in MANUAL_MAPPINGS:
        return MANUAL_MAPPINGS[basename]
    
    # Priority 2: Exact Match
    if basename in valid_pages:
        return basename
    
    # Priority 3: Case-insensitive Match
    for page in valid_pages:
        if basename.lower() == page.lower():
            return page
            
    # Priority 4: Partial/English Name Match
    for page in valid_pages:
        if basename.lower() in page.lower():
            return page
    
    return None

def standardize_link(match):
    label = match.group(1)
    path = match.group(2)
    
    # Skip external links or anchor links
    if path.startswith("http") or path.startswith("#"):
        return match.group(0)
    
    # Skip relative paths pointing outside wiki (e.g. ../../.agent/...)
    if path.startswith("../") or path.startswith("./"):
        return match.group(0)
    
    # Skip non-wiki files usually referenced from repo root
    source_prefixes = ("scripts/", "src/", "services/", "prompts/", "k8s/", "tests/",
                       "data/", "infra/", "deployment/", ".agent/", ".github/", ".streamlit/",
                       "file://")
    if path in ["Dockerfile", "Dockerfile.mcp", "docker-compose.yml"]:
        return match.group(0)
    if any(path.startswith(p) for p in source_prefixes):
        return match.group(0)
    # Skip paths that look like source code files (contain / and have code extensions)
    code_extensions = (".py", ".sh", ".sql", ".js", ".ts", ".yaml", ".yml", ".json", ".toml", ".cfg", ".xml")
    if "/" in path and any(path.endswith(ext) for ext in code_extensions):
        return match.group(0)

    match_page = find_best_match(path)
    if match_page:
        return f"[{label}]({match_page})"
    
    return match.group(0)

if __name__ == "__main__":
    count = 0
    for root, dirs, files in os.walk(wiki_dir):
        for file in files:
            if file.endswith(".md"):
                filepath = os.path.join(root, file)
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
                
                new_content = link_pattern.sub(standardize_link, content)
                
                if new_content != content:
                    print(f"Updating {filepath}")
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    count += 1
    print(f"Standardization complete. Updated {count} files.")
