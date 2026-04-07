import asyncio
import json
import os
import time
import random
from datetime import datetime
from loguru import logger
from config import (
    MIN_DELAY_BETWEEN_REQUESTS,
    MAX_DELAY_BETWEEN_REQUESTS,
    RATELIMIT_SAFE_THRESHOLD,
    RATELIMIT_CRITICAL_THRESHOLD,
    RATELIMIT_PAUSE_SECONDS,
    MAX_DAILY_REQUESTS,
    MAX_SESSION_REQUESTS,
    USAGE_LOG_FILE
)

class DailyCapReachedError(Exception):
    pass

class SessionCapReachedError(Exception):
    pass

class RateLimiter:
    def __init__(self):
        self.remaining = 500
        self.reset_seconds = 37
        self.last_request_time = 0
        self.session_count = 0
        self.daily_count = self.load_today_count()

    def load_today_count(self) -> int:
        if not os.path.exists(USAGE_LOG_FILE):
            return 0
        
        try:
            with open(USAGE_LOG_FILE, "r") as f:
                data = json.load(f)
            
            today_date = datetime.now().strftime("%Y-%m-%d")
            if data.get("date") == today_date:
                return data.get("count", 0)
        except Exception as e:
            logger.error(f"Failed to load daily count: {e}")
            
        return 0

    def save_today_count(self):
        os.makedirs(os.path.dirname(USAGE_LOG_FILE), exist_ok=True)
        today_date = datetime.now().strftime("%Y-%m-%d")
        with open(USAGE_LOG_FILE, "w") as f:
            json.dump({
                "date": today_date,
                "count": self.daily_count
            }, f, indent=2)

    def update(self, remaining, reset_seconds):
        self.remaining = int(remaining)
        self.reset_seconds = int(reset_seconds)
        logger.debug(f"Rate limit: {self.remaining} remaining, resets in {self.reset_seconds}s")
        if self.remaining < RATELIMIT_SAFE_THRESHOLD:
            logger.warning(f"Rate limit below safe threshold: {self.remaining} left")

    async def wait(self):
        # 1. Enforce minimum delay since last request
        elapsed = time.time() - self.last_request_time
        delay = random.uniform(MIN_DELAY_BETWEEN_REQUESTS, MAX_DELAY_BETWEEN_REQUESTS)
        if elapsed < delay:
            await asyncio.sleep(delay - elapsed)

        # 2. Critical threshold
        if self.remaining < RATELIMIT_CRITICAL_THRESHOLD:
            logger.warning(f"CRITICAL RATE LIMIT: {self.remaining} left. Pausing {RATELIMIT_PAUSE_SECONDS}s.")
            await asyncio.sleep(RATELIMIT_PAUSE_SECONDS)

        # 3. Safe threshold
        elif self.remaining < RATELIMIT_SAFE_THRESHOLD:
            logger.warning(f"Rate limit low: {self.remaining} left. Waiting for reset window: {self.reset_seconds} + 10s.")
            await asyncio.sleep(self.reset_seconds + 10)

        # 4. Daily cap
        if self.daily_count >= MAX_DAILY_REQUESTS:
            raise DailyCapReachedError(f"Daily limit of {MAX_DAILY_REQUESTS} reached.")

        # 5. Session cap
        if self.session_count >= MAX_SESSION_REQUESTS:
            raise SessionCapReachedError(f"Session limit of {MAX_SESSION_REQUESTS} reached.")

        # 6. Update local counters
        self.last_request_time = time.time()
        self.session_count += 1
        self.daily_count += 1
        
        # 7. Persist daily count
        self.save_today_count()
