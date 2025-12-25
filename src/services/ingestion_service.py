import os
import logging
import pandas as pd
# from src.data.ingestor import TradeIngestor # Deprecated

from src.analytics import update_daily_snapshot
from src.data.ingestors import IngestorFactory

logger = logging.getLogger("IngestionService")

class IngestionService:
    def __init__(self, db_path=None, user_id=None):
        self.db_path = db_path
        self.user_id = user_id
        # self.ingestor = TradeIngestor(db_path) # Deprecated


    def process_csv_upload(self, file_buffer, broker_type: str):
        """
        Handles CSV upload, saves to temp, ingests, and cleans up.
        """
        temp_filename = f"temp_upload_{self.user_id or 'anon'}.csv"
        try:
            with open(temp_filename, "wb") as f:
                f.write(file_buffer.getbuffer())
            
            logger.info(f"Ingesting CSV for user {self.user_id}, broker {broker_type}")
            
            
            # Read CSV
            df = pd.read_csv(temp_filename)

            # Get Ingestor from Factory
            ingestor = IngestorFactory.get_ingestor(broker_type, self.db_path)
            
            # Ingest
            ingestor.ingest(df, user_id=self.user_id)
            
            # Update Snapshot
            if self.user_id:
                update_daily_snapshot(self.db_path, user_id=self.user_id)
            
            return True, "匯入成功！ (Import Successful)"
            
        except Exception as e:
            logger.error(f"Ingestion failed: {e}")
            return False, f"匯入失敗: {str(e)}"
        finally:
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
