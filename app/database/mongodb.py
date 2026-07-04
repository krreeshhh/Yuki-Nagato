import logging
from typing import Optional, List, Dict, Any
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import IndexModel, ASCENDING
from app.core.config import settings

logger = logging.getLogger(__name__)

class Database:
    client: Optional[AsyncIOMotorClient] = None
    db = None

    @classmethod
    async def connect(cls):
        """Establish connection to MongoDB Atlas."""
        if cls.client is not None:
            return
        
        try:
            logger.info("Connecting to MongoDB Atlas...")
            cls.client = AsyncIOMotorClient(settings.MONGODB_URI)
            cls.db = cls.client[settings.DATABASE_NAME]
            logger.info(f"Connected to database: {settings.DATABASE_NAME}")
            
            # Initialize collections and indexes
            await cls.init_indexes()
        except Exception as e:
            logger.error(f"Failed to connect to MongoDB: {e}")
            raise e

    @classmethod
    async def close(cls):
        """Close MongoDB connection."""
        if cls.client is not None:
            cls.client.close()
            cls.client = None
            cls.db = None
            logger.info("MongoDB connection closed.")

    @classmethod
    async def init_indexes(cls):
        """Create required unique and partial indexes on users and files collections."""
        if cls.db is None:
            raise RuntimeError("Database not connected.")
        
        users_col = cls.db.users
        files_col = cls.db.files

        # 1. Users Indexes
        # public_id must be unique
        await users_col.create_index("public_id", unique=True)
        # slug must be unique, but since it's optional, use partial unique index to allow multiple null values
        await users_col.create_index(
            "slug",
            unique=True,
            partialFilterExpression={"slug": {"$type": "string"}}
        )
        # telegram_id must be unique
        await users_col.create_index("telegram_id", unique=True)

        # 2. Files Indexes
        # hash must be unique globally
        await files_col.create_index("hash", unique=True)
        # (owner_id, alias) compound index must be unique, but since alias is optional, use partial unique index
        await files_col.create_index(
            [("owner_id", ASCENDING), ("alias", ASCENDING)],
            unique=True,
            partialFilterExpression={"alias": {"$type": "string"}}
        )
        
        logger.info("MongoDB indexes successfully verified/created.")

    # User operations
    @classmethod
    async def get_user_by_telegram_id(cls, telegram_id: int) -> Optional[Dict[str, Any]]:
        return await cls.db.users.find_one({"telegram_id": telegram_id})

    @classmethod
    async def get_user_by_slug(cls, slug: str) -> Optional[Dict[str, Any]]:
        # Slug is stored lowercase for case-insensitive matching
        return await cls.db.users.find_one({"slug": slug.lower()})

    @classmethod
    async def get_user_by_public_id(cls, public_id: str) -> Optional[Dict[str, Any]]:
        return await cls.db.users.find_one({"public_id": public_id})

    @classmethod
    async def get_user_by_identifier(cls, identifier: str) -> Optional[Dict[str, Any]]:
        """Resolves owner using slug or public_id."""
        user = await cls.get_user_by_slug(identifier)
        if not user:
            user = await cls.get_user_by_public_id(identifier)
        return user

    @classmethod
    async def create_user(cls, user_data: Dict[str, Any]) -> Dict[str, Any]:
        if "slug" in user_data and user_data["slug"]:
            user_data["slug"] = user_data["slug"].lower()
        await cls.db.users.insert_one(user_data)
        return user_data

    @classmethod
    async def update_user_slug(cls, telegram_id: int, slug: Optional[str]) -> bool:
        """Update user slug. Pass None to remove/clear the slug."""
        normalized_slug = slug.lower() if slug else None
        res = await cls.db.users.update_one(
            {"telegram_id": telegram_id},
            {"$set": {"slug": normalized_slug}}
        )
        return res.modified_count > 0

    # File operations
    @classmethod
    async def get_file_by_hash(cls, file_hash: str) -> Optional[Dict[str, Any]]:
        return await cls.db.files.find_one({"hash": file_hash})

    @classmethod
    async def get_file_by_alias(cls, owner_id: int, alias: str) -> Optional[Dict[str, Any]]:
        return await cls.db.files.find_one({"owner_id": owner_id, "alias": alias})

    @classmethod
    async def create_file(cls, file_data: Dict[str, Any]) -> Dict[str, Any]:
        await cls.db.files.insert_one(file_data)
        return file_data

    @classmethod
    async def delete_file(cls, file_id: str) -> bool:
        res = await cls.db.files.delete_one({"_id": file_id})
        return res.deleted_count > 0

    @classmethod
    async def delete_file_by_hash(cls, file_hash: str) -> bool:
        res = await cls.db.files.delete_one({"hash": file_hash})
        return res.deleted_count > 0

    @classmethod
    async def get_user_files(cls, owner_id: int) -> List[Dict[str, Any]]:
        cursor = cls.db.files.find({"owner_id": owner_id}).sort("created_at", -1)
        return await cursor.to_list(length=1000)

    @classmethod
    async def increment_views(cls, file_hash: str):
        await cls.db.files.update_one({"hash": file_hash}, {"$inc": {"views": 1}})

    @classmethod
    async def increment_downloads(cls, file_hash: str):
        await cls.db.files.update_one({"hash": file_hash}, {"$inc": {"downloads": 1}})

    @classmethod
    async def get_user_stats(cls, owner_id: int) -> Dict[str, int]:
        """Aggregate total files, views, and downloads for a user."""
        pipeline = [
            {"$match": {"owner_id": owner_id}},
            {
                "$group": {
                    "_id": None,
                    "total_files": {"$sum": 1},
                    "total_views": {"$sum": "$views"},
                    "total_downloads": {"$sum": "$downloads"}
                }
            }
        ]
        cursor = cls.db.files.aggregate(pipeline)
        res = await cursor.to_list(length=1)
        if res:
            return {
                "total_files": res[0].get("total_files", 0),
                "total_views": res[0].get("total_views", 0),
                "total_downloads": res[0].get("total_downloads", 0)
            }
        return {"total_files": 0, "total_views": 0, "total_downloads": 0}
