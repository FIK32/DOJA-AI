# DOJA AI Studio — Appwrite database edition

This project uses **Appwrite for all database records**. It does not use SQLite.
FastAPI is the web/API server, and Groq provides chat responses.

## Included
- Appwrite-backed account records, sessions, chat conversations, chat messages, projects and settings
- Groq chat endpoint, conversation context and selectable model
- DuckDuckGo search for prompts that explicitly request current/web information
- Upload and text extraction for PDF, TXT, Markdown, Python, JavaScript, HTML, CSS, JSON, CSV and XML
- Simple responsive chat UI

## 1. Create/prepare Appwrite
In Appwrite Console, use your existing project and create (or use) one database. Create these collections with the collection IDs matching the names below (or change them in `.env`):


### `users`
Attributes:
- `username` String, 32, required
- `email` String, 255, required
- `password_hash` String, 255, required
- `created_at` String, 50, required
Indexes: unique index on `email`; unique index on `username`

### `sessions`
Attributes:
- `user_id` String, 36, required
- `token_hash` String, 64, required
- `expires_at` Integer, required
- `created_at` String, 50, required
Indexes: unique index on `token_hash`; index on `user_id`

### `conversations`
Attributes:
- `user_id` String, 36, required
- `title` String, 100, required
- `created_at` String, 50, required
- `updated_at` String, 50, required
Indexes: index on `user_id`

### `messages`
Attributes:
- `user_id` String, 36, required
- `conversation_id` String, 36, required
- `role` String, 20, required
- `content` String, 10000, required
- `created_at` String, 50, required
Indexes: index on `user_id`; index on `conversation_id`

### `projects`
Attributes:
- `user_id` String, 36, required
- `title` String, 100, required
- `content` String, 10000, required
- `created_at` String, 50, required
- `updated_at` String, 50, required
Indexes: index on `user_id`

### `settings`
Attributes:
- `user_id` String, 36, required
- `model` String, 120, required
- `theme` String, 20, required
- `updated_at` String, 50, required
Indexes: unique index on `user_id`


Use a server API key with the database read/write permissions needed for these collections. Keep that API key private and only in the server `.env` file. The API key is never sent to the browser.


## 2. Set environment variables
Copy `.env.example` to `.env` and fill the values from Appwrite Console and your Groq API-key page:

- `APPWRITE_ENDPOINT` (your Appwrite endpoint)
- `APPWRITE_PROJECT_ID`
- `APPWRITE_API_KEY` (server key, never commit it)
- `APPWRITE_DATABASE_ID`
- `GROQ_API_KEY`
- `SESSION_SECRET` (long random string)

You may adjust collection ID environment values if your existing Appwrite IDs differ.


## 3. Install and run (Windows)
Open the project folder in VS Code, then run in terminal:

```powershell
py -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```
Edit `.env`, then start:

```powershell
uvicorn main:app --reload
```
Open http://127.0.0.1:8000

## Notes before public deployment
This is a development starter, not production-ready. Before deploying publicly, implement secure production cookie settings (`secure=True` behind HTTPS), CSRF protection, rate limiting, email verification, account recovery, moderation, usage limits, Appwrite Storage for uploaded files, and review permissions. Appwrite collections should not be public; this backend uses server credentials. Add `.env` to `.gitignore`.

