import logging
import urllib.parse
from fastapi import APIRouter, Request, HTTPException, Depends, status
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from app.core.config import settings
from app.database.mongodb import Database
from app.core.security import rate_limiter
from app.utils.helpers import format_file_size
from app.services.qr import generate_qr_code_bytes
from app.services.telegram import get_storage_message, stream_telegram_file

logger = logging.getLogger(__name__)

router = APIRouter()

# Dependency to get templates from request.app.state
def get_templates(request: Request):
    return request.app.state.templates

# Helper to parse HTTP Range header
def parse_range_header(range_header: str, file_size: int):
    """
    Parses 'bytes=start-end' range header.
    Returns (start_byte, end_byte).
    """
    if not range_header or not range_header.startswith("bytes="):
        return 0, file_size - 1
        
    try:
        parts = range_header.replace("bytes=", "").split("-")
        start = int(parts[0]) if parts[0] else 0
        end = int(parts[1]) if parts[1] else file_size - 1
        
        # Clip limits to actual size
        start = max(0, min(start, file_size - 1))
        end = max(start, min(end, file_size - 1))
        return start, end
    except (ValueError, IndexError):
        return 0, file_size - 1

# Landing page
@router.get("/", response_class=HTMLResponse)
async def home_route(request: Request, templates=Depends(get_templates)):
    return templates.TemplateResponse(request, "index.html")

# QR Code dynamic generation route
@router.get("/qr/{file_hash}", dependencies=[Depends(rate_limiter)])
async def qr_route(file_hash: str):
    file_meta = await Database.get_file_by_hash(file_hash)
    if not file_meta:
        raise HTTPException(status_code=404, detail="File not found")
        
    # Resolve owner
    owner = await Database.get_user_by_telegram_id(file_meta["owner_id"])
    if not owner:
        raise HTTPException(status_code=404, detail="Owner not found")
        
    owner_part = owner.get("slug") or owner.get("public_id")
    file_part = file_meta.get("alias") or file_meta.get("hash")
    
    # Reconstruct dynamic share URL
    share_url = f"{settings.BASE_URL}/{owner_part}/{file_part}"
    
    try:
        qr_png_bytes = generate_qr_code_bytes(share_url)
        return Response(content=qr_png_bytes, media_type="image/png")
    except Exception as e:
        logger.error(f"Failed to generate QR Code: {e}")
        raise HTTPException(status_code=500, detail="Failed to generate QR Code")

# File details page (e.g. /crishna/resume or /8f3d2a9c/7f3a92c1)
@router.get("/{owner}/{file}", response_class=HTMLResponse)
async def file_details_route(
    request: Request,
    owner: str,
    file: str,
    templates=Depends(get_templates),
    _rate_limit=Depends(rate_limiter)
):
    # 1. Resolve owner (slug first, then public_id)
    user = await Database.get_user_by_identifier(owner)
    if not user:
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "error_title": "Account Not Found",
                "error_message": f"No account matches the identifier '{owner}'."
            },
            status_code=404
        )
        
    # 2. Resolve file under this owner (alias first, then hash)
    file_meta = await Database.get_file_by_alias(user["telegram_id"], file)
    if not file_meta:
        # Check if the file is specified by hash directly
        file_meta = await Database.get_file_by_hash(file)
        if not file_meta or file_meta["owner_id"] != user["telegram_id"]:
            return templates.TemplateResponse(
                request,
                "error.html",
                {
                    "error_title": "File Not Found",
                    "error_message": f"The file '{file}' does not exist or has been deleted."
                },
                status_code=404
            )
            
    # 3. Check if file has expired
    # Create FileMetadata object to use properties
    from app.models.file import FileMetadata
    file_obj = FileMetadata(**file_meta)
    if file_obj.is_expired:
        return templates.TemplateResponse(
            request,
            "error.html",
            {
                "error_title": "File Link Expired",
                "error_message": "This file link has expired and is no longer accessible."
            },
            status_code=410
        )
        
    # 4. Increment view counter
    await Database.increment_views(file_obj.hash)
    
    # Refresh views locally for rendering
    file_meta["views"] += 1
    
    # 5. Format details
    formatted_size = format_file_size(file_obj.file_size)
    is_video = file_obj.mime_type.split("/")[0] == "video" or file_obj.mime_type in [
        "video/mp4", "video/x-matroska", "video/webm", "video/quicktime"
    ]
    
    share_url = f"{settings.BASE_URL}/{owner}/{file}"
    
    return templates.TemplateResponse(
        request,
        "file.html",
        {
            "file": file_meta,
            "formatted_size": formatted_size,
            "is_video": is_video,
            "share_url": share_url
        }
    )

# Video view page
@router.get("/stream/{file_hash}/view", response_class=HTMLResponse)
async def video_view_route(
    request: Request,
    file_hash: str,
    templates=Depends(get_templates),
    _rate_limit=Depends(rate_limiter)
):
    file_meta = await Database.get_file_by_hash(file_hash)
    if not file_meta:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"error_title": "File Not Found", "error_message": "The video you are trying to stream does not exist."},
            status_code=404
        )
        
    # Check expiry
    from app.models.file import FileMetadata
    file_obj = FileMetadata(**file_meta)
    if file_obj.is_expired:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"error_title": "Link Expired", "error_message": "This video stream link has expired."},
            status_code=410
        )
        
    user = await Database.get_user_by_telegram_id(file_obj.owner_id)
    if not user:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"error_title": "Owner Not Found", "error_message": "The file owner's account could not be found."},
            status_code=404
        )
        
    owner_slug_or_id = user.get("slug") or user.get("public_id")
    formatted_size = format_file_size(file_obj.file_size)
    
    return templates.TemplateResponse(
        request,
        "video.html",
        {
            "file": file_meta,
            "formatted_size": formatted_size,
            "owner_slug_or_id": owner_slug_or_id
        }
    )

# File download and video range streaming route
@router.get("/stream/{file_hash}")
async def stream_file_route(
    request: Request,
    file_hash: str,
    _rate_limit=Depends(rate_limiter)
):
    file_meta = await Database.get_file_by_hash(file_hash)
    if not file_meta:
        raise HTTPException(status_code=404, detail="File not found")
        
    # Check expiry
    from app.models.file import FileMetadata
    file_obj = FileMetadata(**file_meta)
    if file_obj.is_expired:
        raise HTTPException(status_code=410, detail="This file link has expired")
        
    # Retrieve original message from private storage channel
    message = await get_storage_message(file_obj.message_id)
    if not message:
        logger.error(f"Message ID {file_obj.message_id} containing the file was not found in Telegram storage channel.")
        raise HTTPException(status_code=404, detail="File not found in storage channel")
        
    # Increment download counter (we increment when file stream starts)
    await Database.increment_downloads(file_hash)
    
    # Parse Range headers for seeking support
    range_header = request.headers.get("Range")
    file_size = file_obj.file_size
    mime_type = file_obj.mime_type or "application/octet-stream"
    
    # URL escape the file name for Content-Disposition header
    safe_filename = urllib.parse.quote(file_obj.file_name)
    
    if range_header:
        start_byte, end_byte = parse_range_header(range_header, file_size)
        content_length = end_byte - start_byte + 1
        
        headers = {
            "Content-Range": f"bytes {start_byte}-{end_byte}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(content_length),
            "Content-Disposition": f"inline; filename*=UTF-8''{safe_filename}",
            "Cache-Control": "no-cache",
        }
        
        # Stream the range slice directly
        return StreamingResponse(
            stream_telegram_file(message, start_byte, end_byte),
            status_code=206,
            headers=headers,
            media_type=mime_type
        )
    else:
        # Full file download
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Length": str(file_size),
            "Content-Disposition": f"attachment; filename*=UTF-8''{safe_filename}",
            "Cache-Control": "no-cache",
        }
        
        return StreamingResponse(
            stream_telegram_file(message, 0, file_size - 1),
            headers=headers,
            media_type=mime_type
        )
