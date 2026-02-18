from src.repositories.settings_repository import AlchemySettingsRepository
from src.repositories.user_repository import AlchemyUserRepository
import os

def enable_email_for_user(user_id):
    repo = AlchemySettingsRepository()
    
    settings = {
        "channel_email_enabled": "true",
        "channel_email_smtp_server": "smtp.gmail.com",
        "channel_email_smtp_port": "587",
        "channel_email_smtp_user": "supermfb@gmail.com",
        "channel_email_smtp_pass": "yrmi qnrb xcpi vkrc",
        "channel_email_from_address": "supermfb@gmail.com",
        "channel_email_to_address": "supermfb@gmail.com"
    }
    
    print(f"Enabling email for {user_id}...")
    for key, value in settings.items():
        repo.set(user_id, key, value)
    print("Settings updated successfully.")

if __name__ == "__main__":
    # Correct UUID for supermfb@gmail.com
    user_uuid = "90693c07-6177-42df-97d9-915f3ce7c573"
    enable_email_for_user(user_uuid)
