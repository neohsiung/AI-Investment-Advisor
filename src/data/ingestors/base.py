from abc import ABC, abstractmethod
import pandas as pd

class BaseIngestor(ABC):
    def __init__(self, db_path: str):
        self.db_path = db_path

    @abstractmethod
    def ingest(self, df: pd.DataFrame, user_id: str) -> None:
        """
        Ingest the dataframe into the database.
        """
        pass
