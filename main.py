import os, secrets, hashlib, time, re, io, zipfile
from pathlib import Path
from datetime import datetime, timezone
from dotenv import load_dotenv
import bcrypt
from fastapi import FastAPI, Request, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import database as store
import doja_engine

load_dotenv()
app = FastAPI(title="DOJA AI Studio", version="Appwrite edition")
STATIC = Path(__file__).parent / "static"
STATIC.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC)), name="static")

SESSION_SECRET = os.getenv("SESSION_SECRET", "")
SESSION_TTL = 60 * 60 * 24 * 14

def hash_token(token: str) -> str:
    return hashlib.sha256((SESSION_SECRET + token).encode()).hexdigest()

def safe_id(value: str) -> str:
    return re.sub(r"[^a-zA-Z0-9_-]", "", value or "")[:80]

def current_user(request: Request):
    token = request.cookies.get("doja_session") or request.headers.get("x-doja-session")
    if not token:
        raise HTTPException(401, "Please log in.")
    session = store.find_one("sessions", "token_hash", hash_token(token))
    if not session or session.get("expires_at", 0) < int(time.time()):
        raise HTTPException(401, "Your session expired. Please log in again.")
    user = store.get("users", session["user_id"])
    return user

def create_session(user):
    token = secrets.token_urlsafe(40)
    store.create("sessions", {
        "user_id": user["$id"], "token_hash": hash_token(token),
        "expires_at": int(time.time()) + SESSION_TTL, "created_at": store.now_iso()
    })
    return token


@app.get("/", response_class=HTMLResponse)
def home():
    path = STATIC / "index.html"
    return path.read_text(encoding="utf-8")


class RegisterInput(BaseModel):
    username: str
    email: str
    password: str

class LoginInput(BaseModel):
    email: str
    password: str

class ChatInput(BaseModel):
    prompt: str
    conversation_id: str | None = None
    history: list[dict] = []
    model: str | None = None



@app.post("/api/register")
def register(data: RegisterInput):
    username = data.username.strip()
    email = data.email.strip().lower()
    if len(username) < 2 or len(username) > 32 or len(data.password) < 8:
        raise HTTPException(400, "Username must be 2–32 characters and password at least 8 characters.")
    if store.find_one("users", "email", email) or store.find_one("users", "username", username):
        raise HTTPException(409, "Email or username already registered.")
    pw = bcrypt.hashpw(data.password.encode(), bcrypt.gensalt()).decode()
    user = store.create("users", {"username": username, "email": email, "password_hash": pw, "created_at": store.now_iso()})
    token = create_session(user)
    response = JSONResponse({"ok": True, "user": {"id": user["$id"], "username": username, "email": email}})
    response.set_cookie("doja_session", token, httponly=True, samesite="lax", secure=False, max_age=SESSION_TTL)
    return response


@app.post("/api/login")
def login(data: LoginInput):
    user = store.find_one("users", "email", data.email.strip().lower())
    if not user or not bcrypt.checkpw(data.password.encode(), user.get("password_hash", "").encode()):
        raise HTTPException(401, "Incorrect email or password.")
    token = create_session(user)
    response = JSONResponse({"ok": True, "user": {"id": user["$id"], "username": user["username"], "email": user["email"]}})
    response.set_cookie("doja_session", token, httponly=True, samesite="lax", secure=False, max_age=SESSION_TTL)
    return response


@app.post("/api/logout")
def logout(request: Request):
    token = request.cookies.get("doja_session") or request.headers.get("x-doja-session")
    if token:
        session = store.find_one("sessions", "token_hash", hash_token(token))
        if session:
            store.delete("sessions", session["$id"])
    response = JSONResponse({"ok": True})
    response.delete_cookie("doja_session")
    return response


@app.get("/api/me")
def me(request: Request):
    user = current_user(request)
    return {"user": {"id": user["$id"], "username": user["username"], "email": user["email"]}}


@app.get("/api/conversations")
def conversations(request: Request):
    user = current_user(request)
    docs = store.list_docs("conversations", limit=100)
    owned = [d for d in docs if d.get("user_id") == user["$id"]]
    owned.sort(key=lambda d: d.get("updated_at", ""), reverse=True)
    return {"conversations": [{"id": d["$id"], "title": d.get("title", "New chat"), "updated_at": d.get("updated_at", "")} for d in owned]}


@app.get("/api/conversations/{conversation_id}/messages")
def get_messages(conversation_id: str, request: Request):
    user = current_user(request)
    conv = store.get("conversations", safe_id(conversation_id))
    if conv.get("user_id") != user["$id"]:
        raise HTTPException(403, "Not allowed to access this conversation.")
    docs = store.list_docs("messages", limit=100)
    msgs = [d for d in docs if d.get("conversation_id") == conv["$id"] and d.get("user_id") == user["$id"]]
    msgs.sort(key=lambda d: d.get("created_at", ""))
    return {"messages": [{"role": d.get("role"), "content": d.get("content", "")} for d in msgs]}


@app.post("/api/chat")
def chat(data: ChatInput, request: Request):
    user = current_user(request)
    prompt = data.prompt.strip()
    if not prompt:
        raise HTTPException(400, "Enter a message first.")
    conv_id = safe_id(data.conversation_id or "")
    if conv_id:
        conv = store.get("conversations", conv_id)
        if conv.get("user_id") != user["$id"]:
            raise HTTPException(403, "Conversation not found or not yours.")
    else:
        title = prompt[:70] + ("..." if len(prompt) > 70 else "")
        conv = store.create("conversations", {"user_id": user["$id"], "title": title or "New chat", "created_at": store.now_iso(), "updated_at": store.now_iso()})
        conv_id = conv["$id"]
    store.create("messages", {"user_id": user["$id"], "conversation_id": conv_id, "role": "user", "content": prompt, "created_at": store.now_iso()})
    try:
        answer = doja_engine.chat_with_doja(prompt, history=data.history, model_name=data.model)
    except Exception as e:
        raise HTTPException(502, str(e))
    store.create("messages", {"user_id": user["$id"], "conversation_id": conv_id, "role": "assistant", "content": answer, "created_at": store.now_iso()})
    store.update("conversations", conv_id, {"updated_at": store.now_iso()})
    return {"response": answer, "conversation_id": conv_id}


@app.post("/api/upload")
async def upload(request: Request, file: UploadFile = File(...), prompt: str = Form(""), conversation_id: str = Form(""), model: str = Form("")):
    user = current_user(request)
    contents = await file.read()
    if len(contents) > 8 * 1024 * 1024:
        raise HTTPException(413, "File too large. Maximum size is 8 MB.")
    name = (file.filename or "upload.txt").lower()
    context = ""
    try:
        if name.endswith(".pdf"):
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(contents))
            context = "\n".join((page.extract_text() or "") for page in reader.pages)
        elif name.endswith((".txt", ".md", ".py", ".js", ".html", ".css", ".json", ".csv", ".xml")):
            context = contents.decode("utf-8", errors="replace")
        else:
            raise HTTPException(415, "Supported uploads: PDF, TXT, MD, PY, JS, HTML, CSS, JSON, CSV, XML.")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(400, f"Could not read file: {e}")
    question = prompt.strip() or f"Summarize and explain the uploaded file {file.filename}."
    answer = doja_engine.chat_with_doja(question, model_name=model or None, file_context=context)
    # Uploaded-file analysis is saved in a new Appwrite conversation.
    conv = store.create("conversations", {"user_id": user["$id"], "title": question[:70], "created_at": store.now_iso(), "updated_at": store.now_iso()})
    store.create("messages", {"user_id": user["$id"], "conversation_id": conv["$id"], "role": "user", "content": f"[Uploaded file: {file.filename}]\n{question}", "created_at": store.now_iso()})
    store.create("messages", {"user_id": user["$id"], "conversation_id": conv["$id"], "role": "assistant", "content": answer, "created_at": store.now_iso()})
    return {"response": answer, "conversation_id": conv["$id"]}


@app.get("/api/projects")
def list_projects(request: Request):
    user = current_user(request)
    docs = store.list_docs("projects", limit=100)
    return {"projects": [d for d in docs if d.get("user_id") == user["$id"]]}


@app.post("/api/projects")
def save_project(request: Request, data: dict):
    user = current_user(request)
    title = str(data.get("title", "Untitled project"))[:100]
    content = str(data.get("content", ""))[:200000]
    return store.create("projects", {"user_id": user["$id"], "title": title, "content": content, "created_at": store.now_iso(), "updated_at": store.now_iso()})

@app.get("/api/settings")
def get_settings(request: Request):
    user = current_user(request)
    doc = store.find_one("settings", "user_id", user["$id"])
    return {"settings": doc or {"model": os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"), "theme": "dark"}}

@app.post("/api/settings")
def save_settings(request: Request, data: dict):
    user = current_user(request)
    doc = store.find_one("settings", "user_id", user["$id"])
    safe = {"user_id": user["$id"], "model": str(data.get("model", "llama-3.3-70b-versatile"))[:120], "theme": str(data.get("theme", "dark"))[:20], "updated_at": store.now_iso()}
    if doc:
        return store.update("settings", doc["$id"], safe)
    return store.create("settings", safe)


@app.get("/health")
def health():
    return {"status": "ok", "database": "Appwrite", "ai_configured": bool(os.getenv("GROQ_API_KEY"))}
