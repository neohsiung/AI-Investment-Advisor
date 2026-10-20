"""The shared declarative Base, in its own module so ORM files can import it without importing src.data.models.
共用的 declarative Base 獨立成模組，讓 ORM 檔案不必匯入 src.data.models，避免循環匯入。"""
from sqlalchemy.orm import declarative_base

Base = declarative_base()
