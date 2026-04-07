import asyncio
import json
from datetime import datetime
from loguru import logger
from config import PAGE_SIZE, TRACKING_CALL_EVERY_N, OUTLET_FUZZY_THRESHOLD, SEARCH_ENDPOINT
from utils import score_match, get_status, normalize_text
from utils import score_match, get_status, normalize_text
from tracking import post_tracking

class JournalistProcessor:
    def __init__(self):
        self.api_call_count = 0
        self.first_run_logged = False

    async def find_journalist(self, client, name, outlet_name, outlet_id, outlet_confidence):
        name = normalize_text(name)
        first_name = name.split(' ')[0] if ' ' in name else name
        last_name = name.split(' ')[-1] if ' ' in name else ""
        
        # Build search strategies
        base_params = {"pageSize": PAGE_SIZE}
        if outlet_id:
            strategies = [
                {"OutletFilter": outlet_id, "MediaFilter": 1, "SearchFilter": name, **base_params},
                {"OutletFilter": outlet_id, "MediaFilter": 1, "SearchFilter": first_name, **base_params},
                {"OutletFilter": outlet_id, "MediaFilter": 1, "SearchFilter": last_name, **base_params},
                {"OutletFilter": outlet_id, "MediaFilter": 1, "SearchFilter": "", **base_params},
            ]
        else:
            strategies = [
                {"SearchFilter": name, **base_params},
                {"SearchFilter": last_name, **base_params},
            ]
        
        best = None
        for q in strategies:
            logger.debug(f"Searching: {q}")
            results = await self.fetch_all_results(client, q)
            if results:
                best_match = self.find_best_match(results, name, outlet_name)
                if best_match and best_match['match_score'] >= 60:
                    best = best_match
                    break
        
        if not best:
            return {"status": "NOT_FOUND", "match_score": 0, "Outlet_Match_Confidence": outlet_confidence}
            
        status = get_status(best["match_score"])
        
        try:
            # Fetch profile for email/phone
            profile_data = await self.get_full_profile(client, best["raw_result"].get("intJournalistId") or best["raw_result"].get("id"))
            
            # Extract
            enriched = self.map_fields(best["raw_result"])
            
            # Merge profile data 
            if profile_data:
                 profile_mapped = self.map_fields(profile_data)
                 for k, v in profile_mapped.items():
                     if v and (not enriched.get(k) or str(enriched.get(k)).strip() == ""):
                         enriched[k] = v
                         
            enriched.update({
                "status": status,
                "match_score": best["match_score"],
                "Outlet_Match_Confidence": outlet_confidence,
                "scraped_at": datetime.now().isoformat()
            })
            return enriched
        except Exception as e:
            logger.error(f"Error processing {name}: {e}")
            return {"status": "ERROR", "match_score": 0, "Outlet_Match_Confidence": outlet_confidence}

    async def fetch_all_results(self, client, params):
        try:
            response = await client.get(SEARCH_ENDPOINT, params=params)
            
            if not self.first_run_logged:
                logger.debug(f"SAMPLE RAW JSON:\n{json.dumps(response, indent=2)}")
                self.first_run_logged = True

            results = response.get("data", []) or response.get("items", []) or response.get("journalists", []) or response.get("results", [])
            total_count = response.get("totalCount") or response.get("total") or len(results)
            
            all_results = list(results)
            page = 1
            while len(all_results) < total_count and page < 5:
                page += 1
                params["pageNumber"] = page
                resp = await client.get(SEARCH_ENDPOINT, params=params)
                data = resp.get("data", []) or resp.get("items", [])
                if not data: break
                all_results.extend(data)
                
            return all_results
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def find_best_match(self, results, name, publication):
        matches = []
        for res in results:
            res_name = res.get("vchJournalistName") or res.get("name") or res.get("journalistName") or res.get("fullName", "")
            res_pub_val = res.get("outlets") or res.get("outlet") or res.get("publication") or res.get("mediaOutlet", "")
            res_pub = self._extract_str(res_pub_val) 
            
            combined, name_score, outlet_score = score_match(name, res_name, publication, res_pub)
            
            matches.append({
                "raw_result": res,
                "match_score": combined,
                "name": res_name,
                "publication": res_pub
            })
            
        matches.sort(key=lambda x: x["match_score"], reverse=True)
        return matches[0] if matches else None

    def _extract_str(self, val):
        if not val:
            return ""
        
        def flatten(item):
            if isinstance(item, dict):
                return str(item.get("outletName") or item.get("beatName") or item.get("city") or item.get("state") or item.get("country") or item.get("name") or item.get("title") or "")
            return str(item)

        if isinstance(val, list):
            filtered = [flatten(v) for v in val if v]
            return ", ".join([f for f in filtered if f])
        
        return flatten(val)

    def map_fields(self, data):
        journalist_id = data.get("intJournalistId") or data.get("id") or data.get("journalistId") or data.get("journoId") or data.get("_id")
        
        media_types = ""
        if data.get("outlets") and isinstance(data.get("outlets"), list):
            media_arr = data["outlets"][0].get("media", [])
            media_types = ", ".join(media_arr)
            
        # Parse Contact Details from Full Profile
        work_email = ""
        personal_email = ""
        mobile = ""
        office_phone = ""
        
        contacts = data.get("contactDetails", [])
        if isinstance(contacts, list):
            for contact in contacts:
                ctype = contact.get("type", "").lower()
                cval = contact.get("value", "")
                if "work email" in ctype:
                    work_email = cval
                elif "personal email" in ctype:
                    personal_email = cval
                elif "email" in ctype and not work_email:
                    work_email = cval
                elif "mobile" in ctype:
                    mobile = cval
                elif "phone" in ctype:
                    office_phone = cval
                    
        # Parse Social
        social = data.get("journoSocial", {})
        twitter = social.get("vchTwitter", "")
        linkedin = social.get("vchLinkedinLink", "")
            
        city_list = data.get("city") or data.get("journoLocations", [])
        city = city_list[0].get("city") or city_list[0].get("vchCity") if city_list and isinstance(city_list, list) else None
        
        state_list = data.get("state") or data.get("journoLocations", [])
        state = state_list[0].get("state") or state_list[0].get("vchState") if state_list and isinstance(state_list, list) else None
        country = data.get("vchCountryName") or data.get("country")
        
        return {
            "Journalist_ID": self._extract_str(journalist_id),
            "Email": self._extract_str(work_email or data.get("email") or data.get("vchEmail")),
            "Email_2": self._extract_str(personal_email or data.get("secondaryEmail")),
            "Phone": self._extract_str(mobile or office_phone or data.get("phone") or data.get("vchPhone")),
            "Twitter": self._extract_str(twitter or data.get("vchTwitter")),
            "LinkedIn": self._extract_str(linkedin or data.get("linkedin")),
            "Beat": self._extract_str(data.get("beat")),
            "Media_Types": media_types,
            "City": self._extract_str(city),
            "State": self._extract_str(state),
            "Country": self._extract_str(country),
            "Title": self._extract_str(data.get("vchJournoTitle") or data.get("journoTitle")),
            "Outlet": self._extract_str(data.get("outlets")),
            "Profile_URL": f"https://www.goskribe.com/journalistProfile/{journalist_id}" if journalist_id else ""
        }

    def map_location(self, data):
        city = self._extract_str(data.get("city") or data.get("locationCity"))
        state = self._extract_str(data.get("state") or data.get("locationState"))
        country = self._extract_str(data.get("country") or data.get("locationCountry"))
        parts = [p for p in [city, state, country] if p]
        return ", ".join(parts) if parts else self._extract_str(data.get("location"))

    async def get_full_profile(self, client, journalist_id):
        if not journalist_id:
            return None
            
        try:
            profile_response = await client.get(f"/journalist/Get-Journalist-by-Id?Id={journalist_id}")
            if profile_response and "data" in profile_response:
                return profile_response["data"]
        except Exception as e:
            logger.warning(f"Could not load full profile for {journalist_id}: {e}")
                
        return None

    async def process_item(self, client, name, outlet_name, outlet_resolver):
        # 1. Resolve outlet
        outlet_id, outlet_confidence = await outlet_resolver.resolve(outlet_name)
        if outlet_confidence < OUTLET_FUZZY_THRESHOLD:
            logger.warning(f"Low outlet match ({outlet_confidence:.0f}%) for '{outlet_name}' - using name-only fallback")
            outlet_id = None
            
        self.api_call_count += 1
        
        # Periodic tracking
        if self.api_call_count % TRACKING_CALL_EVERY_N == 0:
            await post_tracking(client, "journalist-search")
            
        result = await self.find_journalist(client, name, outlet_name, outlet_id, outlet_confidence)
        
        if result["status"] != "NOT_FOUND" and result.get("Journalist_ID"):
            # Send profile tracking via tracking.py
            await post_tracking(client, "journalist-profile", result["Journalist_ID"])
            
        return result
