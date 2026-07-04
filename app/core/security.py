import re
from typing import Set, Tuple, Dict
import time
from fastapi import Request, HTTPException, status

# Slug validation rules
SLUG_REGEX = re.compile(r"^[a-z0-9-]{3,32}$")
RESERVED_SLUGS: Set[str] = {
    "admin", "api", "stream", "files", "help", "upload", "static", "u", "www", "qr", "stats", "status"
}

# Alias validation rules
ALIAS_REGEX = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")

def validate_slug(slug: str) -> Tuple[bool, str]:
    """
    Validate a user slug.
    Returns (is_valid, error_message).
    """
    if not slug:
        return False, "Slug cannot be empty."
    
    slug_lower = slug.lower()
    
    if slug_lower in RESERVED_SLUGS:
        return False, f"Slug '{slug}' is a reserved keyword."
    
    if not SLUG_REGEX.match(slug_lower):
        return False, "Slug must be 3-32 characters long and contain only lowercase letters, numbers, and hyphens."
    
    return True, ""

def validate_alias(alias: str) -> Tuple[bool, str]:
    """
    Validate a file alias.
    Returns (is_valid, error_message).
    """
    if not alias:
        return False, "Alias cannot be empty."
    
    if not ALIAS_REGEX.match(alias):
        return False, "Alias must be 1-64 characters long and contain only alphanumeric characters, underscores, and hyphens."
    
    return True, ""

# In-memory sliding window rate limiter (simple implementation for server environments)
# key -> list of timestamps
rate_limit_store: Dict[str, list] = {}

async def rate_limiter(request: Request):
    """
    Simple sliding window rate limiter dependency.
    Limits requests to 60 requests per minute per IP address.
    """
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    window = 60  # seconds
    max_requests = 60  # requests per window
    
    if client_ip not in rate_limit_store:
        rate_limit_store[client_ip] = []
        
    # Filter out timestamps older than the window
    rate_limit_store[client_ip] = [t for t in rate_limit_store[client_ip] if now - t < window]
    
    if len(rate_limit_store[client_ip]) >= max_requests:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later."
        )
        
    rate_limit_store[client_ip].append(now)
