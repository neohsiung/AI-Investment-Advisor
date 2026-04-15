import urllib.request
from src.utils.jwt_utils import create_access_token

def test_api():
    token = create_access_token({"sub": "test_user_id"})
    
    for endpoint in ["/summary", "/positions", "/intelligence", "/agents"]:
        req = urllib.request.Request(f"http://localhost:8000/api/v1/dashboard{endpoint}")
        req.add_header("Authorization", f"Bearer {token}")
        
        try:
            print(f"Testing {endpoint}...")
            response = urllib.request.urlopen(req)
            print(f"Response {endpoint}:", response.status)
        except urllib.error.HTTPError as e:
            print(f"HTTP Error {endpoint}:", e.code)
            print("Response:", e.read().decode())
        except Exception as e:
            print("Error:", e)

if __name__ == "__main__":
    test_api()
