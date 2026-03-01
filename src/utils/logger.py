import logging
import sys
import os
from pythonjsonlogger import jsonlogger

# OpenTelemetry Logging Imports (OTel 1.25.0+ stable paths)
try:
    from opentelemetry._logs import set_logger_provider
    try:
        # Modern stable path (1.25.0+)
        from opentelemetry.exporter.otlp.proto.grpc.logs_exporter import OTLPLogExporter
    except ImportError:
        # Legacy/internal path
        from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    
    try:
        # Modern stable SDK path
        from opentelemetry.sdk.logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk.logs.export import BatchLogRecordProcessor
    except ImportError:
        # Legacy/internal SDK path
        from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
        from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
        
    from opentelemetry.sdk.resources import Resource
    OTEL_LOGGING_AVAILABLE = True
except ImportError:
    OTEL_LOGGING_AVAILABLE = False

# To avoid adding multiple handlers if setup_logger is called multiple times
_loggers = {}
_logger_provider_initialized = False

def setup_logger(name, level=logging.INFO):
    """
    設定並回傳一個 Logger 實例
    此版本已升級為結構化 JSON 日誌 (Structured JSON Logging)，
    並整合 OpenTelemetry OTLP Exporter 以支援 SigNoz 收集。
    """
    global _logger_provider_initialized

    if name in _loggers:
        return _loggers[name]

    logger = logging.getLogger(name)
    # Enable propagation in tests for caplog compatibility
    # 偵測是否在測試環境，若是則允許傳回 Root Logger 供 pytest caplog 捕獲
    is_testing = "pytest" in sys.modules or os.getenv("PYTEST_CURRENT_TEST")
    logger.propagate = bool(is_testing)

    # 避免重複添加 Handler
    if not logger.handlers:
        logger.setLevel(level)

        # 1. Standard Output Handler (JSON Formatted)
        # 輸出到 stdout，方便被 subprocess 捕獲
        stdout_handler = logging.StreamHandler(sys.stdout)
        
        # 建立 JSON Formatter，並指定標準化與 OTel 所需的關鍵欄位
        formatter = jsonlogger.JsonFormatter(
            '%(asctime)s %(levelname)s %(name)s %(filename)s %(lineno)d %(message)s',
            datefmt='%Y-%m-%dT%H:%M:%SZ',  # ISO-8601 UTC string
            rename_fields={"levelname": "level", "asctime": "timestamp", "name": "service.name"}
        )
        stdout_handler.setFormatter(formatter)
        logger.addHandler(stdout_handler)

        # 2. OpenTelemetry OTLP Log Handler (Optional)
        otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
        if OTEL_LOGGING_AVAILABLE and otel_endpoint:
            try:
                if not _logger_provider_initialized:
                    service_name = os.getenv("OTEL_SERVICE_NAME", "investment-advisor")
                    resource = Resource.create({"service.name": service_name})
                    
                    logger_provider = LoggerProvider(resource=resource)
                    set_logger_provider(logger_provider)
                    
                    exporter = OTLPLogExporter(endpoint=otel_endpoint, insecure=True)
                    logger_provider.add_log_record_processor(BatchLogRecordProcessor(exporter))
                    _logger_provider_initialized = True
                
                # Add OTel Logging Handler to this logger
                otel_handler = LoggingHandler(level=level)
                logger.addHandler(otel_handler)
                # logger.info(f"OTLP Log Handler added for {name}")
            except Exception as e:
                # Fallback to stdout only if OTel fails
                print(f"Failed to initialize OTel logging for {name}: {e}", file=sys.stderr)

    _loggers[name] = logger
    return logger
