import httpx
import json
import asyncio
from loguru import logger
from config import BASE_URL, DEFAULT_HEADERS
from rate_limiter import RateLimiter
from token_manager import TokenExpiredError

class AccountFlaggedError(Exception):
    pass

class RateLimitError(Exception):
    pass

class ServerError(Exception):
    pass

class APIError(Exception):
    def __init__(self, status_code, body):
        self.status_code = status_code
        self.body = body
        super().__init__(f"API Error {status_code}: {body}")

class SkribeAPIClient:
    def __init__(self, rate_limiter: RateLimiter):
        self.client = httpx.AsyncClient(
            base_url=BASE_URL,
            headers=DEFAULT_HEADERS,
            timeout=30.0,
            follow_redirects=True
        )
        self.rate_limiter = rate_limiter

    async def get(self, endpoint, params=None) -> dict:
        await self.rate_limiter.wait()
        
        try:
            response = await self.client.get(endpoint, params=params)
            return await self.handle_response(response)
        except httpx.HTTPError as e:
            return await self.handle_http_error(e, "GET", endpoint, params)

    async def post(self, endpoint, json_body=None) -> dict:
        await self.rate_limiter.wait()
        
        try:
            response = await self.client.post(endpoint, json=json_body)
            # Tracking doesn't return much, handled differently inside catch if needed
            if "tracking" in endpoint:
                return response.json() if response.status_code == 200 else {}
            return await self.handle_response(response)
        except httpx.HTTPError as e:
            if "tracking" in endpoint:
                logger.warning(f"PostTracking failed: {e}")
                return {}
            return await self.handle_http_error(e, "POST", endpoint)

    async def handle_response(self, response):
        # Update rate limits
        remaining = response.headers.get("X-Ratelimit-Remaining")
        reset = response.headers.get("X-Ratelimit-Reset")
        if remaining is not None and reset is not None:
            self.rate_limiter.update(remaining, int(float(reset)))

        status = response.status_code
        if status == 200:
            return response.json()
        elif status == 401:
            raise TokenExpiredError("Skribe JWT token is expired or unauthorized (401).")
        elif status == 403:
            raise AccountFlaggedError("Access Forbidden (403). Your account may be flagged.")
        elif status == 429:
            raise RateLimitError("Rate limit exceeded (429).")
        elif status >= 500:
            raise ServerError(f"Server error ({status}).")
        else:
            raise APIError(status, response.text)

    async def handle_http_error(self, e, method, endpoint, params=None):
        logger.error(f"HTTP Connection Error during {method} {endpoint}: {str(e)}")
        # Implement retries in higher level if needed
        raise e

    async def close(self):
        await self.client.aclose()
