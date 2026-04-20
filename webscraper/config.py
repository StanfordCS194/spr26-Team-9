from dotenv import load_dotenv
import os

load_dotenv()  # loads .env from current directory

current_api = os.getenv("CURRENT_API")
current_url = os.getenv("CURRENT_URL")

news_api_key = os.getenv("NEWS_API_KEY")
news_api_url = os.getenv("NEWS_API_URL")