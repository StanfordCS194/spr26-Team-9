from dotenv import load_dotenv
import os

load_dotenv()  # loads .env from current directory

current_api = os.getenv("CURRENT_API")
current_url = os.getenv("CURRENT_URL")