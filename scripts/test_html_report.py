import os
from src.services.reporting_service import ReportingService

def test_html_generation():
    service = ReportingService()
    
    mock_markdown = """
    # 🦁 週報：戰略復盤與記憶鞏固 (Weekly Strategy & Memory Consolidation)
    日期: 2024-10-27
    
    ## 0. 產業大局觀 (Thematic & Big Picture)
    > 系統追蹤的核心主題與供應鏈動態。
    - **實體 AI (Physical AI)**: TSLA, GOOG
    
    ## 1. 記憶鏈回顧 (Memory Chain Review)
    > System 2 對本週 System 1 決策的審計，並糾正敘事偏離。
    
    ### 上週敘事偏離復盤 (Narrative Drift Analysis)
    - **準確度評分 (Accuracy)**: 8/10
    - **偏離理由 (Rationale)**: 提早看空，但市場情緒依然高漲。
    - **本週修正建議 (Correction)**: 保持中立，觀察 CPI。
    
    - **本週戰術總結**: 本週我們在 NVDA 財報前進行了兩次加碼，目前看來是正確的。
    
    ## 2. 議會深度審議 (Council Deep Dive)
    ### 關鍵持倉再評估 (Positions under Review)
    #### NVDA
    - **Long-Term Thesis Check**:
      - 🟢 **Fundamental**: AI 晶片需求持續強勁。
      - 🔴 **Risk**: 估值偏高，需注意回檔風險。
    - **Verdict**: **Stay the Course**
    
    ## 3. 下週戰略指引 (The Playbook)
    - **Regime**: Growth
    - **Focus**: 下週關注核心 PCE 數據。
    
    | 資產類別 | 建議配置比例 | 備註 |
    | :--- | :--- | :--- |
    | 股票 (Equity) | 70% | 偏向 AI 基礎設施 |
    | 現金 (Cash) | 30% | 保留彈性 |
    """
    
    try:
        html = service.generate_professional_html(mock_markdown)
        with open("sample_report.html", "w", encoding="utf-8") as f:
            f.write(html)
        print("Successfully generated sample_report.html")
    except Exception as e:
        print(f"Failed: {e}")

if __name__ == "__main__":
    test_html_generation()
