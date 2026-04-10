import asyncio
from unittest.mock import MagicMock, AsyncMock

async def main():
    mock_macro = MagicMock()
    mock_macro.run = AsyncMock(return_value="Bullish Macro View")
    
    print("type mock_macro.run:", type(mock_macro.run))
    result = mock_macro.run({})
    print("type result:", type(result))
    
    val = await result
    print("val:", val)

asyncio.run(main())
