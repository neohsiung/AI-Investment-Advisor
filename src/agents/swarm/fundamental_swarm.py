from src.utils.logger import setup_logger
logger = setup_logger("FundamentalSwarm")

class FundamentalSubAgent(BaseAgent):
    """
    Generic Sub-Agent for Fundamental Swarm.
    Overrides `run()` to inject specific instructions.
    """
    def __init__(self, name: str, instruction: str, tier: str, **kwargs):
        super().__init__(name=name, prompt_path="prompts/common/default_system.j2", tier=tier, **kwargs)
        self.instruction = instruction

    def run(self, context: Any) -> str:
        ctx_dump = json.dumps(context, indent=2, ensure_ascii=False) if isinstance(context, dict) else str(context)
        prompt_data = {
            "user_request": f"{self.instruction}\n\nData Context:\n{ctx_dump}"
        }
        return self.run_tool_loop(context=prompt_data)

class FundamentalSwarm(RoleSwarm):
    """
    Fundamental Swarm replaces the old monolithic FundamentalAgent.
    Distributes processing across 3 sub-agents to parallelize revenue extraction, risk scanning, and valuation.
    """
    def __init__(self, use_cache=True, ttl_hours=None, **kwargs):
        ttl = ttl_hours if ttl_hours is not None else 24
        
        user_id = kwargs.pop("user_id", "system")
        super().__init__(name="FundamentalSwarm", use_cache=use_cache, ttl_hours=ttl, user_id=user_id, **kwargs)
        
        # Initialize Sub-Agents
        self.revenue_extractor = FundamentalSubAgent(
            name="RevenueExtractor", 
            instruction="分析財務數據與尋找營收增長點與利潤率趨勢 (Extract revenue and margin trends). Focus only on profitability and growth vectors.",
            tier="smart",
            user_id=user_id,
            use_cache=use_cache,
            ttl_hours=ttl
        )
        self.risk_scanner = FundamentalSubAgent(
            name="RiskFactorScanner", 
            instruction="掃描新聞與財報中的風險因子 (Scan for risk factors). If any critical risks are found affecting bankruptcy or massive drops, MUST start your response with 'CRITICAL DANGER'. Otherwise, summarize risks.",
            tier="fast",
            user_id=user_id,
            use_cache=use_cache,
            ttl_hours=ttl
        )
        self.valuation_modeler = FundamentalSubAgent(
            name="ValuationModeler", 
            instruction="建立估值模型，綜合判斷當前價格是否合理 (Build valuation model and determine if current price is fair based on fundamentals, margins, and macro).",
            tier="adv",
            user_id=user_id,
            use_cache=use_cache,
            ttl_hours=ttl
        )
        
        # Register to RoleSwarm
        self.register_agent("col_smart", self.revenue_extractor)
        self.register_agent("col_fast", self.risk_scanner)
        self.register_agent("col_adv", self.valuation_modeler)
        
    def run(self, context: Any) -> str:
        tickers = context.get("tickers", [])
        single_ticker = context.get("ticker", "UNKNOWN")
        
        if not tickers and single_ticker != "UNKNOWN":
            tickers = [single_ticker]
            
        market_data = context.get("market_data", {})
        reports = []
        sc_service = SupplyChainService()
        
        for t in tickers:
            t_data = market_data.get(t, {}) if market_data else context
            
            fin = t_data.get("financials", {})
            news = t_data.get("news", [])
            
            sc_info = sc_service.get_shortage_premium(t)
            shortage_narrative = sc_info.get("narrative", "")
            
            swarm_context = {
                "ticker": t,
                "financials": fin,
                "news": news,
                "shortage_premium": shortage_narrative,
            }
            
            wrapped_ctx = {
                "user_request": f"Analyze fundamentals for {t}.",
                "data": swarm_context
            }
            
            try:
                # Execution via Swarm Orchestrator
                res = super().run(wrapped_ctx)
                reports.append(f"### {t} Fundamental Swarm Analysis\n{res}")
            except Exception as e:
                logger.error(f"FundamentalSwarm execution failed for {t}: {e}")
                reports.append(f"### {t} Analysis\nError: {e}")
                
        return "\n\n".join(reports)
