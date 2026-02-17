import logging
import sys
import os

# Configure baseline logging to see what's happening
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

sys.path.append(os.getcwd())

from src.services.interaction_service import InteractionService
from src.services.settings_service import SettingsService
from src.infrastructure.channels.channel_factory import ChannelFactory

def simulate():
    # 1. Load Real Settings
    settings_svc = SettingsService(db_path="data/portfolio.db")
    settings = settings_svc.get_all_settings()
    
    # 2. Create Adapters
    adapters = ChannelFactory.create_adapters(settings)
    print(f"Created {len(adapters)} adapters: {[a.__class__.__name__ for a in adapters]}")
    
    # 3. Create Service
    # We use None for intent_classifier to see if it triggers the "No Classifier" warning
    # Or we can create one.
    from src.infrastructure.nlp.intent_classifier import IntentClassifier
    try:
        classifier = IntentClassifier()
    except Exception as e:
        print(f"Classifier init failed (it might expect models/keys): {e}")
        classifier = None

    svc = InteractionService(
        adapters=adapters,
        intent_classifier=classifier,
        settings_service=settings_svc
    )
    
    # 4. Simulate LINE Text from User
    line_user_id = "U89230a0a471836b5533901492ed503bc"
    line_adapter = next((a for a in adapters if "LineBotAdapter" in a.__class__.__name__), None)
    
    if line_adapter:
        print("\n--- Simulating LINE Text Message ---")
        svc.handle_text_response(line_adapter, line_user_id, "hello")
        
    # 5. Simulate Telegram Text from User
    tg_chat_id = "982605706"
    tg_adapter = next((a for a in adapters if "TelegramAdapter" in a.__class__.__name__), None)
    
    if tg_adapter:
        print("\n--- Simulating Telegram Text Message ---")
        svc.handle_text_response(tg_adapter, tg_chat_id, "hello")

if __name__ == "__main__":
    simulate()
