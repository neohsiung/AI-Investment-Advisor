import functools
import json
import asyncio
from typing import Any, Callable, Optional
from fastapi.encoders import jsonable_encoder
from src.utils.cache import ResponseCache
from src.utils.logger import setup_logger

logger = setup_logger("APICacheDecorator")

# Initialize shared cache client
cache_instance = ResponseCache()

def cached_api_response(ttl_seconds: int = 60):
    """
    FastAPI endpoint decorator to cache responses in Redis with multi-tenant user isolation.
    FastAPI 路由裝飾器：在 Redis 中快取回應，支援多租戶用戶隔離。
    """
    def decorator(func: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            # 1. Identify User ID for Multi-Tenant Isolation
            user_id = None
            
            # Check kwargs for service or user_id
            if 'user_id' in kwargs:
                user_id = kwargs['user_id']
            elif 'service' in kwargs:
                service = kwargs['service']
                if hasattr(service, 'user_id'):
                    user_id = service.user_id
            else:
                # Check positional args
                for arg in args:
                    if isinstance(arg, str) and len(arg) == 36 and arg.count('-') == 4:
                        # Simple heuristic for UUID user_id
                        user_id = arg
                        break
                    elif hasattr(arg, 'user_id'):
                        user_id = getattr(arg, 'user_id')
                        break
            
            # If no user context can be established, bypass cache for security (no cross-contamination)
            if not user_id:
                logger.debug(f"API Cache bypassed for {func.__name__} (No user_id found)")
                if asyncio.iscoroutinefunction(func):
                    return await func(*args, **kwargs)
                return func(*args, **kwargs)
            
            # 2. Build Cache Key isolated by endpoint name and user_id
            cache_key = f"cache:api:{func.__name__}:{user_id}"
            
            # 3. Check Cache
            try:
                cached_data = cache_instance.get_value(cache_key)
                if cached_data:
                    logger.info(f"API Cache HIT for {func.__name__} (User: {user_id})")
                    return json.loads(cached_data)
            except Exception as e:
                logger.error(f"API Cache read error for {func.__name__}: {e}")
            
            # 4. Fetch fresh data
            logger.info(f"API Cache MISS for {func.__name__} (User: {user_id}). Fetching fresh data...")
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                result = func(*args, **kwargs)
            
            # 5. Write to Cache
            try:
                # Serialize response using jsonable_encoder (handles Pydantic models, datetimes, etc.)
                serialized = jsonable_encoder(result)
                cache_instance.set_value(cache_key, json.dumps(serialized), ttl_seconds)
                logger.debug(f"API Cache set for {func.__name__} (User: {user_id}, TTL: {ttl_seconds}s)")
            except Exception as e:
                logger.error(f"API Cache write error for {func.__name__}: {e}")
                
            return result
        return wrapper
    return decorator
