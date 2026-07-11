import os
import re

wiki_dir = "wiki"
# Regex to find markdown links: [label](path)
link_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
# Regex to find double bracket links: [[target]] or [[target|label]]
dbl_bracket_pattern = re.compile(r'\[\[([^\]|]+)(?:\|([^\]]+))?\]\]')

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
    # Added mappings
    "底層通信協議-Agent-Mesh-Protocols": "智能體調度與通訊規範-Agentic-Orchestration-Specs",
    "封存-Archive": "WIKI_INDEX",
    "Archive/Legacy/WIKI_INDEX": "WIKI_INDEX",
    "Archive/Legacy/Agent-Playbook": "Agent-Playbook",
    "設計模式-智能體集群-Swarm-Patterns": "設計模式全集-Design-Patterns-Compendium",
    "文件框架定義-Document-Frameworks": "文件規範-Wiki-Standard",
    "數據與記憶核心架構-Data-Memory-Core-Specs": "三層認知記憶系統-3-Tier-Cognitive-Memory-System",
    "券商整合指南-Broker-Integration-Guide": "交易服務-Trading-Services",
    "通知微服務架構-Notification-Microservice-Architecture": "排程與通知系統-Scheduler-Notification",
    "設計模式-存儲庫-Repository-Pattern": "設計模式全集-Design-Patterns-Compendium",
    "測試策略與CI-Testing-Strategy-And-CI": "測試與外部服務整合-Testing-External-Services",
    "配置管理與動態演化-Config-and-Evolution-Spec": "系統設定與金鑰管理-System-Configuration",
    "設計模式導讀-Design-Patterns-Intro": "設計模式全集-Design-Patterns-Compendium",
    "設計模式-依賴注入-DI-Pattern": "設計模式全集-Design-Patterns-Compendium",
    "記憶系統與Redis架構-Memory-Redis-Architecture": "安全存儲與Redis任務隊列-Secure-Storage-Redis-Queue",
    "理解任務進度表-Task-Board": "代碼理解進度表-Code-Understanding-Task-Board",
    "配置管理架構-Configuration-Management": "系統設定與金鑰管理-System-Configuration",
    "工具層指南-Tools-Layer-Guide": "Agent技能系統-Agent-Skills-System",
    "部署層-Deployment-Layer": "雲端部署-Deployment-GCP-CloudRun",
    "06_SRE_Observability/可觀測性面板操作指南-Observability-Dashboard-Guide": "系統可觀測性與通知規範-Observability-Notification-Standards",
    "multi_provider_multi_model_design": "多模型多提供商設計-Multi-Provider-Multi-Model-Design",
    "llm_settings_user_guide": "LLM系統設定操作手冊-LLM-Settings-User-Guide",
    "ollama_setup": "Ollama本地模型架設-Ollama-Setup",
    "Template Method Pattern": "設計模式全集-Design-Patterns-Compendium",
    "設計模式-策略-Strategy-Pattern": "設計模式全集-Design-Patterns-Compendium",
    "設計模式-工廠-Factory-Pattern": "設計模式全集-Design-Patterns-Compendium",
    "設計模式-樣板方法-Template-Method": "設計模式全集-Design-Patterns-Compendium",
    "通知微服務架構-Notification-Microservice-Architecture": "排程與通知系統-Scheduler-Notification",
    "基礎設施層-Infrastructure-Layer": "系統全景圖-System-Landscape",
}

# Get all valid page names (filenames without .md)
valid_pages = []
for root, dirs, files in os.walk(wiki_dir):
    for file in files:
        if file.endswith(".md"):
            valid_pages.append(file[:-3])

def find_best_match(path):
    # Priority 1: Manual Mapping (full path)
    if path in MANUAL_MAPPINGS:
        return MANUAL_MAPPINGS[path]

    basename = os.path.basename(path)
    if basename.endswith(".md"):
        basename = basename[:-3]
    
    # Priority 2: Manual Mapping (basename)
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
                
                def standardize_dbl_bracket(match):
                    target = match.group(1).strip()
                    label = match.group(2).strip() if match.group(2) else None
                    
                    if target.startswith(("http", "mailto", "#")):
                        return match.group(0)
                        
                    match_page = find_best_match(target)
                    if match_page:
                        if label:
                            return f"[[{match_page}|{label}]]"
                        else:
                            return f"[[{match_page}]]"
                    return match.group(0)

                new_content = link_pattern.sub(standardize_link, content)
                new_content = dbl_bracket_pattern.sub(standardize_dbl_bracket, new_content)
                
                if new_content != content:
                    print(f"Updating {filepath}")
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    count += 1
    print(f"Standardization complete. Updated {count} files.")
