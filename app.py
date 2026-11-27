import os
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

import database as db
import doja_engine as engine

app = FastAPI(title="DOJA AI")
ROOT = Path(__file__).parent
WORKSPACE = Path(os.getenv("WORKSPACE_DIR", str(ROOT / "workspace")))
WORKSPACE.mkdir(parents=True, exist_ok=True)
COOKIE = "doja_session"
COOKIE_SECURE = os.getenv("COOKIE_SECURE", "false").lower() == "true"
MAX_UPLOAD = 8 * 1024 * 1024


def fail(message: str, code: int = 400):
    return JSONResponse({"detail": message}, status_code=code)


def session(request: Request) -> str | None:
    return request.cookies.get(COOKIE)


def user(request: Request) -> dict | None:
    token = session(request)
    if not token:
        return None
    try:
        return db.account(token)
    except Exception:
        return None


def require_user(request: Request):
    current = user(request)
    if not current:
        raise PermissionError("Please sign in again.")
    return current


def safe_name(name: str) -> str:
    return Path(name.replace("\\", "/")).name[:180] or "file.txt"


def read_payload(doc: dict) -> dict:
    try:
        return json.loads(doc.get("payload", "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}


def api_error(exc: Exception):
    if isinstance(exc, PermissionError):
        return fail(str(exc), 401)
    if isinstance(exc, db.ConfigurationError):
        return fail(str(exc), 503)
    return fail(str(exc) or "Request failed.", 400)


@app.get("/")
def index():
    return FileResponse(ROOT / "index.html")


@app.get("/api/session")
def session_status(request: Request):
    current = user(request)
    if not current:
        return fail("Please sign in again.", 401)
    return {"user": {"id": current.get("$id"), "name": current.get("name", ""), "email": current.get("email", "")}}


@app.post("/api/signup")
async def signup(request: Request):
    data = await request.json()
    name, email, password = str(data.get("name", "")).strip(), str(data.get("email", "")).strip(), str(data.get("password", ""))
    if not name or not email or len(password) < 8:
        return fail("Enter a name and valid email. Passwords must be at least 8 characters.")
    try:
        db.create_account(name, email, password)
        result = db.login(email, password)
        response = JSONResponse({"ok": True})
        response.set_cookie(COOKIE, result["secret"], httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=30 * 86400)
        return response
    except Exception as exc:
        return api_error(exc)


@app.post("/api/login")
async def login(request: Request):
    data = await request.json()
    try:
        result = db.login(str(data.get("email", "")).strip(), str(data.get("password", "")))
        response = JSONResponse({"ok": True})
        response.set_cookie(COOKIE, result["secret"], httponly=True, secure=COOKIE_SECURE, samesite="lax", max_age=30 * 86400)
        return response
    except Exception:
        return fail("Sign-in failed. Check your email and password.", 401)


@app.post("/api/logout")
def logout(request: Request):
    token = session(request)
    if token:
        try:
            db.logout(token)
        except Exception:
            pass
    response = JSONResponse({"ok": True})
    response.delete_cookie(COOKIE, httponly=True, secure=COOKIE_SECURE, samesite="lax")
    return response


@app.post("/api/password/recovery")
async def password_recovery(request: Request):
    data = await request.json()
    try:
        db.password_recovery(str(data.get("email", "")), str(data.get("url", os.getenv("APPWRITE_RECOVERY_URL", ""))))
        return {"ok": True, "message": "If the account exists, Appwrite will send a recovery email."}
    except Exception as exc:
        return api_error(exc)


@app.post("/api/password/reset")
async def password_reset(request: Request):
    data = await request.json()
    password = str(data.get("password", ""))
    if len(password) < 8:
        return fail("Password must be at least 8 characters.")
    try:
        db.password_reset(str(data.get("userId", "")), str(data.get("secret", "")), password)
        return {"ok": True}
    except Exception as exc:
        return api_error(exc)


@app.post("/api/password/change")
async def password_change(request: Request):
    try:
        current = require_user(request)
        data = await request.json()
        new = str(data.get("newPassword", ""))
        if len(new) < 8:
            return fail("Password must be at least 8 characters.")
        db.password_change(session(request), str(data.get("currentPassword", "")), new)
        return {"ok": True}
    except Exception as exc:
        return api_error(exc)


@app.get("/api/models")
def models():
    return {"models": engine.available_models(), "default": engine.default_model()}


@app.get("/api/settings")
def get_settings(request: Request):
    try:
        current = require_user(request)
        return db.get_settings(current["$id"])
    except Exception as exc:
        return api_error(exc)


@app.put("/api/settings")
async def put_settings(request: Request):
    try:
        current = require_user(request)
        data = await request.json()
        clean = {k: str(v)[:4000] for k, v in data.items() if k in {"instructions", "theme", "model"}}
        return db.put_settings(current["$id"], clean)
    except Exception as exc:
        return api_error(exc)


@app.post("/api/chat")
async def chat(request: Request):
    try:
        current = require_user(request)
        data = await request.json()
        prompt = str(data.get("message", "")).strip()
        if not prompt or len(prompt) > 16000:
            return fail("Message is empty or too long.")
        settings = db.get_settings(current["$id"])
        model = str(data.get("model") or settings.get("model") or engine.default_model())
        history = data.get("history", [])
        if not isinstance(history, list):
            history = []
        history = [{"role": m.get("role"), "content": str(m.get("content", ""))[:8000]} for m in history[-16:] if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
        attachment = str(data.get("attachment_text", ""))[:24000]
        result = engine.answer(prompt, history, model=model, instructions=settings.get("instructions", ""), attachment_text=attachment)
        now = datetime.now(timezone.utc).isoformat()
        chat_id = str(data.get("chat_id") or "")
        title = str(data.get("title") or prompt[:80])
        record = {"id": chat_id, "title": title, "messages": history + [{"role": "user", "content": prompt}, {"role": "assistant", "content": result["answer"]}], "updatedAt": now}
        saved = db.save_chat(current["$id"], record)
        return {**result, "chat_id": saved.get("$id", chat_id), "title": title}
    except Exception as exc:
        return api_error(exc)


@app.get("/api/chats")
def chats(request: Request):
    try:
        current = require_user(request)
        docs = db.list_records("chats", current["$id"])
        return {"chats": [{"id": d["$id"], **read_payload(d)} for d in docs]}
    except Exception as exc:
        return api_error(exc)


@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str, request: Request):
    try:
        current = require_user(request)
        doc = db.get_record("chats", current["$id"], chat_id)
        return {"id": doc["$id"], **read_payload(doc)}
    except Exception as exc:
        return api_error(exc)


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str, request: Request):
    try:
        current = require_user(request)
        db.delete_record("chats", current["$id"], chat_id)
        return {"ok": True}
    except Exception as exc:
        return api_error(exc)


@app.get("/api/projects")
def projects(request: Request):
    try:
        current = require_user(request)
        docs = db.list_records("projects", current["$id"])
        return {"projects": [{"id": d["$id"], **read_payload(d)} for d in docs]}
    except Exception as exc:
        return api_error(exc)


@app.post("/api/projects")
async def create_project(request: Request):
    try:
        current = require_user(request)
        data = await request.json()
        record = {"name": str(data.get("name", "New project"))[:120], "description": str(data.get("description", ""))[:4000], "createdAt": datetime.now(timezone.utc).isoformat()}
        saved = db.create_record("projects", current["$id"], record)
        return {"id": saved["$id"], **record}
    except Exception as exc:
        return api_error(exc)


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str, request: Request):
    try:
        current = require_user(request)
        db.delete_record("projects", current["$id"], project_id)
        return {"ok": True}
    except Exception as exc:
        return api_error(exc)


@app.post("/api/upload")
async def upload(request: Request, file: UploadFile = File(...)):
    try:
        current = require_user(request)
        content = await file.read(MAX_UPLOAD + 1)
        if len(content) > MAX_UPLOAD:
            return fail("Uploads are limited to 8 MB.", 413)
        name = safe_name(file.filename or "upload")
        stored = db.storage_upload(current["$id"], name, content, file.content_type or "application/octet-stream")
        local = WORKSPACE / current["$id"]
        local.mkdir(parents=True, exist_ok=True)
        (local / name).write_bytes(content)
        text, image_data = engine.extract_upload(name, file.content_type or "", content)
        return {"file": {"id": stored.get("$id", name), "name": name}, "text": text, "image_data": image_data}
    except Exception as exc:
        return api_error(exc)


@app.get("/api/files")
def files(request: Request):
    try:
        current = require_user(request)
        return {"files": db.storage_list(current["$id"])}
    except Exception as exc:
        return api_error(exc)


@app.get("/api/files/{file_id}")
def download_file(file_id: str, request: Request):
    try:
        current = require_user(request)
        name, content, mime = db.storage_download(current["$id"], file_id)
        return Response(content, media_type=mime, headers={"Content-Disposition": f'attachment; filename="{safe_name(name)}"'})
    except Exception as exc:
        return api_error(exc)


@app.delete("/api/files/{file_id}")
def delete_file(file_id: str, request: Request):
    try:
        current = require_user(request)
        db.storage_delete(current["$id"], file_id)
        return {"ok": True}
    except Exception as exc:
        return api_error(exc)


@app.get("/api/workspace/zip")
def workspace_zip(request: Request):
    try:
        import io, zipfile
        current = require_user(request)
        files = db.storage_list(current["$id"])
        output = io.BytesIO()
        with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in files:
                name, content, _ = db.storage_download(current["$id"], item["id"])
                archive.writestr(safe_name(name), content)
        return Response(output.getvalue(), media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="doja-workspace.zip"'})
    except Exception as exc:
        return api_error(exc)


@app.get("/api/search")
def web_search(request: Request, q: str):
    try:
        require_user(request)
        return {"results": engine.web_search(q)}
    except Exception as exc:
        return api_error(exc)


@app.get("/api/github")
def github_lookup(request: Request, repo: str):
    try:
        require_user(request)
        return engine.github_lookup(repo)
    except Exception as exc:
        return api_error(exc)


@app.get("/api/images/search")
def image_search(request: Request, q: str):
    try:
        require_user(request)
        return {"results": engine.image_search(q)}
    except Exception as exc:
        return api_error(exc)


@app.post("/api/images/generate")
async def image_generate(request: Request):
    try:
        require_user(request)
        data = await request.json()
        return {"url": engine.image_generation_url(str(data.get("prompt", "")), str(data.get("style", "")), str(data.get("size", "1024x1024")))}
    except Exception as exc:
        return api_error(exc)


@app.get("/api/workspace/preview", response_class=FileResponse)
def workspace_preview(request: Request):
    try:
        current = require_user(request)
        path = WORKSPACE / current["$id"] / "index.html"
        if not path.exists():
            return fail("Create or upload index.html to preview the workspace.", 404)
        return FileResponse(path)
    except Exception as exc:
        return api_error(exc)

