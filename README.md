# DOJA AI Studio — restored full project

This project retains the DOJA AI Studio layout and includes chat, account registration/login, Appwrite-backed conversations/messages, coding workspace, projects, image-studio URL integration, web search, file analysis, browser speech recognition, and settings/theme preferences.


## Important notes
- `database.py` uses Appwrite only; no SQLite database is used.
- The chat model is accessed through the Groq API. Configure `GROQ_API_KEY` on the server. The key must never be placed in frontend JavaScript.
- Image Studio currently creates a third-party Pollinations image URL. This is a URL-based integration, not a guaranteed image-generation backend; service availability, moderation, and privacy are controlled by the third party.
- The coding workspace's HTML preview and CSS sample preview run in a sandboxed iframe. JavaScript preview is also sandboxed. Python is not executed in the browser.
- Voice recognition uses browser SpeechRecognition/Web Speech API where available. Support and permissions vary by browser. This build does not provide a speech-to-speech model or guaranteed audio playback.
- Search results come from DuckDuckGo's search library and may be temporarily unavailable or limited.
- Appwrite custom account/session storage is implemented here. It is not Appwrite Auth. Protect the Appwrite API key and set collection permissions so only server access with the key is permitted.
- The backend currently reads at most 100 documents per collection and filters by user ID in Python. For a large app, implement pagination and indexed server-side queries.


## Local setup
1. Install Python 3.11 or later.
2. Unzip the project and open the folder in VS Code.
3. Create a virtual environment: `python -m venv .venv`
4. Activate it (Windows PowerShell): `.venv\\Scripts\\Activate.ps1`
5. Install packages: `pip install -r requirements.txt`
6. Copy `.env.example` to `.env` and fill in the Appwrite/Groq values.
7. Run: `uvicorn main:app --reload`
8. Open `http://127.0.0.1:8000`


## Appwrite database configuration
Create a database and six collections matching the names configured in `.env` (defaults below). Server-side API key must have database/collection document permissions for these collections. Avoid enabling public write access.


### Collections and attributes
All attributes should be created with the indicated types and generous limits. Required fields marked `Required` should be required; others can be optional.


**users**
- `username` — string, 32, Required
- `email` — string, 254, Required
- `password_hash` — string, 255, Required
- `created_at` — string, 40, Required
- Indexes: unique `email`; unique `username`

**sessions**
- `user_id` — string, 36, Required
- `token_hash` — string, 64, Required
- `expires_at` — string, 40, Required
- `created_at` — string, 40, Required
- Index: unique `token_hash`; index `user_id`

**conversations**
- `user_id` — string, 36, Required
- `title` — string, 120, Required
- `created_at` — string, 40, Required
- `updated_at` — string, 40, Required
- Index: `user_id`

**messages**
- `user_id` — string, 36, Required
- `conversation_id` — string, 36, Required
- `role` — string, 20, Required
- `content` — string, 45000, Required
- `created_at` — string, 40, Required
- Indexes: `user_id`; `conversation_id`

**projects**
- `user_id` — string, 36, Required
- `title` — string, 120, Required
- `content` — string, 50000, Required
- `created_at` — string, 40, Required
- `updated_at` — string, 40, Required
- Index: `user_id`

**settings**
- `user_id` — string, 36, Required
- `theme` — string, 30, Required
- `model` — string, 120, Required
- `created_at` — string, 40, Required
- `updated_at` — string, 40, Required
- Index: unique `user_id`

Note: Appwrite may limit string attribute sizes depending on plan/database configuration. If a 45,000 or 50,000 character string attribute cannot be created, use a lower maximum and adjust file/project truncation limits in `main.py` to match.


## Render deployment
- Use Python runtime.
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
- Add the Appwrite and Groq variables from `.env.example` to Render's Environment settings.
- Set `COOKIE_SECURE=true` for HTTPS.
- Do not upload or commit `.env`.


## API routes
- `POST /api/register`, `POST /api/login`, `POST /api/logout`, `GET /api/me`
- `GET /api/conversations`, `GET /api/conversations/{id}/messages`, `POST /api/chat`
- `POST /api/upload`
- `GET /api/projects`, `POST /api/projects`, `DELETE /api/projects/{id}`
- `GET /api/settings`, `POST /api/settings`
- `POST /api/search`, `POST /api/images`, `POST /api/code-assistant`
- `GET /health`
