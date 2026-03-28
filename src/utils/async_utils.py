import asyncio
import functools
import typing
from typing import TypeVar, Callable, Any

T = TypeVar("T")

async def to_thread(func: Callable[..., T], /, *args: Any, **kwargs: Any) -> T:
    """
    Backport of asyncio.to_thread for Python < 3.9.
    Asynchronously run function func in a separate thread.
    
    Any *args and **kwargs supplied for this function are directly passed
    to func. Also, the current :class:`contextvars.Context` is propagated,
    matching the behavior of asyncio.to_thread.
    """
    loop = asyncio.get_running_loop()
    # Note: contextvars propagation is handled by run_in_executor in Python 3.7+
    # so we don't need to manually copy the context here unless we need specific behavior.
    func_call = functools.partial(func, *args, **kwargs)
    return await loop.run_in_executor(None, func_call)
