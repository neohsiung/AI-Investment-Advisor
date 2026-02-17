from typing import List
from src.domain.interfaces import FeedbackRepository
from src.domain.entities import FeedbackExample, SecurityContext, SignalType
from src.data.feedback_store import FeedbackStore
import json
from datetime import datetime

class FeedbackRepositoryImpl(FeedbackRepository):
    """
    Adapter implementation of FeedbackRepository using SQLAlchemy (via FeedbackStore).
    """
    def __init__(self, db_path=None):
        self.store = FeedbackStore(db_path)

    def save(self, example: FeedbackExample) -> None:
        # Convert Domain Entity to Infrastructure DTOs
        json_context = example.context.to_json()
        embedding = None # We generate this elsewhere or skip for now
        
        self.store.save_example(
            agent_name=example.agent_name,
            context_embedding=embedding,
            context_text=json_context,
            response_text=example.response_text,
            outcome_score=example.outcome_score
        )

    def get_training_examples(self, agent_name: str, min_score: float, limit: int) -> List[FeedbackExample]:
        raw_rows = self.store.get_examples_for_training(agent_name, min_score, limit)
        examples = []
        for row in raw_rows:
            # Reconstruct Entity
            # Note: We need to parse json_context back to SecurityContext
            # For strictness we should, but for now we might leave context as basic dict inside if just needed for DSPy.
            # But the interface says SecurityContext.
            
            try:
                ctx_dict = json.loads(row['context'])
                sec_ctx = SecurityContext(
                    ticker=ctx_dict.get('ticker', 'UNKNOWN'),
                    date=datetime.fromisoformat(ctx_dict.get('date')) if ctx_dict.get('date') else datetime.now(),
                    price=ctx_dict.get('price', 0.0),
                    indicators=ctx_dict.get('indicators', {}),
                    news_headlines=ctx_dict.get('news', []),
                    financials=ctx_dict.get('financials', {})
                )
                
                # Heuristic signal parse if not stored
                signal_str = "HOLD"
                if "BUY" in row['response']: signal_str = "BUY"
                elif "SELL" in row['response']: signal_str = "SELL"
                
                examples.append(FeedbackExample(
                    id=None,
                    agent_name=agent_name,
                    context=sec_ctx,
                    response_text=row['response'],
                    signal=SignalType(signal_str),
                    outcome_score=row['score']
                ))
            except Exception as e:
                print(f"Error reconstructing entity: {e}")
                continue
                
        return examples
