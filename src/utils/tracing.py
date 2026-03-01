import os
import logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.resources import Resource
try:
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
    OTEL_EXPORTER_AVAILABLE = True
except ImportError:
    OTEL_EXPORTER_AVAILABLE = False

try:
    from opentelemetry.instrumentation.requests import RequestsInstrumentor
    from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
    from opentelemetry.instrumentation.psycopg2 import Psycopg2Instrumentor
    OTEL_INSTRUMENTATION_AVAILABLE = True
except ImportError:
    OTEL_INSTRUMENTATION_AVAILABLE = False

logger = logging.getLogger(__name__)

def init_tracing(service_name: str):
    """
    Initialize OpenTelemetry tracing for the service.
    初始化服務的 OpenTelemetry 追蹤。
    """
    endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if not endpoint:
        logger.info(f"OTEL_EXPORTER_OTLP_ENDPOINT not set. Tracing disabled for {service_name}.")
        return

    # Create Resource
    resource = Resource.create({
        "service.name": service_name,
        "service.version": "1.1.0",
        "deployment.environment": os.getenv("ENV", "development")
    })

    # Initialize TracerProvider
    provider = TracerProvider(resource=resource)
    trace.set_tracer_provider(provider)

    # Initialize OTLP Exporter (gRPC)
    if not OTEL_EXPORTER_AVAILABLE:
        logger.warning(f"OTLP Exporter not available. Tracing partially disabled for {service_name}.")
        return

    try:
        otlp_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
        span_processor = BatchSpanProcessor(otlp_exporter)
        provider.add_span_processor(span_processor)
        logger.info(f"OpenTelemetry Tracing initialized for {service_name} -> {endpoint}")
    except Exception as e:
        logger.error(f"Failed to initialize OTLP Exporter: {e}")
        return

    # Auto-instrumentation for Trace Propagation
    if OTEL_INSTRUMENTATION_AVAILABLE:
        try:
            RequestsInstrumentor().instrument()
            HTTPXClientInstrumentor().instrument()
            Psycopg2Instrumentor().instrument()
            logger.info("Auto-instrumentation for 'requests', 'httpx', and 'psycopg2' enabled.")
        except Exception as e:
            logger.warning(f"Failed to auto-instrument libraries: {e}")
    else:
        logger.info("Auto-instrumentation libraries not available. Skipping.")

    # Note: SQLAlchemy instrumentation is handled in get_db_engine to avoid circular imports
    return trace.get_tracer(__name__)

def trace_external_call(provider_name: str):
    """
    Decorator to wrap external API calls in a span.
    裝飾器：將外部 API 調用封裝在 span 中。
    """
    def decorator(func):
        from functools import wraps
        @wraps(func)
        def wrapper(*args, **kwargs):
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span(f"{provider_name}.{func.__name__}") as span:
                span.set_attribute("provider.name", provider_name)
                span.set_attribute("provider.method", func.__name__)
                try:
                    result = func(*args, **kwargs)
                    span.set_status(trace.Status(trace.StatusCode.OK))
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    raise
        
        # Async version
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            tracer = trace.get_tracer(__name__)
            with tracer.start_as_current_span(f"{provider_name}.{func.__name__}") as span:
                span.set_attribute("provider.name", provider_name)
                span.set_attribute("provider.method", func.__name__)
                try:
                    result = await func(*args, **kwargs)
                    span.set_status(trace.Status(trace.StatusCode.OK))
                    return result
                except Exception as e:
                    span.record_exception(e)
                    span.set_status(trace.Status(trace.StatusCode.ERROR, str(e)))
                    raise

        import inspect
        return async_wrapper if inspect.iscoroutinefunction(func) else wrapper
    return decorator
