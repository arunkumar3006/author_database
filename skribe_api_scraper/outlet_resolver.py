import os
import json
import time
from urllib.parse import quote
from rapidfuzz import process, utils as fuzz_utils
from loguru import logger
from config import OUTLET_CACHE_FILE, OUTLET_CACHE_TTL_DAYS, OUTLET_FUZZY_THRESHOLD, BASE_URL

KNOWN_OUTLETS = {
    "the times of india": 294,
    "times of india": 294,
    "toi": 294,
}

class OutletResolver:
    def __init__(self, client):
        self.client = client
        self.outlets = {}
        self.cache_loaded = False

    async def _load_or_fetch(self, force_refresh=False):
        if self.cache_loaded and not force_refresh:
            return

        # 1. Try to load from cache
        if not force_refresh and os.path.exists(OUTLET_CACHE_FILE):
            try:
                stat = os.stat(OUTLET_CACHE_FILE)
                age_days = (time.time() - stat.st_mtime) / (24 * 3600)
                if age_days < OUTLET_CACHE_TTL_DAYS:
                    with open(OUTLET_CACHE_FILE, "r", encoding="utf-8") as f:
                        cached = json.load(f)
                        if isinstance(cached, dict) and cached:
                            self.outlets = cached
                            self.cache_loaded = True
                            logger.debug(f"Loaded {len(self.outlets)} outlets from cache ({age_days:.1f} days old).")
                            return
                else:
                    logger.info("Outlet cache is stale, will refresh.")
            except Exception as e:
                logger.warning(f"Failed to read outlet cache: {e}. Will refresh.")
                if os.path.exists(OUTLET_CACHE_FILE):
                    os.remove(OUTLET_CACHE_FILE)
                    
        # 2. Fetch from API
        logger.info("Fetching outlet list from API...")
        fetched = await self._fetch_all_outlets()
        
        # 3. Combine with KNOWN_OUTLETS and save
        self.outlets = dict(KNOWN_OUTLETS)
        for k, v in fetched.items():
            self.outlets[k] = v
            
        try:
            os.makedirs(os.path.dirname(OUTLET_CACHE_FILE), exist_ok=True)
            with open(OUTLET_CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(self.outlets, f)
            logger.info(f"Saved {len(self.outlets)} outlets to cache.")
        except Exception as e:
            logger.warning(f"Could not save outlet cache: {e}")
            
        self.cache_loaded = True

    async def _fetch_all_outlets(self) -> dict:
        result = {}
        # Try primary endpoint
        try:
            resp = await self.client.get("/journo-record/Get-Search-by-Category", params={"type": "Outlet", "SearchFilter": "", "pageSize": 10000, "pageNumber": 1})
            data = resp.get("data", [])
            for item in data:
                # The exact structure depends on the API, let's look for common ID/Name pairs
                id_val = item.get("id") or item.get("intOutletId") or item.get("value")
                name_val = item.get("name") or item.get("vchOutletName") or item.get("label")
                if id_val and name_val:
                    # Normalize key
                    norm = fuzz_utils.default_process(str(name_val))
                    result[norm] = id_val
            if result:
                return result
        except Exception as e:
            logger.warning(f"Failed to fetch from Get-Search-by-Category: {e}")

        # Try secondary endpoint
        try:
            resp = await self.client.get("/journo-record/GetOutlets", params={"pageSize": 10000, "pageNumber": 1})
            data = resp.get("data", [])
            for item in data:
                id_val = item.get("id") or item.get("intOutletId") or item.get("value")
                name_val = item.get("name") or item.get("vchOutletName") or item.get("label")
                if id_val and name_val:
                    norm = fuzz_utils.default_process(str(name_val))
                    result[norm] = id_val
            return result
        except Exception as e:
            logger.warning(f"Failed to fetch from GetOutlets: {e}")
            
        return result

    async def resolve(self, outlet_name: str, force_refresh=False) -> tuple[int | None, float]:
        if not outlet_name or not str(outlet_name).strip():
            return None, 0.0
            
        await self._load_or_fetch(force_refresh=force_refresh)
        
        normalized_name = fuzz_utils.default_process(str(outlet_name))
        if not normalized_name:
            return None, 0.0

        if not self.outlets:
            return None, 0.0

        best_match = process.extractOne(normalized_name, self.outlets.keys())
        if not best_match:
            return None, 0.0
            
        matched_str, score, _ = best_match
        if score >= OUTLET_FUZZY_THRESHOLD:
            outlet_id = self.outlets[matched_str]
            return outlet_id, score
            
        return None, score
