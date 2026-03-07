import os
import json
import typing
from typing import List, Dict, Tuple, Any, Optional, Callable, Dict, List, Tuple, Any, Optional, Callable

# Domain & Infrastructure
try:
    import dspy
    from dspy.teleprompt import BootstrapFewShot
except (ImportError, AttributeError):
    dspy = None
    BootstrapFewShot = None

from src.agents.dspy_modules import MomentumSignature
from src.repositories.feedback_repository import AlchemyFeedbackRepository
from src.domain.entities import FeedbackExample

class OptimizerPipeline:
    """
    優化管道 (Optimizer Pipeline)
    
    負責從儲存庫中提取高質量的回饋數據，並使用 DSPy 的 BootstrapFewShot 算法
    來優化 Agent 的 Prompt Signature。這是自我修正迴圈的核心組件。
    
    Attributes:
        db_path (str): 資料庫路徑
        repo (FeedbackRepository): 回饋數據存取介面
    """
    def __init__(self, db_path=None, model_name="gemini-1.5-pro"):
        self.db_path = db_path  # None will use environment DB_URL or DB_TYPE
        self.repo = AlchemyFeedbackRepository(db_path)
        
        # Setup DSPy LM
        # In real usage, we should use the API Key from settings or env
        api_key = os.getenv("API_KEY")
        if not api_key:
             # Fallback or raise, for now assume env is set or passed
             pass

    def load_training_data(self, agent_name="Momentum", k=20) -> List[Any]: # Avoid dspy.Example if dspy is None
        """
        載入訓練數據 (Load Training Data)
        
        從 Repository 獲取分數較高的範例，並轉換為 DSPy 的 Example 格式。
        
        Args:
            agent_name (str): Agent 名稱
            k (int): 最大樣本數
            
        Returns:
            List[dspy.Example]: DSPy 訓練集
        """
        if dspy is None:
            print("DSPy not available (requires Python 3.9+). Skipping training data load.")
            return []

        # Fetch positive examples from Repository (Domain Entities)
        # 我們只取分數 > 0.1 的正向範例
        domain_examples = self.repo.get_training_examples(agent_name, min_score=0.1, limit=k)
        
        trainset = []
        for ex in domain_examples:
            try:
                # 建構 DSPy Example
                # Context 來自 SecurityContext (轉為 JSON string 以符合 Signature 定義)
                # Analysis/Response 來自 response_text
                # Signal 來自 signal enum
                
                # 注意: MomentumSignature 定義了 input: context, output: analysis, signal, confidence
                # 但我們的 stored response 是一個非結構化的文字 (analysis)。
                # 為了讓 BootstrapFewShot 運作，我們需要將現有的回應映射到 Signature 的欄位。
                
                # 這裡做一個假設: response_text 主要是 analysis。
                # Signal 我們從 Entity 中明確獲取。
                
                dsp_ex = dspy.Example(
                    context=ex.context.to_json(),
                    analysis=ex.response_text,
                    signal=ex.signal.value, 
                    confidence="0.9" # Placeholder, 因為我們沒有儲存 confidence
                ).with_inputs('context')
                
                trainset.append(dsp_ex)
            except Exception as e:
                print(f"Skipping example: {e}")
                
        print(f"Loaded {len(trainset)} training examples for {agent_name}.")
        return trainset

    def optimize_momentum_agent(self, trainset):
        """
        優化 Momentum Agent (Optimize Momentum Agent)
        
        使用 BootstrapFewShot 進行 Few-Shot Learning 優化。
        """
        if not dspy or not trainset:
            print("DSPy not available or no training data.")
            return None

        # 定義評估指標 (Metric Function)
        def validate_response(example, pred, trace=None):
            # 簡單驗證: 信號是否一致
            return example.signal == pred.signal

        print("Starting optimization (BootstrapFewShot)...")
        # max_bootstrapped_demos: 我們希望從訓練集中選出多少個最佳範例作為 Prompt 的 Demo
        teleprompter = BootstrapFewShot(metric=validate_response, max_bootstrapped_demos=4)
        
        # Compile (進行優化)
        # 我們優化一個簡單的 ChainOfThought 模組
        program = dspy.ChainOfThought(MomentumSignature)
        compiled_module = teleprompter.compile(program, trainset=trainset)
        
        # 儲存優化後的模組
        save_path = "prompts/optimized/momentum_optimized.json"
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        compiled_module.save(save_path)
        print(f"Optimized module saved to {save_path}")
        return compiled_module
