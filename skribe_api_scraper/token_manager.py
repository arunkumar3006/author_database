import jwt
import json
import os
import time
from datetime import datetime
from loguru import logger
from config import TOKEN_META_FILE, SKRIBE_JWT_TOKEN

class TokenExpiredError(Exception):
    pass

class TokenManager:
    @staticmethod
    def decode_token(token):
        try:
            payload = jwt.decode(token, options={"verify_signature": False})
            return payload
        except Exception as e:
            logger.error(f"Failed to decode JWT token: {str(e)}")
            return None

    @staticmethod
    def check_expiry():
        if not SKRIBE_JWT_TOKEN:
            return False, "SKRIBE_JWT_TOKEN missing in .env"

        payload = TokenManager.decode_token(SKRIBE_JWT_TOKEN)
        if not payload:
            return False, "Failed to decode token"

        exp_timestamp = payload.get("exp")
        if not exp_timestamp:
            return False, "Token does not have an expiry field"

        exp_date = datetime.fromtimestamp(exp_timestamp)
        now = datetime.now()
        
        # Save meta
        os.makedirs(os.path.dirname(TOKEN_META_FILE), exist_ok=True)
        with open(TOKEN_META_FILE, "w") as f:
            json.dump({
                "exp": exp_timestamp,
                "expiry_date": exp_date.isoformat(),
                "last_checked": datetime.now().isoformat()
            }, f, indent=2)

        if exp_date < now:
            return False, f"Token expired on {exp_date.strftime('%Y-%m-%d %H:%M:%S')}"
        
        days_left = (exp_date - now).days
        if days_left < 1:
            logger.warning(f"Token will expire very soon: {exp_date}")
        
        return True, exp_date

    @staticmethod
    def print_refresh_instructions():
        print("\n" + "="*60)
        print("Your Mavericks JWT token has expired or is invalid.")
        print("To refresh:")
        print(" 1. Open Chrome, log in to goskribe.com")
        print(" 2. Open DevTools (F12) -> Network -> Fetch/XHR")
        print(" 3. Click any GetJournalists request")
        print(" 4. Copy the Authorization header value (the part after 'Bearer ')")
        print(" 5. Update SKRIBE_JWT_TOKEN in your .env file")
        print(" 6. Copy the full Cookie header value")
        print(" 7. Update SKRIBE_COOKIE in your .env file")
        print(" 8. Re-run the script")
        print("="*60 + "\n")
