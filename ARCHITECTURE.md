# Architecture

## Core Components
- **Telegram Bot Daemon (`dvachbot/main.py`)**: Manages real-time interactions with users via Telegram.
- **Web/API Backend (`site_tgach/main.py`)**: A FastAPI application handling the web frontend, external API requests, and media uploads.

## Bot Modules
- **`delivery_manager.py`**: Manages the message delivery queue. It pulls pending broadcasts from `DeliveryQueue` and safely dispatches messages to Telegram users/channels while respecting rate limits and handling retries.
- **`handlers/message_router.py`**: The core `aiogram` router that parses incoming Telegram messages, commands, and reactions, passing them to appropriate logic flows.
- **`ai_manager.py`**: Integrates LLM features. It handles the bot's "modes" (e.g., persona replies), processes text generation requests, and orchestrates summarization features.

## Backend Modules
- **`site_tgach/tagging_worker.py`**: A background worker that asynchronously computes hashes (SHA256, pHash, BlurHash) for uploaded media and invokes the neuro-tagging pipeline to classify content.
- **`site_tgach/vision.py`**: Prepares images (resizing/converting via PIL) and interfaces with AI vision APIs to analyze image content, generating moderation tags.

## Data Layer
- **Database**: The 1.5GB SQLite database (`dvach_bot.db`) is the connective tissue.
- Both systems read/write to the same tables (`Boards`, `Posts`, `Threads`, `Users`).
- Utilizes `fts5` for Full-Text Search (`PostsFTS`) and tracks read/unread states (`UserReplies`, `UserAlerts`).

## External APIs
Telegram Bot API, Telegram MTProto (via pyrogram & tgcrypto), Groq API, Gemini API, ImgBB, PixHost, Catbox, FreeImage, Telegraph API.
