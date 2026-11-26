import io
import os
import zipfile
from pathlib import Path
from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
import database
import doja_engine

app = FastAPI(title="DOJA AI Studio")
os.makedirs("workspace", exist_ok=True)
app.mount("/workspace", StaticFiles(directory="workspace", html=True), name="workspace")
APPWRITE_RECOVERY_URL = os.getenv("APPWRITE_RECOVERY_URL", "").strip()


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


class ChangePasswordRequest(BaseModel):
    user_id: str = ""
    old_password: str
    new_password: str = Field(min_length=8, max_length=256)


class ChatRequest(BaseModel):
    prompt: str
    user_id: str = ""
    history: list = Field(default_factory=list)
    model: str = "openai/gpt-oss-120b"


class SettingsRequest(BaseModel):
    user_id: str = ""
    custom_instructions: str = ""


def set_session(response: JSONResponse, secret: str, request: Request):
    response.set_cookie("doja_session", secret, httponly=True, secure=request.url.scheme == "https", samesite="lax", max_age=2592000, path="/")


def clear_session(response: JSONResponse):
    response.delete_cookie("doja_session", path="/")


def current_user(request: Request):
    user = database.get_account_from_session(request.cookies.get("doja_session", ""))
    if not user:
        raise HTTPException(status_code=401, detail="Please sign in again.")
    return user


def owned_user(request: Request, requested_id=""):
    user = current_user(request)
    if requested_id and str(requested_id) != user["$id"]:
        raise HTTPException(status_code=403, detail="You do not own this resource.")
    return user


@app.get("/", response_class=HTMLResponse)
def home():
    path = Path("index.html")
    if not path.is_file():
        return "<h1>DOJA AI: index.html was not found</h1>"
    html = path.read_text(encoding="utf-8")
    bridge = r"""
<script id="doja-appwrite-bridge">
(function () {
  localStorage.removeItem('doja_vault');

  window.logout = async function () {
    try { await fetch('/api/logout', { method:'POST', credentials:'same-origin' }); } catch (_) {}
    localStorage.removeItem('doja_user');
    localStorage.removeItem('doja_vault');
    currentUser = null;
    location.reload();
  };

  window.submitChangePassword = async function () {
    if (!currentUser) return alert('Please sign in first.');
    const oldPassword = document.getElementById('oldPasswordInput').value;
    const newPassword = document.getElementById('newPasswordInput').value;
    const message = document.getElementById('passChangeMsg');
    try {
      const response = await fetch('/api/change-password', {
        method:'POST', credentials:'same-origin', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({user_id:currentUser.user_id,old_password:oldPassword,new_password:newPassword})
      });
      const data = await response.json();
      message.className = data.success ? 'text-xs text-emerald-400' : 'text-xs text-red-400';
      message.innerText = data.message || data.error || 'Password update failed.';
      message.classList.remove('hidden');
      if (data.success) setTimeout(closeSettingsModal, 1200);
    } catch (_) {
      message.className = 'text-xs text-red-400';
      message.innerText = 'Error updating password.';
      message.classList.remove('hidden');
    }
  };

  async function synchronizeSession() {
    try {
      const response = await fetch('/api/session', {credentials:'same-origin'});
      if (!response.ok) throw new Error('signed out');
      const data = await response.json();
      currentUser = {success:true,user_id:data.user_id,username:data.username,email:data.email};
      localStorage.setItem('doja_user', JSON.stringify(currentUser));
      initAuth();
    } catch (_) {
      localStorage.removeItem('doja_user');
      currentUser = null;
      initAuth();
    }
  }

  const params = new URLSearchParams(location.search);
  if (params.has('userId') && params.has('secret')) {
    setTimeout(async function () {
      const newPassword = prompt('Enter a new password of at least 8 characters:');
      if (!newPassword) return;
      const response = await fetch('/api/reset-password', {
        method:'POST', headers:{'Content-Type':'application/json'},
        body:JSON.stringify({user_id:params.get('userId'),secret:params.get('secret'),new_password:newPassword})
      });
      const data = await response.json();
      alert(data.message || data.error || 'Reset failed.');
      if (data.success) history.replaceState({}, '', '/');
    }, 300);
  }
  synchronizeSession();
})();
</script>
"""
    html = html.replace("</body>", bridge + "\n</body>", 1) if "</body>" in html else html + bridge
    return HTMLResponse(html)


@app.post("/api/signup")
def signup(req: SignupRequest, request: Request):
    result = database.create_user(req.username, req.email, req.password)
    if not result["success"]:
        return JSONResponse(status_code=400, content=result)
    login = database.authenticate_user(req.email, req.password)
    if not login["success"]:
        return JSONResponse(status_code=201, content=result)
    response = JSONResponse(content={k:v for k,v in login.items() if k != "session_secret"})
    set_session(response, login["session_secret"], request)
    return response


@app.post("/api/login")
def login(req: LoginRequest, request: Request):
    result = database.authenticate_user(req.username_or_email, req.password)
    if not result["success"]:
        return JSONResponse(status_code=401, content=result)
    response = JSONResponse(content={k:v for k,v in result.items() if k != "session_secret"})
    set_session(response, result["session_secret"], request)
    return response


@app.get("/api/session")
def session(request: Request):
    user = current_user(request)
    return {"success":True,"user_id":user["$id"],"username":user.get("name",""),"email":user.get("email","")}


@app.post("/api/logout")
def logout(request: Request):
    database.delete_session(request.cookies.get("doja_session", ""))
    response = JSONResponse({"success":True})
    clear_session(response)
    return response


@app.post("/api/change-password")
def change_password(req: ChangePasswordRequest, request: Request):
    owned_user(request, req.user_id)
    result = database.change_password(request.cookies.get("doja_session", ""), req.old_password, req.new_password)
    if not result["success"]:
        return JSONResponse(status_code=400, content=result)
    return result


@app.post("/api/forgot-password")
def forgot_password(req: ForgotPasswordRequest):
    if not APPWRITE_RECOVERY_URL:
        return JSONResponse(status_code=500, content={"success":False,"error":"Password recovery is not configured."})
    try:
        database.create_password_reset_token(req.email, APPWRITE_RECOVERY_URL)
    except RuntimeError:
        pass
    return {"success":True,"message":"If the account exists, Appwrite will send a recovery email."}


@app.post("/api/reset-password")
def reset_password(req: ResetPasswordRequest):
    result = database.reset_password_with_token(req.token, req.new_password, req.user_id, req.secret)
    if not result["success"]:
        return JSONResponse(status_code=400, content=result)
    return result


@app.post("/api/chat")
def chat(req: ChatRequest, request: Request):
    user = owned_user(request, req.user_id)
    try:
        return {"status":"success","response":doja_engine.chat_with_doja(req.prompt,user["$id"],req.history,req.model)}
    except Exception:
        return JSONResponse(status_code=500, content={"status":"error","message":"DOJA could not complete the request."})


@app.post("/api/upload")
async def upload_file(request: Request, file: UploadFile = File(...), prompt: str = Form(""), user_id: str = Form(""), model: str = Form("openai/gpt-oss-120b")):
    user = owned_user(request, user_id)
    content = await file.read(8388609)
    if len(content) > 8388608:
        raise HTTPException(status_code=413, detail="File exceeds the 8 MB analysis limit.")
    text = content.decode("utf-8", errors="ignore")[:6000] or "[Binary content]"
    combined = f"File: {Path(file.filename or 'upload').name}\n\nContent:\n{text}\n\nRequest: {prompt or 'Analyze this file and summarize.'}"
    try:
        return {"status":"success","response":doja_engine.chat_with_doja(combined,user["$id"],[],model)}
    except Exception:
        return JSONResponse(status_code=500, content={"status":"error","message":"DOJA could not analyze that file."})


@app.get("/api/download-zip")
def download_workspace_zip(request: Request):
    user = current_user(request)
    files = database.list_workspace_files(user["$id"])
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    buffer.seek(0)
    return StreamingResponse(buffer, media_type="application/zip", headers={"Content-Disposition":"attachment; filename=doja_ai_project.zip"})


@app.get("/api/get-code")
def get_workspace_code(request: Request):
    user = current_user(request)
    return {"files":database.list_workspace_files(user["$id"])}


@app.get("/api/projects/{user_id}")
def projects(user_id: str, request: Request):
    user = owned_user(request, user_id)
    return {"projects":database.get_user_projects(user["$id"])}


@app.get("/api/projects/{project_id}/load")
def load_project(project_id: str, user_id: str, request: Request):
    user = owned_user(request, user_id)
    messages = database.get_project(project_id, user["$id"])
    if messages is None:
        return JSONResponse(status_code=404, content={"success":False,"error":"Project not found."})
    return {"messages":messages}


@app.delete("/api/projects/{project_id}")
def delete_project(project_id: str, user_id: str, request: Request):
    user = owned_user(request, user_id)
    database.delete_project(project_id, user["$id"])
    return {"success":True}


@app.post("/api/settings")
def save_settings(req: SettingsRequest, request: Request):
    user = owned_user(request, req.user_id)
    database.save_user_instructions(user["$id"], req.custom_instructions.strip())
    return {"success":True}


@app.get("/api/settings/{user_id}")
def get_settings(user_id: str, request: Request):
    user = owned_user(request, user_id)
    return {"custom_instructions":database.get_user_instructions(user["$id"])}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT","8000")))
