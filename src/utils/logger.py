import logging
import sys

def setup_logger(name, level=logging.INFO):
    """
    設定並回傳一個 Logger 實例
    格式: 2023-10-27 10:00:01 - INFO - [Name] - Message
    """
    logger = logging.getLogger(name)
    
    # 避免重複添加 Handler
    if not logger.handlers:
        logger.setLevel(level)
        
        # 輸出到 stdout，方便被 subprocess 捕獲
        handler = logging.StreamHandler(sys.stdout)
        
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - [%(name)s] - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger
