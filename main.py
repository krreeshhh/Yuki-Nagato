import sys
import os
import logging

# Force unbuffered output for real-time logging in cloud environments like Render
if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(line_buffering=True)
if sys.stderr and hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(line_buffering=True)
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse

from app.core.config import settings
from app.database.mongodb import Database
from app.services.telegram import start_web_client, stop_web_client
from app.api.routes import router as api_router
import app.bot.bot

# Setup Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Resolve Paths Dynamically
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "app", "templates")
STATIC_DIR = os.path.join(BASE_DIR, "app", "static")

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup and shutdown events."""
    logger.info("Initializing TeleHost Application...")
    
    # 1. Connect to MongoDB Atlas
    await Database.connect()
    
    # 2. Start global Pyrogram client for file streaming
    await start_web_client()
    
    yield
    
    # 3. Stop Pyrogram client
    await stop_web_client()
    
    # 4. Close MongoDB client
    await Database.close()
    logger.info("TeleHost Application stopped.")

# Initialize FastAPI App
app = FastAPI(
    title="TeleHost",
    description="Zero-Server-Storage Telegram File Hosting Platform",
    version="1.0.0",
    lifespan=lifespan
)

# Set up CORS Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up Templates and Static Files
app.state.templates = Jinja2Templates(directory=TEMPLATES_DIR)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Include Application Router
app.include_router(api_router)

# Custom Global Exception Handlers to show beautiful HTML error pages
@app.exception_handler(404)
async def custom_404_handler(request: Request, exc):
    templates = app.state.templates
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "error_title": "404 - Page Not Found",
            "error_message": "The page or file you are looking for does not exist on this server."
        },
        status_code=404
    )

@app.exception_handler(500)
async def custom_500_handler(request: Request, exc):
    templates = app.state.templates
    return templates.TemplateResponse(
        request,
        "error.html",
        {
            "error_title": "500 - Internal Server Error",
            "error_message": "A critical system error occurred. We have logged the error and are working on it."
        },
        status_code=500
    )

