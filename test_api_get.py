import requests
from src.utils.jwt_utils import create_access_token

def test_api():
    # Use the real user ID from Postgres
    token = create_access_token({"sub": "65b548cf-110e-4d57-b7ed-5ea5f9b957be", "email": "supermfb@gmail.com"})
    
    url = "http://localhost:8000/api/v1/settings"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        response = requests.get(url, headers=headers)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    test_api()
