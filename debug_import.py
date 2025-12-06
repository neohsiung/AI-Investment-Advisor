import sys
from unittest.mock import MagicMock
sys.modules["streamlit"] = MagicMock()
sys.path.append(".")

try:
    import src.pages.4_Settings as m
    print("SUCCESS")
except Exception as e:
    import traceback
    traceback.print_exc()
