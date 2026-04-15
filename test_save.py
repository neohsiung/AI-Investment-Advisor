import requests
from src.utils.jwt_utils import create_access_token

def test_api():
    from src.services.settings_service import SettingsService
    service = SettingsService("90693c07-6177-42df-97d9-915f3ce7c573")
    
    # 填補基礎 UX 必備預設值
    defaults = {
        "auto_trade_threshold": 75,
        "auto_trade_min_threshold": 30,
        "risk_profile": "Aggressive",
        "target_cash_ratio": 0.2,
        "AI_PROVIDER": "OpenRouter",
    }
    
    for key, val in defaults.items():
        success, msg = service.save_setting(key, val, user_id="90693c07-6177-42df-97d9-915f3ce7c573")
        print(f"Saving {key}: success={success}, msg={msg}")

if __name__ == "__main__":
    test_api()
