import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

def generate_secure_id(length: int = 8) -> str:
    """Generate a cryptographically secure random hexadecimal string."""
    # Each byte is 2 hex characters, so divide length by 2
    num_bytes = (length + 1) // 2
    return secrets.token_hex(num_bytes)[:length]

def format_file_size(size_in_bytes: int) -> str:
    """Format file size in bytes to a human-readable string."""
    if size_in_bytes < 0:
        return "0 B"
    
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size_in_bytes < 1024.0:
            # Avoid decimal point for Bytes
            if unit == "B":
                return f"{int(size_in_bytes)} {unit}"
            return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024.0
    return f"{size_in_bytes:.2f} PB"

def parse_expiry_duration(duration_str: str) -> Tuple[bool, Optional[datetime], str]:
    """
    Parse duration string (e.g. 1h, 6h, 12h, 24h, 7d, 30d, 90d).
    Returns (is_valid, expires_at, error_message).
    """
    if not duration_str:
        return True, None, ""
        
    duration_str = duration_str.strip().lower()
    
    # Supported durations
    valid_durations = {"1h", "6h", "12h", "24h", "7d", "30d", "90d"}
    if duration_str not in valid_durations:
        return False, None, f"Invalid duration. Supported: {', '.join(valid_durations)}"
        
    now = datetime.now(timezone.utc)
    unit = duration_str[-1]
    value = int(duration_str[:-1])
    
    if unit == "h":
        delta = timedelta(hours=value)
    elif unit == "d":
        delta = timedelta(days=value)
    else:
        return False, None, "Invalid duration format."
        
    return True, now + delta, ""
