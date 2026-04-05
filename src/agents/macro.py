import json
from .base_agent import BaseAgent

class MacroAgent(BaseAgent):
    def __init__(self, use_cache=True, ttl_hours=None, **kwargs):
        ttl = ttl_hours if ttl_hours is not None else 24
        tier = kwargs.pop('tier', 'smart')
        super().__init__(name="Macro", prompt_path="prompts/macro_agent.txt", use_cache=use_cache, ttl_hours=ttl, tier=tier, **kwargs)

    async def run(self, context):
        """
        context: {
            "macro_data": {...}
        }
        """
        prompt_data = {
            "macro_data": json.dumps(context.get("macro_data", {}), indent=2, ensure_ascii=False)
        }
        
        # Inject Structural Cooling Context
        macro_data = context.get("macro_data", {})
        mfg_pmi = macro_data.get("ISM_Mfg_PMI", {}).get("value")
        svc_pmi = macro_data.get("ISM_Svc_PMI", {}).get("value")
        
        structural_cooling_signal = False
        cooling_narrative = ""
        
        # Dynamic Threshold calculation based on historical data (Rule #8)
        # 根據歷史數據計算動態閾值（規則 #8）
        mfg_history = macro_data.get("ISM_Mfg_PMI", {}).get("history", [])
        svc_history = macro_data.get("ISM_Svc_PMI", {}).get("history", [])
        
        mfg_threshold = sum(mfg_history) / len(mfg_history) if mfg_history else 50.0
        svc_threshold = sum(svc_history) / len(svc_history) if svc_history else 52.0
        
        if mfg_pmi is not None and svc_pmi is not None:
            if mfg_pmi < mfg_threshold and svc_pmi > svc_threshold:
                structural_cooling_signal = True
                cooling_narrative = (
                    f"**Structural Cooling Detected**: Manufacturing PMI ({mfg_pmi}) is below its moving average ({mfg_threshold:.1f}), "
                    f"while Services PMI ({svc_pmi}) is robust and above its moving average ({svc_threshold:.1f}). "
                    "This indicates a structural slowdown in goods rather than a broad recession. "
                    "Capital allocation should favor software, services, and productivity-enhancing assets."
                )
        
        prompt_data["structural_cooling_context"] = cooling_narrative
        
        # Inject Labor Cooling Context (Milestone 1.3)
        labor_cooling_ind = macro_data.get("Labor_Cooling_Indicator", {}).get("value", False)
        labor_narrative = ""
        if labor_cooling_ind:
            labor_narrative = (
                 "**Labor Market Cooling Detected**: Employment growth is slowing but still positive (Cooling vs. Freezing). "
                 "This gives the Fed flexibility to pause or ease, rather than an emergency cut. "
                 "Favor defensive productivity moats."
            )
        prompt_data["labor_cooling_context"] = labor_narrative
        
        # Inject CPI & FOMC Context (v5.0)
        cpi_val = macro_data.get("CPI", {}).get("value")
        nfp_val = macro_data.get("NFP", {}).get("value")
        fed_funds = macro_data.get("FedFunds", {}).get("value")
        
        macro_summary = (
            f"- **CPI (Inflation)**: {cpi_val if cpi_val else 'N/A'}\n"
            f"- **NFP (Employment)**: {nfp_val if nfp_val else 'N/A'}\n"
            f"- **Fed Funds Rate (FOMC Context)**: {fed_funds if fed_funds else 'N/A'}%\n"
        )
        prompt_data["macro_indicator_summary"] = macro_summary

        return await self.run_tool_loop(context=prompt_data)

        if "Mock response" in response:
            return f"""
### 全球總經環境分析
*   **週期階段**: 放緩 (Slowdown)
*   **結構性降溫**: {"是 (Yes) - 偏好軟體服務業" if structural_cooling_signal else "否 (No)"}
*   **就業市場降溫**: {"是 (Yes) - Fed 具備彈性" if labor_cooling_ind else "否 (No)"}
*   **Fed 動向**: Data Dependent
*   **關鍵數據解讀**:
    *   製造業 PMI: {mfg_pmi if mfg_pmi else 'N/A'}
    *   服務業 PMI: {svc_pmi if svc_pmi else 'N/A'}
    *   CPI (通膨): {cpi_val if cpi_val else 'N/A'}
    *   NFP (非農): {nfp_val if nfp_val else 'N/A'}
*   **配置建議**:
    *   **看好板塊**: 軟體服務 (Software), 生產力工具 (Productivity)
    *   **避開板塊**: 傳統製造業 (Traditional Manufacturing)
*   **結論**: {cooling_narrative if structural_cooling_signal else '維持中性配置 (Neutral)'}
    *   **附加說明**: {labor_narrative if labor_cooling_ind else ''}
    *   **Fed 政策環境**: 目前利率水平 {fed_funds if fed_funds else 'N/A'}%，需關注降息預期與通膨路徑。
"""
        return response
