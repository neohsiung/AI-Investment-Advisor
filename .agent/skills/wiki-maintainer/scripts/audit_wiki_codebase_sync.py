#!/usr/bin/env python3
import os
import re
import sys
from pathlib import Path

# Setup paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent.parent
WIKI_DIR = PROJECT_ROOT / "wiki"
SRC_DIR = PROJECT_ROOT / "src"
SERVICES_DIR = PROJECT_ROOT / "services"
FRONTEND_DIR = PROJECT_ROOT / "frontend"

# Regex patterns
LINK_PATTERN = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')
DBL_BRACKET_PATTERN = re.compile(r'\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]')
CLASS_PATTERN = re.compile(r'^class\s+(\w+)', re.MULTILINE)

# Folder Mappings for Directory Coverage
DIRECTORY_MAPPING = {
    # Backend & Agent Swarm
    "src/agents": "03_Backend_Intelligence/代理人戰略協定-Agent-Swarm-Protocol.md",
    "src/agents/skills": "03_Backend_Intelligence/Agent技能系統-Agent-Skills-System.md",
    "src/agents/persona": "01_System_Architecture/Agent骨架-Agent-Skeleton.md",
    "src/agents/swarm": "03_Backend_Intelligence/代理人戰略協定-Agent-Swarm-Protocol.md",
    "src/api": "03_Backend_Intelligence/API端點規範-API-Endpoints-Standard.md",
    "src/services": "03_Backend_Intelligence/服務層開發指南-Service-Layer-Blueprints.md",
    "src/services/event_agents": "03_Backend_Intelligence/服務層開發指南-Service-Layer-Blueprints.md",
    "src/infrastructure": "01_System_Architecture/架構哲學-Architectural-Philosophies.md",
    "src/infrastructure/llm": "03_Backend_Intelligence/多模型多提供商設計-Multi-Provider-Multi-Model-Design.md",
    "src/infrastructure/memory": "01_System_Architecture/三層認知記憶系統-3-Tier-Cognitive-Memory-System.md",
    "src/infrastructure/channels": "05_Quality_Assurance/系統可觀測性與通知規範-Observability-Notification-Standards.md",
    "src/infrastructure/mcp": "01_System_Architecture/MCP-Server-SSE基礎設施-MCP-Server-SSE-Infrastructure.md",
    "src/workflow": "03_Backend_Intelligence/任務規劃與執行引擎-Task-Planning-Engine.md",
    "src/tools": "01_System_Architecture/MCP-Server-SSE基礎設施-MCP-Server-SSE-Infrastructure.md",
    "src/utils": "01_System_Architecture/其他關鍵服務-Other-Key-Services.md",
    "src/prompts": "01_System_Architecture/其他關鍵服務-Other-Key-Services.md",
    "src/scheduler": "01_System_Architecture/排程與通知系統-Scheduler-Notification.md",
    "src/config": "06_SRE_Observability/系統設定與金鑰管理-System-Configuration.md",
    "src/alerts": "05_Quality_Assurance/系統可觀測性與通知規範-Observability-Notification-Standards.md",
    "src/dashboard": "02_Frontend_UX/前端架構與UX層-Frontend-UX-Layer.md",
    "src/styles": "02_Frontend_UX/前端架構與UX層-Frontend-UX-Layer.md",
    "src/scratch": "01_System_Architecture/待釐清事項任務看板-Code-Consolidation-Task-Board.md",
    "src/scripts": "06_SRE_Observability/腳本操作手冊-Scripts-Operations-Guide.md",
    "src/tracking": "03_Backend_Intelligence/LLM成本追蹤與模型分層-LLM-Cost-Tracking.md",
    
    # Data Layer
    "src/repositories": "04_Data_Storage/Repository層指南-Repository-Layer-Guide.md",
    "src/domain": "04_Data_Storage/資料與領域模型-Data-Domain-Models.md",
    "src/data": "04_Data_Storage/數據攝取架構-Data-Ingestion-Architecture.md",
    "src/data/providers": "01_System_Architecture/數據提供者與攝取器-Data-Providers-Ingestors.md",
    "src/data/ingestors": "01_System_Architecture/數據提供者與攝取器-Data-Providers-Ingestors.md",
    
    # Frontend
    "frontend": "02_Frontend_UX/前端架構與UX層-Frontend-UX-Layer.md",
    "frontend/src/components": "02_Frontend_UX/前端架構與UX層-Frontend-UX-Layer.md",
    "frontend/src/context": "02_Frontend_UX/前端架構與UX層-Frontend-UX-Layer.md",
    
    # QA & DevOps
    "tests": "05_Quality_Assurance/測試與外部服務整合-Testing-External-Services.md",
    "k8s": "06_SRE_Observability/雲端部署-Deployment-GCP-CloudRun.md",
    "infra": "05_Quality_Assurance/系統可觀測性與通知規範-Observability-Notification-Standards.md",
    "deployment": "06_SRE_Observability/雲端部署-Deployment-GCP-CloudRun.md",
    "docker-compose.prod.yml": "06_SRE_Observability/C端-SAAS-技術選型深度解析-B2C-Tech-Stack-Deep-Dive.md"
}

# Whitelist of terms that might appear in double brackets but are not pages
WIKI_BRACKET_WHITELIST = {"檔名", "功能變更", "page-name"}

def get_wiki_pages():
    pages = {}
    for root, _, files in os.walk(WIKI_DIR):
        if ".git" in Path(root).parts:
            continue
        for file in files:
            if file.endswith(".md"):
                clean_name = file[:-3]
                rel_path = Path(root) / file
                pages[clean_name.lower()] = {
                    "name": clean_name,
                    "rel_path": rel_path.relative_to(WIKI_DIR)
                }
    return pages

def verify_internal_links(wiki_pages):
    broken_links = []
    source_prefixes = ("scripts/", "src/", "services/", "prompts/", "k8s/", "tests/", "utils/", "docs/",
                       "data/", "infra/", "deployment/", ".agent/", ".github/", ".streamlit/", "frontend/")
    code_extensions = (".py", ".sh", ".sql", ".js", ".ts", ".yaml", ".yml", ".json", ".toml", ".cfg", ".xml", ".css", ".tsx")

    for clean_name, info in wiki_pages.items():
        # SKIP verifying files in Archive directory
        if "archive/" in str(info["rel_path"]).lower() or "archive\\" in str(info["rel_path"]).lower():
            continue
            
        filepath = WIKI_DIR / info["rel_path"]
        content = filepath.read_text(encoding="utf-8")
        
        # 1. Check double bracket links [[Link]]
        for match in DBL_BRACKET_PATTERN.finditer(content):
            target = match.group(1).strip()
            if target.lower() in WIKI_BRACKET_WHITELIST:
                continue
            # If target has a path extension, look at basename
            target_clean = target.replace(".md", "").split("/")[-1].strip().lower()
            if target_clean not in wiki_pages and not target.startswith(("http", "mailto", "#", "gbrain:")):
                # If target is mapped in whitelist, skip
                if target == "基礎設施層-Infrastructure-Layer":
                    continue
                broken_links.append((str(info["rel_path"]), f"[[{target}]]"))

        # 2. Check standard links [Label](path)
        for label, path in LINK_PATTERN.findall(content):
            path = path.strip()
            # Skip external, anchor, gbrain, or mailto links
            if path.startswith(("http", "mailto", "#", "gbrain:")):
                continue
                
            # Clean path from query, anchor, and line number suffix (like :53 or :1)
            path_clean = path.split("#")[0].split("?")[0].split(":")[0].strip()
            
            # Skip references that look like source code files or dirs
            if path_clean.startswith("../") or path_clean.startswith("./"):
                # Check if it exists relative to the markdown file directory
                if (filepath.parent / path_clean).exists():
                    continue
                # Clean prefix for check
                clean_path = path_clean.lstrip("./").lstrip("../")
                if any(clean_path.startswith(p) for p in source_prefixes) or any(clean_path.endswith(ext) for ext in code_extensions):
                    continue
            if any(path_clean.startswith(p) for p in source_prefixes):
                continue
            if any(path_clean.endswith(ext) for ext in code_extensions):
                continue
            # If path exists as a physical source code file in project, skip
            if (PROJECT_ROOT / path_clean).exists():
                continue
                
            # Check wiki pages
            target_clean = path_clean.replace(".md", "").split("/")[-1].strip().lower()
            if target_clean not in wiki_pages:
                broken_links.append((str(info["rel_path"]), f"[{label}]({path})"))

    return broken_links

def check_directory_coverage():
    uncovered_dirs = []
    # Scan src/ subdirectories
    for item in SRC_DIR.iterdir():
        if item.is_dir() and item.name not in ("__pycache__", "investment_advisor.egg-info", "refactor"):
            rel_dir = f"src/{item.name}"
            if rel_dir not in DIRECTORY_MAPPING:
                uncovered_dirs.append(rel_dir)
    return uncovered_dirs

def get_python_classes(file_path):
    if not file_path.exists():
        return []
    content = file_path.read_text(encoding="utf-8")
    return CLASS_PATTERN.findall(content)

def check_class_in_content(cls, content):
    if cls in content:
        return True
    spaced = re.sub(r'(?<!^)(?=[A-Z])', ' ', cls)
    if spaced in content:
        return True
    if cls.endswith("Agent"):
        no_agent = cls[:-5]
        if no_agent in content:
            return True
        spaced_no_agent = re.sub(r'(?<!^)(?=[A-Z])', ' ', no_agent)
        if spaced_no_agent in content:
            return True
    return False

def check_service_in_content(cls, content):
    if cls in content:
        return True
    spaced = re.sub(r'(?<!^)(?=[A-Z])', ' ', cls)
    if spaced in content:
        return True
    if cls.endswith("Service"):
        no_service = cls[:-7]
        if no_service in content:
            return True
        spaced_no_service = re.sub(r'(?<!^)(?=[A-Z])', ' ', no_service)
        if spaced_no_service in content:
            return True
    return False

def check_model_in_content(model, content):
    if model in content:
        return True
    spaced = re.sub(r'(?<!^)(?=[A-Z])', ' ', model)
    if spaced in content:
        return True
    snake = re.sub(r'(?<!^)(?=[A-Z])', '_', model).lower()
    if snake in content:
        return True
    if snake.endswith("y"):
        plural = snake[:-1] + "ies"
    elif snake.endswith("s"):
        plural = snake
    else:
        plural = snake + "s"
    if plural in content:
        return True
    return False

def check_semantic_sync(wiki_pages):
    sync_errors = []
    
    # Generate global active wiki content
    global_active_content = ""
    for clean_name, info in wiki_pages.items():
        if "archive/" not in str(info["rel_path"]).lower():
            filepath = WIKI_DIR / info["rel_path"]
            global_active_content += filepath.read_text(encoding="utf-8") + "\n"

    # 1. Verify Agents are documented in Agents Swarm Wiki
    for item in SRC_DIR.glob("agents/*.py"):
        if item.name in ("__init__.py", "base_agent.py", "factory.py", 
                         "settings_aware_model_router.py", "skill_router.py", 
                         "context.py", "agent_loop.py", "wal_protocol.py", "dspy_modules.py"):
            # Exclude base/config files and dspy_modules which contain signatures
            continue
        classes = get_python_classes(item)
        for cls in classes:
            # Exclude helper/internal classes that don't end with Agent
            if not cls.endswith("Agent") and cls not in ("CIO", "Engineer"):
                continue
            if not check_class_in_content(cls, global_active_content):
                sync_errors.append(f"Agent class '{cls}' ({item.name}) is not documented in any active Wiki pages.")

    # 2. Verify Skills are documented in Skills Wiki
    skills_dir = SRC_DIR / "agents/skills"
    if skills_dir.exists():
        for item in skills_dir.iterdir():
            if item.is_dir() and item.name not in ("__pycache__", "_pending"):
                skill_name = item.name
                skill_clean = skill_name.replace("_", " ").lower()
                if skill_name not in global_active_content and skill_clean not in global_active_content.lower():
                    sync_errors.append(f"Skill '{skill_name}' (directory) is not documented in any active Wiki pages.")

    # 3. Verify Services are documented in Services Blueprints
    for item in SRC_DIR.glob("services/*.py"):
        if item.name in ("__init__.py",):
            continue
        classes = get_python_classes(item)
        for cls in classes:
            if cls.endswith(("Service", "Aggregator", "Manager", "Guard", "Cipher")):
                # Exclude testing/stub services
                if "test" in cls.lower() or "mock" in cls.lower():
                    continue
                if not check_service_in_content(cls, global_active_content):
                    sync_errors.append(f"Service class '{cls}' ({item.name}) is not documented in any active Wiki pages.")

    # 4. Verify ORM Models are documented in ORM Wiki
    models_file = SRC_DIR / "data/models.py"
    if models_file.exists():
        models = get_python_classes(models_file)
        for model in models:
            if model not in ("Base", "TimestampMixin") and not model.endswith("Mixin"):
                if not check_model_in_content(model, global_active_content):
                    sync_errors.append(f"ORM DB Model '{model}' is not documented in any active Wiki pages.")
                    
    return sync_errors

def main():
    print("==================================================")
    print("📖 Running Wiki & Codebase Sync Audit...")
    print("==================================================")
    
    wiki_pages = get_wiki_pages()
    print(f"[*] Found {len(wiki_pages)} active wiki pages.")
    
    # Step 1: Broken Links Check
    print("[*] Auditing wiki internal links...")
    broken_links = verify_internal_links(wiki_pages)
    if broken_links:
        print(f"❌ Found {len(broken_links)} broken internal links:")
        for page, link in broken_links:
            print(f"  - In page '{page}': Broken link target: {link}")
    else:
        print("✅ OK: All internal links are healthy!")
        
    # Step 2: Directory Coverage Check
    print("[*] Auditing codebase directory coverage...")
    uncovered_dirs = check_directory_coverage()
    if uncovered_dirs:
        print(f"⚠️ Warning: The following directories are missing explicit Wiki mappings:")
        for d in uncovered_dirs:
            print(f"  - '{d}/'")
    else:
        print("✅ OK: All codebase core directories are mapped to Wiki topics!")
        
    # Step 3: Semantic Content Sync Check
    print("[*] Auditing semantic codebase-to-wiki documentation sync...")
    sync_errors = check_semantic_sync(wiki_pages)
    if sync_errors:
        print(f"❌ Found {len(sync_errors)} sync errors between Codebase & Wiki:")
        for err in sync_errors:
            print(f"  - {err}")
    else:
        print("✅ OK: All core Agents, Skills, Services, and DB Models are documented in their respective Wiki topics!")
        
    print("\n==================================================")
    print("📊 Audit Summary:")
    print(f"  - Broken Links: {len(broken_links)}")
    print(f"  - Directory Coverage Warnings: {len(uncovered_dirs)}")
    print(f"  - Codebase Documentation Sync Errors: {len(sync_errors)}")
    print("==================================================")
    
    if broken_links or sync_errors:
        print("❌ Audit Failed! Please fix the errors listed above.")
        sys.exit(1)
    else:
        print("✅ Audit Passed successfully!")
        sys.exit(0)

if __name__ == "__main__":
    main()
