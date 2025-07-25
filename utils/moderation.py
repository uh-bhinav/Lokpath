import re

BANNED_WORDS = [
    "nude", "sex", "violence", "drugs", "kill", "blood", "porn", "weapon", "abuse", "nsfw"
]

def is_description_safe(description):
    # Lowercase and tokenize
    description_lower = description.lower()
    
    # Check for banned words
    for word in BANNED_WORDS:
        if re.search(r'\b' + re.escape(word) + r'\b', description_lower):
            return False, word  # Unsafe
    
    # Check for very short/meaningless descriptions
    if len(description.strip()) < 20:
        return False, "too short"
    
    return True, None  # Safe