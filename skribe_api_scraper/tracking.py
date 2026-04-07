from loguru import logger
from config import SKRIBE_USER_ID, TRACKING_ENDPOINT

async def post_tracking(client, page_name, click_id=""):
    if not SKRIBE_USER_ID:
        logger.warning("SKRIBE_USER_ID missing in .env - PostTracking skipped.")
        return
        
    payload = {
        "userId": SKRIBE_USER_ID,
        "pageName": page_name,
        "clickId": click_id
    }
    
    try:
        # Client.post handles 200, log error, and no raise for tracking
        await client.post(TRACKING_ENDPOINT, json_body=payload)
        logger.debug(f"PostTracking: {page_name} | clickId: {click_id}")
    except Exception as e:
        logger.warning(f"Failed to post tracking: {e}")
