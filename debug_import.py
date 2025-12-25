import sys
import os
print(f"CWD: {os.getcwd()}")
print(f"sys.path: {sys.path}")

try:
    import src.data.ingestors
    print(f"src.data.ingestors type: {type(src.data.ingestors)}")
    print(f"src.data.ingestors file: {src.data.ingestors.__file__}")
    print(f"src.data.ingestors path: {src.data.ingestors.__path__}")
    
    from src.data.ingestors import IngestorFactory
    print("IngestorFactory imported successfully")
except Exception as e:
    print(f"Error: {e}")
