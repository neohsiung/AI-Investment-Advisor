
import unittest
import sys
import os
from datetime import datetime

# Ensure project root is in path
sys.path.append(os.getcwd())

from src.utils.time_utils import (
    get_current_time, 
    get_current_utc_time, 
    format_time 
)

class TestTimeUtilsExtra(unittest.TestCase):
    def test_basic_funcs(self):
        t = get_current_time()
        assert isinstance(t, datetime)
        
        utc = get_current_utc_time()
        assert isinstance(utc, datetime)
        
        fmt = format_time(t, "%Y-%m-%d")
        assert len(fmt) == 10

if __name__ == '__main__':
    unittest.main()
