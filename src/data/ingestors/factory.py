from .base import BaseIngestor
from .strategies import SimpleIngestor, RobinhoodIngestor, IBKRIngestor

class IngestorFactory:
    @staticmethod
    def get_ingestor(broker_name: str, db_path: str) -> BaseIngestor:
        broker = broker_name.lower()
        if broker == 'simple':
            return SimpleIngestor(db_path)
        elif broker == 'robinhood':
            return RobinhoodIngestor(db_path)
        elif broker == 'ibkr':
            return IBKRIngestor(db_path)
        else:
            raise ValueError(f"Unknown broker: {broker_name}")
