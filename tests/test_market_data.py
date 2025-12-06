import pytest
from unittest.mock import MagicMock, patch
import pandas as pd
from src.market_data import MarketDataService

@pytest.fixture
def market_data():
    return MarketDataService()

@patch('yfinance.download')
def test_get_current_prices_single(mock_download, market_data):
    # Mock data for single ticker
    mock_df = pd.DataFrame({'Close': [150.0]}, index=[pd.Timestamp('2023-01-01')])
    mock_download.return_value = mock_df
    
    prices = market_data.get_current_prices(['AAPL'])
    assert prices['AAPL'] == 150.0

@patch('yfinance.download')
def test_get_current_prices_multiple(mock_download, market_data):
    # Mock data for multiple tickers
    mock_df = pd.DataFrame({
        ('Close', 'AAPL'): [150.0],
        ('Close', 'GOOGL'): [2800.0]
    }, index=[pd.Timestamp('2023-01-01')])
    # Adjust for yfinance structure which might return MultiIndex columns
    # If yfinance returns a flat dataframe with columns as tickers for 'Close'
    # It depends on how yf.download is mocked.
    # Let's mock the behavior expected by the code: data['Close'] returning a DataFrame with columns as tickers
    
    mock_data = MagicMock()
    mock_close = pd.DataFrame({
        'AAPL': [150.0],
        'GOOGL': [2800.0]
    }, index=[pd.Timestamp('2023-01-01')])
    
    mock_data.__getitem__.return_value = mock_close
    # Handle 'empty' check
    mock_data.empty = False
    # Handle 'Close' in columns check
    mock_data.columns = ['Close']
    
    # Actually the code does: data['Close']
    # So we need mock_download return value to behave like a DF
    
    # Let's construct a real DF to be safe
    data = pd.DataFrame({
        'AAPL': [150.0],
        'GOOGL': [2800.0]
    })
    # The code expects `data['Close']` to exist if multiple tickers
    # But yfinance structure varies.
    # Code:
    # if 'Close' in data.columns:
    #    close_data = data['Close']
    
    # So let's mock a MultiIndex DF
    arrays = [['Close', 'Close'], ['AAPL', 'GOOGL']]
    tuples = list(zip(*arrays))
    index = pd.MultiIndex.from_tuples(tuples, names=['Price', 'Ticker'])
    df = pd.DataFrame([[150.0, 2800.0]], columns=index)
    
    mock_download.return_value = df
    
    # The code handles:
    # if 'Close' in data.columns:
    #    close_data = data['Close']
    # But with MultiIndex, 'Close' is a level.
    # Let's check the code:
    # if 'Close' in data.columns: -> This works for MultiIndex if 'Close' is top level?
    # Actually yfinance usually returns:
    #              Close
    #              AAPL  GOOGL
    # Date
    # ...          150   2800
    
    # So data['Close'] returns the sub-dataframe.
    
    prices = market_data.get_current_prices(['AAPL', 'GOOGL'])
    assert prices['AAPL'] == 150.0
    assert prices['GOOGL'] == 2800.0

@patch('yfinance.download')
def test_get_technical_indicators(mock_download, market_data):
    # Create enough data for RSI (14) and MACD (26)
    # Need at least 26+ points
    dates = pd.date_range(start='2023-01-01', periods=50)
    # Create a trend
    values = [100 + i for i in range(50)]
    df = pd.DataFrame({'Close': values}, index=dates)
    
    mock_download.return_value = df
    
    indicators = market_data.get_technical_indicators('AAPL')
    
    assert 'rsi' in indicators
    assert 'macd' in indicators
    assert 'macd_val' in indicators
    assert indicators['rsi'] > 0

@patch('yfinance.Ticker')
def test_get_news(mock_ticker, market_data):
    mock_instance = MagicMock()
    mock_instance.news = [
        {
            'title': 'Test News',
            'link': 'http://example.com',
            'providerPublishTime': 1672531200
        }
    ]
    mock_ticker.return_value = mock_instance
    
    news = market_data.get_news('AAPL')
    assert len(news) == 1
    assert 'Test News' in news[0]

@patch('yfinance.Ticker')
def test_get_financials(mock_ticker, market_data):
    mock_instance = MagicMock()
    mock_instance.info = {
        'marketCap': 1000000,
        'trailingPE': 20.5,
        'forwardPE': 18.5,
        'trailingEps': 5.0,
        'revenueGrowth': 0.1,
        'profitMargins': 0.2,
        'sector': 'Technology',
        'industry': 'Consumer Electronics'
    }
    mock_ticker.return_value = mock_instance
    
    financials = market_data.get_financials('AAPL')
    assert financials['market_cap'] == 1000000
    assert financials['sector'] == 'Technology'
