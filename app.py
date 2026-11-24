import io
import os
import re
import zipfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

import database
import doja_engine

app = FastAPI(title="DOJA AI Studio")
os.makedirs("workspace", exist_ok=True)
app.mount("/static", StaticFiles(directory="workspace"), name="static")
GMAIL_USER = os.getenv("GMAIL_USER", "")  # configured for Appwrite mail/recovery delivery


class SignupRequest(BaseModel):
    username: str = Field(min_length=1, max_length=100)
    email: str
    password: str = Field(min_length=8, max_length=256)


class LoginRequest(BaseModel):
    username_or_email: str
    password: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str = ""
    user_id: str = ""
    secret: str = ""
    new_password: str = Field(min_length=8, max_length=256)


class ChatRequest(BaseModel):
    prompt: str
    user_id: str = ""
    history: list = Field(default_factory=list)
    model: str = "openai/gpt-oss-120b"


class SettingsRequest(BaseModel):
    user_id: str = ""
    custom_instructions: str = ""


def _set_session_cookie(response, secret, request):
    response.set_cookie(
        "doja_session", secret, httponly=True, secure=request.url.scheme == "https",
        samesite="lax", max_age=60 * 60 * 24 * 30, path="/",
    )


def _clear_session_cookie(response):
    response.delete_cookie("doja_session", path="/")


def _current_user(request):
    user = database.get_account_from_session(request.cookies.get("doja_session", ""))
    if not user:
        raise HTTPException(status_code=401, detail="Please sign in again.")
    return user


def _owned_user(request, requested_id=""):
    user = _current_user(request)
    if requested_id and str(requested_id) != user["$id"]:
        raise HTTPException(status_code=403, detail="User does not own this resource.")
    return user


@app.get("/", response_class=HTMLResponse)
def home():
    path = Path("index.html")
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return "<h1>DOJA AI: index.html was not found</h1>"


@app.post("/api/signup")
def signup(req: SignupRequest, request: Request):
    result = database.create_user(req.username.strip(), req.email.strip().lower(), req.password)
    if not result["success"]:
        return JSONResponse(status_code=400, content=result)
    login = database.authenticate_user(req.email.strip().lower(), req.password)
    if not login.get("success"):
        return JSONResponse(status_code=201, content=result)
    response = JSONResponse(content={k: v for k, v in login.items() if k != "session_secret"})
    _set_session_cookie(response, login["session_secret"], request)
    return response


@app.post("/api/login")
def login(req: LoginRequest, request: Request):
    result = database.authenticate_user(req.username_or_email.strip(), req.password)
    if not result["success"]:
        return JSONResponse(status_code=401, content=result)
    response = JSONResponse(content={k: v for k, v in result.items() if k != "session_secret"})
    _set_session_cookie(response, result["session_secret"], request)
    return response


@app.get("/api/session")
def session(request: Request):
    user = _current_user(request)
    return {"success": True, "user_id": user["$id"], "username": user.get("name", ""), "email": user.get("email", "")}


@app.post("/api/logout")
def logout(request: Request):
    database.delete_session(request.cookies.get("doja_session", ""))
    response = JSONResponse({"success": True})
    _clear_session_cookie(response)
    return response


@app.post("/api/forgot-password")
def forgot_password(req: ForgotPasswordRequest):
    try:
        database.create_password_reset_token(req.email)
    except RuntimeError:
        # Avoid account enumeration: respond the same way for unknown accounts or mail failures.
        pass
    return {"success": True, "message": "If the account exists, Appwrite will send a recovery email."}


@app.post("/api/reset-password")
def reset_password(req: ResetPasswordRequest):
    result = database.reset_password_with_token(req.token, req.new_password, req.user_id, req.secret)
    if not result["success"]:
        return JSONResponse(status_code=400, content=result)
    return result


@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    user = _owned_user(request, req.user_id)
    try:
        text = doja_engine.chat_with_doja(req.prompt, user["$id"], req.history, req.model)
        return {"status": "success", "response": text}
    except Exception:
        return JSONResponse(status_code=500, content={"status": "error", "message": "DOJA could not complete the request."})


@app.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...), prompt: str = Form(""), user_id: str = Form(""), model: str = Form("openai/gpt-oss-120b")):
    user = _owned_user(request, user_id)
    content = await file.read(8 * 1024 * 1024 + 1)
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File exceeds the 8 MB analysis limit.")
    text_content = content.decode("utf-8", errors="ignore")[:6000] or "[Binary content]"
    combined = f"File: {Path(file.filename or 'upload').name}\n\nContent:\n{text_content}\n\nRequest: {prompt or 'Analyze this file and summarize.'}"
    try:
        answer = doja_engine.chat_with_doja(combined, user["$id"], [], model)
        return {"status": "success", "response": answer}
    except Exception:
        return JSONResponse(status_code=500, content={"status": "error", "message": "DOJA could not analyze that file."})


@app.get("/api/download-zip")
def download_workspace_zip(request: Request):
    user = _current_user(request)
    files = database.list_workspace_files(user["$id"])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/zip", headers={"Content-Disposition": "attachment; filename=doja_ai_project.zip"})


@app.get("/api/get-code")
def get_workspace_code(request: Request):
    user = _current_user(request)
    return {"files": database.list_workspace_files(user["$id"])}


@app.get("/workspace/{filename:path}")
def workspace_file(filename: str, request: Request):
    user = _current_user(request)
    if not filename or ".." in Path(filename).parts:
        raise HTTPException(status_code=404, detail="File not found.")
    files = database.list_workspace_files(user["$id"])
    if filename not in files:
        raise HTTPException(status_code=404, detail="File not found.")
    path = (Path("workspace").resolve() / user["$id"] / filename).resolve()
    root = (Path("workspace").resolve() / user["$id"]).resolve()
    if root not in path.parents and path != root:
        raise HTTPException(status_code=404, detail="File not found.")
    return FileResponse(path)


@app.get("/api/projects/{user_id}")
def user_projects(user_id: str, request: Request):
    user = _owned_user(request, user_id)
    return {"projects": database.get_user_projects(user["$id"])}


@app.get("/api/projects/{project_id}/load")
def load_user_project(project_id: str, user_id: str, request: Request):
    user = _owned_user(request, user_id)
    messages = database.get_project(project_id, user["$id"])
    if messages is None:
        return JSONResponse(status_code=404, content={"success": False, "error": "Project not found."})
    return {"messages": messages}


@app.delete("/api/projects/{project_id}")
def delete_user_project(project_id: str, user_id: str, request: Request):
    user = _owned_user(request, user_id)
    database.delete_project(project_id, user["$id"])
    return {"success": True}


@app.post("/api/settings")
def update_settings(req: SettingsRequest, request: Request):
    user = _owned_user(request, req.user_id)
    database.save_user_instructions(user["$id"], req.custom_instructions.strip())
    return {"success": True}


@app.get("/api/settings/{user_id}")
def get_settings(user_id: str, request: Request):
    user = _owned_user(request, user_id)
    return {"custom_instructions": database.get_user_instructions(user["$id"])}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
