import unicodedata
from rapidfuzz import fuzz
from config import FUZZY_MATCH_THRESHOLD, FUZZY_PARTIAL_THRESHOLD

def normalize_text(text: str) -> str:
    if not text or not isinstance(text, str):
        return ""
    # Normalize unicode (NFKD), strip and title case
    return unicodedata.normalize('NFKD', text).strip().title()

def score_match(input_name, result_name, input_pub, result_pub):
    # Equal weight for name and outlet? No, 65/35 weights as per prompt
    name_score = fuzz.ratio(normalize_text(result_name).lower(), normalize_text(input_name).lower())
    outlet_score = fuzz.partial_ratio(normalize_text(result_pub).lower(), normalize_text(input_pub).lower())
    
    combined = (name_score * 0.65) + (outlet_score * 0.35)
    return combined, name_score, outlet_score

def get_status(score):
    if score >= FUZZY_MATCH_THRESHOLD:
        return "SUCCESS"
    elif score >= FUZZY_PARTIAL_THRESHOLD:
        return "PARTIAL"
    return "NOT_FOUND"
