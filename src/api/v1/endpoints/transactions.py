from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from typing import List, Dict, Any
import io
import pandas as pd
from src.api.v1.router import get_current_user_id
from src.api.v1.schemas.transaction_schemas import (
    TransactionListResponse, TransactionRecord, 
    TransactionCreateRequest, TransactionActionResponse
)
from src.services.transaction_service import TransactionService
from src.utils.logger import setup_logger

logger = setup_logger("API_Transactions")
router = APIRouter()

def get_transaction_service(user_id: str = Depends(get_current_user_id)) -> TransactionService:
    return TransactionService(user_id=user_id)

@router.get("", response_model=TransactionListResponse)
async def get_transactions(service: TransactionService = Depends(get_transaction_service)):
    """獲取使用者的所有交易紀錄"""
    try:
        df = service.get_transactions()
        records = []
        for _, row in df.iterrows():
            records.append(TransactionRecord(
                id=str(row.get('id', 'N/A')),
                ticker=str(row.get('ticker', '')).upper(),
                action=str(row.get('action', '')).upper(),
                quantity=float(row.get('quantity', 0)),
                price=float(row.get('price', 0)),
                fees=float(row.get('fees', 0)),
                date=str(row.get('trade_date', ''))
            ))
        return {"status": "success", "data": records}
    except Exception as e:
        logger.error(f"Error fetching transactions: {e}")
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("", response_model=TransactionActionResponse)
async def add_transaction(
    payload: TransactionCreateRequest,
    service: TransactionService = Depends(get_transaction_service)
):
    """手動新增交易紀錄"""
    try:
        success, msg = service.add_manual_trade(
            ticker=payload.ticker,
            date_str=payload.date,
            action=payload.action,
            quantity=payload.quantity,
            price=payload.price,
            fees=payload.fees
        )
        if not success:
            raise HTTPException(status_code=400, detail="交易新增失敗，請檢查輸入數據是否正確。")
        return {"status": "success", "message": msg}
    except Exception as e:
        logger.error(f"Error adding transaction: {e}")
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail="Internal server error")

@router.post("/upload-csv", response_model=TransactionActionResponse)
async def upload_csv(
    file: UploadFile = File(...),
    user_id: str = Depends(get_current_user_id)
):
    """批次匯入 CSV 交易紀錄"""
    try:
        content = await file.read()
        df = pd.read_csv(io.BytesIO(content))
        
        required_cols = ["date", "ticker", "action", "quantity", "price"]
        for col in required_cols:
            if col not in df.columns:
                raise HTTPException(status_code=400, detail=f"遺失必要欄位: {col}")
        
        service = TransactionService(user_id=user_id)
        count = 0
        for _, row in df.iterrows():
            try:
                await service.create_transaction(
                    ticker=str(row["ticker"]).upper(),
                    action=str(row["action"]).upper(),
                    quantity=float(row["quantity"]),
                    price=float(row["price"]),
                    fees=float(row.get("fees", 0)),
                    trade_date=str(row["date"])
                )
                count += 1
            except Exception as row_err:
                logger.warning(f"Failed to import CSV row: {row_err}")
                continue

        return {"status": "success", "message": f"成功匯入 {count} 筆交易紀錄"}
    except Exception as e:
        logger.error(f"CSV upload error: {e}")
        if isinstance(e, HTTPException): raise e
        raise HTTPException(status_code=500, detail="Internal server error")
