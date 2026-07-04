from datetime import datetime, timezone
from pydantic import BaseModel, Field
from typing import Optional

class User(BaseModel):
    telegram_id: int
    public_id: str  # 8-char secure random unique identifier
    slug: Optional[str] = None  # Optional custom slug (globally unique, 3-32 chars)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    model_config = {
        "json_schema_extra": {
            "example": {
                "telegram_id": 123456789,
                "public_id": "8f3d2a9c",
                "slug": "crishna",
                "created_at": "2026-07-04T12:00:00Z"
            }
        }
    }
