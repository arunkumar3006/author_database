import os
from dotenv import load_dotenv

load_dotenv()

# API configuration
BASE_URL = os.getenv("SKRIBE_BASE_URL", "https://www.goskribe.com/api/v1")
SEARCH_ENDPOINT = "/journo-record/GetJournalists"
TRACKING_ENDPOINT = "/tracking/PostTracking"
OUTLET_CACHE_FILE = "session/outlet_cache.json"
OUTLET_CACHE_TTL_DAYS = 7
PAGE_SIZE = 60

# Authentication
SKRIBE_JWT_TOKEN = os.getenv("SKRIBE_JWT_TOKEN")
SKRIBE_COOKIE = os.getenv("SKRIBE_COOKIE")
SKRIBE_USER_ID = os.getenv("SKRIBE_USER_ID")

# Safe rate limits
MIN_DELAY_BETWEEN_REQUESTS = 4.0
MAX_DELAY_BETWEEN_REQUESTS = 8.0
RATELIMIT_SAFE_THRESHOLD = 50
RATELIMIT_CRITICAL_THRESHOLD = 10
RATELIMIT_PAUSE_SECONDS = 60

# Volume caps
MAX_DAILY_REQUESTS = 2000
MAX_SESSION_REQUESTS = 1000
SHORT_BREAK_EVERY_N = 20
SHORT_BREAK_MIN = 30
SHORT_BREAK_MAX = 60
LONG_BREAK_EVERY_N = 50
LONG_BREAK_MIN = 120
LONG_BREAK_MAX = 180
TRACKING_CALL_EVERY_N = 10

# Matching
FUZZY_MATCH_THRESHOLD = 80
FUZZY_PARTIAL_THRESHOLD = 60
OUTLET_FUZZY_THRESHOLD = 75

# File paths
INPUT_FILE = "input/journalists.xlsx"
OUTPUT_FILE = "output/journalists_enriched.xlsx"
CHECKPOINT_FILE = "session/checkpoint.json"
USAGE_LOG_FILE = "session/usage_log.json"
TOKEN_META_FILE = "session/token_meta.json"

# Headers logic
DEFAULT_HEADERS = {
    "Authorization": f"Bearer {SKRIBE_JWT_TOKEN}",
    "Cookie": SKRIBE_COOKIE,
    "X-Source-App": "FrontendApp",
    "Content-Type": "application/json",
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://www.goskribe.com/journalist-search",
    "Sec-Ch-Ua": '"Chromium";v="124", "Not-A-Brand";v="24", "Google Chrome";v="124"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
}
