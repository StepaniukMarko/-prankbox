import os
from dotenv import load_dotenv
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = [int(x) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()]
REFERRAL_BONUS = int(os.getenv("REFERRAL_BONUS", "10"))
DB_PATH = "data/bot.db"
