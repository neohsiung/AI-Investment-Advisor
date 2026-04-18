#!/usr/bin/env python3
"""
Wiki Tree Sync Auditor
確保專案 src, frontend, k8s, tests 等核心模組皆有對應的 Wiki 說明文件。
納入 8大分類拓樸 防腐機制。
"""

import os
from pathlib import Path

# 定義專案根目錄
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
WIKI_DIR = PROJECT_ROOT / "wiki"

# 定義映射矩陣 (Repo Node -> Wiki Tree)
# 相對 PROJECT_ROOT 的路徑
MAPPING_MATRIX = {
    # Backend & Auth
    "src/agents": "03_Backend_Intelligence/代理人戰略協定-Agent-Swarm-Protocol.md",
    "src/agents/skills": "03_Backend_Intelligence/Agent技能系統-Agent-Skills-System.md",
    "src/api": "03_Backend_Intelligence/API端點規範-API-Endpoints-Standard.md",
    "src/services": "03_Backend_Intelligence/服務層開發指南-Service-Layer-Blueprints.md",
    "src/infrastructure/llm": "03_Backend_Intelligence/多模型多提供商設計-Multi-Provider-Multi-Model-Design.md",
    "src/workflow": "03_Backend_Intelligence/任務規劃與執行引擎-Task-Planning-Engine.md",
    
    # Data Layer
    "src/repositories": "04_Data_Storage/Repository層指南-Repository-Layer-Guide.md",
    "src/domain": "04_Data_Storage/資料與領域模型-Data-Domain-Models.md",
    
    # Frontend
    "frontend": "02_Frontend_UX/前端架構與UX層-Frontend-UX-Layer.md",
    
    # QA
    "tests": "05_Quality_Assurance/測試與外部服務整合-Testing-External-Services.md",
    
    # DevOps / SRE
    "k8s": "06_SRE_Observability/雲端部署-Deployment-GCP-CloudRun.md",
    "docker-compose.prod.yml": "06_SRE_Observability/C端-SAAS-技術選型深度解析-B2C-Tech-Stack-Deep-Dive.md"
}

def check_mappings():
    """驗證 MAPPING_MATRIX 中的每項映射"""
    errors = 0
    warnings = 0
    
    print("=== 全域 Wiki Tree Mapping Audit ===\n")
    
    # 檢查矩陣定義的 Code Directory 與 Wiki 文件是否存在
    for code_node, wiki_file in MAPPING_MATRIX.items():
        code_path = PROJECT_ROOT / code_node
        wiki_path = WIKI_DIR / wiki_file
        
        if not code_path.exists():
            print(f"⚠️ 警告 (Code Missing): Mapping Matrix 包含已不存在的程式碼目錄 '{code_node}'")
            warnings += 1
            
        if not wiki_path.exists():
            print(f"❌ 錯誤 (Wiki Missing): '{code_node}' 映射的 Wiki 文件不存在 -> {wiki_file}")
            errors += 1
        else:
            print(f"✅ OK: '{code_node}' -> '{wiki_file}'")
            
    print("\n=== Orphan Analysis ===")
    
    # 簡化版 Orphan 檢查: 檢查 src/ 下的第一層是否被覆蓋
    src_dir = PROJECT_ROOT / "src"
    ignore_dirs = ["__pycache__", "config", "styles"]
    
    if src_dir.exists():
        src_dirs = [d for d in os.listdir(src_dir) if (src_dir / d).is_dir() and d not in ignore_dirs]
        for d in src_dirs:
            # Check if this top level src dir is mapped
            full_route = f"src/{d}"
            if full_route not in MAPPING_MATRIX:
                print(f"⚠️ 斷軌警告 (Orphan): 原始碼目錄 '{full_route}/' 在 Wiki 中缺乏明確的映射文件。")
                warnings += 1

    print("\n=== Audit Summary ===")
    print(f"Errors: {errors}")
    print(f"Warnings: {warnings}")
    
    if errors > 0:
        print("\nAudit Failed! 請修正上述錯誤。")
        return False
    else:
        print("\nAudit Passed!")
        return True

if __name__ == "__main__":
    success = check_mappings()
    exit(0 if success else 1)
