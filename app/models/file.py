from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Optional

class FileMetadata(BaseModel):
    owner_id: int  # Owner's telegram_id
    alias: Optional[str] = None  # User-defined custom path name, unique per owner_id
    hash: str  # Secure random unique 8-character hash
    channel_id: int  # Telegram private storage channel ID
    message_id: int  # Telegram message ID containing the file
    file_name: str  # Original filename
    mime_type: str  # MIME type of the file
    file_size: int  # File size in bytes
    views: int = 0  # Page view counter
    downloads: int = 0  # Download counter
    expires_at: Optional[datetime] = None  # Expiration timestamp, null if perpetual
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def is_expired(self) -> bool:
        if self.expires_at is None:
            return False
        # Ensure comparison is timezone-aware
        expires = self.expires_at
        if expires.tzinfo is None:
            expires = expires.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) > expires

    model_config = {
        "json_schema_extra": {
            "example": {
                "owner_id": 123456789,
                "alias": "resume",
                "hash": "7f3a92c1",
                "channel_id": -100123456,
                "message_id": 1001,
                "file_name": "resume.pdf",
                "mime_type": "application/pdf",
                "file_size": 1048576,
                "views": 5,
                "downloads": 2,
                "expires_at": "2026-07-05T12:00:00Z",
                "created_at": "2026-07-04T12:00:00Z"
            }
        }
    }
