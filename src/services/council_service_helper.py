    
    async def _call_agent_llm(self, agent_name: str, context: Dict[str, Any], tier: str = "smart", 
                              temperature: float = 0.7, max_tokens: int = 2000) -> str:
        """
        PAD Phase 2: Replace AgentFactory.create_*_agent().run() with direct gateway calls.
        Generic method to call LLM for any agent role.
        """
        try:
            # Get model from router
            model = self.model_router.get_model(self.user_id, tier)
            if not model:
                raise ValueError(f"Failed to route model for tier={tier}")
            
            # Build agent system prompt
            agent_prompts = {
                "Momentum": "You are a Momentum analyst. Analyze price trends and technical indicators.",
                "Fundamental": "You are a Fundamental analyst. Analyze financial statements and valuations.",
                "Risk": "You are a Risk manager. Assess portfolio risks and downsides.",
                "Sentiment": "You are a Sentiment analyst. Analyze market sentiment and investor psychology.",
                "Macro": "You are a Macro strategist. Assess macroeconomic trends and cyclical factors."
            }
            
            system_prompt = agent_prompts.get(agent_name, f"You are a {agent_name} analyst.")
            
            # Build messages
            messages = [
                Message(role="system", content=system_prompt),
                Message(role="user", content=json.dumps(context))
            ]
            
            # Create config
            config = LLMConfig(
                temperature=temperature,
                max_tokens=max_tokens,
                model=model
            )
            
            # Call gateway
            logger.debug(f"Council: Calling {agent_name} agent via {model}")
            response = await self.gateway.chat(messages, config)
            
            # Validate response is string (not HTML error)
            if not isinstance(response, str):
                raise ValueError(f"Unexpected response type from gateway: {type(response)}")
            
            return response
            
        except Exception as e:
            logger.error(f"Council: {agent_name} agent failed: {e}")
            raise
