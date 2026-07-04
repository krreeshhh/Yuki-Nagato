# TeleHost ⚡ - Telegram-Powered File Hosting Platform

A production-ready, high-performance, **zero-server-storage** file hosting and streaming platform. TeleHost uses a Telegram private channel as storage, MongoDB Atlas for metadata, and streams files dynamically using Pyrogram with full support for **HTTP Range Requests** (video play, pause, seek, and resume).

---

## 🏗️ Architecture

```
                                 ┌──────────────┐
                                 │ Telegram Bot │
                                 └──────┬───────┘
                                        │ (Copies Media)
┌────────┐    HTTPS Requests     ┌──────▼───────┐     MTProto Chunks      ┌──────────────────┐
│ Client ├──────────────────────►│ FastAPI Web  ├────────────────────────►│ Private Telegram │
└────────┘   (Video seeking)    └──────┬───────┘   (Streaming Generator)  │ Storage Channel  │
                                       │                                  └──────────────────┘
                                       │ (Queries Meta)
                                 ┌─────▼────────┐
                                 │   MongoDB    │
                                 └──────────────┘
```

### Core Design Decisions

1.  **Zero Server Disk Footprint**: File binaries are never permanently written to the web server's disk. They are copied directly within Telegram's servers from the user's bot chat to the private channel, and are streamed dynamically to the web client using an asynchronous generator.
2.  **Separate Sessions**: The FastAPI web process (`web_session`) and the bot worker process (`bot_session`) run on separate Pyrogram sessions. This prevents database locking and RPC conflict issues.
3.  **Range Request Streaming**: Custom chunking engine handles HTTP Range requests from browsers, enabling video scrubbing and partial file downloading.
4.  **Ephemeral Serverless Support**: Utilizes the writeable `/tmp` directory on serverless environments like Vercel to store Pyrogram session files.

---

## 🛠️ Tech Stack

*   **Backend**: Python 3.12+, FastAPI, Pyrogram, Motor (MongoDB Async Driver), Pydantic v2, Uvicorn, Gunicorn
*   **Database**: MongoDB Atlas
*   **Storage**: Telegram Private Channel (via MTProto)
*   **Frontend**: HTML5, Vanilla CSS (Glassmorphic theme), Vanilla JavaScript

---

## 🔑 Environment Variables

Create a `.env` file in the root directory (refer to `.env.example`):

```env
# Telegram Credentials (get from https://my.telegram.org)
API_ID=1234567
API_HASH=abcdef0123456789abcdef0123456789

# Telegram Bot Token (get from @BotFather)
BOT_TOKEN=1234567890:ABCdefGHIjklMNOpqrSTUvwxYZ

# Private Telegram Storage Channel ID (must start with -100)
STORAGE_CHANNEL_ID=-1002233445566

# MongoDB Configuration
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/?retryWrites=true&w=majority
DATABASE_NAME=telegram_file_host

# Website configuration
BASE_URL=http://localhost:8000

# Security Key for cookie signing, tokens, etc.
SECRET_KEY=your_secure_hex_key

# Environment Type (vercel or development)
VERCEL_ENV=development
```

---

## 🚀 Setup & Installation

### Prerequisite 1: Telegram Setup
1.  Go to [my.telegram.org](https://my.telegram.org), log in, create a new application, and retrieve your `API_ID` and `API_HASH`.
2.  Chat with [@BotFather](https://t.me/BotFather) to create a new bot and copy the `BOT_TOKEN`.
3.  Create a **Private Channel** in Telegram.
4.  Add your bot as an **Administrator** in this channel with permissions to *Post Messages* and *Delete Messages*.
5.  Retrieve the channel ID (e.g. using a bot like `@MissRose_bot` or by forwarding a message from the channel to a bot info helper). The ID **must start with `-100`**.

### Prerequisite 2: MongoDB Atlas Setup
1.  Sign up or log in to [MongoDB Atlas](https://www.mongodb.com/cloud/atlas).
2.  Create a free M0 Cluster.
3.  Add a Database User and configure Network Access to allow connections (IP whitelist).
4.  Copy the connection string (`MONGODB_URI`) and insert it in `.env`.

---

### Local Installation

1.  **Clone the Repository**:
    ```bash
    git clone <repo-url>
    cd Filemanager
    ```

2.  **Create and Activate Virtual Environment**:
    ```bash
    python -m venv venv
    # Windows:
    venv\Scripts\activate
    # macOS/Linux:
    source venv/bin/activate
    ```

3.  **Install Dependencies**:
    ```bash
    pip install -r requirements.txt
    ```

4.  **Database Indexes Initialization**:
    Database indexes are automatically initialized and verified whenever the FastAPI server or Bot starts up.
    
    *   **Users Collection**:
        *   `public_id` -> Unique
        *   `slug` -> Unique (Partial: only active when slug is a string to allow duplicate null values)
        *   `telegram_id` -> Unique
    *   **Files Collection**:
        *   `hash` -> Unique
        *   `(owner_id, alias)` -> Unique (Partial: only active when alias is a string to allow duplicate null values)

5.  **Run the Web Application**:
    ```bash
    uvicorn main:app --reload --port 8000
    ```

6.  **Run the Telegram Bot Worker**:
    Open a separate terminal window and run:
    ```bash
    python -m app.bot.bot
    ```

---

## ⚡ Deployment

### 1. Deploying to Vercel (Testing)
Vercel is ideal for serving the serverless FastAPI web endpoints:

1.  Install the Vercel CLI: `npm install -g vercel`
2.  Log in: `vercel login`
3.  Run `vercel` in the project root.
4.  Link it to your project, add the **Environment Variables** in the Vercel dashboard, and deploy.
5.  *Note: On Vercel, the Pyrogram Bot listener (`app.bot.bot`) will not run continuously. The bot worker should be run separately on a VPS or persistent host.*

### 2. Deploying to a VPS (Production)
For production, you should run the web server and the bot worker persistently on a VPS (Ubuntu/Debian).

#### Setup Systemd Services

1.  **FastAPI Web Server Service (`/etc/systemd/system/telehost-web.service`)**:
    ```ini
    [Unit]
    Description=TeleHost FastAPI Web Application
    After=network.target

    [Service]
    User=ubuntu
    WorkingDirectory=/home/ubuntu/Filemanager
    EnvironmentFile=/home/ubuntu/Filemanager/.env
    ExecStart=/home/ubuntu/Filemanager/venv/bin/gunicorn main:app -w 4 -k uvicorn.workers.UvicornWorker -b 0.0.0.0:8000
    Restart=always

    [Install]
    WantedBy=multi-user.target
    ```

2.  **Telegram Bot Worker Service (`/etc/systemd/system/telehost-bot.service`)**:
    ```ini
    [Unit]
    Description=TeleHost Pyrogram Bot Worker
    After=network.target

    [Service]
    User=ubuntu
    WorkingDirectory=/home/ubuntu/Filemanager
    EnvironmentFile=/home/ubuntu/Filemanager/.env
    ExecStart=/home/ubuntu/Filemanager/venv/bin/python -m app.bot.bot
    Restart=always

    [Install]
    WantedBy=multi-user.target
    ```

3.  **Start and Enable Services**:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable --now telehost-web
    sudo systemctl enable --now telehost-bot
    ```

4.  **Reverse Proxy Setup (Nginx)**:
    Set up Nginx to proxy port `8000` to port `80`/`443` with SSL (Certbot).

---

## 🤖 Bot Usage Reference

*   `/start` - Register account and display your `public_id`.
*   `/help` - View usage guide.
*   `/slug <name>` - Set a custom URL slug (e.g. `/slug profile`).
*   `/upload` - Reply to any file message with this command to upload it. Optional flags:
    *   `-a <alias>`: Set a custom path alias (e.g. `/upload -a cv`).
    *   `-expire <duration>`: Set link duration (e.g. `24h`, `7d`).
*   `/files` - Open the interactive file manager with inline buttons for Statistics, QR Code, Rename, and Delete actions.
*   `/stats` - View account analytics.
