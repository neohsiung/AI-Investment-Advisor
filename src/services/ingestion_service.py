import os
import logging
import pandas as pd
# from src.data.ingestor import TradeIngestor # Deprecated

from src.services.analytics_service import update_daily_snapshot
from src.data.ingestors import IngestorFactory

logger = logging.getLogger("IngestionService")

class IngestionService:
    """
    Service for handling data ingestion, specifically CSV uploads for trade history.
    資料匯入服務：負責處理數據匯入，特別是交易歷史的 CSV 上傳。
    """
    def __init__(self, db_path: str = None, user_id: str = None) -> None:
        """
        Initialize the ingestion service.
        初始化匯入服務。
        """
        self.db_path = db_path
        self.user_id = user_id
        # self.ingestor = TradeIngestor(db_path) # Deprecated


    def process_csv_upload(self, file_buffer: Any, broker_type: str) -> tuple[bool, str]:
        """
        Process a CSV file upload, ingest data, and update the daily snapshot.
        處理 CSV 檔案上傳、匯入數據並更新每日快照。
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
