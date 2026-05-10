from .base import BaseIngestor
import typing

_REGISTRY: typing.Dict[str, typing.Type[BaseIngestor]] = {}

def register_ingestor(name: str):
    """Decorator to register an ingestor class."""
    def wrapper(cls):
        _REGISTRY[name.lower()] = cls
        return cls
    return wrapper

class IngestorFactory:
    @staticmethod
    def get_ingestor(broker_name: str, db_path: str) -> BaseIngestor:
        if not _REGISTRY:
            # Lazy import to populate registry and avoid circular deps
            from . import strategies
            
        broker = broker_name.lower()
        cls = _REGISTRY.get(broker)
        if cls:
            return cls(db_path)
        
        # Fallback: check if it's already there but case-mismatch
        for k, v in _REGISTRY.items():
            if k == broker:
                return v(db_path)
                
        raise ValueError(f"Unknown broker: {broker_name}")
