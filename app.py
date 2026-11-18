import os
import io
import zipfile
import smtplib
from email.mime.text import MIMEText
from fastapi import FastAPI, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import doja_engine
import database

app = FastAPI(title="DOJA AI Studio")

os.makedirs("workspace", exist_ok=True)
app.mount("/workspace", StaticFiles(directory="workspace", html=True), name="workspace")

GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_APP_PASS = os.getenv("GMAIL_APP_PASS", "")

def send_reset_email(to_email: str, reset_link: str):
    if GMAIL_USER and GMAIL_APP_PASS:
        try:
            msg = MIMEText(f"Click the link below to reset your DOJA AI password:\n\n{reset_link}\n\nExpires in 1 hour.")
            msg['Subject'] = 'DOJA AI - Password Reset'
            msg['From'] = GMAIL_USER
            msg['To'] = to_email
            with smtplib.SMTP_SSL('smtp.gmail.com', 465) as server:
                server.login(GMAIL_USER, GMAIL_APP_PASS)
                server.send_message(msg)
            return True
        except Exception:
            return False
    else:
        print(f"\n🔑 [RESET LINK FOR {to_email}]: {reset_link}\n")
        return True

class SignupRequest(BaseModel):
    username: str
    email: str
    password: str

class LoginRequest(BaseModel):
    username_or_email: str
    password: str

class ForgotPasswordRequest(BaseModel):
    email: str

class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str

class ChatRequest(BaseModel):
    prompt: str
    user_id: int = 1
    history: list = []
    model: str = "openai/gpt-oss-120b"

class SettingsRequest(BaseModel):
    user_id: int
    custom_instructions: str

@app.get("/", response_class=HTMLResponse)
def home():
    with open("templates/index.html", "r", encoding="utf-8") as f:
        return f.read()

# ----------------- AUTH ROUTES -----------------
@app.post("/api/signup")
def signup(req: SignupRequest):
    result = database.create_user(req.username.strip(), req.email.strip().lower(), req.password.strip())
    if not result["success"]:
        return JSONResponse(status_code=400, content=result)
    return result

@app.post("/api/login")
def login(req: LoginRequest):
    result = database.authenticate_user(req.username_or_email.strip(), req.password.strip())
    if not result["success"]:
        return JSONResponse(status_code=401, content=result)
    return result

@app.post("/api/forgot-password")
def forgot_password(req: ForgotPasswordRequest, request: Request):
    email = req.email.strip().lower()
    token = database.create_password_reset_token(email)
    if not token:
        return JSONResponse(status_code=404, content={"success": False, "error": "No account found with that email."})
    base_url = str(request.base_url).rstrip("/")
    reset_link = f"{base_url}/?reset_token={token}"
    send_reset_email(email, reset_link)
    return {"success": True, "message": "Password reset link created!", "preview_link": reset_link}

@app.post("/api/reset-password")
def reset_password(req: ResetPasswordRequest):
    result = database.reset_password_with_token(req.token, req.new_password)
    if not result["success"]:
        return JSONResponse(status_code=400, content=result)
    return result

# ----------------- CHAT & FILE ANALYSIS -----------------
@app.post("/api/chat")
def chat(req: ChatRequest):
    try:
        response_text = doja_engine.chat_with_doja(req.prompt, req.user_id, req.history, req.model)
        return {"status": "success", "response": response_text}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

@app.post("/api/upload")
async def upload_file(file: UploadFile = File(...), prompt: str = Form(""), user_id: int = Form(1), model: str = Form("openai/gpt-oss-120b")):
    try:
        content = await file.read()
        try:
            text_content = content.decode("utf-8", errors="ignore")[:6000]
        except Exception:
            text_content = "[Binary content]"
        combined_prompt = f"File: {file.filename}\n\nContent:\n{text_content}\n\nRequest: {prompt or 'Analyze this file and summarize.'}"
        response_text = doja_engine.chat_with_doja(combined_prompt, user_id, [], model)
        return {"status": "success", "response": response_text}
    except Exception as e:
        return JSONResponse(status_code=500, content={"status": "error", "message": str(e)})

# ----------------- WORKSPACE ZIP & CODE INSPECTOR -----------------
@app.get("/api/download-zip")
def download_workspace_zip():
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        for root, _, files in os.walk("workspace"):
            for file in files:
                filepath = os.path.join(root, file)
                arcname = os.path.relpath(filepath, "workspace")
                zip_file.write(filepath, arcname)
    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=doja_ai_project.zip"}
    )

@app.get("/api/get-code")
def get_workspace_code():
    files_data = {}
    for root, _, files in os.walk("workspace"):
        for file in files:
            filepath = os.path.join(root, file)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    files_data[file] = f.read()
            except Exception:
                pass
    return {"files": files_data}

# ----------------- USER PROJECTS & CUSTOM INSTRUCTIONS -----------------
@app.get("/api/projects/{user_id}")
def user_projects(user_id: int):
    projects = database.get_user_projects(user_id)
    return {"projects": projects}

@app.delete("/api/projects/{project_id}")
def delete_user_project(project_id: int, user_id: int):
    database.delete_project(project_id, user_id)
    return {"success": True}

@app.post("/api/settings")
def update_settings(req: SettingsRequest):
    database.save_user_instructions(req.user_id, req.custom_instructions.strip())
    return {"success": True}

@app.get("/api/settings/{user_id}")
def get_settings(user_id: int):
    inst = database.get_user_instructions(user_id)
    return {"custom_instructions": inst}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)