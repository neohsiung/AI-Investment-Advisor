import logging
import sys
from pythonjsonlogger import jsonlogger

# To avoid adding multiple handlers if setup_logger is called multiple times
_loggers = {}

def setup_logger(name, level=logging.INFO):
    """
    設定並回傳一個 Logger 實例
    此版本已升級為結構化 JSON 日誌 (Structured JSON Logging)，
    符合 SaaS Best Practices，並為 OpenTelemetry 整合做好準備。
    """
    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)

    # 避免重複添加 Handler
    if not logger.handlers:
        logger.setLevel(level)

        # 輸出到 stdout，方便被 subprocess 捕獲
        handler = logging.StreamHandler(sys.stdout)

        # 建立 JSON Formatter，並指定標準化與 OTel 所需的關鍵欄位
        formatter = jsonlogger.JsonFormatter(
            '%(asctime)s %(levelname)s %(name)s %(filename)s %(lineno)d %(message)s',
            datefmt='%Y-%m-%dT%H:%M:%SZ',  # ISO-8601 UTC string
            rename_fields={"levelname": "level", "asctime": "timestamp", "name": "service.name"}
        )

        handler.setFormatter(formatter)
        logger.addHandler(handler)

    _loggers[name] = logger
    return logger
