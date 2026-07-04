from typing import Optional, Tuple

def parse_upload_arguments(text: str) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Parse the /upload command arguments.
    Supported inputs:
      - /upload
      - /upload -a resume
      - /upload -expire 24h
      - /upload -a resume -expire 7d
    
    Returns (alias, expire_duration, error_message)
    """
    parts = text.split()
    if not parts:
        return None, None, "Command is empty."
    
    if parts[0].lower() != "/upload":
        return None, None, "Invalid command prefix."
        
    alias = None
    expire = None
    
    i = 1
    while i < len(parts):
        arg = parts[i].lower()
        if arg in ("-a", "--alias"):
            if i + 1 < len(parts):
                alias = parts[i + 1]
                i += 2
            else:
                return None, None, "Error: Missing value for alias (`-a`)."
        elif arg in ("-expire", "--expire"):
            if i + 1 < len(parts):
                expire = parts[i + 1]
                i += 2
            else:
                return None, None, "Error: Missing value for expiration duration (`-expire`)."
        else:
            # Let's check if the user wrote something like /upload -aresume (without space)
            # and assist them.
            return None, None, f"Error: Unknown argument `{parts[i]}`. Use `-a <alias>` or `-expire <duration>`."
            
    return alias, expire, None
