import urllib.request
import urllib.parse
from src.utils.jwt_utils import create_access_token
import json

def test_api():
    # Primary user id hardcoded for test
    token = create_access_token({"sub": "test_user_id"})
    
    req = urllib.request.Request("http://localhost:8000/api/v1/dashboard/summary")
    req.add_header("Authorization", f"Bearer {token}")
    
    try:
        response = urllib.request.urlopen(req)
        print("Response:", response.status)
        print(response.read().decode())
    except urllib.error.HTTPError as e:
        print("HTTP Error:", e.code)
        print(e.read().decode())
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    test_api()
