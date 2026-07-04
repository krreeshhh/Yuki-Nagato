import os
import logging
from typing import Optional, Tuple, AsyncGenerator
import asyncio

# Fix for Python 3.12+ (especially 3.14) where asyncio.get_event_loop() throws RuntimeError if no loop is running
# Pyrogram imports sync methods that require an active loop at import time
try:
    asyncio.get_event_loop()
except RuntimeError:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

from pyrogram import Client
from pyrogram.types import Message
from app.core.config import settings

logger = logging.getLogger(__name__)

# Determine working directory for sessions (especially writeable /tmp on Vercel serverless)
if settings.VERCEL_ENV == "development" or os.name == "nt":
    # On Windows or local dev, create a local directory for sessions
    SESSIONS_DIR = os.path.join(os.getcwd(), ".sessions")
    os.makedirs(SESSIONS_DIR, exist_ok=True)
else:
    # On Vercel or production linux, /tmp is always writeable
    SESSIONS_DIR = "/tmp"

# Create single shared client configuration
telegram_client = Client(
    name="telehost_session",
    api_id=settings.API_ID,
    api_hash=settings.API_HASH,
    bot_token=settings.BOT_TOKEN,
    workdir=SESSIONS_DIR
)
web_client = telegram_client

async def start_web_client():
    """Start the global Pyrogram client."""
    if not telegram_client.is_connected:
        logger.info("Starting Pyrogram Client...")
        await telegram_client.start()
        
        # Warm up peer cache for the storage channel to avoid PeerIdInvalid
        try:
            logger.info("Warming up storage channel peer cache...")
            await telegram_client.get_chat(settings.STORAGE_CHANNEL_ID)
            logger.info("Storage channel peer cache warmed up successfully.")
        except Exception as e:
            logger.warning(f"Failed to warm up storage channel peer cache: {e}")
            
        logger.info("Pyrogram Client started successfully.")

async def stop_web_client():
    """Stop the global Pyrogram client."""
    if telegram_client.is_connected:
        logger.info("Stopping Pyrogram Client...")
        await telegram_client.stop()
        logger.info("Pyrogram Client stopped.")

def get_media_metadata(message: Message) -> Tuple[Optional[str], Optional[str], int]:
    """
    Extract file_name, mime_type, and file_size from a Message object.
    Supports documents, videos, audio, animations, and photos.
    """
    if message.document:
        return message.document.file_name, message.document.mime_type, message.document.file_size
    elif message.video:
        return message.video.file_name or "video.mp4", message.video.mime_type or "video/mp4", message.video.file_size
    elif message.audio:
        return message.audio.file_name or "audio.mp3", message.audio.mime_type or "audio/mpeg", message.audio.file_size
    elif message.animation:
        return message.animation.file_name or "animation.gif", message.animation.mime_type or "image/gif", message.animation.file_size
    elif message.photo:
        # Photos don't have a filename or mime_type in the same way, return defaults
        # Photo size is the largest photo in the array
        largest_photo = message.photo
        return f"photo_{message.id}.jpg", "image/jpeg", largest_photo.file_size
    elif message.voice:
        return f"voice_{message.id}.ogg", message.voice.mime_type or "audio/ogg", message.voice.file_size
    elif message.video_note:
        return f"video_note_{message.id}.mp4", "video/mp4", message.video_note.file_size
    
    return None, None, 0

async def copy_file_to_storage(client: Client, from_chat_id: int, message_id: int) -> Optional[Message]:
    """
    Copies a file message to the private storage channel using the provided active client.
    Returns the copied Message object or None.
    """
    try:
        copied_message = await client.copy_message(
            chat_id=settings.STORAGE_CHANNEL_ID,
            from_chat_id=from_chat_id,
            message_id=message_id
        )
        return copied_message
    except Exception as e:
        logger.error(f"Failed to copy file to storage channel: {e}")
        return None

async def get_storage_message(message_id: int) -> Optional[Message]:
    """Retrieve the original message containing the media from the storage channel."""
    try:
        message = await web_client.get_messages(
            chat_id=settings.STORAGE_CHANNEL_ID,
            message_ids=message_id
        )
        # In Pyrogram, if message doesn't exist, it might be empty or None
        if message and not message.empty:
            return message
        return None
    except Exception as e:
        logger.error(f"Failed to retrieve message {message_id} from storage: {e}")
        return None

async def stream_telegram_file(
    message: Message,
    start_byte: int,
    end_byte: int
) -> AsyncGenerator[bytes, None]:
    """
    Streams file bytes from a Pyrogram message, skipping to start_byte
    and ending at end_byte (inclusive).
    """
    bytes_to_skip = start_byte
    bytes_to_read = end_byte - start_byte + 1
    
    try:
        # Iterate over the file chunks streamed from Telegram
        async for chunk in web_client.stream_media(message):
            chunk_len = len(chunk)
            
            # If we are still skipping bytes
            if bytes_to_skip >= chunk_len:
                bytes_to_skip -= chunk_len
                continue
            
            # If we need to skip a portion of this chunk
            if bytes_to_skip > 0:
                chunk = chunk[bytes_to_skip:]
                chunk_len = len(chunk)
                bytes_to_skip = 0
            
            # If the remaining bytes to read fit within this chunk
            if bytes_to_read <= chunk_len:
                yield chunk[:bytes_to_read]
                break
            else:
                yield chunk
                bytes_to_read -= chunk_len
    except Exception as e:
        logger.error(f"Error during Telegram file streaming: {e}")
        raise e
