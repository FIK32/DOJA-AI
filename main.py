import os, secrets, hashlib, bcrypt, io, re
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import database as store
import doja_engine

load_dotenv()
BASE = Path(__file__).resolve().parent
STATIC = BASE / "static"
STATIC.mkdir(exist_ok=True)
app = FastAPI(title="DOJA AI Studio")
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")
SESSION_COOKIE = "doja_session"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "true").lower() == "true"

class ChatPayload(BaseModel):
    prompt: str = ""
    history: list = []
    conversation_id: Optional[str] = None
    model: Optional[str] = None

class ProjectPayload(BaseModel):
    title: str
    content: str = ""
    project_id: Optional[str] = None

class SettingsPayload(BaseModel):
    theme: Optional[str] = "neon"
    model: Optional[str] = None

class SearchPayload(BaseModel):
    query: str

class ImagePayload(BaseModel):
    prompt: str
    style: str = "realistic"
    ratio: str = "1:1"


def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()

def safe_error(exc):
    text = str(exc)
    # Avoid leaking API key values even if provider exception contains a request dump.
    for secret in (os.getenv("APPWRITE_API_KEY", ""), os.getenv("GROQ_API_KEY", "")):
        if secret:
            text = text.replace(secret, "[hidden]")
    return text[:700]

def current_user(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    try:
        session = store.find_one("sessions", "token_hash", hash_token(token))
        if not session:
            return None
        if session.get("expires_at"):
            expires = datetime.fromisoformat(session["expires_at"].replace("Z", "+00:00"))
            if expires < datetime.now(timezone.utc):
                try: store.delete("sessions", session["$id"])
                except Exception: pass
                return None
        return store.get("users", session["user_id"])
    except Exception:
        return None

def require_user(request: Request):
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Please log in to continue.")
    return user

def user_docs(collection, user_id, limit=100):
    # Owner filtering is done in Python to avoid requiring an index for every query.
    docs = store.list_docs(collection, limit=100)
    return [d for d in docs if d.get("user_id") == user_id][:limit]

def conversation_owned(conversation_id, user_id):
    if not conversation_id:
        return None
    try:
        conv = store.get("conversations", conversation_id)
        return conv if conv.get("user_id") == user_id else None
    except Exception:
        return None

def make_conversation(user_id, title="New chat"):
    return store.create("conversations", {"user_id": user_id, "title": (title or "New chat")[:120], "created_at": store.now_iso(), "updated_at": store.now_iso()})

def title_from_prompt(prompt):
    text = re.sub(r"\s+", " ", (prompt or "")).strip()
    return (text[:58] + "…") if len(text) > 58 else (text or "File analysis")

def save_message(user_id, conversation_id, role, content):
    return store.create("messages", {"user_id": user_id, "conversation_id": conversation_id, "role": role, "content": content[:45000], "created_at": store.now_iso()})

def generate_for_chat(user, prompt, history, conversation_id, model, file_context="", force_search=False):
    uid = user["$id"]
    conv = conversation_owned(conversation_id, uid) if conversation_id else None
    if not conv:
        conv = make_conversation(uid, title_from_prompt(prompt))
    if prompt.strip():
        save_message(uid, conv["$id"], "user", prompt)
    try:
        answer = doja_engine.chat_with_doja(prompt, history=history, model_name=model, file_context=file_context, force_search=force_search)
    except Exception as e:
        # The user message remains saved; return a useful error instead of silently failing.
        raise HTTPException(status_code=502, detail=safe_error(e))
    save_message(uid, conv["$id"], "assistant", answer)
    try:
        store.update("conversations", conv["$id"], {"updated_at": store.now_iso(), "title": conv.get("title") or title_from_prompt(prompt)})
    except Exception: pass
    return {"response": answer, "conversation_id": conv["$id"]}


@app.get("/", response_class=HTMLResponse)
def home():
    path = STATIC / "index.html"
    if not path.exists():
        raise HTTPException(404, "Frontend index.html is missing")
    return path.read_text(encoding="utf-8")


@app.get("/health")
def health():
    return {"status": "ok", "app": "DOJA AI Studio", "ai_configured": bool(os.getenv("GROQ_API_KEY"))}


@app.post("/api/register")
def register(payload: dict, request: Request):
    username = str(payload.get("username", "")).strip()
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    if len(username) < 2 or len(username) > 32:
        raise HTTPException(400, "Username must be between 2 and 32 characters.")
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(400, "Please enter a valid email address.")
    if len(password) < 8:
        raise HTTPException(400, "Password must be at least 8 characters.")
    try:
        if store.find_one("users", "email", email):
            raise HTTPException(409, "An account with this email already exists.")
        if store.find_one("users", "username", username):
            raise HTTPException(409, "That username is already taken.")
        user = store.create("users", {"username": username, "email": email, "password_hash": bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode(), "created_at": store.now_iso()})
        token = secrets.token_urlsafe(40)
        store.create("sessions", {"user_id": user["$id"], "token_hash": hash_token(token), "expires_at": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(), "created_at": store.now_iso()})
        resp = JSONResponse({"user": {"id": user["$id"], "username": username, "email": email}})
        resp.set_cookie(SESSION_COOKIE, token, httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=14*24*3600, path="/")
        return resp
    except HTTPException: raise
    except Exception as e: raise HTTPException(500, "Registration failed. Check Appwrite collections, attributes, permissions, and server configuration.") from e


@app.post("/api/login")
def login(payload: dict):
    email = str(payload.get("email", "")).strip().lower()
    password = str(payload.get("password", ""))
    try:
        user = store.find_one("users", "email", email)
        if not user or not bcrypt.checkpw(password.encode(), user.get("password_hash", "").encode()):
            raise HTTPException(401, "Incorrect email or password.")
        token = secrets.token_urlsafe(40)
        store.create("sessions", {"user_id": user["$id"], "token_hash": hash_token(token), "expires_at": (datetime.now(timezone.utc) + timedelta(days=14)).isoformat(), "created_at": store.now_iso()})
        resp = JSONResponse({"user": {"id": user["$id"], "username": user.get("username"), "email": user.get("email")}})
        resp.set_cookie(SESSION_COOKIE, token, httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=14*24*3600, path="/")
        return resp
    except HTTPException: raise
    except Exception as e: raise HTTPException(500, "Login failed. Check Appwrite configuration and required collection attributes.") from e


@app.post("/api/logout")
def logout(request: Request):
    token = request.cookies.get(SESSION_COOKIE)
    if token:
        try:
            session = store.find_one("sessions", "token_hash", hash_token(token))
            if session: store.delete("sessions", session["$id"])
        except Exception: pass
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@app.get("/api/me")
def me(request: Request):
    user = require_user(request)
    return {"user": {"id": user["$id"], "username": user.get("username"), "email": user.get("email")}}


@app.get("/api/conversations")
def conversations(request: Request):
    user = require_user(request)
    docs = user_docs("conversations", user["$id"])
    docs.sort(key=lambda d: d.get("updated_at", d.get("created_at", "")), reverse=True)
    return {"conversations": [{"id": d["$id"], "title": d.get("title", "Chat"), "created_at": d.get("created_at"), "updated_at": d.get("updated_at")} for d in docs]}

@app.get("/api/conversations/{conversation_id}/messages")
def conversation_messages(conversation_id: str, request: Request):
    user = require_user(request)
    if not conversation_owned(conversation_id, user["$id"]):
        raise HTTPException(404, "Conversation not found.")
    docs = user_docs("messages", user["$id"])
    docs = [d for d in docs if d.get("conversation_id") == conversation_id]
    docs.sort(key=lambda d: d.get("created_at", ""))
    return {"messages": [{"role": d.get("role", "assistant"), "content": d.get("content", "")} for d in docs]}

@app.post("/api/chat")
def chat(payload: ChatPayload, request: Request):
    user = require_user(request)
    return generate_for_chat(user, payload.prompt, payload.history, payload.conversation_id, payload.model)


@app.post("/api/upload")
async def upload(request: Request, file: UploadFile = File(...), prompt: str = Form(""), model: str = Form(""), conversation_id: str = Form("")):
    user = require_user(request)
    name = (file.filename or "upload").lower()
    if not any(name.endswith(ext) for ext in (".txt", ".md", ".pdf", ".py", ".js", ".html", ".css", ".json", ".csv", ".xml")):
        raise HTTPException(400, "File type not supported.")
    raw = await file.read()
    if len(raw) > 8 * 1024 * 1024:
        raise HTTPException(413, "File is larger than the 8 MB upload limit.")
    try:
        if name.endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw))
            text = "\n".join(page.extract_text() or "" for page in reader.pages)
        else:
            text = raw.decode("utf-8", errors="replace")
    except Exception as e:
        raise HTTPException(400, "Could not read this file. If it is a PDF, ensure it contains selectable text.") from e
    task = prompt.strip() or f"Analyze the uploaded file named {file.filename}. Summarize it and identify important details."
    return generate_for_chat(user, task, [], conversation_id or None, model or None, file_context=f"File: {file.filename}\n\n{text}")

@app.get("/api/projects")
def get_projects(request: Request):
    user = require_user(request)
    docs = user_docs("projects", user["$id"])
    docs.sort(key=lambda d: d.get("updated_at", d.get("created_at", "")), reverse=True)
    return {"projects": [{"id": d["$id"], "title": d.get("title", "Untitled"), "content": d.get("content", ""), "created_at": d.get("created_at"), "updated_at": d.get("updated_at")} for d in docs]}
@app.post("/api/projects")
def save_project(payload: ProjectPayload, request: Request):
    user = require_user(request)
    title = payload.title.strip()
    if not title: raise HTTPException(400, "Project title is required.")
    data = {"user_id": user["$id"], "title": title[:120], "content": payload.content[:50000], "updated_at": store.now_iso()}
    if payload.project_id:
        try:
            existing = store.get("projects", payload.project_id)
            if existing.get("user_id") != user["$id"]: raise HTTPException(404, "Project not found.")
            project = store.update("projects", payload.project_id, data)
        except HTTPException: raise
        except Exception as e: raise HTTPException(404, "Project not found.") from e
    else:
        data["created_at"] = store.now_iso()
        project = store.create("projects", data)
    return {"project": {"id": project["$id"], "title": project.get("title", title), "content": project.get("content", payload.content)}}
@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str, request: Request):
    user = require_user(request)
    try:
        project = store.get("projects", project_id)
        if project.get("user_id") != user["$id"]: raise HTTPException(404, "Project not found.")
        store.delete("projects", project_id)
        return {"ok": True}
    except HTTPException: raise
    except Exception as e: raise HTTPException(404, "Project not found.") from e

@app.get("/api/settings")
def get_settings(request: Request):
    user = require_user(request)
    doc = store.find_one("settings", "user_id", user["$id"])
    return {"settings": {"theme": (doc or {}).get("theme", "neon"), "model": (doc or {}).get("model", doja_engine.MODEL_DEFAULT)}}
@app.post("/api/settings")
def save_settings(payload: SettingsPayload, request: Request):
    user = require_user(request)
    data = {"user_id": user["$id"], "theme": (payload.theme or "neon")[:30], "model": (payload.model or doja_engine.MODEL_DEFAULT)[:120], "updated_at": store.now_iso()}
    existing = store.find_one("settings", "user_id", user["$id"])
    if existing: store.update("settings", existing["$id"], data)
    else: data["created_at"] = store.now_iso(); store.create("settings", data)
    return {"settings": {"theme": data["theme"], "model": data["model"]}}
@app.post("/api/search")
def search(payload: SearchPayload, request: Request):
    require_user(request)
    results = doja_engine.web_search(payload.query, 8)
    if not results: return {"results": [], "message": "Search returned no results or is temporarily unavailable."}
    return {"results": results}
@app.post("/api/images")
def images(payload: ImagePayload, request: Request):
    require_user(request)
    if not payload.prompt.strip(): raise HTTPException(400, "Enter an image description.")
    url = doja_engine.image_url(payload.prompt.strip(), payload.style, payload.ratio)
    return {"image_url": url, "notice": "This uses a third-party image endpoint. Availability and safety filtering depend on that service."}
@app.post("/api/code-assistant")
def code_assistant(payload: ChatPayload, request: Request):
    user = require_user(request)
    code_context = ""
    # The frontend includes editor contents at the beginning of the prompt.
    return {"response": doja_engine.chat_with_doja(payload.prompt, payload.history, payload.model, code_context)}
