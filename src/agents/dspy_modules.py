try:
    import dspy
    # Verify it's the correct DSPy (LLM framework) by checking for Signature
    if not hasattr(dspy, 'Signature'):
        raise ImportError("Probably wrong dspy package")
except ImportError:
    # Mock DSPy for local compatibility (Python < 3.9)
    class MockDSPy:
        class Signature: pass
        @staticmethod
        def InputField(**kwargs): return None
        @staticmethod
        def OutputField(**kwargs): return None
    dspy = MockDSPy

class MomentumSignature(dspy.Signature):
    """
    You are a Momentum Trading Specialist. 
    Analyze the provided market data (Price, RSI, MACD) to determine the short-term trend strength.
    Provide a clear BUY, SELL, or HOLD signal with reasoning.
    """
    context = dspy.InputField(desc="JSON string containing ticker, price, and technical indicators (RSI, MACD).")
    analysis = dspy.OutputField(desc="A detailed analysis explaining the technical setup.")
    signal = dspy.OutputField(desc="One of: BUY, SELL, HOLD")
    confidence = dspy.OutputField(desc="Confidence score between 0.0 and 1.0")

class FundamentalSignature(dspy.Signature):
    """
    You are a Fundamental Investment Analyst (Value Investing).
    Analyze the financial data (PE, Revenue Growth, Margins) to determine the intrinsic value and long-term viability.
    """
    context = dspy.InputField(desc="JSON string containing financial metrics (PE, Market Cap, Growth) and news headlines.")
    analysis = dspy.OutputField(desc="A detailed analysis of the company's fundamental health.")
    signal = dspy.OutputField(desc="One of: BUY, SELL, HOLD")

class CIOSignature(dspy.Signature):
    """
    You are the Chief Investment Officer (CIO).
    Synthesize reports from Momentum, Fundamental, and Macro agents to make a final portfolio decision.
    Balance risk and reward.
    """
    macro_report = dspy.InputField(desc="Summary of macroeconomic conditions.")
    momentum_report = dspy.InputField(desc="Technical analysis report.")
    fundamental_report = dspy.InputField(desc="Fundamental analysis report.")
    leverage_info = dspy.InputField(desc="Current portfolio leverage status.")
    
    final_decision = dspy.OutputField(desc="Comprehensive investment strategy and final allocation decision.")
