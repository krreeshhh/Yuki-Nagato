import os
import logging
import asyncio
from datetime import datetime, timezone
import io
from pyrogram import Client, filters, idle
from pyrogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery, ForceReply
)
from app.core.config import settings
from app.database.mongodb import Database
from app.models.user import User
from app.models.file import FileMetadata
from app.core.security import validate_slug, validate_alias
from app.utils.helpers import generate_secure_id, format_file_size, parse_expiry_duration
from app.services.qr import generate_qr_code_bytes
from app.services.telegram import get_media_metadata, copy_file_to_storage

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Determine working directory for sessions (writeable /tmp on Vercel serverless)
if settings.VERCEL_ENV == "development" or os.name == "nt":
    SESSIONS_DIR = os.path.join(os.getcwd(), ".sessions")
    os.makedirs(SESSIONS_DIR, exist_ok=True)
else:
    SESSIONS_DIR = "/tmp"

# Initialize Pyrogram Bot Client
bot_client = Client(
    name="bot_session",
    api_id=settings.API_ID,
    api_hash=settings.API_HASH,
    bot_token=settings.BOT_TOKEN,
    workdir=SESSIONS_DIR
)

# HELPER: Get dynamic base link for user and file
def get_file_url(user: dict, file_meta: dict) -> str:
    owner_part = user.get("slug") or user.get("public_id")
    file_part = file_meta.get("alias") or file_meta.get("hash")
    return f"{settings.BASE_URL}/{owner_part}/{file_part}"

# Command: /start
@bot_client.on_message(filters.command("start") & filters.private)
async def start_command(client: Client, message: Message):
    telegram_id = message.from_user.id
    
    # Check if user exists
    user = await Database.get_user_by_telegram_id(telegram_id)
    if not user:
        # Generate new user
        public_id = generate_secure_id(8)
        # Ensure public_id is unique in database
        while await Database.get_user_by_public_id(public_id):
            public_id = generate_secure_id(8)
            
        new_user = User(
            telegram_id=telegram_id,
            public_id=public_id
        )
        user = await Database.create_user(new_user.model_dump())
        logger.info(f"Registered new user: {telegram_id} (ID: {public_id})")
        welcome_text = (
            f"👋 Welcome to the **Telegram File Hosting Platform**!\n\n"
            f"An account has been created for you.\n"
            f"🔑 **Your Public ID:** `{public_id}`\n\n"
            f"To get started, send any file here, then reply to it with `/upload`."
        )
    else:
        welcome_text = (
            f"👋 Welcome back!\n\n"
            f"🔑 **Your Public ID:** `{user['public_id']}`\n"
            f"🌐 **Your Slug:** `{user.get('slug') or 'None (use /slug <name> to set one)'}`\n\n"
            f"Send a file here and reply to it with `/upload` to share it."
        )
    
    await message.reply_text(welcome_text)

# Command: /help
@bot_client.on_message(filters.command("help") & filters.private)
async def help_command(client: Client, message: Message):
    help_text = (
        "🚀 **Telegram File Host Help Guide**\n\n"
        "📎 **How to Upload:**\n"
        "1. Send a file to this bot (document, video, photo, audio, etc.).\n"
        "2. Reply to the file message with the `/upload` command.\n\n"
        "🔧 **Upload Command Options:**\n"
        "• `/upload` - Generates a secure random link.\n"
        "• `/upload -a resume` - Sets a custom path/alias (`/resume`).\n"
        "• `/upload -expire 24h` - Sets file to expire in 24 hours.\n"
        "• `/upload -a resume -expire 7d` - Combined alias and expiry.\n\n"
        "⏳ **Supported Expirations:**\n"
        "`1h`, `6h`, `12h`, `24h`, `7d`, `30d`, `90d`\n\n"
        "⚙️ **User Commands:**\n"
        "• `/slug <name>` - Set a custom URL slug (e.g. `/slug portfolio`). To remove your slug, use `/slug none`.\n"
        "• `/files` - Manage your uploaded files.\n"
        "• `/stats` - View your total storage and traffic stats.\n"
        "• `/help` - Show this usage guide."
    )
    await message.reply_text(help_text)

# Command: /slug
@bot_client.on_message(filters.command("slug") & filters.private)
async def slug_command(client: Client, message: Message):
    telegram_id = message.from_user.id
    user = await Database.get_user_by_telegram_id(telegram_id)
    if not user:
        await message.reply_text("❌ Please run /start first to create an account.")
        return
        
    parts = message.text.split()
    if len(parts) < 2:
        current_slug = user.get("slug")
        slug_status = f"🌐 Your current slug: `{current_slug}`" if current_slug else "🌐 You do not have a custom slug set. Files use your Public ID."
        await message.reply_text(
            f"{slug_status}\n\n"
            f"To set a slug, use: `/slug <name>`\n"
            f"Regex: `3-32 characters, lowercase a-z, 0-9, and hyphen`"
        )
        return
        
    new_slug = parts[1].strip()
    
    if new_slug.lower() == "none":
        # Remove custom slug
        await Database.update_user_slug(telegram_id, None)
        await message.reply_text("✅ Your custom slug has been removed. Your links will now use your Public ID.")
        return
        
    # Validate slug
    is_valid, err_msg = validate_slug(new_slug)
    if not is_valid:
        await message.reply_text(f"❌ {err_msg}")
        return
        
    # Check uniqueness
    existing_user = await Database.get_user_by_slug(new_slug)
    if existing_user and existing_user["telegram_id"] != telegram_id:
        await message.reply_text("❌ This slug is already taken by another user.")
        return
        
    # Update slug
    await Database.update_user_slug(telegram_id, new_slug)
    await message.reply_text(
        f"✅ Custom slug updated successfully!\n"
        f"Your files will now be hosted under: `{settings.BASE_URL}/{new_slug}/<file>`\n\n"
        f"⚠️ Note: Any old links using your previous slug or public ID will stop working."
    )

# Command: /upload
@bot_client.on_message(filters.command("upload") & filters.private)
async def upload_command(client: Client, message: Message):
    telegram_id = message.from_user.id
    user = await Database.get_user_by_telegram_id(telegram_id)
    if not user:
        await message.reply_text("❌ Please run /start first to create an account.")
        return
        
    # Verify command is a reply to another message
    if not message.reply_to_message:
        await message.reply_text("❌ This command must only work when replying to a file message.")
        return
        
    target_msg = message.reply_to_message
    
    # Extract media metadata
    file_name, mime_type, file_size = get_media_metadata(target_msg)
    if not file_name:
        await message.reply_text("❌ No supported media/file found in the message you replied to.")
        return
        
    # Parse arguments
    alias, expire_duration, parse_err = parse_upload_arguments(message.text)
    if parse_err:
        await message.reply_text(f"❌ {parse_err}")
        return
        
    # Validate alias
    if alias:
        is_valid_alias, alias_err = validate_alias(alias)
        if not is_valid_alias:
            await message.reply_text(f"❌ {alias_err}")
            return
            
        # Check alias uniqueness for this user
        existing_alias_file = await Database.get_file_by_alias(telegram_id, alias)
        if existing_alias_file:
            await message.reply_text(f"❌ You already have a file with the alias '{alias}'. Choose another or delete the old one.")
            return
            
    # Validate and parse expiration
    expires_at = None
    if expire_duration:
        is_valid_exp, parsed_expiry, exp_err = parse_expiry_duration(expire_duration)
        if not is_valid_exp:
            await message.reply_text(f"❌ {exp_err}")
            return
        expires_at = parsed_expiry
        
    # Copy file to private storage channel
    status_msg = await message.reply_text("📤 Copying file to storage channel...")
    storage_msg = await copy_file_to_storage(message.chat.id, target_msg.id)
    if not storage_msg:
        await status_msg.edit_text("❌ Error copying file to private storage. Make sure the bot is configured correctly as an admin.")
        return
        
    # Generate unique hash for the file
    file_hash = generate_secure_id(8)
    while await Database.get_file_by_hash(file_hash):
        file_hash = generate_secure_id(8)
        
    # Insert metadata
    file_data = {
        "owner_id": telegram_id,
        "alias": alias,
        "hash": file_hash,
        "channel_id": settings.STORAGE_CHANNEL_ID,
        "message_id": storage_msg.id,
        "file_name": file_name,
        "mime_type": mime_type,
        "file_size": file_size,
        "views": 0,
        "downloads": 0,
        "expires_at": expires_at,
        "created_at": datetime.now(timezone.utc)
    }
    
    await Database.create_file(file_data)
    
    # Generate public link
    public_url = get_file_url(user, file_data)
    
    # Generate QR Code image in memory
    qr_bytes = generate_qr_code_bytes(public_url)
    qr_photo = io.BytesIO(qr_bytes)
    qr_photo.name = "qrcode.png"
    
    # Build response message
    expiry_str = f"🕒 Expires at: {expires_at.strftime('%Y-%m-%d %H:%M:%S')} UTC" if expires_at else "🕒 Expires at: Never"
    caption = (
        f"✅ **File Uploaded Successfully!**\n\n"
        f"📄 **Name:** `{file_name}`\n"
        f"⚖️ **Size:** {format_file_size(file_size)}\n"
        f"🏷️ **Mime:** `{mime_type}`\n"
        f"{expiry_str}\n\n"
        f"🔗 **Public Link:** {public_url}"
    )
    
    # Send QR photo with details
    await status_msg.delete()
    await client.send_photo(
        chat_id=message.chat.id,
        photo=qr_photo,
        caption=caption,
        reply_to_message_id=target_msg.id
    )

# Command: /files
@bot_client.on_message(filters.command("files") & filters.private)
async def files_command(client: Client, message: Message):
    await show_files_list(message.chat.id, message.from_user.id, page=1)

# Helper: Show list of files
async def show_files_list(chat_id: int, telegram_id: int, page: int = 1, message_id: int = None):
    user = await Database.get_user_by_telegram_id(telegram_id)
    if not user:
        return
        
    files = await Database.get_user_files(telegram_id)
    if not files:
        no_files_text = "❌ You haven't uploaded any files yet. Send a file here and reply with `/upload`."
        if message_id:
            await bot_client.edit_message_text(chat_id, message_id, no_files_text)
        else:
            await bot_client.send_message(chat_id, no_files_text)
        return
        
    # Paginate (10 files per page)
    per_page = 5
    total_pages = (len(files) + per_page - 1) // per_page
    page = max(1, min(page, total_pages))
    
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    page_files = files[start_idx:end_idx]
    
    text = f"📂 **Your Files (Page {page}/{total_pages}):**\n\n"
    keyboard = []
    
    for idx, f in enumerate(page_files, start=start_idx + 1):
        display_name = f['alias'] if f['alias'] else f['hash']
        text += f"**{idx}.** `{f['file_name']}`\n"
        text += f"   └ Link: /{display_name} | Size: {format_file_size(f['file_size'])}\n\n"
        
        # Row with select button for each file
        keyboard.append([
            InlineKeyboardButton(
                text=f"⚙️ Manage File #{idx}",
                callback_data=f"manage:{f['hash']}"
            )
        ])
        
    # Navigation row
    nav_row = []
    if page > 1:
        nav_row.append(InlineKeyboardButton("⬅️ Prev", callback_data=f"page:{page-1}"))
    if page < total_pages:
        nav_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"page:{page+1}"))
        
    if nav_row:
        keyboard.append(nav_row)
        
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if message_id:
        await bot_client.edit_message_text(chat_id, message_id, text, reply_markup=reply_markup)
    else:
        await bot_client.send_message(chat_id, text, reply_markup=reply_markup)

# Command: /stats
@bot_client.on_message(filters.command("stats") & filters.private)
async def stats_command(client: Client, message: Message):
    telegram_id = message.from_user.id
    user = await Database.get_user_by_telegram_id(telegram_id)
    if not user:
        await message.reply_text("❌ Please run /start first.")
        return
        
    stats = await Database.get_user_stats(telegram_id)
    stats_text = (
        f"📊 **Your Hosting Stats**\n\n"
        f"📁 **Total Files:** `{stats['total_files']}`\n"
        f"👁️ **Total Views:** `{stats['total_views']}`\n"
        f"📥 **Total Downloads:** `{stats['total_downloads']}`"
    )
    await message.reply_text(stats_text)

# Callback Query Handler
@bot_client.on_callback_query()
async def callback_query_handler(client: Client, query: CallbackQuery):
    data = query.data
    telegram_id = query.from_user.id
    
    user = await Database.get_user_by_telegram_id(telegram_id)
    if not user:
        await query.answer("Account not found.", show_alert=True)
        return
        
    # Page navigation
    if data.startswith("page:"):
        page = int(data.split(":")[1])
        await show_files_list(query.message.chat.id, telegram_id, page=page, message_id=query.message.id)
        await query.answer()
        return
        
    # File management actions
    action, f_hash = data.split(":", 1)
    file_meta = await Database.get_file_by_hash(f_hash)
    
    if not file_meta:
        await query.answer("File not found or already deleted.", show_alert=True)
        # Refresh lists
        await show_files_list(query.message.chat.id, telegram_id, page=1, message_id=query.message.id)
        return
        
    if file_meta["owner_id"] != telegram_id:
        await query.answer("Unauthorized.", show_alert=True)
        return
        
    if action == "manage":
        display_name = file_meta['alias'] if file_meta['alias'] else file_meta['hash']
        expiry_str = file_meta['expires_at'].strftime('%Y-%m-%d %H:%M:%S UTC') if file_meta['expires_at'] else "Never"
        
        detail_text = (
            f"🛠️ **File Manager**\n\n"
            f"📄 **Name:** `{file_meta['file_name']}`\n"
            f"🔗 **Path:** `/{display_name}`\n"
            f"⚖️ **Size:** {format_file_size(file_meta['file_size'])}\n"
            f"🕒 **Expires:** {expiry_str}\n"
            f"👁️ **Views:** `{file_meta['views']}`\n"
            f"📥 **Downloads:** `{file_meta['downloads']}`"
        )
        
        keyboard = [
            [
                InlineKeyboardButton("📊 Stats", callback_data=f"stats:{f_hash}"),
                InlineKeyboardButton("📱 QR", callback_data=f"qr:{f_hash}")
            ],
            [
                InlineKeyboardButton("✏ Rename", callback_data=f"rename:{f_hash}"),
                InlineKeyboardButton("🗑 Delete", callback_data=f"delete:{f_hash}")
            ],
            [
                InlineKeyboardButton("⬅️ Back to List", callback_data="page:1")
            ]
        ]
        await query.message.edit_text(detail_text, reply_markup=InlineKeyboardMarkup(keyboard))
        await query.answer()
        
    elif action == "stats":
        stats_info = (
            f"📄 File: {file_meta['file_name']}\n"
            f"👁️ Views: {file_meta['views']}\n"
            f"📥 Downloads: {file_meta['downloads']}"
        )
        await query.answer(stats_info, show_alert=True)
        
    elif action == "qr":
        public_url = get_file_url(user, file_meta)
        qr_bytes = generate_qr_code_bytes(public_url)
        qr_photo = io.BytesIO(qr_bytes)
        qr_photo.name = "qrcode.png"
        
        await query.answer("Sending QR Code...")
        await client.send_photo(
            chat_id=query.message.chat.id,
            photo=qr_photo,
            caption=f"📱 **QR Code for:**\n`{file_meta['file_name']}`\n\n🔗 Link: {public_url}"
        )
        
    elif action == "rename":
        await query.answer()
        await client.send_message(
            chat_id=query.message.chat.id,
            text=(
                f"✏ **Renaming file:** `{file_meta['file_name']}`\n"
                f"Reply to this message with the new alias you want to use.\n\n"
                f"⚠️ Only alphanumeric characters, hyphens, and underscores are allowed.\n"
                f"Identifier: `[hash:{f_hash}]`"
            ),
            reply_markup=ForceReply(selective=True)
        )
        
    elif action == "delete":
        confirm_text = (
            f"⚠️ **Delete Confirmation**\n\n"
            f"Are you sure you want to delete `{file_meta['file_name']}`?\n"
            f"This action is permanent and links will stop working immediately."
        )
        keyboard = [
            [
                InlineKeyboardButton("✅ Yes, Delete", callback_data=f"confirm_del:{f_hash}"),
                InlineKeyboardButton("❌ Cancel", callback_data=f"manage:{f_hash}")
            ]
        ]
        await query.message.edit_text(confirm_text, reply_markup=InlineKeyboardMarkup(keyboard))
        await query.answer()
        
    elif action == "confirm_del":
        await Database.delete_file_by_hash(f_hash)
        await query.answer("File deleted successfully.", show_alert=True)
        # Go back to files page
        await show_files_list(query.message.chat.id, telegram_id, page=1, message_id=query.message.id)

# ForceReply Handler for renaming files
@bot_client.on_message(filters.reply & filters.private)
async def rename_reply_handler(client: Client, message: Message):
    # Check if the replied message is from the bot and contains the rename prompt
    reply_to = message.reply_to_message
    if not reply_to.from_user or reply_to.from_user.id != (await client.get_me()).id:
        return
        
    if "✏ **Renaming file:**" not in reply_to.text or "Identifier:" not in reply_to.text:
        return
        
    # Extract file hash from prompt text
    try:
        f_hash = reply_to.text.split("[hash:")[1].split("]")[0].strip()
    except IndexError:
        await message.reply_text("❌ Failed to parse file identifier. Please try renaming again from `/files`.")
        return
        
    new_alias = message.text.strip()
    
    # Validate alias
    is_valid, err_msg = validate_alias(new_alias)
    if not is_valid:
        await message.reply_text(f"❌ {err_msg}\n\nUse `/files` to try renaming again.")
        return
        
    # Fetch file details
    file_meta = await Database.get_file_by_hash(f_hash)
    if not file_meta or file_meta["owner_id"] != message.from_user.id:
        await message.reply_text("❌ File not found or unauthorized.")
        return
        
    # Check if this user already uses this alias
    existing_alias = await Database.get_file_by_alias(message.from_user.id, new_alias)
    if existing_alias and existing_alias["hash"] != f_hash:
        await message.reply_text("❌ You already have a file with this alias. Please select a unique alias.")
        return
        
    # Update alias in database
    await Database.db.files.update_one(
        {"hash": f_hash},
        {"$set": {"alias": new_alias}}
    )
    
    user = await Database.get_user_by_telegram_id(message.from_user.id)
    new_url = get_file_url(user, {**file_meta, "alias": new_alias})
    
    await message.reply_text(
        f"✅ **File Renamed Successfully!**\n\n"
        f"📄 **File:** `{file_meta['file_name']}`\n"
        f"🏷️ **New Alias:** `{new_alias}`\n"
        f"🔗 **New URL:** {new_url}"
    )

# Raw files sent directly to the bot (prompt to reply with /upload)
@bot_client.on_message(filters.private & (filters.document | filters.video | filters.audio | filters.photo | filters.animation | filters.voice | filters.video_note))
async def raw_file_handler(client: Client, message: Message):
    welcome_msg = (
        "📎 **File received.**\n\n"
        "Reply to this file message with:\n"
        "`/upload`"
    )
    await message.reply_text(welcome_msg, reply_to_message_id=message.id)

# Main runner for running bot as a standalone process
async def main():
    logger.info("Initializing database...")
    await Database.connect()
    logger.info("Starting Telegram Bot...")
    await bot_client.start()
    logger.info("Telegram Bot is running! Press Ctrl+C to stop.")
    await idle()
    logger.info("Stopping Telegram Bot...")
    await bot_client.stop()
    await Database.close()

if __name__ == "__main__":
    asyncio.run(main())
